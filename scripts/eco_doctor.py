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

# Operators that bound a range from above. "~=" is here on measurement, not
# reasoning: a compatible-release specifier bounds above in its own right and is
# never decomposed into ">=" plus "<".
BOUNDING_OPERATORS = ("<", "<=", "==", "===", "~=")

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
    """Ordering key for a version's release segment.

    Stdlib only — ``packaging`` is not guaranteed present, and a tool that
    reports dependency problems should not need a dependency to do it. Epoch is
    stripped rather than honoured: no sibling has ever used one, and silently
    mis-ordering is worse than ignoring a case that does not occur.
    """
    v = version.split("+", 1)[0].split("!", 1)[-1]
    core = re.match(r"\d+(?:\.\d+)*", v)
    return tuple(int(p) for p in core.group(0).split(".")) if core else ()


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


def sibling_versions(repos: list[Path]) -> dict[str, str]:
    """Canonical name -> version, from each repo's WORKING TREE pyproject."""
    found: dict[str, str] = {}
    for repo in repos:
        pj = repo / "pyproject.toml"
        if not pj.is_file():
            continue
        try:
            data = tomllib.loads(pj.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            continue
        project = data.get("project", {})
        name, version = project.get("name"), project.get("version")
        if name and version:
            found[canonical(name)] = version
    return found


def locked_versions(lock_text: str) -> dict[str, str]:
    return {
        canonical(m.group(1)): m.group(2)
        for m in _LOCK_PACKAGE.finditer(lock_text)
    }


def parse_clauses(spec: str) -> tuple[list[str], list[str], bool, bool]:
    """(floors, ceilings, bounded_above, had_any_clause) from a specifier string."""
    floors: list[str] = []
    ceilings: list[str] = []
    bounded_above = False
    clauses = [c.strip() for c in spec.split(",") if c.strip()]
    for clause in clauses:
        m = _SPECIFIER.match(clause)
        if not m:
            continue
        op, value = m.group(1), m.group(2).strip()
        if op == ">=":
            floors.append(value)
        elif op in ("<", "<="):
            ceilings.append(value)
            bounded_above = True
        elif op in BOUNDING_OPERATORS:
            bounded_above = True
    return floors, ceilings, bounded_above, bool(clauses)


def check_repo(repo: Path, siblings: dict[str, str]) -> list[str]:
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

    for raw in data.get("project", {}).get("dependencies", []) or []:
        m = _REQUIREMENT.match(raw)
        if not m:
            continue
        dep = canonical(m.group(1))
        if dep not in siblings:
            continue  # third-party: not this tool's business
        spec = m.group(2).strip()
        sib = siblings[dep]
        lock_v = locked.get(dep)
        floors, ceilings, bounded_above, had_clauses = parse_clauses(spec)

        if lock_v and lock_v != sib:
            findings.append(
                f"STALE            {name:28} lock has {dep} {lock_v}, checkout is {sib}"
            )
        if lock_v and floors:
            lo = min(floors, key=release_tuple)
            if release_tuple(lock_v) < release_tuple(lo):
                findings.append(
                    f"LOCK<FLOOR       {name:28} lock has {dep} {lock_v}, below declared >={lo}"
                )
        if ceilings:
            hi = max(ceilings, key=release_tuple)
            if release_tuple(sib) >= release_tuple(hi):
                findings.append(
                    f"SIBLING>CEILING  {name:28} checkout {dep} {sib} excluded by declared <{hi}"
                )
        if had_clauses and not bounded_above:
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

    siblings = sibling_versions(repos)

    findings: list[str] = []
    for repo in repos:
        findings.extend(check_repo(repo, siblings))
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
