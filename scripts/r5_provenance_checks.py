#!/usr/bin/env python3
"""Round 0's provenance mechanical checks [opensrm-6kqs.5, R5-R1, R5-R33].

Bead 5 in section 3 of
docs/superpowers/specs/2026-11-03-r5-gate-v2-nthlayer-spec.md: before the
first reviewer, r5-supervise runs lint, the type check, the full suite and
these checks on ``BASE..HEAD``; any hit is a blocking provenance finding in
the record and the gate stops before any model is dispatched. The normative
wording is cúramóir's (``docs/r5-gate-v2-curamoir-spec.md``, section 5 and
section 7), copied here so the fixtures can be derived from it rather than
from this code:

    R5-R1 (round 0). Before any model is dispatched the runner runs the
    deterministic pre-pass on BASE..HEAD: curamoir-lint, the configured
    linters and type check, the full suite, and the provenance mechanical
    checks (R5-R33). Any failure ends the gate PREFLIGHT_FAILED with the tool
    output as the record.

    R5-R33 (execution and guard checks). In round 0 and after every fix
    round: no test added or changed in BASE..HEAD is SKIPPED or deselected;
    no changed test module collects zero; no collection-time parametrise list
    lacks a non-zero minimum; no changed test file contains a module-level
    skip, a layout-relative path, an early return in a test body, or a bare
    except that swallows. Each is a curamoir-lint rule with a fixture,
    shipped in examples/python/ (E5-R27). A hit is a blocking provenance
    finding.

    r5_provenance_checks.py check --repo <path> --base <sha> --head <sha>
                                  [--static-only] [--pytest "<prefix>"]
                                  [--timeout <seconds>]

Output: one JSON object on stdout with ``base`` and ``head`` (full SHAs),
``static_only``, ``test_files`` (the changed test files checked),
``findings`` (section 6 Finding objects) and ``checks`` (per check: ``ran``,
``hits``, ``detail``). Exit 0: every check ran, no hit. Exit 2: every check
ran and at least one hit. Exit 1: a usage error, or a check that could not
run (named in its ``detail``, and in ``errors``): a check that cannot run is
never passed, so the caller treats round 0 as not clean. ``--static-only``
leaves the runtime checks ``ran: false`` with that reason and does not by
itself exit 1; the output says ``static_only: true`` and the caller decides.

Findings. Each hit is a section 6 Finding built through r5_findings's
validator (so the fingerprint is its ``sha256(lens|path|normalised claim)``):
lens ``provenance``, severity CRITICAL, ``verification_level`` ``script``,
``evidence`` the check's concrete output. CRITICAL because every check here
names a test that can stay green without exercising what it claims to:
R5-R32 makes a surviving mutation (a test that passes with the behaviour
broken) CRITICAL, and a skipped, uncollected or never-failing test is the
same outcome reached without mutating anything. That is the shape of both
escapes in this workspace's record: opensrm-ih0v's archetype module, which
skipped silently outside the sibling layout, and oh27's never-firing branch.

What a "changed test file" is: a path added, modified, renamed or copied in
``git diff BASE HEAD`` (rename detection on; deletions ignored) whose
basename matches pytest's default ``python_files``: ``test_*.py`` or
``*_test.py``. A repository that configures other ``python_files``, and
``conftest.py``, are not covered. Static checks read each file at HEAD with
``git cat-file``; they never check out or modify anything. A file that does
not parse under the interpreter running this script cannot be checked
(exit 1).

Static checks, exactly:

- ``module_level_skip``: in module-scope code (top-level statements and the
  bodies of top-level ``if``/``try``/``with``/``for``/``while``, never a
  ``def``, ``class`` or ``lambda``), any of: an assignment (plain, annotated
  or augmented) to ``pytestmark`` whose value contains a ``<x>.mark.skip``
  or ``<x>.mark.skipif``; a call to ``<x>.skip`` or ``skip`` with
  ``allow_module_level`` set to anything but a literal False; a call to
  ``<x>.importorskip`` or ``importorskip`` (it skips the whole module when
  the import fails); ``raise`` of ``SkipTest`` (``unittest.SkipTest``,
  ``<x>.skip.Exception``). Not flagged: ``xfail`` marks (a strict xfail
  fails on XPASS, so it is a ledger, not a skip); skip marks on a class or a
  function (the runtime check reports the tests they skip).
- ``layout_relative_path``: a path anchored on ``__file__`` that climbs
  above the repository root. The file's repository path fixes how far up the
  root is: ``k`` = the number of components in that path (``tests/x.py`` has
  2), and the path escapes when it climbs more than ``k`` levels above the
  file at any point. Climbing: ``.parent`` 1, ``.parents[N]`` N+1,
  ``os.path.dirname`` 1, a ``..`` segment joined by ``/``, ``joinpath``,
  ``os.path.join`` or extra ``Path()`` arguments 1 (a literal segment
  descends 1; a non-literal segment is taken as one descending segment).
  Transparent: ``Path``/``pathlib.Path``/``PurePath``, ``str``,
  ``os.fspath``, ``os.path.abspath``/``realpath``/``normpath``,
  ``.resolve()``/``.absolute()``/``.expanduser()``. A name assigned exactly
  once in the file is followed to its value (``HERE = Path(__file__).parent``
  then ``HERE.parent.parent``), and the hit is reported where the climb
  first escapes, never again at each use of the escaped name. A
  ``.parents[...]`` index that is not an integer literal is a hit (it cannot
  be shown to stay inside). Deliberately not flagged: ``parents[N]`` that
  stays inside the repository (``tests/x.py``'s ``parents[1]`` is the
  root, which a worktree preserves), cwd-relative paths (``Path("..")``,
  ``os.getcwd()``), and paths from fixtures such as ``rootpath``.
- ``early_return``: a ``return`` in the body of a test function, at any
  depth except inside a nested ``def``, ``lambda`` or ``class``. A test
  function is a function named ``test*`` at module scope, or a method named
  ``test*`` of a module-scope class named ``Test*`` (pytest's default
  ``python_functions`` and ``python_classes``). A bare ``return`` that is
  the body's last statement is not flagged: it ends nothing early. Returns in
  fixtures and helpers are not flagged.
- ``swallowing_except``: anywhere in the file, an ``except:`` or an
  ``except`` naming ``Exception`` or ``BaseException`` (alone or in a
  tuple) whose handler contains no ``raise`` and no call to ``pytest.fail``
  or ``fail`` (outside nested defs; a conditional raise counts as a
  raise), and any ``with`` item ``suppress(Exception|BaseException)``. An
  ``except ValueError:`` that passes is not flagged: it is narrow.
- ``unguarded_parametrize``: a ``<x>.mark.parametrize`` call (decorator or
  ``pytestmark``) whose argvalues (second positional or ``argvalues=``) is
  not a non-empty literal list, tuple or set without ``*`` elements, nor a
  name bound exactly once in the file to one, unless a module-scope
  ``assert`` guards its source. An empty literal is always a hit. The source
  is the argvalues expression itself, the iterable of a comprehension's first
  ``for``, a ``*`` element's value, and the value a once-bound name holds.
  An accepted guard is ``assert S``, ``assert bool(S)``, ``assert len(S)``,
  ``assert len(S) > c`` (c >= 0), ``assert len(S) >= c``,
  ``assert len(S) == c`` (c >= 1), ``assert len(S) != 0``, or the same
  comparisons written the other way round, with ``S`` the source written
  exactly as at the parametrise site. ``metafunc.parametrize`` in
  ``pytest_generate_tests`` is not covered. The guard runs at import, so a
  collection-time empty list fails collection instead of skipping.

Runtime checks (unless ``--static-only``), run inside the repository's own
environment with the ``--pytest`` prefix (default ``uv run --frozen
pytest``), with the working directory the repository. They refuse (exit 1)
unless ``git rev-parse HEAD`` is ``--head`` and no tracked file differs from
HEAD. Each changed test module is run once, ``<prefix> -rs -p
no:cacheprovider -p r5_round0_probe <module>``, with
``PYTHONDONTWRITEBYTECODE=1``; the probe is a pytest plugin this script writes
to a temporary directory on ``PYTHONPATH``, which records the collected and
deselected node ids, collection errors and skips, and each test's outcome as
structured data, so the result never depends on parsing pytest's output or on
the repository's ``-q`` in ``addopts``. One run gives what ``--collect-only``
would, plus the outcomes. A module whose collection errors, or a run that
exits other than 0, 1 or 5 or writes no probe output, cannot be checked
(exit 1). Test failures are the suite's business, not this check's.

- ``zero_collected``: the module collects no item (selected plus
  deselected), including a module skipped at collection.
- ``skipped_or_deselected``: a changed test with an item reported SKIPPED
  (an xfail is not a skip), or deselected, or with no item collected at all
  (unless the module collected zero, already reported). A test is changed
  when a line of it (decorators included) is added or modified in the
  ``BASE..HEAD`` diff, or the file is new; a changed line at class level
  makes every test of that class changed, and one at module level every test
  of the module. Blank and comment-only lines are ignored; a deletion counts
  at the line it was deleted before.

Standard library only, Python 3.9 compatible, like the other gate scripts.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r5_findings import ReportError, _finding  # noqa: E402  (sibling script)

LENS = "provenance"
SEVERITY = "CRITICAL"
LEVEL = "script"
STATIC_CHECKS = ("module_level_skip", "layout_relative_path", "early_return",
                 "swallowing_except", "unguarded_parametrize")
RUNTIME_CHECKS = ("zero_collected", "skipped_or_deselected")
DEFAULT_PYTEST = "uv run --frozen pytest"
PROBE = "r5_round0_probe"
OK_EXITS = (0, 1, 5)  # passed, tests failed, none collected


class CannotRun(Exception):
    """A check could not run; it is reported, never passed."""


# ------------------------------------------------------------------- git


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), "-c", "core.quotePath=false", *args],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise CannotRun(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout


def _commit(repo: Path, rev: str) -> str:
    return _git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").strip()


def is_test_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def changed_test_files(repo: Path, base: str, head: str) -> list[str]:
    """Added, modified, renamed or copied test files in BASE..HEAD, at HEAD."""
    raw = _git(repo, "diff", "--name-status", "-z", "--find-renames", "--no-ext-diff", base, head)
    fields = raw.split("\0")
    out, i = [], 0
    while i < len(fields) and fields[i]:
        status = fields[i]
        if status[0] in "RC":
            path, i = fields[i + 2], i + 3
        else:
            path, i = fields[i + 1], i + 2
        if status[0] != "D" and is_test_file(path):
            out.append(path)
    return sorted(set(out))


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(repo: Path, base: str, head: str) -> dict[str, set[int]]:
    """HEAD-side lines added or modified per file; a pure deletion counts at
    the line it was deleted before (and the one after it)."""
    raw = _git(repo, "diff", "-U0", "--find-renames", "--no-color", "--no-ext-diff",
               "--src-prefix=a/", "--dst-prefix=b/", base, head)
    out: dict[str, set[int]] = {}
    current: set[int] | None = None
    for line in raw.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = out.setdefault(target[2:], set()) if target.startswith("b/") else None
            continue
        m = _HUNK.match(line)
        if m and current is not None:
            start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            if count == 0:
                current.update({start, start + 1})
            else:
                current.update(range(start, start + count))
    return out


# --------------------------------------------------------------- ast help


def _dotted(node: ast.AST | None) -> str | None:
    """``a.b.c`` for a Name/Attribute chain, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _ends(name: str | None, *tails: str) -> bool:
    return name is not None and any(name == t or name.endswith("." + t) for t in tails)


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _walk_scope(node: ast.AST) -> Iterator[ast.AST]:
    """Every node under ``node`` without entering a nested def, lambda or class."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        yield child
        if not isinstance(child, _SCOPES):
            stack.extend(ast.iter_child_nodes(child))


def _blocks(stmt: ast.stmt) -> list[list[ast.stmt]]:
    """The statement lists a compound module-scope statement runs at import."""
    out = []
    for field in ("body", "orelse", "finalbody"):
        value = getattr(stmt, field, None)
        if isinstance(value, list):
            out.append(value)
    for handler in getattr(stmt, "handlers", []) or []:
        out.append(handler.body)
    return out


def module_scope(tree: ast.Module) -> Iterator[ast.stmt]:
    """Statements executed at import: top level and nested compound bodies."""
    stack = list(reversed(tree.body))
    while stack:
        stmt = stack.pop()
        yield stmt
        if isinstance(stmt, (ast.If, ast.Try, ast.With, ast.For, ast.While)) or \
                type(stmt).__name__ == "TryStar":
            for block in reversed(_blocks(stmt)):
                stack.extend(reversed(block))


def _src(node: ast.AST) -> str:
    return ast.unparse(node)


def _hit(check: str, node: ast.AST, claim: str, evidence: str, fix: str) -> dict:
    start = getattr(node, "lineno", 1)
    return {"check": check, "start_line": start,
            "end_line": getattr(node, "end_lineno", None) or start,
            "claim": claim, "evidence": evidence, "fix": fix}


# ---------------------------------------------------------- static checks


def check_module_level_skip(tree: ast.Module) -> list[dict]:
    hits = []
    for stmt in module_scope(tree):
        targets: list[ast.AST] = []
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
        elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
            targets = [stmt.target]
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets) and stmt.value:
            for node in [stmt.value, *_walk_scope(stmt.value)]:
                if isinstance(node, ast.Attribute) and node.attr in ("skip", "skipif") \
                        and _ends(_dotted(node.value), "mark"):
                    hits.append(_hit("module_level_skip", stmt,
                                     f"pytestmark applies {node.attr} to the whole module",
                                     _src(stmt), "remove the module-level skip; make the "
                                     "precondition fail the module instead of skipping it"))
                    break
        if isinstance(stmt, ast.Raise) and stmt.exc is not None:
            exc = stmt.exc.func if isinstance(stmt.exc, ast.Call) else stmt.exc
            if _ends(_dotted(exc), "SkipTest", "skip.Exception"):
                hits.append(_hit("module_level_skip", stmt,
                                 "the module raises SkipTest at import", _src(stmt),
                                 "fail instead of skipping the module"))
        if isinstance(stmt, _SCOPES):
            roots = []  # a def or class body is not module scope
        elif isinstance(stmt, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
            # The bodies are yielded on their own; read only the header here.
            heads = [getattr(stmt, "test", None), getattr(stmt, "iter", None)]
            heads += [i.context_expr for i in getattr(stmt, "items", [])]
            roots = [h for h in heads if h is not None]
        else:
            roots = [stmt]
        for root in roots:
            for node in [root, *_walk_scope(root)]:
                if not isinstance(node, ast.Call):
                    continue
                name = _dotted(node.func)
                if _ends(name, "importorskip"):
                    hits.append(_hit("module_level_skip", node,
                                     "importorskip at module scope skips the whole module "
                                     "when the import fails", _src(node),
                                     "import the dependency plainly so a missing one fails"))
                elif _ends(name, "skip"):
                    flag = next((k.value for k in node.keywords
                                 if k.arg == "allow_module_level"), None)
                    if flag is not None and not (isinstance(flag, ast.Constant)
                                                 and flag.value is False):
                        hits.append(_hit("module_level_skip", node,
                                         "skip with allow_module_level skips the whole module",
                                         _src(node), "fail instead of skipping the module"))
    return hits


_TRANSPARENT = ("Path", "PurePath", "PosixPath", "PurePosixPath", "str", "fspath",
                "abspath", "realpath", "normpath")
_JOIN_CALLS = ("Path", "PurePath", "PosixPath", "PurePosixPath", "os.path.join", "path.join")
_UNKNOWN = 10 ** 6  # a parents index that is not a literal: cannot be shown inside


class _Paths:
    """Levels above the test file a __file__-anchored expression climbs."""

    def __init__(self, tree: ast.Module):
        self.bindings: dict[str, list[ast.AST]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                self.bindings.setdefault(node.targets[0].id, []).append(node.value)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) \
                    and isinstance(node.target, ast.Name):
                # Annotated, augmented or walrus binding: counted, so a name
                # bound twice is never followed.
                self.bindings.setdefault(node.target.id, []).append(
                    node.value if node.value is not None else node)
        self._visiting: set[str] = set()

    def once(self, name: str) -> ast.AST | None:
        values = self.bindings.get(name, [])
        return values[0] if len(values) == 1 else None

    @staticmethod
    def _segments(state: tuple[int, int], args: list[ast.AST]) -> tuple[int, int]:
        cur, top = state
        for arg in args:
            parts = arg.value.split("/") if isinstance(arg, ast.Constant) \
                and isinstance(arg.value, str) else ["<segment>"]
            for part in parts:
                if part in ("", "."):
                    continue
                if part == "..":
                    cur += 1
                    top = max(top, cur)
                else:
                    cur -= 1
        return cur, top

    @staticmethod
    def _is_method(node: ast.Call) -> bool:
        """``x.resolve()`` rather than ``os.path.dirname(x)`` or ``pathlib.Path(x)``."""
        return isinstance(node.func, ast.Attribute) and not _ends(
            _dotted(node.func), "path.join", "path.dirname", *_TRANSPARENT)

    def base(self, node: ast.AST) -> ast.AST | None:
        """The anchored expression ``node`` climbs from, if any."""
        if isinstance(node, ast.Call):
            if self._is_method(node):
                return node.func.value
            return node.args[0] if node.args else None
        if isinstance(node, ast.Attribute):
            return node.value
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            return node.value.value
        if isinstance(node, ast.BinOp):
            return node.left
        return None

    def levels(self, node: ast.AST) -> tuple[int, int] | None:
        """(levels above the file now, most levels above it reached), or None."""
        if isinstance(node, ast.Name):
            if node.id == "__file__":
                return 0, 0
            value = self.once(node.id)
            if value is None or node.id in self._visiting:
                return None
            self._visiting.add(node.id)
            try:
                return self.levels(value)
            finally:
                self._visiting.discard(node.id)
        if isinstance(node, ast.Call):
            name = _dotted(node.func) or ""
            if self._is_method(node):
                state = self.levels(node.func.value)
                if state is None:
                    return None
                if node.func.attr in ("resolve", "absolute", "expanduser"):
                    return state
                if node.func.attr == "joinpath":
                    return self._segments(state, node.args)
                return None
            if not node.args:
                return None
            state = self.levels(node.args[0])
            if state is None:
                return None
            if _ends(name, "dirname"):
                return state[0] + 1, max(state[1], state[0] + 1)
            if _ends(name, *_JOIN_CALLS):
                return self._segments(state, node.args[1:])
            if _ends(name, *_TRANSPARENT):
                return state
            return None
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            state = self.levels(node.value)
            if state is None:
                return None
            return state[0] + 1, max(state[1], state[0] + 1)
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) \
                and node.value.attr == "parents":
            state = self.levels(node.value.value)
            if state is None:
                return None
            index = node.slice
            up = index.value + 1 if isinstance(index, ast.Constant) and isinstance(
                index.value, int) and not isinstance(index.value, bool) and index.value >= 0 \
                else _UNKNOWN
            return state[0] + up, max(state[1], state[0] + up)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            state = self.levels(node.left)
            if state is None:
                return None
            return self._segments(state, [node.right])
        return None


def check_layout_relative_path(tree: ast.Module, path: str) -> list[dict]:
    depth = len(PurePosixPath(path).parts)
    paths = _Paths(tree)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            continue  # a use of an escaped name; reported where it escaped
        state = paths.levels(node)
        if state is None or state[1] <= depth:
            continue
        inner = paths.base(node)
        before = paths.levels(inner) if inner is not None else None
        if before is not None and before[1] > depth:
            continue  # the escape happened inside this expression
        how = "a non-literal parents index" if state[1] >= _UNKNOWN else \
            f"{state[1]} levels above the file, {state[1] - depth} above the repository root"
        hits.append(_hit("layout_relative_path", node,
                         f"a path anchored on __file__ climbs out of the repository: {_src(node)}",
                         f"{path} is {depth} levels below the root; {_src(node)} reaches {how}",
                         "read the file from inside the repository, or take its location "
                         "from configuration and fail when it is missing"))
    return hits


def test_functions(tree: ast.Module) -> list[tuple[str | None, ast.AST]]:
    """(class name or None, def) for pytest's default test functions."""
    out: list[tuple[str | None, ast.AST]] = []
    for stmt in module_scope(tree):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name.startswith("test"):
            out.append((None, stmt))
        elif isinstance(stmt, ast.ClassDef) and stmt.name.startswith("Test"):
            for item in stmt.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and item.name.startswith("test"):
                    out.append((stmt.name, item))
    return out


def _qual(cls: str | None, fn: ast.AST) -> str:
    return f"{cls}::{fn.name}" if cls else fn.name


def check_early_return(tree: ast.Module) -> list[dict]:
    hits = []
    for cls, fn in test_functions(tree):
        last = fn.body[-1]
        for node in _walk_scope(fn):
            if not isinstance(node, ast.Return):
                continue
            if node is last and node.value is None:
                continue  # a trailing bare return ends nothing early
            hits.append(_hit("early_return", node,
                             f"test {_qual(cls, fn)} returns early, so the assertions after "
                             "the return can be skipped while the test passes",
                             f"{_src(node)} in def {fn.name} (line {fn.lineno})",
                             "assert or fail instead of returning"))
    return hits


def _broad(expr: ast.AST | None) -> bool:
    if expr is None:
        return True
    if isinstance(expr, ast.Tuple):
        return any(_broad(e) for e in expr.elts)
    return _ends(_dotted(expr), "Exception", "BaseException")


def _reraises(handler: ast.ExceptHandler) -> bool:
    for stmt in handler.body:
        for node in [stmt, *_walk_scope(stmt)]:
            if isinstance(node, ast.Raise):
                return True
            if isinstance(node, ast.Call) and _ends(_dotted(node.func), "fail"):
                return True
    return False


def check_swallowing_except(tree: ast.Module) -> list[dict]:
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _broad(node.type) and not _reraises(node):
            what = "a bare except" if node.type is None else f"except {_src(node.type)}"
            end = node.body[-1]
            hit = _hit("swallowing_except", node,
                       f"{what} swallows every error without re-raising",
                       "\n".join(_src(s) for s in node.body)[:400] or "pass",
                       "catch the specific exception, or re-raise")
            hit["end_line"] = getattr(end, "end_lineno", hit["end_line"])
            hits.append(hit)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call) and _ends(_dotted(ctx.func), "suppress") \
                        and any(_broad(a) for a in ctx.args):
                    hits.append(_hit("swallowing_except", ctx,
                                     f"{_src(ctx)} swallows every error", _src(ctx),
                                     "suppress the specific exception, or none"))
    return hits


def _literal_display(node: ast.AST) -> bool | None:
    """True for a non-empty literal list/tuple/set, False for an empty one,
    None for anything computed (including one with a * element)."""
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        if any(isinstance(e, ast.Starred) for e in node.elts):
            return None
        return bool(node.elts)
    return None


def _sources(node: ast.AST, paths: _Paths) -> list[ast.AST]:
    out = [node]
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        out.append(node.generators[0].iter)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        out += [e.value for e in node.elts if isinstance(e, ast.Starred)]
    if isinstance(node, ast.Name):
        value = paths.once(node.id)
        if value is not None:
            out += _sources(value, paths)
    return out


def _guards(tree: ast.Module) -> list[ast.AST]:
    """The expressions module-scope asserts prove non-empty."""
    out = []
    for stmt in module_scope(tree):
        if not isinstance(stmt, ast.Assert):
            continue
        test = stmt.test
        if isinstance(test, ast.Call) and _dotted(test.func) in ("bool", "len") \
                and len(test.args) == 1:
            out.append(test.args[0])
        elif isinstance(test, ast.Compare) and len(test.ops) == 1:
            left, op, right = test.left, test.ops[0], test.comparators[0]
            if isinstance(left, ast.Constant):  # c < len(S) -> len(S) > c
                flip = {ast.Lt: ast.Gt, ast.LtE: ast.GtE, ast.Gt: ast.Lt, ast.GtE: ast.LtE,
                        ast.Eq: ast.Eq, ast.NotEq: ast.NotEq}
                if type(op) not in flip:
                    continue
                left, op, right = right, flip[type(op)](), left
            if not (isinstance(left, ast.Call) and _dotted(left.func) == "len"
                    and len(left.args) == 1 and isinstance(right, ast.Constant)
                    and isinstance(right.value, int) and not isinstance(right.value, bool)):
                continue
            c = right.value
            if (isinstance(op, ast.Gt) and c >= 0) or (isinstance(op, (ast.GtE, ast.Eq)) and c >= 1) \
                    or (isinstance(op, ast.NotEq) and c == 0):
                out.append(left.args[0])
        else:
            out.append(test)
    return out


def check_unguarded_parametrize(tree: ast.Module) -> list[dict]:
    paths = _Paths(tree)
    guarded = {ast.dump(g) for g in _guards(tree)}
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "parametrize" and _ends(_dotted(node.func.value), "mark")):
            continue
        argvalues = node.args[1] if len(node.args) >= 2 else next(
            (k.value for k in node.keywords if k.arg == "argvalues"), None)
        if argvalues is None:
            continue
        shape = _literal_display(argvalues)
        if shape is None and isinstance(argvalues, ast.Name):
            value = paths.once(argvalues.id)
            shape = _literal_display(value) if value is not None else None
        if shape is True:
            continue
        if shape is False:
            claim = f"parametrize over an empty list: {_src(argvalues)}"
            evidence = f"{_src(node)}: no case, so pytest collects one skipped item"
        else:
            sources = _sources(argvalues, paths)
            if any(ast.dump(s) in guarded for s in sources):
                continue
            claim = (f"parametrize over {_src(argvalues)}, computed at collection with no "
                     "non-zero minimum")
            evidence = (f"{_src(node)}: no module-scope assert that any of "
                        f"{', '.join(sorted({_src(s) for s in sources}))} is non-empty")
        hits.append(_hit("unguarded_parametrize", node, claim, evidence,
                         f"assert {_src(argvalues)} is non-empty at module scope, or list "
                         "the cases literally"))
    return hits


def static_hits(path: str, source: str) -> list[dict]:
    """Every static check's hits on one test file's source."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        raise CannotRun(f"{path} does not parse under Python "
                        f"{sys.version_info[0]}.{sys.version_info[1]}: {exc}") from None
    hits = []
    hits += check_module_level_skip(tree)
    hits += check_layout_relative_path(tree, path)
    hits += check_early_return(tree)
    hits += check_swallowing_except(tree)
    hits += check_unguarded_parametrize(tree)
    scopes = _scopes(tree)
    seen: dict[str, int] = {}
    for h in hits:
        h["path"] = path
        # The claim names where the hit is, so two hits in one file keep
        # distinct fingerprints (lens|path|claim, line numbers stripped).
        owner = next((name for first, last, name in scopes
                      if first <= h["start_line"] <= last), None)
        h["claim"] += f" (in {owner})" if owner else " (at module scope)"
        seen[h["claim"]] = seen.get(h["claim"], 0) + 1
        if seen[h["claim"]] > 1:
            h["claim"] += f" (occurrence {seen[h['claim']]})"
    return hits


def _scopes(tree: ast.Module) -> list[tuple[int, int, str]]:
    """(first line incl. decorators, last line, qualified name) of every def
    and class, innermost first."""
    out = []

    def visit(node: ast.AST, prefix: str, depth: int) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                first = min([child.lineno] + [d.lineno for d in child.decorator_list])
                name = f"{prefix}{child.name}"
                out.append((depth, first, child.end_lineno, name))
                visit(child, name + ".", depth + 1)
            else:
                visit(child, prefix, depth)

    visit(tree, "", 0)
    out.sort(key=lambda t: -t[0])
    return [(first, last, name) for _, first, last, name in out]


# --------------------------------------------------------- runtime checks


PROBE_SOURCE = '''\
"""Round 0 probe, written by r5_provenance_checks.py: collection and outcomes."""
import json
import os

_DATA = {"collected": [], "deselected": [], "collect_errors": [], "collect_skips": [],
         "outcomes": {}}


def _text(longrepr):
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2])
    return str(longrepr)[-2000:]


def pytest_deselected(items):
    _DATA["deselected"].extend(item.nodeid for item in items)


def pytest_collection_finish(session):
    _DATA["collected"] = [item.nodeid for item in session.items]


def pytest_collectreport(report):
    if report.failed:
        _DATA["collect_errors"].append({"nodeid": report.nodeid, "text": _text(report.longrepr)})
    elif report.skipped:
        _DATA["collect_skips"].append({"nodeid": report.nodeid, "text": _text(report.longrepr)})


def pytest_runtest_logreport(report):
    entry = _DATA["outcomes"].setdefault(report.nodeid, {"outcome": "passed", "reason": None})
    if report.skipped and not hasattr(report, "wasxfail"):
        entry["outcome"], entry["reason"] = "skipped", _text(report.longrepr)
    elif report.skipped and entry["outcome"] == "passed":
        entry["outcome"] = "xfailed"
    elif report.failed and entry["outcome"] != "skipped":
        entry["outcome"] = "failed"


def pytest_sessionfinish(session, exitstatus):
    _DATA["exitstatus"] = int(exitstatus)
    with open(os.environ["R5_ROUND0_OUT"], "w", encoding="utf-8") as handle:
        json.dump(_DATA, handle)
'''


def _tail(text: str, lines: int = 40) -> str:
    return "\n".join(text.splitlines()[-lines:])


def run_module(repo: Path, prefix: list[str], module: str, probe_dir: str,
               timeout: float) -> tuple[dict, str]:
    """One pytest run over one module: the probe's data and the output tail."""
    out_file = os.path.join(probe_dir, "out.json")
    if os.path.exists(out_file):
        os.unlink(out_file)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (probe_dir, env.get("PYTHONPATH")) if p)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["R5_ROUND0_OUT"] = out_file
    command = [*prefix, "-rs", "-p", "no:cacheprovider", "-p", PROBE, module]
    try:
        proc = subprocess.run(command, cwd=str(repo), env=env, capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CannotRun(f"{shlex.join(command)}: {exc}") from None
    tail = _tail(proc.stdout + proc.stderr)
    data = None
    if os.path.exists(out_file):
        with open(out_file, encoding="utf-8") as handle:
            data = json.load(handle)
    if data is not None and data["collect_errors"]:
        raise CannotRun(f"{module} has collection errors:\n"
                        + "\n".join(e["text"] for e in data["collect_errors"])[-2000:])
    if proc.returncode not in OK_EXITS or data is None:
        raise CannotRun(f"{shlex.join(command)} exited {proc.returncode} with no usable "
                        f"result:\n{tail}")
    return data, tail


def _meaningful(source_lines: list[str], line: int) -> bool:
    if not 1 <= line <= len(source_lines):
        return False
    text = source_lines[line - 1].strip()
    return bool(text) and not text.startswith("#")


def changed_tests(tree: ast.Module, source: str, lines: set[int] | None) -> set[tuple]:
    """(class or None, name) of each test a changed line touches; lines None
    means the file is new."""
    tests = test_functions(tree)
    keys = {(cls, fn.name) for cls, fn in tests}
    if lines is None:
        return keys
    src = source.splitlines()

    def span(node: ast.AST) -> range:
        first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        return range(first, node.end_lineno + 1)

    out: set[tuple] = set()
    for line in (n for n in lines if _meaningful(src, n)):
        owner = next((s for s in tree.body if line in span(s)), None)
        if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)) and (None, owner.name) in keys:
            out.add((None, owner.name))
        elif isinstance(owner, ast.ClassDef):
            method = next((m for m in owner.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                           and line in span(m)), None)
            if method is not None and (owner.name, method.name) in keys:
                out.add((owner.name, method.name))
            else:
                # class-level code, or a helper or fixture method: every test of the class
                out |= {k for k in keys if k[0] == owner.name}
        else:
            return keys  # module-scope code (imports, helpers, fixtures): all of them
    return out


def _key_of(nodeid: str) -> tuple:
    # Strip the parametrise id before splitting: an id may itself contain
    # "::" (test_ids[a::b]), which would otherwise read as a class boundary.
    _, _, rest = nodeid.partition("::")
    parts = rest.split("[", 1)[0].split("::") if rest else []
    if not parts:
        return (None, "")
    return (parts[-2] if len(parts) >= 2 else None, parts[-1])


def runtime_hits(repo: Path, prefix: list[str], module: str, tree: ast.Module, source: str,
                 lines: set[int] | None, probe_dir: str, timeout: float) -> tuple[list, list, dict]:
    data, tail = run_module(repo, prefix, module, probe_dir, timeout)
    zero, skipped = [], []
    n_lines = max(1, len(source.splitlines()))
    total = len(data["collected"]) + len(data["deselected"])
    detail = {"collected": len(data["collected"]), "deselected": len(data["deselected"]),
              "exitstatus": data.get("exitstatus")}
    if total == 0:
        why = "; ".join(s["text"] for s in data["collect_skips"]) or "no test item"
        zero.append({"check": "zero_collected", "path": module, "start_line": 1,
                     "end_line": n_lines,
                     "claim": "the changed test module collects zero tests",
                     "evidence": f"collected 0 items: {why}\n{tail}"[:2000],
                     "fix": "make the module collect its tests in this layout, or fail"})
        return zero, skipped, detail
    defs = {(cls, fn.name): fn for cls, fn in test_functions(tree)}
    by_test: dict[tuple, dict[str, list[str]]] = {}
    for nodeid in data["collected"] + data["deselected"]:
        by_test.setdefault(_key_of(nodeid), {"skipped": [], "deselected": []})
    for nodeid in data["deselected"]:
        by_test[_key_of(nodeid)]["deselected"].append(nodeid)
    for nodeid, entry in data["outcomes"].items():
        if entry["outcome"] == "skipped":
            by_test.setdefault(_key_of(nodeid), {"skipped": [], "deselected": []})[
                "skipped"].append(f"{nodeid}: {entry['reason']}")
    for key in sorted(changed_tests(tree, source, lines), key=lambda k: (k[0] or "", k[1])):
        fn = defs[key]
        name = f"{key[0]}::{key[1]}" if key[0] else key[1]
        base = {"check": "skipped_or_deselected", "path": module, "start_line": fn.lineno,
                "end_line": fn.end_lineno}
        seen = by_test.get(key)
        if seen is None:
            skipped.append({**base, "claim": f"changed test {name} collects no item",
                            "evidence": f"no collected or deselected node id names {name}\n{tail}"[:2000],
                            "fix": "make the test collect, or remove it"})
            continue
        if seen["skipped"]:
            skipped.append({**base, "claim": f"changed test {name} is SKIPPED when run",
                            "evidence": "\n".join(seen["skipped"])[:2000],
                            "fix": "make the test run here, or fail when its precondition is missing"})
        if seen["deselected"]:
            skipped.append({**base, "claim": f"changed test {name} is deselected",
                            "evidence": "deselected: " + ", ".join(seen["deselected"])[:2000],
                            "fix": "select the test in the gate's run, or remove the deselection"})
    return zero, skipped, detail


# -------------------------------------------------------------------- run


def to_finding(hit: dict, n: int) -> dict:
    raw = {"lens": LENS, "severity": SEVERITY, "path": hit["path"],
           "start_line": hit["start_line"], "end_line": hit["end_line"],
           "claim": hit["claim"], "evidence": hit["evidence"], "fix": hit["fix"],
           "verification_level": LEVEL, "resolves": None, "regression": False}
    finding = _finding(raw, LENS, n)
    finding["check"] = hit["check"]
    return finding


def check(repo: Path, base: str, head: str, static_only: bool, prefix: list[str],
          timeout: float) -> tuple[dict, int]:
    result: dict[str, Any] = {"base": None, "head": None, "static_only": static_only,
                              "test_files": [], "findings": [], "errors": [],
                              "checks": {name: {"ran": False, "hits": 0, "detail": {}}
                                         for name in STATIC_CHECKS + RUNTIME_CHECKS}}
    checks = result["checks"]
    try:
        result["base"], result["head"] = _commit(repo, base), _commit(repo, head)
        files = changed_test_files(repo, result["base"], result["head"])
        lines = changed_lines(repo, result["base"], result["head"])
        added = set(_git(repo, "diff", "--name-only", "--diff-filter=A", "-z",
                         result["base"], result["head"]).split("\0"))
    except CannotRun as exc:
        result["errors"].append(str(exc))
        for name in checks:
            checks[name]["detail"] = {"error": str(exc)}
        return result, 1
    result["test_files"] = files
    hits: list[dict] = []
    parsed: dict[str, tuple[ast.Module, str]] = {}
    static_errors = []
    for path in files:
        try:
            source = _git(repo, "cat-file", "blob", f"{result['head']}:{path}")
            hits += static_hits(path, source)
            parsed[path] = (ast.parse(source, filename=path), source)
        except CannotRun as exc:
            static_errors.append(str(exc))
    for name in STATIC_CHECKS:
        checks[name]["ran"] = not static_errors
        checks[name]["detail"] = {"files": len(files)}
        if static_errors:
            checks[name]["detail"]["error"] = static_errors
    result["errors"] += static_errors

    if static_only:
        for name in RUNTIME_CHECKS:
            checks[name]["detail"] = {"skipped": "--static-only"}
    else:
        try:
            current = _git(repo, "rev-parse", "HEAD").strip()
            if current != result["head"]:
                raise CannotRun(f"the checkout is at {current}, not --head {result['head']}")
            dirty = _git(repo, "status", "--porcelain", "--untracked-files=no").strip()
            if dirty:
                raise CannotRun(f"tracked files differ from HEAD:\n{dirty}")
            runtime_errors, per_module = [], {}
            with tempfile.TemporaryDirectory(prefix="r5-round0-") as probe_dir:
                Path(probe_dir, PROBE + ".py").write_text(PROBE_SOURCE, encoding="utf-8")
                for path in files:
                    if path not in parsed:
                        continue  # did not parse: already an error above
                    tree, source = parsed[path]
                    try:
                        zero, skipped, detail = runtime_hits(
                            repo, prefix, path, tree, source,
                            None if path in added else lines.get(path, set()),
                            probe_dir, timeout)
                    except CannotRun as exc:
                        runtime_errors.append(str(exc))
                        continue
                    per_module[path] = detail
                    hits += zero + skipped
            if _git(repo, "status", "--porcelain", "--untracked-files=no").strip():
                runtime_errors.append("the pytest runs changed tracked files in the checkout")
            for name in RUNTIME_CHECKS:
                checks[name]["ran"] = not runtime_errors and len(per_module) == len(parsed)
                checks[name]["detail"] = {"modules": per_module, "command": shlex.join(prefix)}
                if runtime_errors:
                    checks[name]["detail"]["error"] = runtime_errors
            result["errors"] += runtime_errors
        except CannotRun as exc:
            result["errors"].append(str(exc))
            for name in RUNTIME_CHECKS:
                checks[name]["detail"] = {"error": str(exc)}

    try:
        result["findings"] = [to_finding(h, n) for n, h in enumerate(hits, 1)]
    except ReportError as exc:  # a hit that is not a valid finding is a bug here
        result["errors"].append(f"internal: {exc}")
        return result, 1
    for f in result["findings"]:
        checks[f["check"]]["hits"] += 1
    if result["errors"] or not all(checks[n]["ran"] for n in STATIC_CHECKS) or (
            not static_only and not all(checks[n]["ran"] for n in RUNTIME_CHECKS)):
        return result, 1
    return result, 2 if result["findings"] else 0


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(prog="r5_provenance_checks.py")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("check", help="run round 0's provenance checks on BASE..HEAD")
    p.add_argument("--repo", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--static-only", action="store_true")
    p.add_argument("--pytest", default=DEFAULT_PYTEST)
    p.add_argument("--timeout", type=float, default=1800.0)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 1
    if args.command != "check":
        parser.print_usage(sys.stderr)
        return 1
    prefix = shlex.split(args.pytest)
    if not prefix:
        print("r5_provenance_checks: --pytest is empty", file=sys.stderr)
        return 1
    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"r5_provenance_checks: {repo} is not a directory", file=sys.stderr)
        return 1
    result, code = check(repo, args.base, args.head, args.static_only, prefix, args.timeout)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
