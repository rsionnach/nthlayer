#!/usr/bin/env python3
"""The PR merge check: a bead's PR merges only on its gate's verdict [opensrm-6kqs.6, R5-R49].

Bead 6 in section 3 of
docs/superpowers/specs/2026-11-03-r5-gate-v2-nthlayer-spec.md: "the PR merge
check" applies section 6's verdict check, which passes when ``verdict.state``
is CLEAN and the tree checked equals ``verdict.tree_sha``. Gate records are
private and local, so the check cannot run in a public repo's CI; it runs as a
Claude Code PreToolUse hook on the Bash tool, before ``gh pr merge`` does.

    r5_merge_check.py hook --root <ecosystem root>     PreToolUse payload on stdin
    r5_merge_check.py pr --root <root> -R <owner/repo> <number>

Exit 0: allowed (not a merge, an exempt PR, or a CLEAN verdict for the PR
head's tree). Exit 2: refused, the reason on stderr (the hook protocol shows
it to the session). Exit 1 (``pr`` only): usage. The hook never exits 1: a
merge it cannot judge is refused, since a guard that fails open is the
merge-before-gate it exists to stop. The owner can still merge by hand.

What it does, for each ``gh pr merge`` in the command (split with shlex, so a
quoted string that mentions one is not one; ``&&``, ``;``, ``|`` and newlines
separate commands). It guards against a merge made by mistake, not one made
on purpose: a merge quoted inside ``bash -c '...'``, or one that does not go
through ``gh pr merge`` (``gh api``, the web UI), is not seen.

1. The PR must be named, by number with ``-R``/``--repo <owner/repo>``, or by
   its URL. A bare ``gh pr merge`` resolves against whatever directory the
   shell happens to be in, which the hook cannot see: refused, naming the fix.
2. ``gh pr view`` gives the head commit, head branch, changed files and
   commit subjects. Exempt, and allowed without a record:
   - doc-only: every changed file ends ``.md``, ``.rst`` or ``.txt`` (doc-only
     PRs skip R5 and merge on green CI); a PR whose file list is truncated
     (``changedFiles`` above the files returned) is not doc-only;
   - a release-please PR (head branch ``release-please--``) or a dependabot
     PR (``dependabot/``): neither carries a bead, and neither is gated.
3. Otherwise the beads are the ``opensrm-<id>`` names in the commit subjects
   (bodies cite other beads freely). None: refused.
4. Each bead's archive is ``<root>/.claude/r5-state-<id>-completed.json`` or
   ``r5-state-<id>-<repo>-completed.json`` (r5-supervise's Final step 3a;
   ``<id>`` with or without its dots as hyphens). An archive counts only if
   its record's ``repo`` is the PR's repository name: a bead gated in
   another repo says nothing about this PR's tree. An epic task has no
   archive: epic-executor writes a bare ``verdict.json`` in each stage-2 run
   directory, ``<root>/.claude/r5-reports/<id>/epic-<ts>/``, and each counts
   (a bare verdict names no repo; its tree is what is checked).
5. The PR head's tree comes from GitHub (``gh api
   repos/<owner>/<repo>/commits/<sha>``, ``commit.tree.sha``), so no local
   checkout needs the commit.
6. Allowed when one of the bead's archives passes ``r5_record.check`` for
   that tree. Otherwise refused, naming each archive's reason.

Standard library only, Python 3.9 compatible, like the other gate scripts.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r5_record  # noqa: E402  (sibling script)

DOC_SUFFIXES = (".md", ".rst", ".txt")
EXEMPT_BRANCHES = ("release-please--", "dependabot/")
PUNCTUATION = frozenset(";&|")
BEAD = re.compile(r"\bopensrm-[0-9a-z]+(?:\.[0-9]+)*\b")
PR_URL = re.compile(r"^https://github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)/?$")


class Refused(Exception):
    """The merge is refused; the message says why."""


class GhError(RuntimeError):
    """gh failed or printed something unreadable."""


def gh(args: list) -> str:
    """Run gh; its stdout, or GhError. The one place this script calls out."""
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True, check=False,
                             timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GhError(f"gh {' '.join(args[:3])}: {exc}") from exc
    if out.returncode != 0:
        raise GhError(f"gh {' '.join(args[:3])}: exit {out.returncode}: "
                      f"{out.stderr.strip()[:200]}")
    return out.stdout


# ------------------------------------------------------------ command parse

def merges_in(command: str) -> list[list[str]]:
    """The argument lists of each ``gh pr merge`` in a shell command."""
    # A newline ends a command as ";" does (inside quotes it stays text).
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError as exc:  # an unbalanced quote
        if "gh" in command and "merge" in command:
            raise Refused(f"cannot parse the command ({exc}), and it may run "
                          "gh pr merge") from exc
        return []
    out, current = [], []
    for tok in tokens + [";"]:
        if tok and set(tok) <= PUNCTUATION:
            out.append(current)
            current = []
        else:
            current.append(tok)
    merges = []
    for words in out:
        for i in range(len(words) - 2):
            if Path(words[i]).name == "gh" and words[i + 1:i + 3] == ["pr", "merge"]:
                merges.append(words[i + 3:])
                break
    return merges


def target_of(args: list) -> tuple[str, str]:
    """(owner/repo, number) a ``gh pr merge`` names, or Refused."""
    repo, positional, i = None, [], 0
    while i < len(args):
        a = args[i]
        if a in ("-R", "--repo"):
            if i + 1 >= len(args):
                raise Refused(f"{a} has no value")
            repo, i = args[i + 1], i + 2
            continue
        if a.startswith("--repo="):
            repo = a.split("=", 1)[1]
        elif a.startswith("-R") and len(a) > 2:
            repo = a[2:]
        elif not a.startswith("-"):
            positional.append(a)
        elif a in ("-b", "--body", "-F", "--body-file", "-t", "--subject",
                   "-A", "--author-email", "--match-head-commit"):
            i += 1  # a flag that takes a value: skip it
        i += 1
    if len(positional) != 1:
        raise Refused("name exactly one PR: gh pr merge <number> -R <owner/repo>, or its URL "
                      f"(got {positional or 'none'})")
    pr = positional[0]
    m = PR_URL.match(pr)
    if m:
        if repo is not None and repo != m.group(1):
            raise Refused(f"-R {repo} disagrees with the URL's {m.group(1)}")
        return m.group(1), m.group(2)
    if not pr.isdigit():
        raise Refused(f"name the PR by number or URL, not {pr!r} (a branch resolves "
                      "against a directory the hook cannot see)")
    if repo is None or repo.count("/") != 1:
        raise Refused("pass -R <owner/repo>: a bare number resolves against the shell's "
                      "directory, which the hook cannot see")
    return repo, pr


# ------------------------------------------------------------------ the PR

def pr_facts(repo: str, number: str) -> dict:
    raw = gh(["pr", "view", number, "-R", repo, "--json",
              "headRefOid,headRefName,files,changedFiles,commits"])
    try:
        data = json.loads(raw)
        return {"head": data["headRefOid"], "branch": data["headRefName"],
                "files": [f["path"] for f in data["files"]],
                "changed": int(data["changedFiles"]),
                "subjects": [c["messageHeadline"] for c in data["commits"]]}
    except (ValueError, KeyError, TypeError) as exc:
        raise GhError(f"gh pr view {number}: unreadable output ({exc})") from exc


def exemption(facts: dict) -> str | None:
    """Why the PR needs no gate record, or None."""
    for prefix in EXEMPT_BRANCHES:
        if facts["branch"].startswith(prefix):
            return f"branch {facts['branch']} ({prefix.rstrip('-/')})"
    files = facts["files"]
    if files and facts["changed"] <= len(files) and \
            all(f.lower().endswith(DOC_SUFFIXES) for f in files):
        return f"doc-only ({len(files)} file{'s' if len(files) != 1 else ''})"
    return None


def beads_in(subjects: list) -> list[str]:
    """Bead names in commit subjects, first seen first. GitHub's
    ``messageHeadline`` cuts a long subject with "…": its last word is then
    a fragment ("[opensrm-6kq…"), never a bead, so it is dropped."""
    seen: list[str] = []
    for s in subjects:
        if s.endswith("\u2026"):
            s = s.rsplit(None, 1)[0] if len(s.split()) > 1 else ""
        for b in BEAD.findall(s):
            if b not in seen:
                seen.append(b)
    return seen


def archives_for(root: Path, bead: str, repo_name: str) -> list[Path]:
    """The archives r5-supervise's Final step 3a may have written for a bead,
    then the verdict.json of each epic-executor run of it, oldest first."""
    ident = bead[len("opensrm-"):]
    stems = dict.fromkeys([ident, ident.replace(".", "-")])
    out = []
    for stem in stems:
        for name in (f"r5-state-{stem}-completed.json",
                     f"r5-state-{stem}-{repo_name}-completed.json"):
            p = root / ".claude" / name
            if p.is_file() and p not in out:
                out.append(p)
    out += sorted((root / ".claude" / "r5-reports" / bead).glob("epic-*/verdict.json"))
    return out


def head_tree(repo: str, sha: str) -> str:
    tree = gh(["api", f"repos/{repo}/commits/{sha}", "--jq", ".commit.tree.sha"]).strip()
    if not r5_record._full_sha(tree):
        raise GhError(f"commit {sha} has no readable tree ({tree[:60]!r})")
    return tree


def judge(root: Path, repo: str, number: str) -> str:
    """Why the merge may go ahead, or Refused."""
    try:
        facts = pr_facts(repo, number)
    except GhError as exc:
        raise Refused(f"cannot read PR {repo}#{number}: {exc}") from exc
    why = exemption(facts)
    if why:
        return f"{repo}#{number} exempt: {why}"
    beads = beads_in(facts["subjects"])
    if not beads:
        raise Refused(f"{repo}#{number}: no opensrm-<id> in any commit subject, so no gate "
                      "record to check (a doc-only PR changes only .md/.rst/.txt files)")
    try:
        tree = head_tree(repo, facts["head"])
    except GhError as exc:
        raise Refused(f"cannot read the head tree of {repo}#{number}: {exc}") from exc
    name = repo.split("/", 1)[1]
    reasons = []
    for bead in beads:
        paths = archives_for(root, bead, name)
        if not paths:
            reasons.append(f"{bead}: no archive (.claude/r5-state-{bead[8:]}-completed.json); "
                           "gate it first")
        for path in paths:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                reasons.append(f"{path.name}: unreadable ({exc})")
                continue
            try:
                record_repo = r5_record.build(data).get("repo") if isinstance(data, dict) else None
            except r5_record.BuildRefused:
                record_repo = None  # check() names the refusal below
            if record_repo is not None and record_repo != name:
                reasons.append(f"{path.name}: gated repo {record_repo}, not {name}")
                continue
            result = r5_record.check(data, tree)
            if result["ok"]:
                return (f"{repo}#{number}: {bead} verdict CLEAN for tree {tree} "
                        f"({path.name})")
            reasons.append(f"{path.name}: {result['reason']}: {result['detail']}")
    raise Refused(f"{repo}#{number} (head {facts['head'][:12]}, tree {tree[:12]}): "
                  + "; ".join(reasons))


# --------------------------------------------------------------------- CLI

def hook(root: Path, payload: str) -> int:
    try:
        data = json.loads(payload)
        command = data.get("tool_input", {}).get("command", "")
    except (ValueError, AttributeError):
        command = None
    if not isinstance(command, str):
        if "pr merge" not in payload:
            return 0  # not a payload this hook can read, and no merge in it
        print("r5-merge-check: merge refused [opensrm-6kqs.6]: the hook payload is "
              "unreadable and mentions pr merge, so the merge cannot be judged.",
              file=sys.stderr)
        return 2
    if "merge" not in command:
        return 0
    try:
        merges = merges_in(command)
        for args in merges:
            print(f"r5-merge-check: {judge(root, *target_of(args))}", file=sys.stderr)
    except Refused as exc:
        print(f"r5-merge-check: merge refused [opensrm-6kqs.6]: {exc}. Gate the bead "
              "(/r5-supervise), or the owner merges by hand.", file=sys.stderr)
        return 2
    return 0


def main(argv: list) -> int:
    usage = ("usage: r5_merge_check.py hook --root <dir>  (payload on stdin)\n"
             "       r5_merge_check.py pr --root <dir> -R <owner/repo> <number>")
    if len(argv) < 3 or argv[0] not in ("hook", "pr") or argv[1] != "--root":
        print(usage, file=sys.stderr)
        return 1
    root = Path(argv[2])
    if argv[0] == "hook":
        if len(argv) != 3:
            print(usage, file=sys.stderr)
            return 1
        return hook(root, sys.stdin.read())
    try:
        result = judge(root, *target_of(argv[3:]))
    except Refused as exc:
        print(f"r5-merge-check: refused: {exc}", file=sys.stderr)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
