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
    """Run git in *repo*; None if it fails. Never raises."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, check=False,
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


def repo_identity(repo: Path) -> str:
    """What repository a checkout belongs to, shared by all its worktrees.

    ``git rev-parse --git-common-dir`` resolves to the same absolute path for a
    repo and every worktree of it — exactly how ``.claude/hooks/r5-lock.sh``
    keys the supervisor mutex per repo. Falls back to the directory path, so an
    unreadable repo is treated as distinct rather than silently merged with
    another.
    """
    out = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return out.strip() if out and out.strip() else str(repo.resolve())


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
    for repo in repos:
        pj = repo / "pyproject.toml"
        if not pj.is_file():
            continue
        try:
            name = tomllib.loads(pj.read_text()).get("project", {}).get("name")
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if not name:
            continue
        # Keyed by repository identity, so a repo and its worktrees collapse to
        # one entry while genuinely separate checkouts stay separate.
        seen.setdefault(canonical(name), {})[repo_identity(repo)] = repo.name

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
