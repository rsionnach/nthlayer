"""Tests for scripts/r5_provenance_checks.py (opensrm-6kqs.5, R5-R1, R5-R33).

Every fixture is derived from cúramóir's normative wording of R5-R33
(``docs/r5-gate-v2-curamoir-spec.md``, section 7), quoted in the script's
docstring, and cites the clause it reproduces:

    "no test added or changed in BASE..HEAD is SKIPPED or deselected; no
    changed test module collects zero; no collection-time parametrise list
    lacks a non-zero minimum; no changed test file contains a module-level
    skip, a layout-relative path, an early return in a test body, or a bare
    except that swallows."

The escape the checks exist for is opensrm-ih0v's archetype module
(nthlayer-common 28d7add, tests/test_manifest_v2_archetypes.py): a
module-level ``pytestmark`` skipif, a ``Path(__file__).resolve().parents[2]``
layout path, and a collection-time parametrise over a list that is empty
outside the sibling layout. ``test_the_archetypes_shape_hits_all_three``
rebuilds that shape synthetically; nothing here is copied from the module.

Synthetic git repositories are built in tmp_path; the runtime checks run a
tiny pytest project with the current interpreter
(``--pytest "<sys.executable> -m pytest"``). No network.

Run: uv run --no-project --with pytest pytest -q test/test_r5_provenance_checks.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "r5_provenance_checks.py"
sys.path.insert(0, str(SCRIPT.parent))
_spec = importlib.util.spec_from_file_location("r5_provenance_checks", SCRIPT)
assert _spec and _spec.loader
checks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checks)
import r5_findings  # noqa: E402  (sibling script, on the path above)

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t"}
PYTEST = [sys.executable, "-m", "pytest"]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env={**os.environ, **ENV}).stdout.strip()


def commit(repo: Path, files: dict, message: str) -> str:
    """Write (dedented) files, None deletes one, and commit."""
    for name, text in files.items():
        path = repo / name
        if text is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    return r


def gate(repo: Path, head_files: dict, base_files: dict | None = None,
         static_only: bool = True) -> tuple[dict, int]:
    """BASE (a README plus base_files), then HEAD (head_files); run check."""
    base = commit(repo, {"README": "x\n", "pytest.ini": "[pytest]\n", **(base_files or {})}, "base")
    head = commit(repo, head_files, "head")
    return checks.check(repo, base, head, static_only, PYTEST, 120)


def hits(result: dict, check: str) -> list[dict]:
    return [f for f in result["findings"] if f["check"] == check]


# ------------------------------------------- "a module-level skip"


@pytest.mark.parametrize("source", [
    """
    import pytest
    pytestmark = pytest.mark.skipif(True, reason="layout")
    def test_a():
        assert 1
    """,
    """
    import pytest
    pytestmark = [pytest.mark.slow, pytest.mark.skip(reason="later")]
    def test_a():
        assert 1
    """,
    """
    import os
    import pytest
    if not os.environ.get("NOPE"):
        pytest.skip("not here", allow_module_level=True)
    def test_a():
        assert 1
    """,
    """
    import pytest
    yaml = pytest.importorskip("yaml")
    def test_a():
        assert 1
    """,
    """
    import unittest
    raise unittest.SkipTest("off")
    """,
], ids=["pytestmark-skipif", "pytestmark-list-skip", "skip-allow-module-level", "importorskip",
        "raise-skiptest"])
def test_a_module_level_skip_hits(repo, source):
    result, code = gate(repo, {"tests/test_m.py": source})
    assert code == 2
    assert len(hits(result, "module_level_skip")) == 1


def test_skips_that_are_not_module_level_do_not_hit(repo):
    """A skip on one test is the runtime check's business; xfail is a ledger."""
    result, code = gate(repo, {"tests/test_m.py": """
        import pytest
        pytestmark = pytest.mark.xfail(strict=True)
        @pytest.mark.skipif(True, reason="one test")
        def test_a():
            pytest.importorskip("yaml")
            pytest.skip("inside", allow_module_level=True)
        class TestB:
            pytestmark = pytest.mark.skip
            def test_b(self):
                assert 1
        pytest.skip("no flag")
        """})
    assert hits(result, "module_level_skip") == []


# --------------------------------------------- "a layout-relative path"


@pytest.mark.parametrize("path,source", [
    ("tests/test_m.py", "ROOT = Path(__file__).resolve().parents[2]\n"),
    ("tests/test_m.py", "ROOT = Path(__file__).parent.parent.parent / 'opensrm'\n"),
    ("tests/test_m.py", "ROOT = Path(__file__).parent / '..' / '..' / 'opensrm'\n"),
    ("tests/test_m.py", "ROOT = os.path.join(os.path.dirname(__file__), '..', '../opensrm')\n"),
    ("tests/test_m.py", "HERE = Path(__file__).parent\nROOT = HERE.parent.parent\n"),
    ("tests/unit/test_m.py", "ROOT = pathlib.Path(__file__).parents[3]\n"),
    ("test_m.py", "ROOT = Path(__file__).parents[1]\n"),
    ("tests/test_m.py", "ROOT = Path(__file__).parents[N]\n"),
], ids=["parents-2", "parent-chain", "dotdot-segments", "os-path-join", "alias",
        "deeper-file", "top-level-file", "non-literal-index"])
def test_a_path_climbing_out_of_the_repository_hits(repo, path, source):
    result, code = gate(repo, {path: "import os, pathlib\nfrom pathlib import Path\nN = 2\n"
                                     + source})
    assert code == 2
    found = hits(result, "layout_relative_path")
    assert len(found) == 1, found
    assert found[0]["start_line"] == 3 + source.count("\n")  # where it first escapes


def test_paths_inside_the_repository_do_not_hit(repo):
    """parents[1] of tests/x.py is the repository root, which a worktree keeps."""
    result, _ = gate(repo, {"tests/test_m.py": """
        from pathlib import Path
        ROOT = Path(__file__).resolve().parents[1]
        DATA = Path(__file__).parent / "data" / "x.json"
        UP = Path(__file__).parent / ".." / "scripts"
        CWD = Path("..") / "elsewhere"
        """, "tests/unit/test_n.py": """
        from pathlib import Path
        ROOT = Path(__file__).parents[2]
        """})
    assert hits(result, "layout_relative_path") == []


def test_an_escaped_name_is_reported_once_not_at_each_use(repo):
    result, _ = gate(repo, {"tests/test_m.py": """
        from pathlib import Path
        ECO = Path(__file__).resolve().parents[2]
        SPEC = ECO / "opensrm" / "spec"
        EXAMPLES = SPEC / "examples"
        """})
    assert [f["start_line"] for f in hits(result, "layout_relative_path")] == [3]


# --------------------------------------- "an early return in a test body"


def test_an_early_return_in_a_test_body_hits(repo):
    result, _ = gate(repo, {"tests/test_m.py": """
        def test_a(flag=False):
            if not flag:
                return
            assert flag
        class TestB:
            def test_b(self):
                for x in range(3):
                    return x
        def test_c():
            assert 1
            return 1
        """})
    assert [f["start_line"] for f in hits(result, "early_return")] == [4, 9, 12]


def test_returns_that_end_nothing_early_do_not_hit(repo):
    result, _ = gate(repo, {"tests/test_m.py": """
        import pytest
        @pytest.fixture
        def thing():
            return 1
        def helper():
            return 2
        def test_a():
            def inner():
                return 3
            f = lambda: 4
            assert inner() + f()
            return
        class Helper:
            def test_not_collected(self):
                return 5
        """})
    assert hits(result, "early_return") == []


# ---------------------------------------- "a bare except that swallows"


@pytest.mark.parametrize("handler", [
    "except:\n        pass",
    "except Exception:\n        x = 1",
    "except (ValueError, BaseException):\n        pass",
    "except Exception:\n        pytest.skip('flaky')",
], ids=["bare", "exception", "tuple-with-base", "into-a-skip"])
def test_a_swallowing_except_hits(repo, handler):
    source = f"import pytest\ndef test_a():\n    try:\n        f()\n    {handler}\n"
    result, code = gate(repo, {"tests/test_m.py": source})
    assert code == 2
    assert len(hits(result, "swallowing_except")) == 1


def test_suppress_exception_hits(repo):
    result, _ = gate(repo, {"tests/test_m.py": """
        import contextlib
        def test_a():
            with contextlib.suppress(Exception):
                f()
        """})
    assert len(hits(result, "swallowing_except")) == 1


def test_excepts_that_re_raise_or_are_narrow_do_not_hit(repo):
    result, _ = gate(repo, {"tests/test_m.py": """
        import pytest
        def test_a():
            try:
                f()
            except Exception:
                raise
            try:
                f()
            except Exception as exc:
                raise RuntimeError("wrapped") from exc
            try:
                f()
            except ValueError:
                pass
            try:
                f()
            except Exception as exc:
                pytest.fail(f"raised {exc}")
        """})
    assert hits(result, "swallowing_except") == []


# ---------- "no collection-time parametrise list lacks a non-zero minimum"


@pytest.mark.parametrize("decl,argvalues", [
    ("def cases():\n    return []\n", "cases()"),
    ("def cases():\n    return []\n", "[c for c in cases()]"),
    ("", "[]"),
    ("def cases():\n    return []\nCASES = cases()\n", "CASES"),
    ("def cases():\n    return []\nassert len(cases()) == 0\n", "cases()"),
    ("def cases():\n    return []\n", "[*cases()]"),
], ids=["call", "comprehension", "empty-literal", "name-of-a-call", "wrong-guard", "starred"])
def test_a_parametrise_without_a_minimum_hits(repo, decl, argvalues):
    source = f"import pytest\n{decl}@pytest.mark.parametrize('x', {argvalues})\ndef test_a(x):\n    assert x\n"
    result, code = gate(repo, {"tests/test_m.py": source})
    assert code == 2
    assert len(hits(result, "unguarded_parametrize")) == 1


@pytest.mark.parametrize("decl,argvalues", [
    ("", "[1, 2]"),
    ("CASES = (1, 2)\n", "CASES"),
    ("def cases():\n    return [1]\nassert cases()\n", "cases()"),
    ("def cases():\n    return [1]\nassert len(cases()) >= 1\n", "cases()"),
    ("def cases():\n    return [1]\nassert 0 < len(cases())\n", "[c for c in cases()]"),
    ("def cases():\n    return [1]\nCASES = cases()\nassert CASES\n", "CASES"),
    ("", "argvalues=[pytest.param(1, id='one')], argnames='x'"),
], ids=["literal", "name-of-a-literal", "assert-truthy", "assert-len", "reversed-compare",
        "assert-the-name", "keyword-literal"])
def test_a_guarded_or_literal_parametrise_does_not_hit(repo, decl, argvalues):
    args = argvalues if argvalues.startswith("argvalues") else f"'x', {argvalues}"
    source = f"import pytest\n{decl}@pytest.mark.parametrize({args})\ndef test_a(x):\n    assert x\n"
    result, _ = gate(repo, {"tests/test_m.py": source})
    assert hits(result, "unguarded_parametrize") == []


# ---------------------------------------------- the ih0v escape, rebuilt


ARCHETYPES = """
    from pathlib import Path
    import pytest

    ECOSYSTEM_ROOT = Path(__file__).resolve().parents[2]
    EXAMPLES = ECOSYSTEM_ROOT / "spec-repo" / "examples"


    def _examples():
        if not EXAMPLES.is_dir():
            return []
        return sorted(EXAMPLES.iterdir())


    pytestmark = pytest.mark.skipif(not _examples(), reason="spec repo not beside this one")


    @pytest.mark.parametrize("path", _examples(), ids=lambda p: p.name)
    def test_example_parses(path):
        assert path.read_text()
    """


def test_the_archetypes_shape_hits_all_three(repo):
    """R5-R33's module-level skip, layout-relative path and parametrise
    without a minimum, on one file shaped like opensrm-ih0v's escape."""
    result, code = gate(repo, {"tests/test_archetypes.py": ARCHETYPES})
    assert code == 2
    assert {f["check"] for f in result["findings"]} == {
        "module_level_skip", "layout_relative_path", "unguarded_parametrize"}
    for f in result["findings"]:
        # The section 6 Finding, lens provenance, blocking, proved by script.
        assert (f["lens"], f["severity"], f["verification_level"]) == (
            "provenance", "CRITICAL", "script")
        assert f["fingerprint"] == r5_findings.fingerprint("provenance", f["path"], f["claim"])
        assert f["evidence"] and f["status"] == "open" and f["resolves"] is None
    assert result["checks"]["module_level_skip"] == {"ran": True, "hits": 1, "detail": {"files": 1}}


def test_the_archetypes_shape_also_fails_at_runtime(repo):
    """Outside the sibling layout the module skips: every changed test is
    SKIPPED (R5-R33's first clause)."""
    result, code = gate(repo, {"tests/test_archetypes.py": ARCHETYPES}, static_only=False)
    assert code == 2
    skipped = hits(result, "skipped_or_deselected")
    assert [f["claim"] for f in skipped] == ["changed test test_example_parses is SKIPPED when run"]


def test_two_hits_with_one_claim_keep_distinct_fingerprints(repo):
    result, _ = gate(repo, {"tests/test_m.py": """
        def test_a():
            try:
                f()
            except:
                pass
            try:
                g()
            except:
                pass
        """})
    prints = [f["fingerprint"] for f in result["findings"]]
    assert len(prints) == 2 and len(set(prints)) == 2


# ------------------------------------------------- which files are checked


def test_only_test_files_changed_in_the_range_are_checked(repo):
    bad = "import pytest\npytestmark = pytest.mark.skip\n"
    result, code = gate(
        repo,
        {"tests/test_touched.py": "def test_a():\n    assert 1\n",
         "tests/test_gone.py": None,
         "tests/test_old.py": None, "tests/test_new_name.py": bad,
         "tests/helpers.py": bad + "# changed\n", "tests/conftest.py": bad},
        {"tests/test_untouched.py": bad, "tests/test_touched.py": "x = 1\n",
         "tests/test_gone.py": bad, "tests/test_old.py": bad, "tests/helpers.py": bad})
    assert result["test_files"] == ["tests/test_new_name.py", "tests/test_touched.py"]
    assert [f["path"] for f in result["findings"]] == ["tests/test_new_name.py"]
    assert code == 2


def test_a_range_with_no_test_file_is_clean(repo):
    result, code = gate(repo, {"src/app.py": "x = 1\n"}, static_only=False)
    assert code == 0 and result["findings"] == [] and result["errors"] == []
    assert all(c["ran"] for c in result["checks"].values())


# ----------------------------------- a check that cannot run never passes


def test_a_file_that_does_not_parse_cannot_be_checked(repo):
    result, code = gate(repo, {"tests/test_m.py": "def test_a(:\n"})
    assert code == 1
    assert result["checks"]["early_return"]["ran"] is False
    assert "does not parse" in result["errors"][0]


def test_an_unknown_base_cannot_be_checked(repo):
    commit(repo, {"README": "x\n"}, "base")
    result, code = checks.check(repo, "0" * 40, "HEAD", True, PYTEST, 60)
    assert code == 1 and not any(c["ran"] for c in result["checks"].values())


def test_runtime_refuses_a_checkout_that_is_not_head(repo):
    base = commit(repo, {"README": "x\n"}, "base")
    head = commit(repo, {"tests/test_m.py": "def test_a():\n    assert 1\n"}, "head")
    git(repo, "checkout", "-q", base)
    result, code = checks.check(repo, base, head, False, PYTEST, 60)
    assert code == 1
    assert "not --head" in result["errors"][0]
    assert result["checks"]["zero_collected"]["ran"] is False


def test_runtime_refuses_tracked_changes(repo):
    base = commit(repo, {"README": "x\n"}, "base")
    head = commit(repo, {"tests/test_m.py": "def test_a():\n    assert 1\n"}, "head")
    (repo / "tests" / "test_m.py").write_text("def test_a():\n    assert 0\n")
    result, code = checks.check(repo, base, head, False, PYTEST, 60)
    assert code == 1 and "tracked files differ" in result["errors"][0]


def test_a_pytest_that_does_not_run_cannot_be_checked(repo):
    base = commit(repo, {"README": "x\n"}, "base")
    head = commit(repo, {"tests/test_m.py": "def test_a():\n    assert 1\n"}, "head")
    result, code = checks.check(repo, base, head, False, ["false"], 60)
    assert code == 1 and result["checks"]["skipped_or_deselected"]["ran"] is False


def test_a_collection_error_cannot_be_checked(repo):
    result, code = gate(repo, {"tests/test_m.py": "import not_a_module_anywhere\n"
                                                  "def test_a():\n    assert 1\n"},
                        static_only=False)
    assert code == 1 and "collection errors" in result["errors"][0]


# ----------------------------- "no changed test module collects zero"


def test_a_module_that_collects_zero_hits(repo):
    """Skipped at collection (allow_module_level) and empty: both zero."""
    result, code = gate(repo, {
        "tests/test_skipped.py": """
            import pytest
            pytest.skip("nowhere", allow_module_level=True)
            def test_a():
                assert 1
            """,
        "tests/test_empty.py": "def helper():\n    return 1\n"}, static_only=False)
    assert code == 2
    assert sorted(f["path"] for f in hits(result, "zero_collected")) == [
        "tests/test_empty.py", "tests/test_skipped.py"]


# -------- "no test added or changed in BASE..HEAD is SKIPPED or deselected"


def test_a_changed_test_skipped_at_run_time_hits(repo):
    result, code = gate(repo, {"tests/test_m.py": """
        import pytest
        def test_runs():
            assert 1
        def test_skips():
            pytest.skip("not today")
        @pytest.mark.xfail(strict=True)
        def test_xfails():
            assert 0
        @pytest.mark.parametrize("x", [])
        def test_empty(x):
            assert x
        """}, static_only=False)
    assert code == 2
    claims = sorted(f["claim"] for f in hits(result, "skipped_or_deselected"))
    # An empty parameter set is collected as one skipped item; an xfail is not a skip.
    assert claims == ["changed test test_empty is SKIPPED when run",
                      "changed test test_skips is SKIPPED when run"]
    assert "not today" in next(f["evidence"] for f in result["findings"]
                               if f["claim"].startswith("changed test test_skips"))


def test_a_changed_test_deselected_by_the_repository_config_hits(repo):
    result, code = gate(repo, {
        "pytest.ini": "[pytest]\naddopts = -m 'not slow'\nmarkers = slow\n",
        "tests/test_m.py": """
            import pytest
            def test_fast():
                assert 1
            @pytest.mark.slow
            def test_slow():
                assert 1
            """}, static_only=False)
    assert code == 2
    assert [f["claim"] for f in hits(result, "skipped_or_deselected")] == [
        "changed test test_slow is deselected"]


UNCHANGED_SKIP = """
    import pytest
    def test_old_skipped():
        pytest.skip("pre-existing")
    def test_other():
        assert 1
    """


def test_an_unchanged_skipped_test_in_a_changed_module_does_not_hit(repo):
    head = UNCHANGED_SKIP.replace("assert 1", "assert 2")
    result, code = gate(repo, {"tests/test_m.py": head}, {"tests/test_m.py": UNCHANGED_SKIP},
                        static_only=False)
    assert code == 0 and result["findings"] == []
    assert result["checks"]["skipped_or_deselected"]["ran"] is True


def test_a_module_scope_change_makes_every_test_changed(repo):
    head = "import os\n" + textwrap.dedent(UNCHANGED_SKIP)
    result, code = gate(repo, {"tests/test_m.py": head}, {"tests/test_m.py": UNCHANGED_SKIP},
                        static_only=False)
    assert code == 2
    assert [f["claim"] for f in hits(result, "skipped_or_deselected")] == [
        "changed test test_old_skipped is SKIPPED when run"]


def test_blank_and_comment_lines_change_no_test(repo):
    head = textwrap.dedent(UNCHANGED_SKIP) + "\n\n# a note\n"
    result, code = gate(repo, {"tests/test_m.py": head}, {"tests/test_m.py": UNCHANGED_SKIP},
                        static_only=False)
    assert code == 0


def test_a_clean_runtime_run_exits_0_and_leaves_the_repository_untouched(repo):
    result, code = gate(repo, {"tests/test_m.py": "def test_a():\n    assert 1\n"},
                        static_only=False)
    assert code == 0 and result["errors"] == []
    assert result["checks"]["zero_collected"]["detail"]["modules"]["tests/test_m.py"][
        "collected"] == 1
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == ""


# --------------------------------------------------------------------- CLI


def test_cli_prints_one_json_object_and_exits_2_on_a_hit(repo):
    base = commit(repo, {"README": "x\n"}, "base")
    head = commit(repo, {"tests/test_m.py": "import pytest\npytestmark = pytest.mark.skip\n"},
                  "head")
    out = subprocess.run([sys.executable, str(SCRIPT), "check", "--repo", str(repo), "--base",
                          base, "--head", head, "--static-only"], capture_output=True, text=True)
    assert out.returncode == 2
    data = json.loads(out.stdout)
    assert (data["base"], data["head"], data["static_only"]) == (base, head, True)
    assert data["checks"]["zero_collected"] == {"ran": False, "hits": 0,
                                                "detail": {"skipped": "--static-only"}}


@pytest.mark.parametrize("args", [[], ["check"], ["check", "--repo", "/nonexistent", "--base",
                                                  "a", "--head", "b"],
                                  ["check", "--repo", ".", "--base", "a", "--head", "b",
                                   "--pytest", ""]],
                         ids=["no-command", "missing-flags", "no-repo", "empty-pytest"])
def test_cli_usage_errors_exit_1(args):
    out = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
    assert out.returncode == 1
