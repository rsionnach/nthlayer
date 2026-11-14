"""Tests for scripts/r5_merge_check.py (opensrm-6kqs.6, R5-R49).

Sources for every input and expected value, never the script:

- section 6's "Verdict check" (docs/superpowers/specs/2026-11-03-r5-gate-v2-
  nthlayer-spec.md): CLEAN and the tree equal to ``verdict.tree_sha``, else a
  refusal naming the state or the mismatch;
- r5-supervise's Final step 3a for the archive names
  (``r5-state-<bead>-completed.json``, then ``-<repo>-``);
- gh's own JSON: ``gh pr view --json headRefOid,headRefName,files,
  changedFiles,commits`` (files as ``{"path", "additions", "deletions"}``,
  commits with ``messageHeadline``) and ``gh api repos/<o>/<r>/commits/<sha>``
  (``commit.tree.sha``), the REST commit object;
- the PreToolUse hook protocol: the payload's ``tool_input.command``, exit 2
  blocks with stderr shown to the session;
- the exemptions ruled for bead 6: doc-only PRs skip R5; release-please and
  dependabot PRs carry no bead.

Run: uv run --no-project --with pytest pytest -q test/test_r5_merge_check.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "r5_merge_check.py"
sys.path.insert(0, str(SCRIPT.parent))
_spec = importlib.util.spec_from_file_location("r5_merge_check", SCRIPT)
assert _spec and _spec.loader
mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mc)

REPO = "rsionnach/nthlayer"
HEAD = "c" * 40
TREE = "ab" * 20
OTHER_TREE = "cd" * 20
# A gated merge binds itself to the head judged (edge-cases, opensrm-6kqs.6).
BOUND = ["--match-head-commit", HEAD]


def view(files=("scripts/x.py",), subjects=("chore: fix it [opensrm-fx.1]",),
         branch="fx-branch", changed=None, head=HEAD) -> dict:
    """gh pr view's JSON for the fields the script asks for."""
    return {"headRefOid": head, "headRefName": branch,
            "files": [{"path": f, "additions": 1, "deletions": 0} for f in files],
            "changedFiles": len(files) if changed is None else changed,
            "commits": [{"oid": "d" * 40, "messageHeadline": s, "messageBody": ""}
                        for s in subjects]}


def archive(root: Path, name: str, *, repo="nthlayer", state="CLEAN", tree=TREE,
            bead="opensrm-fx.1") -> Path:
    """An r5-state archive whose audit trail ends in verdict_recorded."""
    rec = {
        "supervisor": "r5-supervise", "version": 2, "target_bead": bead,
        "started_at": "2026-11-14T10:00:00+00:00", "passes": [], "advisory_passes": [],
        "completed_passes": [], "advisory_results": [], "status": "completed",
        "diff_range": {repo: {"base": "1" * 40, "head": HEAD, "worktree": None}},
        "audit_trail": [{"ts": "2026-11-14T10:30:00+00:00", "event": "verdict_recorded",
                         "state": state, "tree_sha": tree, "head_sha": HEAD}],
    }
    (root / ".claude").mkdir(exist_ok=True)
    path = root / ".claude" / name
    path.write_text(json.dumps(rec))
    return path


@pytest.fixture
def stub(monkeypatch):
    """gh answers from a dict: the PR view and the head commit's tree."""
    answers = {"view": view(), "tree": TREE}
    calls = []

    def fake(args):
        calls.append(args)
        if args[:2] == ["pr", "view"]:
            if isinstance(answers["view"], Exception):
                raise answers["view"]
            return json.dumps(answers["view"])
        if args[:2] == ["api", "--paginate"]:
            assert args[2] == f"repos/{REPO}/pulls/7/files"
            if isinstance(answers.get("renamed_from"), Exception):
                raise answers["renamed_from"]
            return "".join(p + "\n" for p in answers.get("renamed_from", ()))
        if args[0] == "api":
            assert args[1] == f"repos/{REPO}/commits/{answers['view']['headRefOid']}"
            return answers["tree"] + "\n"
        raise AssertionError(args)

    monkeypatch.setattr(mc, "gh", fake)
    answers["calls"] = calls
    return answers


def payload(command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


# ------------------------------------------------------------ the verdict


def test_a_clean_verdict_for_the_head_tree_allows(tmp_path, stub):
    archive(tmp_path, "r5-state-fx.1-completed.json")
    assert "verdict CLEAN" in mc.judge(tmp_path, REPO, "7", BOUND)


def test_a_commit_after_the_gate_refuses_naming_the_mismatch(tmp_path, stub):
    archive(tmp_path, "r5-state-fx.1-completed.json")
    stub["tree"] = OTHER_TREE
    with pytest.raises(mc.Refused) as caught:
        mc.judge(tmp_path, REPO, "7", BOUND)
    assert "tree_mismatch" in str(caught.value)
    assert TREE in str(caught.value) and OTHER_TREE in str(caught.value)


def test_a_verdict_that_is_not_clean_refuses(tmp_path, stub):
    archive(tmp_path, "r5-state-fx.1-completed.json", state="ESCALATED")
    with pytest.raises(mc.Refused, match="not_clean: state ESCALATED"):
        mc.judge(tmp_path, REPO, "7", BOUND)


def test_no_archive_refuses(tmp_path, stub):
    with pytest.raises(mc.Refused, match="opensrm-fx.1: no archive"):
        mc.judge(tmp_path, REPO, "7", BOUND)


def test_an_archive_with_no_verdict_refuses(tmp_path, stub):
    path = archive(tmp_path, "r5-state-fx.1-completed.json")
    rec = json.loads(path.read_text())
    rec["audit_trail"] = []
    path.write_text(json.dumps(rec))
    with pytest.raises(mc.Refused, match="no_verdict"):
        mc.judge(tmp_path, REPO, "7", BOUND)


def test_an_archive_from_another_repo_says_nothing_about_this_pr(tmp_path, stub):
    archive(tmp_path, "r5-state-fx.1-completed.json", repo="nthlayer-common")
    with pytest.raises(mc.Refused, match="gated repo nthlayer-common, not nthlayer"):
        mc.judge(tmp_path, REPO, "7", BOUND)


def test_the_repo_named_archive_is_read_when_the_plain_one_is_another_repos(tmp_path, stub):
    """Final step 3a: the second gate of a bead is r5-state-<bead>-<repo>-completed.json."""
    archive(tmp_path, "r5-state-fx.1-completed.json", repo="nthlayer-common")
    archive(tmp_path, "r5-state-fx.1-nthlayer-completed.json")
    assert "r5-state-fx.1-nthlayer-completed.json" in mc.judge(tmp_path, REPO, "7", BOUND)


def test_a_hyphenated_archive_name_is_found(tmp_path, stub):
    """Older archives spell the bead's dots as hyphens (r5-state-wo62-4-1-...)."""
    archive(tmp_path, "r5-state-fx-1-completed.json")
    assert "verdict CLEAN" in mc.judge(tmp_path, REPO, "7", BOUND)


def _epic_verdict(root: Path, run: str, tree: str = TREE, state: str = "CLEAN") -> None:
    """epic-executor Step 9 writes <run-dir>/verdict.json (ruling M3)."""
    d = root / ".claude" / "r5-reports" / "opensrm-fx.1" / run
    d.mkdir(parents=True)
    (d / "verdict.json").write_text(json.dumps(
        {"state": state, "tree_sha": tree, "head_sha": HEAD, "at": "2026-11-14T10:00:00Z"}))


def test_an_epic_task_s_verdict_json_is_read(tmp_path, stub):
    _epic_verdict(tmp_path, "epic-20261114T100000Z", tree=OTHER_TREE)
    with pytest.raises(mc.Refused, match="tree_mismatch"):
        mc.judge(tmp_path, REPO, "7", BOUND)
    _epic_verdict(tmp_path, "epic-20261114T110000Z")
    assert "verdict.json" in mc.judge(tmp_path, REPO, "7", BOUND)


def test_an_epic_verdict_that_is_not_clean_refuses(tmp_path, stub):
    _epic_verdict(tmp_path, "epic-20261114T100000Z", state="ESCALATED")
    with pytest.raises(mc.Refused, match="not_clean"):
        mc.judge(tmp_path, REPO, "7", BOUND)


def test_any_bead_in_the_subjects_with_a_matching_verdict_allows(tmp_path, stub):
    stub["view"] = view(subjects=("test: first [opensrm-fx.2]", "chore: then [opensrm-fx.1]"))
    archive(tmp_path, "r5-state-fx.1-completed.json")
    assert "opensrm-fx.1 verdict CLEAN" in mc.judge(tmp_path, REPO, "7", BOUND)


def test_beads_come_from_subjects_only():
    assert mc.beads_in(["r5(provenance): 1 finding · opensrm-6kqs.15",
                        "chore: x [opensrm-6kqs.15]", "fix: y (opensrm-ab12)"]) == \
        ["opensrm-6kqs.15", "opensrm-ab12"]


@pytest.mark.parametrize("subject,expected", [
    ("test: R5-R33 fixtures per clause and the preflight round [opensrm-6kq\u2026", []),
    ("chore: x [opensrm-fx.1] and a long tail \u2026", ["opensrm-fx.1"]),
    ("opensrm-fx.1\u2026", []),
], ids=["cut-in-the-id", "cut-after-the-id", "one-cut-word"])
def test_a_subject_github_cut_short_loses_only_its_last_word(subject, expected):
    """gh's messageHeadline truncates long subjects with an ellipsis (seen on PR 204)."""
    assert mc.beads_in([subject]) == expected


def test_no_bead_in_any_subject_refuses(tmp_path, stub):
    stub["view"] = view(subjects=("quick fix",))
    with pytest.raises(mc.Refused, match="no opensrm-<id> in any commit subject"):
        mc.judge(tmp_path, REPO, "7", BOUND)


def test_a_head_tree_gh_cannot_give_refuses(tmp_path, stub):
    archive(tmp_path, "r5-state-fx.1-completed.json")
    stub["tree"] = "null"
    with pytest.raises(mc.Refused, match="cannot read the head tree"):
        mc.judge(tmp_path, REPO, "7", BOUND)


def test_a_pr_gh_cannot_read_refuses(tmp_path, stub):
    stub["view"] = mc.GhError("gh pr view: exit 1: no pull requests found")
    with pytest.raises(mc.Refused, match="cannot read PR"):
        mc.judge(tmp_path, REPO, "7", BOUND)


# ------------------------------------------------------------ exemptions


@pytest.mark.parametrize("files", [("CLAUDE.md",), ("docs/r5-gate.md", "README.rst", "x.txt")],
                         ids=["one-md", "md-rst-txt"])
def test_a_doc_only_pr_is_exempt(tmp_path, stub, files):
    stub["view"] = view(files=files, subjects=("no bead here",))
    assert "exempt: doc-only" in mc.judge(tmp_path, REPO, "7", BOUND)
    assert not any(c[:2] == ["api", f"repos/{REPO}/commits/{HEAD}"] for c in stub["calls"])


@pytest.mark.parametrize("files,changed", [(("CLAUDE.md", "scripts/x.py"), None),
                                           (("CLAUDE.md",), 101), (("docs/x.py",), None),
                                           ((), 0)],
                         ids=["md-and-py", "truncated-list", "py-under-docs", "no-files"])
def test_a_pr_that_is_not_only_docs_is_not_exempt(tmp_path, stub, files, changed):
    stub["view"] = view(files=files, changed=changed, subjects=("no bead here",))
    with pytest.raises(mc.Refused, match="no opensrm-<id>"):
        mc.judge(tmp_path, REPO, "7", BOUND)


@pytest.mark.parametrize("branch", ["release-please--branches--main--components--meta",
                                    "dependabot/uv/meta-package/nthlayer-core-5.0.0"])
def test_release_please_and_dependabot_prs_are_exempt(tmp_path, stub, branch):
    stub["view"] = view(branch=branch, subjects=("chore(main): release meta 1.2.0",))
    assert "exempt: branch" in mc.judge(tmp_path, REPO, "7", BOUND)


def test_a_branch_merely_mentioning_release_please_is_not_exempt(tmp_path, stub):
    stub["view"] = view(branch="fix-release-please--config", subjects=("x",))
    with pytest.raises(mc.Refused):
        mc.judge(tmp_path, REPO, "7", BOUND)


# --------------------------------------------------------- command parsing


@pytest.mark.parametrize("command,expected", [
    ("gh pr merge 206 -R rsionnach/nthlayer --merge", [["206", "-R", "rsionnach/nthlayer", "--merge"]]),
    ("cd /x && gh pr merge 5 --repo a/b", [["5", "--repo", "a/b"]]),
    ("gh pr checks 5; gh pr merge 5 -Ra/b | tail -2", [["5", "-Ra/b"]]),
    ("gh pr view 1\n/usr/bin/gh pr merge 9 -R a/b", [["9", "-R", "a/b"]]),
    ("gh pr merge 1 -R a/b && gh pr merge 2 -R a/c", [["1", "-R", "a/b"], ["2", "-R", "a/c"]]),
    ('git commit -m "then gh pr merge 5"', []),
    ("git merge --ff-only origin/main", []),
    ("gh pr view 5 --json mergeCommit", []),
], ids=["plain", "after-cd", "semicolon-pipe", "newline-abs-path", "two", "quoted",
        "git-merge", "view"])
def test_merges_in(command, expected):
    assert mc.merges_in(command) == expected


def test_an_unparseable_command_that_may_merge_refuses():
    with pytest.raises(mc.Refused, match="cannot parse"):
        mc.merges_in('gh pr merge 5 -R a/b --body "unclosed')
    assert mc.merges_in('echo "unclosed') == []


@pytest.mark.parametrize("args,expected", [
    (["206", "-R", "a/b", "--merge"], ("a/b", "206")),
    (["--repo=a/b", "7"], ("a/b", "7")),
    (["-Ra/b", "7", "-d"], ("a/b", "7")),
    (["https://github.com/a/b/pull/12"], ("a/b", "12")),
    (["-R", "a/b", "https://github.com/a/b/pull/12/"], ("a/b", "12")),
    (["7", "-R", "a/b", "--body", "merge 8", "--merge"], ("a/b", "7")),
    (["5", "-R", "o/r", "-A", "me@example.invalid"], ("o/r", "5")),
    (["-t", "", "5", "-R", "o/r"], ("o/r", "5")),
])
def test_target_of(args, expected):
    assert mc.target_of(args) == expected


@pytest.mark.parametrize("args,match", [
    (["7"], "pass -R"),
    ([], "name exactly one PR"),
    (["-R", "a/b"], "name exactly one PR"),
    (["7", "8", "-R", "a/b"], "name exactly one PR"),
    (["my-branch", "-R", "a/b"], "by number or URL"),
    (["-R", "x/y", "https://github.com/a/b/pull/1"], "disagrees"),
    (["7", "-R"], "has no value"),
    (["7", "-R", "nthlayer"], "pass -R"),
])
def test_target_of_refuses_what_it_cannot_pin(args, match):
    with pytest.raises(mc.Refused, match=match):
        mc.target_of(args)


# -------------------------------------------------------------- the hook


def test_hook_allows_a_command_that_is_not_a_merge(tmp_path, stub, capsys):
    assert mc.hook(tmp_path, payload("git status --short")) == 0
    assert stub["calls"] == []


def test_hook_refuses_with_exit_2_and_says_why(tmp_path, stub, capsys):
    assert mc.hook(tmp_path, payload(f"gh pr merge 7 -R rsionnach/nthlayer --merge --match-head-commit {HEAD}")) == 2
    err = capsys.readouterr().err
    assert "merge refused" in err and "no archive" in err


def test_hook_allows_a_gated_merge(tmp_path, stub, capsys):
    archive(tmp_path, "r5-state-fx.1-completed.json")
    assert mc.hook(tmp_path, payload(f"gh pr merge 7 -R rsionnach/nthlayer --merge --match-head-commit {HEAD}")) == 0


def test_hook_refuses_when_any_merge_in_the_command_is_ungated(tmp_path, stub, capsys):
    archive(tmp_path, "r5-state-fx.1-completed.json")
    cmd = f"gh pr merge 7 -R rsionnach/nthlayer --match-head-commit {HEAD} && gh pr merge 8"
    assert mc.hook(tmp_path, payload(cmd)) == 2
    assert "pass -R" in capsys.readouterr().err


@pytest.mark.parametrize("raw", ["", "not json", json.dumps(["x"]), json.dumps({"tool_input": 5})])
def test_hook_lets_an_unreadable_payload_through(tmp_path, stub, raw):
    """Not a Bash payload it can read, and no merge in it."""
    assert mc.hook(tmp_path, raw) == 0


@pytest.mark.parametrize("raw", ['{"tool_input": "gh pr merge 5"}', 'gh pr merge 5 -R a/b',
                                 json.dumps({"tool_input": {"command": ["gh pr merge 5"]}})])
def test_hook_refuses_an_unreadable_payload_that_mentions_a_merge(tmp_path, stub, raw, capsys):
    """The module docstring: a merge it cannot judge is refused."""
    assert mc.hook(tmp_path, raw) == 2
    assert "unreadable" in capsys.readouterr().err


def test_the_hook_end_to_end_with_a_fake_gh(tmp_path):
    """The CLI as the PreToolUse shim runs it, with gh a script on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "view.json").write_text(json.dumps(view()))
    fake = bin_dir / "gh"
    fake.write_text("#!/bin/sh\n"
                    f'if [ "$1" = pr ]; then cat "{tmp_path}/view.json"; '
                    f"else echo {TREE}; fi\n")
    fake.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    run = lambda: subprocess.run(  # noqa: E731
        [sys.executable, str(SCRIPT), "hook", "--root", str(tmp_path)],
        input=payload(f"gh pr merge 7 -R {REPO} --merge --match-head-commit {HEAD}"), capture_output=True, text=True,
        env=env)
    refused = run()
    assert refused.returncode == 2 and "no archive" in refused.stderr
    archive(tmp_path, "r5-state-fx.1-completed.json")
    assert run().returncode == 0


@pytest.mark.parametrize("argv", [[], ["hook"], ["hook", "--root"], ["other", "--root", "x"],
                                  ["hook", "--root", "x", "y"], ["pr", "x"]])
def test_usage_exits_1(argv):
    out = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True,
                         input="")
    assert out.returncode == 1


def test_pr_with_no_pr_named_is_refused_not_a_usage_error():
    out = subprocess.run([sys.executable, str(SCRIPT), "pr", "--root", "x"],
                         capture_output=True, text=True)
    assert out.returncode == 2 and "name exactly one PR" in out.stderr


# ------------------------------------- edge-cases pass findings [6kqs.6]


@pytest.mark.parametrize("args,match", [
    (["--auto"] + BOUND, "--auto merges whatever head"),
    (["--auto=true"] + BOUND, "--auto merges whatever head"),
    (["--auto=1"] + BOUND, "--auto merges whatever head"),
    ([], f"add --match-head-commit {HEAD}"),
    (["--match-head-commit", "e" * 40], "got eeee"),
    (["--match-head-commit=" + HEAD[:12]], "got cccccccccccc"),
], ids=["auto", "auto-true", "auto-1", "unbound", "other-head", "short-head"])
def test_a_gated_merge_must_be_bound_to_the_head_judged(tmp_path, stub, args, match):
    """gh merges later than this check reads the head (much later with
    --auto): a push in between would merge a tree no verdict holds for."""
    archive(tmp_path, "r5-state-fx.1-completed.json")
    with pytest.raises(mc.Refused, match=match):
        mc.judge(tmp_path, REPO, "7", args)


@pytest.mark.parametrize("off", ["--auto=false", "--auto=False", "--auto=0"])
def test_auto_spelled_false_is_off(tmp_path, stub, off):
    archive(tmp_path, "r5-state-fx.1-completed.json")
    assert "verdict CLEAN" in mc.judge(tmp_path, REPO, "7", [off] + BOUND)


def test_the_equals_form_of_the_binding_is_read(tmp_path, stub):
    archive(tmp_path, "r5-state-fx.1-completed.json")
    assert "verdict CLEAN" in mc.judge(tmp_path, REPO, "7", [f"--match-head-commit={HEAD}"])


def test_an_exempt_pr_needs_no_binding(tmp_path, stub):
    stub["view"] = view(files=("CLAUDE.md",), subjects=("x",))
    assert "exempt" in mc.judge(tmp_path, REPO, "7", ["--auto"])


@pytest.mark.parametrize("name", ["r5-state-fx.1-common-completed.json",
                                  "r5-state-fx.1-frontdoor-completed.json"])
def test_a_second_archive_under_any_short_repo_name_is_read(tmp_path, stub, name):
    """Final step 3a names the second gate's archive by its repo, and the
    archives on disk use short names (zo0o-common, h0at-frontdoor)."""
    archive(tmp_path, "r5-state-fx.1-completed.json", repo="nthlayer-common")
    archive(tmp_path, name)
    assert name in mc.judge(tmp_path, REPO, "7", BOUND)


def test_a_glob_match_of_another_bead_is_not_its_record(tmp_path, stub):
    """r5-state-fx-1-*-completed.json also matches bead fx.1.2's hyphenated
    archive: the record's target_bead decides."""
    archive(tmp_path, "r5-state-fx-1-2-completed.json", bead="opensrm-fx.1.2")
    with pytest.raises(mc.Refused, match="record of opensrm-fx.1.2, not opensrm-fx.1"):
        mc.judge(tmp_path, REPO, "7", BOUND)


@pytest.mark.parametrize("command,expected", [
    ("gh pr  merge 5 -R o/r", [["5", "-R", "o/r"]]),
    ("echo $(gh pr merge 5 -R o/r)", [["5", "-R", "o/r"]]),
    ("(gh pr merge 5 -R o/r)", [["5", "-R", "o/r"]]),
    ("echo `gh pr merge 5 -R o/r`", [["5", "-R", "o/r"]]),
    ("gh pr merge 5 \\\n  -R o/r", [["5", "-R", "o/r"]]),
    ("( gh pr merge 5 -R o/r )", [["5", "-R", "o/r"]]),
    ("echo $( gh pr merge 5 -R o/r )", [["5", "-R", "o/r"]]),
    ('gh pr merge 5 -t "" -R o/r', [["5", "-t", "", "-R", "o/r"]]),
], ids=["two-spaces", "dollar-paren", "subshell", "backticks", "continuation",
        "spaced-subshell", "spaced-dollar-paren", "empty-quoted-value"])
def test_merges_in_finds_the_shell_forms_edge_cases_named(command, expected):
    assert mc.merges_in(command) == expected


def test_a_code_file_renamed_to_a_doc_name_is_not_doc_only(tmp_path, stub):
    """gh pr view lists a rename by its new path only."""
    stub["view"] = view(files=("notes.md",), subjects=("x",))
    stub["renamed_from"] = ["scripts/x.py"]
    with pytest.raises(mc.Refused, match="no opensrm-<id>"):
        mc.judge(tmp_path, REPO, "7", BOUND)
    stub["renamed_from"] = ["old-notes.txt"]
    assert "exempt: doc-only" in mc.judge(tmp_path, REPO, "7", BOUND)




def test_a_newline_separates_two_merges():
    """Without the newline rule the second gh would read as the first's argument."""
    assert mc.merges_in("gh pr merge 1 -R a/b\ngh pr merge 2 -R a/c") == \
        [["1", "-R", "a/b"], ["2", "-R", "a/c"]]


def test_a_doc_only_pr_whose_renames_cannot_be_read_is_refused(tmp_path, stub):
    stub["view"] = view(files=("notes.md",), subjects=("x",))
    stub["renamed_from"] = mc.GhError("gh api --paginate repos: exit 1")
    with pytest.raises(mc.Refused, match="cannot read the renames"):
        mc.judge(tmp_path, REPO, "7", BOUND)


# --------------------------------- parse false positives [opensrm-6kqs.18]
#
# Bash's own grammar (bash(1), REDIRECTION and Here Documents) fixes every
# shape here: a heredoc body is data, not commands, up to a line holding only
# its delimiter (leading tabs stripped for <<-); a redirection is an optional
# fd number, an operator (<, >, >>, &>, >&, <&, <<<) and a target word, or
# &N / &- right after >& / <&. The two refusals that prompted the bead, a
# heredoc with an apostrophe in its body and "2>&1" after a merge, are the
# first cases.

HEREDOC_APOSTROPHE = ("cat >> plan.md <<'EOF'\n"
                      "the merge hook's fallback; gh is not run here\n"
                      "EOF\n"
                      "echo done")


def test_an_unparseable_heredoc_that_mentions_gh_and_merge_is_allowed():
    assert mc.merges_in(HEREDOC_APOSTROPHE) == []


def test_a_heredoc_body_line_that_reads_like_a_merge_is_not_one():
    cmd = "cat > notes.md <<EOF\ngh pr merge 5 -R a/b --merge\nEOF"
    assert mc.merges_in(cmd) == []


def test_a_merge_after_a_heredoc_is_still_seen():
    cmd = "cat > x <<'EOF'\nit's text\nEOF\ngh pr merge 5 -R a/b"
    assert mc.merges_in(cmd) == [["5", "-R", "a/b"]]


def test_a_dash_heredoc_ends_at_a_tab_indented_delimiter():
    cmd = "cat <<-END\n\tit's text\n\tEND\ngh pr merge 6 -R a/b"
    assert mc.merges_in(cmd) == [["6", "-R", "a/b"]]


def test_a_here_string_is_not_a_heredoc():
    cmd = "grep x <<< 'abc'\ngh pr merge 7 -R a/b"
    assert mc.merges_in(cmd) == [["7", "-R", "a/b"]]


@pytest.mark.parametrize("command", [
    "gh pr merge 208 -R a/b --merge 2>&1",
    "gh pr merge 208 -R a/b --merge 2>&1 | tail -2",
    "gh pr merge 208 -R a/b >/dev/null 2>&1",
    "gh pr merge 208 -R a/b > out.txt",
    "gh pr merge 208 -R a/b &> log",
    "gh pr merge 208 -R a/b 2> err.txt",
    "gh pr merge 208 -R a/b >> log 2>&-",
    "gh pr merge 208 < /dev/null -R a/b",
], ids=["2>&1", "2>&1-pipe", "devnull", "stdout-file", "both", "stderr-file",
        "append-close", "stdin"])
def test_redirections_are_not_arguments(command):
    args = ["208", "-R", "a/b"] + (["--merge"] if "--merge" in command else [])
    assert mc.merges_in(command) == [args]


def test_a_quoted_redirection_stays_an_argument():
    """Inside quotes, > is text: a --body value keeps it."""
    assert mc.merges_in('gh pr merge 5 -R a/b --body "x > y"') == \
        [["5", "-R", "a/b", "--body", "x > y"]]


def test_a_pr_number_before_a_spaced_redirect_is_kept():
    """A digit word is an fd number only when the operator touches it."""
    assert mc.merges_in("gh pr merge 208 > out") == [["208"]]


def test_an_unparseable_command_with_the_merge_words_is_still_refused():
    with pytest.raises(mc.Refused, match="cannot parse"):
        mc.merges_in("gh pr merge 5 -R a/b --body \"it's")


@pytest.mark.parametrize("command", [
    'echo "the gh tool can merge; it' + "'s fine",
    "echo 'merge it' \"and gh",
], ids=["gh-and-merge-in-prose", "split-words"])
def test_an_unparseable_command_without_the_merge_words_is_allowed(command):
    assert mc.merges_in(command) == []


def test_the_hook_allows_the_heredoc_that_prompted_the_bead(tmp_path, stub):
    assert mc.hook(tmp_path, payload(HEREDOC_APOSTROPHE)) == 0
    assert stub["calls"] == []


# --------------------------------- correctness pass findings [6kqs.18]


@pytest.mark.parametrize("command", [
    "n=$((1<<2))\ngh pr merge 5 -R o/r",
    'git commit -m "shift x<<y"\ngh pr merge 5 -R o/r',
    "echo 'a<<b'\ngh pr merge 5 -R o/r",
    "((x<<=1))\ngh pr merge 5 -R o/r",
], ids=["arithmetic", "double-quoted", "single-quoted", "arith-command"])
def test_a_shift_or_quoted_double_angle_hides_no_later_merge(command):
    """A << that is no heredoc operator opens no body: a merge after it is seen."""
    assert mc.merges_in(command) == [["5", "-R", "o/r"]]


def test_an_unclosed_heredoc_body_is_kept():
    """A body that never reaches its delimiter was no heredoc: nothing is hidden."""
    assert mc.merges_in("cat <<EOF\ngh pr merge 5 -R o/r") == [["5", "-R", "o/r"]]


def test_a_closed_heredoc_still_hides_its_body_after_an_arithmetic_shift():
    cmd = "n=$((1<<2)); cat <<EOF\ngh pr merge 9 -R o/r\nEOF\ngh pr merge 5 -R o/r"
    assert mc.merges_in(cmd) == [["5", "-R", "o/r"]]


@pytest.mark.parametrize("command", [
    "\"gh\" pr merge 5 -R o/r\necho it's",
    "gh 'pr' \"merge\" 5 -R o/r\necho it's",
], ids=["quoted-gh", "quoted-pr-merge"])
def test_an_unparseable_command_with_quoted_merge_words_is_refused(command):
    with pytest.raises(mc.Refused, match="cannot parse"):
        mc.merges_in(command)


def test_a_file_target_after_dup_operator_is_not_an_argument():
    assert mc.merges_in("gh pr merge 5 -R o/r >&log") == [["5", "-R", "o/r"]]
    assert mc.merges_in("gh pr merge 5 -R o/r >& log") == [["5", "-R", "o/r"]]



@pytest.mark.parametrize("command", [
    'echo "a\nx <<EOF"\ngh pr merge 5 -R o/r\nEOF',
    "# see x <<EOF\ngh pr merge 5 -R o/r\nEOF",
    "echo hi # x <<EOF\ngh pr merge 5 -R o/r\nEOF",
], ids=["multi-line-quote", "comment-line", "trailing-comment"])
def test_a_double_angle_in_a_multi_line_quote_or_a_comment_opens_no_body(command):
    """Correctness verify (6kqs.18): quote state spans lines; a comment is text."""
    assert ["5", "-R", "o/r"] in mc.merges_in(command)


def test_a_hash_inside_a_word_is_not_a_comment():
    cmd = "cat a#b <<EOF\ngh pr merge 9 -R o/r\nEOF\ngh pr merge 5 -R o/r"
    assert mc.merges_in(cmd) == [["5", "-R", "o/r"]]


@pytest.mark.parametrize("command", ["gh pr merge 5 -R o/r >&2x", "gh pr merge 5 -R o/r >&2",
                                     "gh pr merge 5 -R o/r 2>&-", "gh pr merge 5 -R o/r 1>&2-"],
                         ids=["file-2x", "dup-2", "close", "move-2"])
def test_a_dup_target_is_a_number_or_dash_or_else_a_file(command):
    assert mc.merges_in(command) == [["5", "-R", "o/r"]]
