"""Detect stale sibling checkouts and dependency-range drift across the workspace.

Invoked through ``scripts/eco-doctor.sh``, which selects an interpreter. Run that
rather than this file directly — stock macOS python3 is 3.9 and has no
``tomllib``.

WHY THIS EXISTS [opensrm-8hn3]

Every member repo points its sibling dependencies at local checkouts via
``tool.uv.sources``. A path source REPLACES registry resolution rather than being
filtered by the version specifier, so ``uv sync`` and ``uv pip install .`` install
whatever the sibling happens to be — regardless of what ``project.dependencies``
declares — and neither warns. Only ``uv pip install --no-sources`` evaluates the
published range.

Measured consequence: five members shipped or nearly shipped a declared
nthlayer-common range no test had exercised (opensrm-p3bm, opensrm-z7gn), and
every one also carried a committed ``uv.lock`` recording a stale sibling version.
``pip install nthlayer-workers nthlayer-override-adapter`` silently resolved
workers back to a release whose measure adapter yielded zero SLOs for every v2
manifest. Nothing compared the declared range, the committed lock, and the
sibling actually on disk.

WHICH SOURCE EACH FACT COMES FROM, AND WHY IT DIFFERS

    sibling version      working tree   what ``uv sync`` would install right now
    declared range       git HEAD       what CI resolves and PyPI publishes
    locked version       git HEAD       what CI resolves

That asymmetry is the whole point: the tool compares "what I would build
against" with "what I have committed to declaring". Reading the lock from the
working tree instead of HEAD is the specific mistake three hand-rolled versions
of this scan made — an uncommitted relock sat in the tree and every repo looked
clean, while CI resolved the stale committed one.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

# Exit codes. Kept distinct so a broken invocation cannot read as a successful
# detection: the test asserts on EXIT_FINDINGS specifically, never on "non-zero".
EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

_SPECIFIER = re.compile(r"(===|==|>=|<=|~=|!=|>|<)\s*(.+)$")
_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(.*)$")
_LOCK_PACKAGE = re.compile(
    r'^\[\[package\]\]\s*\nname\s*=\s*"([^"]+)"\s*\nversion\s*=\s*"([^"]+)"',
    re.MULTILINE,
)


def canonical(name: str) -> str:
    """PEP 503 normalisation. `nthlayer_common` and `nthlayer-common` are one package."""
    return re.sub(r"[-_.]+", "-", name).lower()


def release_tuple(version: str) -> tuple[int, ...]:
    """Ordering key for a version's release segment, zero-padded to 4 parts.

    Padding matters: without it `2.1` sorts below `2.1.0` because a shorter
    tuple compares less, so a floor of `>=2.1` would falsely flag a `2.1.0`
    checkout. A pre-release sorts just below its own release via the marker
    below, so `2.1.0rc1` does not satisfy `>=2.1.0`.

    Stdlib only — ``packaging`` is not guaranteed present, and a tool that
    reports dependency problems should not need a dependency to do it. Epoch is
    stripped rather than honoured: no sibling has ever used one, and it is
    recorded here as a known gap rather than silently mis-ordered.
    """
    v = version.split("+", 1)[0].split("!", 1)[-1].strip()
    core = re.match(r"\d+(?:\.\d+)*", v)
    if not core:
        return ()
    parts = [int(p) for p in core.group(0).split(".")]
    parts += [0] * (4 - len(parts))
    # Pre-release marker: 0 for a/b/rc, 1 for a final release, so
    # (2,1,0,0,0) < (2,1,0,0,1).
    rest = v[core.end():]
    is_pre = bool(re.match(r"(a|b|c|rc|alpha|beta|pre|preview|dev)", rest))
    return (*parts, 0 if is_pre else 1)


def _bump(version: str, index: int) -> str:
    """Version with component *index* incremented and the rest truncated.

    Turns a compatible-release or wildcard clause into the exclusive ceiling it
    actually implies: `~=2.1` -> `3.0`, `~=2.1.2` -> `2.2`, `==2.*` -> `3`.
    """
    parts = [int(p) for p in re.findall(r"\d+", version)]
    parts += [0] * (index + 1 - len(parts))
    parts = parts[: index + 1]
    parts[index] += 1
    return ".".join(str(p) for p in parts)


class Bounds:
    """Effective floor and ceiling implied by a whole specifier set.

    Effective floor is the MAX of the declared floors and the effective ceiling
    the MIN of the declared ceilings — the intersection, not the extremes. An
    earlier revision had these reversed, which let `>=1.0,>=2.1.2` be checked
    against 1.0.
    """

    def __init__(self) -> None:
        self.floor: str | None = None
        self.floor_inclusive = True
        self.ceiling: str | None = None
        self.ceiling_inclusive = False
        self.had_clauses = False

    def add_floor(self, value: str, inclusive: bool) -> None:
        if self.floor is None or release_tuple(value) > release_tuple(self.floor):
            self.floor, self.floor_inclusive = value, inclusive

    def add_ceiling(self, value: str, inclusive: bool) -> None:
        if self.ceiling is None or release_tuple(value) < release_tuple(self.ceiling):
            self.ceiling, self.ceiling_inclusive = value, inclusive

    def below_floor(self, version: str) -> bool:
        if self.floor is None:
            return False
        v, f = release_tuple(version), release_tuple(self.floor)
        return v < f if self.floor_inclusive else v <= f

    def above_ceiling(self, version: str) -> bool:
        if self.ceiling is None:
            return False
        v, c = release_tuple(version), release_tuple(self.ceiling)
        # `<=2.1.2` admits 2.1.2; `<2.1.2` does not. Treating the two alike
        # produced a false SIBLING>CEILING on an inclusive ceiling.
        return v > c if self.ceiling_inclusive else v >= c


def parse_bounds(spec: str) -> Bounds:
    """Effective bounds from a PEP 440 specifier set.

    Every operator that constrains from above is converted to an actual ceiling
    VALUE, not merely a "bounded" flag. An earlier revision recorded `==` and
    `~=` as bounded-above without a value, so SIBLING>CEILING could never fire
    for them — a silent pass on the headline check.
    """
    bounds = Bounds()
    clauses = [c.strip() for c in spec.split(",") if c.strip()]
    bounds.had_clauses = bool(clauses)
    for clause in clauses:
        m = _SPECIFIER.match(clause)
        if not m:
            continue
        op, value = m.group(1), m.group(2).strip()
        if op == ">=":
            bounds.add_floor(value, inclusive=True)
        elif op == ">":
            bounds.add_floor(value, inclusive=False)
        elif op == "<":
            bounds.add_ceiling(value, inclusive=False)
        elif op == "<=":
            bounds.add_ceiling(value, inclusive=True)
        elif op == "~=":
            # ~=X.Y admits X.* ; ~=X.Y.Z admits X.Y.* — drop the last
            # component and bump the one before it.
            digits = re.findall(r"\d+", value)
            bounds.add_floor(value, inclusive=True)
            if len(digits) >= 2:
                bounds.add_ceiling(_bump(value, len(digits) - 2), inclusive=False)
        elif op in ("==", "==="):
            if value.endswith(".*"):
                stem = value[:-2]
                digits = re.findall(r"\d+", stem)
                bounds.add_floor(stem, inclusive=True)
                if digits:
                    bounds.add_ceiling(_bump(stem, len(digits) - 1), inclusive=False)
            else:
                bounds.add_floor(value, inclusive=True)
                bounds.add_ceiling(value, inclusive=True)
        # "!=" constrains neither bound.
    return bounds


def git(repo: Path, *args: str) -> str | None:
    """Run git in *repo*; None if it fails. Never raises.

    ``GIT_DIR``, ``GIT_COMMON_DIR`` and ``GIT_WORK_TREE`` are scrubbed from the
    environment. They OVERRIDE ``-C``, so an ambient one — exported by a hook, a
    wrapper script, or a shell the operator happened to run this from — makes
    every repo answer for the same repository: identical ``pyproject.toml`` and
    ``uv.lock`` content read for all of them, and one identity shared by all.
    Both failure modes are the silent kind, which is the class of bug this tool
    exists to catch. It always addresses repos explicitly by path and never
    wants an ambient one.

    ``errors="replace"``, because ``text=True`` decodes as UTF-8 and a committed
    file that is not valid UTF-8 — a latin-1 byte in an author comment, a
    UTF-16 BOM from Windows — otherwise raises ``UnicodeDecodeError`` from
    inside ``subprocess.run``. That is a ``ValueError``, so ``except OSError``
    did not catch it and the whole scan died with a traceback. Replacing the
    undecodable bytes keeps the text readable enough for tomllib, which either
    parses it or raises ``TOMLDecodeError`` and gets reported as PARSE-ERROR —
    a VISIBLE finding either way, rather than a crash.

    The trade is accepted knowingly: two names differing ONLY in undecodable
    bytes both become the same U+FFFD string and are reported as one duplicate,
    a false positive. It is the right way round — the replacement character is
    visible in the output, mojibake cannot collide with a valid ASCII package
    name, and the alternative is a traceback that reads as a clean scan.
    """
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE")
    }
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, check=False, env=env,
            errors="replace",
        )
    except OSError:
        return None
    return out.stdout if out.returncode == 0 else None


def discover_repos(workspace: Path) -> list[Path]:
    """Immediate subdirectories that are git repos.

    Discovered rather than hard-listed: a hand-kept roster is one more thing to
    forget, and workspace membership does change — five standalone repos were
    consolidated into nthlayer-workers under RM.7.
    """
    return sorted(p for p in workspace.iterdir() if (p / ".git").exists())


def path_sources(head_pyproject: dict) -> dict[str, str]:
    """Canonical dep name -> relative path, from ``[tool.uv.sources]``.

    THE AUTHORITATIVE ANSWER to "which directory is this sibling". An earlier
    revision built one flat name->version map across every discovered
    directory, which a git worktree silently defeats: CLAUDE.md mandates
    worktrees named ``<repo>-<slug>``, those sort AFTER ``<repo>``, and the
    worktree's pyproject therefore overwrote the real checkout's version.
    Measured on the broken version — a real nthlayer-common at 3.5.0
    (violating <3.0.0, and disagreeing with the lock) alongside a
    nthlayer-common-wip worktree at 2.1.2 reported "no drift found", exit 0.
    Both genuine findings vanished, and this workspace almost always has a
    worktree on disk.
    """
    sources = head_pyproject.get("tool", {}).get("uv", {}).get("sources", {}) or {}
    resolved: dict[str, str] = {}
    for name, spec in sources.items():
        if isinstance(spec, dict) and "path" in spec:
            resolved[canonical(name)] = str(spec["path"])
    return resolved


def version_at(path: Path) -> str | None:
    """Version from a checkout's WORKING TREE pyproject, or None."""
    pj = path / "pyproject.toml"
    if not pj.is_file():
        return None
    try:
        data = tomllib.loads(pj.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return data.get("project", {}).get("version")


def recorded_common_dir(repo: Path) -> str | None:
    """A linked worktree's parent git dir, read from its own ``.git`` file.

    Last resort for when git cannot answer at all. A worktree's ``.git`` is a
    file reading ``gitdir: <parent>/.git/worktrees/<name>``, written by git at
    creation; everything before ``/worktrees/`` is the parent's common dir —
    the same string a healthy worktree's ``--git-common-dir`` returns.

    The case this exists for: the parent repo is MOVED or DELETED while two of
    its worktrees remain in the workspace. git can then resolve neither, both
    fall to the path fallback, and they are reported as a DUPLICATE-NAME —
    which is (a) the one finding the opensrm-px23 pre-flight treats as
    BLOCKING, so it refuses every gate in the workspace exactly as the bug this
    bead fixes did, and (b) simply untrue: it says two DISTINCT repositories
    claim one name, when they are one repository checked out twice. A finding
    that misdescribes what it found trains people to ignore the tool, which is
    the reason check_repo() stays silent about a missing pyproject rather than
    reporting it.

    RESOLVED AGAINST *repo*, not used as a raw string. git >= 2.48 can write a
    RELATIVE gitdir (``worktree.useRelativePaths``, ``--relative-paths``), so
    the recorded form is not reliably absolute — and two worktrees of ONE parent
    then disagree if one was created before that setting and one after, which
    splits them and fires the blocking false positive this function exists to
    remove. Resolving makes both forms comparable, and keeps the key in the same
    shape as the resolved candidate repo_identity() produces on the happy path.
    The result is never dereferenced, so it does not matter that the path may no
    longer exist.

    This cannot merge distinct repositories: the resolved path names one
    specific parent git dir, so two worktrees made from different parents yield
    different keys.

    Returns None for a main checkout (``.git`` is a directory), for a ``.git``
    file that records no ``gitdir:``, and for one that is unreadable.
    """
    gitfile = repo / ".git"
    try:
        if not gitfile.is_file():
            return None
        text = gitfile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("gitdir:"):
            recorded = line.split(":", 1)[1].strip()
            # rsplit: git appends exactly one "/worktrees/<name>", so the LAST
            # occurrence is the separator even if the parent's own path
            # contains that string.
            if "/worktrees/" in recorded:
                common = recorded.rsplit("/worktrees/", 1)[0]
                # `repo / common` yields common unchanged when it is already
                # absolute, so this handles both forms.
                return str((repo / common).resolve())
            return None
    return None


def unidentified(repo: Path) -> str:
    """Identity for a checkout git could not describe: recorded, else its path.

    The path fallback is a deliberate SPLIT — a wrong MERGE silences a real
    ambiguity, a wrong SPLIT reports one that is easy to dismiss — but a
    worktree whose parent has vanished is not ambiguous at all, and
    recorded_common_dir() recovers what git itself wrote down.
    """
    return recorded_common_dir(repo) or str(repo.resolve())


def is_main_checkout(repo: Path) -> bool:
    """True if *repo* is a repository's own checkout rather than a linked worktree.

    ``.git`` is a DIRECTORY in a main checkout and a FILE in a linked worktree.

    Used only to order reporting, never to decide whether a finding fires, which
    is what makes the one case it gets wrong harmless: a checkout made with
    ``--separate-git-dir`` also has a ``.git`` file and so reads as a worktree
    here. repo_identity() still resolves it to its own separate git dir and it
    still shares one identity with its worktrees, so the most that can change is
    WHICH of two directory names for the same repository gets printed.
    """
    return (repo / ".git").is_dir()


def repo_identity(repo: Path) -> str:
    """What repository a checkout belongs to, shared by all its worktrees.

    THE RULE, in the order the code applies it:

      1. ``--show-toplevel`` must resolve to *repo* itself, or give up.
      2. ``--git-common-dir`` must be a single line.
      3. Resolved against *repo*, it must be a git directory (a ``HEAD``).
      4. Otherwise fall back to *repo*'s own path — a deliberate SPLIT.

    ``git rev-parse --git-common-dir`` resolves to the same location for a repo
    and every worktree of it — the same key ``.claude/hooks/r5-lock.sh`` uses to
    make the supervisor mutex per repo rather than per directory. A bare
    ``--git-common-dir`` returns ``.git`` for a main checkout and an absolute
    path for a worktree, so resolving it against *repo* converges both without
    depending on any git version.

    Step 4 splits rather than merges because the two errors are not symmetrical:
    a wrong MERGE silences a real ambiguity, a wrong SPLIT reports one that is
    easy to dismiss. Every guard below therefore falls back, never guesses.

    Steps 1-3 each exist because of a specific way git can hand back something
    plausible and wrong. In order:

    STEP 1 — git ASCENDS. A directory whose ``.git`` is an empty DIRECTORY (an
    interrupted clone, a half-finished manual copy) is not a repository, so
    ``rev-parse`` answers for the nearest ANCESTOR REPO and exits 0. Verified:
    it prints ``../../.git``. That path has a ``HEAD``, so step 3 would accept
    it, and every such member would collapse onto the ancestor's identity — a
    genuine DUPLICATE-NAME silenced. Unlike the step-3 hazard this needs no old
    git; it is reachable on any version. (An invalid ``.git`` FILE fails cleanly
    with rc=128, so that path was already safe.) A ``--show-toplevel`` that is
    not *repo* means git is describing some other checkout, whatever the reason.

    STEP 2 — NO ``--path-format=absolute``, deliberately. That flag needs git
    >= 2.31 (Ubuntu 20.04 ships 2.25, Debian bullseye 2.30) and ``git rev-parse``
    ECHOES an unrecognised flag and exits 0 rather than failing:

        $ git rev-parse --bogus-flag=x --git-common-dir
        --bogus-flag=x
        .git
        $ echo $?
        0

    So on older git the identity became the constant string
    ``"--path-format=absolute\n.git"`` for every main checkout, merging all
    distinct repositories into one and silencing genuine duplicates — the
    false-negative direction. And it did not even buy the worktree fix, because
    a worktree reports its parent's absolute path regardless.

    This check is now SUBSUMED by step 3: with the flag reinstated the first
    line is ``--path-format=absolute``, which has no ``HEAD`` beneath it either.
    Mutating ``len(lines) == 1`` therefore survives the suite by design, and it
    is kept as defence in depth rather than removed — a git that printed an
    unexpected second line should not have its first one trusted on the strength
    of one guard alone.

    STEP 3 — ``(candidate / "HEAD").exists()``, not ``candidate.exists()``.
    Before 2.31, ``--git-common-dir`` inside a linked worktree could print the
    raw contents of ``.git/worktrees/<name>/commondir``, which is the relative
    string ``../..``. Resolved against *repo* that is the workspace's PARENT
    directory — which exists, so a mere existence check accepts it. Two
    worktrees of two DIFFERENT repos then resolve to the same shared parent
    directory and are silently MERGED, so a genuine duplicate goes unreported.
    Requiring a ``HEAD`` beneath the candidate rejects any path that is not a
    git directory, whatever produced it.

    ``.resolve()`` follows symlinks, so two directories whose ``.git`` symlinks
    to one git dir merge into a single identity. That is INTENDED, not a gap:
    two checkouts sharing one git directory are one repository by exactly the
    rule this function implements. It is only reachable by hand-made symlink,
    and reporting it would require deciding that "same repository" means
    something other than "same common dir".
    """
    top = (git(repo, "rev-parse", "--show-toplevel") or "").strip()
    if not top or Path(top).resolve() != repo.resolve():
        return unidentified(repo)

    out = git(repo, "rev-parse", "--git-common-dir")
    if out:
        lines = [line for line in out.splitlines() if line.strip()]
        if len(lines) == 1:
            candidate = (repo / lines[0]).resolve()
            if (candidate / "HEAD").exists():
                return str(candidate)
    # Unreadable, or output we do not recognise: fall back to what the worktree
    # itself records, else treat this checkout as DISTINCT. A wrong merge
    # silences a real ambiguity; a wrong split reports one that is easy to
    # dismiss — except when the split is itself the blocking false positive
    # this bead exists to remove, which is what unidentified() handles.
    return unidentified(repo)


def duplicate_name_findings(repos: list[Path]) -> list[str]:
    """Report DISTINCT repositories that declare the same package name.

    A safety net beneath path_sources(): if two unrelated checkouts claim one
    name, any name-based reasoning is ambiguous and saying so beats picking one.

    Worktrees are excluded, and that exclusion is the point [opensrm-bnal]. A
    worktree always declares its parent's ``project.name``, and CLAUDE.md
    MANDATES sibling worktrees for parallel work — so reporting them made this
    finding fire on every correct workflow. The /r5-supervise pre-flight
    (opensrm-px23) classifies DUPLICATE-NAME as blocking, so it then refused
    every R5 gate in the workspace. Caught on that pre-flight's first real use.

    The net was written beneath NAME-BASED sibling resolution, and the same
    change that added it replaced that with ``[tool.uv.sources]`` path
    resolution — so it had been sitting beneath a mechanism that no longer used
    names at all.
    """
    seen: dict[str, dict[str, str]] = {}
    # MAIN CHECKOUTS FIRST, so first-wins below does not depend on how the
    # directories happen to sort. discover_repos() sorts lexicographically, and a
    # worktree named to sort before its parent — nothing stops one, only
    # eco-worktree.sh's `<repo>-<slug>` convention — would otherwise be named in
    # place of the checkout actually in conflict, reintroducing the defect the
    # setdefault below was written to fix. Stable sort, so lexicographic order
    # still holds within each class.
    for repo in sorted(repos, key=lambda p: not is_main_checkout(p)):
        pj = repo / "pyproject.toml"
        if not pj.is_file():
            continue
        try:
            # errors="replace" and UnicodeDecodeError both, for the reason
            # git() gives: text=True / read_text() decode as UTF-8, and an
            # undecodable byte raises a ValueError that neither OSError nor
            # TOMLDecodeError catches. Unguarded, one latin-1 byte in one
            # pyproject killed the ENTIRE scan with a traceback — and since the
            # /r5-supervise pre-flight classifies findings by line PREFIX, a
            # traceback emits no prefix at all, so the gate read zero blocking
            # findings and proceeded having scanned nothing. A clean record from
            # a check that never ran is the failure this tool exists to prevent.
            text = pj.read_text(encoding="utf-8", errors="replace")
            name = tomllib.loads(text).get("project", {}).get("name")
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
        # strip(): a whitespace-only name is not a name. `if not name` admitted
        # "   ", which then rendered a finding with an empty gap where the
        # package should be — unreadable, and indistinguishable from a
        # formatting bug in the tool.
        if not name or not name.strip():
            continue
        # REBIND, do not merely test. canonical() collapses [-_.]+ and
        # lowercases; it does NOT trim. Keying the untrimmed string meant
        # "dup" and " dup " canonicalised to different keys, so a genuine
        # duplicate was silenced — the false-negative direction. The stripped
        # value is also what gets printed, so the column has no leading gap.
        name = name.strip()
        # Keyed by repository identity, so a repo and its worktrees collapse to
        # one entry while genuinely separate checkouts stay separate.
        # setdefault, not assignment: last-wins named whichever directory came
        # last, so a worktree — which declares nothing independently — could be
        # reported in place of the checkout actually in conflict.
        seen.setdefault(canonical(name), {}).setdefault(
            repo_identity(repo), repo.name
        )

    out = []
    for name, by_identity in sorted(seen.items()):
        if len(by_identity) > 1:
            dirs = ", ".join(sorted(by_identity.values()))
            out.append(
                f"DUPLICATE-NAME   {'(workspace)':28} {name} declared by {dirs}"
            )
    return out


def locked_versions(lock_text: str) -> dict[str, str]:
    return {
        canonical(m.group(1)): m.group(2)
        for m in _LOCK_PACKAGE.finditer(lock_text)
    }


def check_repo(repo: Path) -> list[str]:
    """Findings for one repo, one line each."""
    name = repo.name
    findings: list[str] = []

    head_pj = git(repo, "show", "HEAD:pyproject.toml")
    if not head_pj:
        # No committed pyproject — opensrm is spec-only. Silence, not a finding:
        # reporting it would train people to ignore this tool's output.
        return findings
    try:
        data = tomllib.loads(head_pj)
    except tomllib.TOMLDecodeError as exc:
        return [f"PARSE-ERROR      {name:28} HEAD:pyproject.toml unreadable: {exc}"]

    locked = locked_versions(git(repo, "show", "HEAD:uv.lock") or "")
    sources = path_sources(data)

    for raw in data.get("project", {}).get("dependencies", []) or []:
        m = _REQUIREMENT.match(raw)
        if not m:
            continue
        dep = canonical(m.group(1))
        if dep not in sources:
            continue  # not a path-sourced sibling: not this tool's business
        spec = m.group(2).strip()

        sibling_dir = (repo / sources[dep]).resolve()
        sib = version_at(sibling_dir)
        if sib is None:
            findings.append(
                f"SIBLING-MISSING  {name:28} {dep} path source {sources[dep]} has no readable pyproject"
            )
            continue

        lock_v = locked.get(dep)
        bounds = parse_bounds(spec)

        if lock_v and lock_v != sib:
            findings.append(
                f"STALE            {name:28} lock has {dep} {lock_v}, checkout is {sib}"
            )
        if lock_v and bounds.below_floor(lock_v):
            findings.append(
                f"LOCK<FLOOR       {name:28} lock has {dep} {lock_v}, below declared floor {bounds.floor}"
            )
        if bounds.above_ceiling(sib):
            findings.append(
                f"SIBLING>CEILING  {name:28} checkout {dep} {sib} excluded by declared ceiling {bounds.ceiling}"
            )
        if bounds.had_clauses and bounds.ceiling is None:
            findings.append(
                f"NO-CEILING       {name:28} declares {dep}{spec} with no upper bound"
            )
    return findings


def check_currency(repo: Path) -> list[str]:
    """Behind/ahead against the branch's own upstream. Requires --fetch."""
    name = repo.name
    upstream = (git(repo, "rev-parse", "--abbrev-ref", "@{upstream}") or "").strip()
    if not upstream:
        return [f"NO-UPSTREAM      {name:28} branch has no tracking remote; currency unknown"]
    # Resolved from the branch, never a hard-coded "origin": the front door
    # tracks nthlayer-remote/main, so assuming origin would report nothing for
    # it and look like a clean result.
    remote = upstream.split("/", 1)[0]
    if git(repo, "fetch", "-q", remote) is None:
        # A network blip must not read as "up to date".
        return [f"FETCH-FAILED     {name:28} could not fetch {remote}; currency unverified"]
    behind = (git(repo, "rev-list", "--count", f"HEAD..{upstream}") or "0").strip()
    if behind.isdigit() and int(behind) > 0:
        return [f"BEHIND           {name:28} {behind} commit(s) behind {upstream}"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eco-doctor",
        description="Detect stale sibling checkouts and dependency-range drift.",
    )
    parser.add_argument(
        "--fetch", action="store_true",
        help="also report behind/ahead vs each tracking remote (needs network)",
    )
    parser.add_argument("repos", nargs="*", help="limit to these member dirs")
    args = parser.parse_args(argv)

    workspace = Path.cwd()

    if args.repos:
        repos = []
        for r in args.repos:
            path = workspace / r
            if not (path / ".git").exists():
                print(f"eco-doctor: not a git repo: {r}", file=sys.stderr)
                return EXIT_ERROR
            repos.append(path)
    else:
        repos = discover_repos(workspace)

    if not repos:
        print(f"eco-doctor: no git repos found in {workspace}", file=sys.stderr)
        print("eco-doctor: run this from the workspace root holding the members",
              file=sys.stderr)
        return EXIT_ERROR

    findings: list[str] = duplicate_name_findings(repos)
    for repo in repos:
        findings.extend(check_repo(repo))
        if args.fetch:
            findings.extend(check_currency(repo))

    for line in findings:
        print(line)

    if findings:
        print()
        print(f"eco-doctor: {len(findings)} finding(s). A path source hides all of these")
        print("eco-doctor: from `uv sync` — only `uv pip install --no-sources` surfaces them.")
        return EXIT_FINDINGS

    print(f"eco-doctor: {len(repos)} repo(s) checked, no drift found")
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
