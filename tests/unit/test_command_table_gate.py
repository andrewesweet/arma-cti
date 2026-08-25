"""The ADR-0013 command-table route is mechanically confined and resolvable (#544)."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from typing import TYPE_CHECKING

from conftest import REPO, load_tool

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    import pytest


gated_paths = load_tool("gated_paths")
check_command_table = load_tool("check_command_table")


def approve_agents(repo: Path, store: Path) -> None:
    """Write a direct approval for the fixture's current AGENTS.md change."""
    content_id = gated_paths.content_id_of(repo, "AGENTS.md")
    _approval, _target, added = gated_paths.record_approval(
        repo,
        store,
        issue=544,
        path="AGENTS.md",
        expected_content_id=content_id,
        approved_at="2026-08-24T06:00:00+00:00",
        approved_by="andre",
        environ={},
    )
    assert added


def git(repo: Path, *args: str) -> None:
    """Run fixture Git and expose any setup failure."""
    completed = subprocess.run(  # noqa: S603 — fixture Git argv only
        ["git", *args],  # noqa: S607 — Git resolves from the test toolchain
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def repository(root: Path, name: str = "issue-544") -> Path:
    """Create a candidate tree with one command row and one just recipe."""
    repo = root / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", "work")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "test")
    (repo / "AGENTS.md").write_text(
        "# Instructions\n\n"
        "## Command surface\n\n"
        "| Command | Purpose | Requires Arma | Run when |\n"
        "|---|---|---|---|\n"
        "| `just old-recipe` | Old purpose | No | Always |\n\n"
        "Other prose.\n",
        encoding="utf-8",
    )
    (repo / "justfile").write_text("old-recipe:\n    @true\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    return repo


def adjacent_repository(root: Path) -> Path:
    """Create a fixture whose command table has two adjacent data rows."""
    repo = repository(root)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace(
            "| `just old-recipe` | Old purpose | No | Always |\n",
            "| `just old-recipe` | Old purpose | No | Always |\n"
            "| `just second-old` | Second purpose | No | Always |\n",
        ),
        encoding="utf-8",
    )
    (repo / "justfile").write_text(
        "old-recipe:\n    @true\n\nsecond-old:\n    @true\n",
        encoding="utf-8",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "add adjacent row")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def delegated_record(repo: Path) -> None:
    """Add the ADR-0013 record that supplies the standing route."""
    adr = repo / "docs" / "adr" / "0099-command-table-rule.md"
    adr.parent.mkdir(parents=True)
    adr.write_text(
        "# Command-table rule\n\n"
        "Delegated-decision: yes\n"
        "Date: 2026-08-24\n"
        "Supersedes: none\n"
        "Reviewed-by-human: pending\n\n"
        "## What would overturn this\n\n"
        "A failed command-table check.\n",
        encoding="utf-8",
    )


def test_a_delegated_row_change_passes_when_the_candidate_recipe_resolves(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace("`just old-recipe`", "`just new-recipe`"),
        encoding="utf-8",
    )
    (repo / "justfile").write_text(
        "old-recipe:\n    @true\n\nnew-recipe:\n    @true\n",
        encoding="utf-8",
    )
    delegated_record(repo)

    report = gated_paths.check(repo, tmp_path / "approvals", issue=544)

    assert report.exit_code == 0
    assert "authorization=command_table" in report.lines[0]
    assert any(line.startswith("command_table=ok path=AGENTS.md") for line in report.lines)


def test_adjacent_delegated_rows_are_one_confined_table_change(tmp_path: Path) -> None:
    repo = adjacent_repository(tmp_path)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace("old-recipe", "new-recipe")
        .replace("second-old", "second-new"),
        encoding="utf-8",
    )
    (repo / "justfile").write_text(
        "old-recipe:\n    @true\n\nsecond-old:\n    @true\n\n"
        "new-recipe:\n    @true\n\nsecond-new:\n    @true\n",
        encoding="utf-8",
    )
    delegated_record(repo)

    report = gated_paths.check(repo, tmp_path / "approvals", issue=544)

    assert report.exit_code == 0
    assert "command_table=ok path=AGENTS.md rows=2 recipes=new-recipe,second-new" in report.lines


def test_an_approval_stands_down_the_command_table_leg_with_a_delegated_adr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CTI_DISPATCH_ISSUE", raising=False)
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace("`just old-recipe`", "`just new-recipe`"),
        encoding="utf-8",
    )
    (repo / "justfile").write_text(
        "old-recipe:\n    @true\n\nnew-recipe:\n    @true\n", encoding="utf-8"
    )
    delegated_record(repo)
    store = tmp_path / "approvals"
    approve_agents(repo, store)
    monkeypatch.setattr(sys.modules["gated_paths"], "APPROVAL_ROOT", store)

    assert check_command_table.main(["--root", str(repo)]) == 0

    assert capsys.readouterr().out.splitlines() == ["command_table=not_applicable"]


def test_deleting_a_command_row_does_not_claim_recipe_resolution(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    (repo / "AGENTS.md").write_text(
        agents.replace("| `just old-recipe` | Old purpose | No | Always |\n", ""),
        encoding="utf-8",
    )
    delegated_record(repo)

    report = gated_paths.check(repo, tmp_path / "approvals", issue=544)

    assert report.exit_code == 0
    verified = next(line for line in report.lines if line.startswith("verified="))
    assert verified == "verified=path_scan,command_table_confinement,delegated_marker"
    assert "recipe_resolution" not in verified


def test_a_delegated_row_change_with_prose_outside_the_table_is_refused(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    current = (repo / "AGENTS.md").read_text(encoding="utf-8")
    (repo / "AGENTS.md").write_text(
        current.replace("`just old-recipe`", "`just new-recipe`").replace(
            "Other prose.", "Changed prose."
        ),
        encoding="utf-8",
    )
    delegated_record(repo)
    content_id = gated_paths.content_id_of(repo, "AGENTS.md")

    report = gated_paths.check(repo, tmp_path / "approvals", issue=544)

    assert report.exit_code == 1
    assert "refusal=command_table_escape" in report.lines
    assert any(line.startswith("escaped=") for line in report.lines)
    action = next(line for line in report.lines if line.startswith("action="))
    assert "Keep the delegated AGENTS.md change to command-table data rows only." in action
    command = f"just gated-paths approve --issue 544 --path AGENTS.md --content-id {content_id}"
    assert command in action


def test_a_delegated_row_change_with_an_unknown_recipe_is_refused(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace("`just old-recipe`", "`just missing-recipe`"),
        encoding="utf-8",
    )
    delegated_record(repo)
    content_id = gated_paths.content_id_of(repo, "AGENTS.md")

    report = gated_paths.check(repo, tmp_path / "approvals", issue=544)

    assert report.exit_code == 1
    assert "refusal=command_table_recipe_unresolved" in report.lines
    assert "recipe=missing-recipe" in report.lines
    action = next(line for line in report.lines if line.startswith("action="))
    assert "Make the candidate justfile define the recipe named by the row." in action
    command = f"just gated-paths approve --issue 544 --path AGENTS.md --content-id {content_id}"
    assert command in action


def test_an_unreadable_delegated_table_still_names_the_direct_approval(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace(
            "| `just old-recipe` | Old purpose | No | Always |\n",
            "| `just old-recipe` | Old purpose | No |\n",
        ),
        encoding="utf-8",
    )
    delegated_record(repo)
    content_id = gated_paths.content_id_of(repo, "AGENTS.md")

    report = gated_paths.check(repo, tmp_path / "approvals", issue=544)

    assert report.exit_code == 1
    assert "refusal=command_table_unreadable" in report.lines
    action = next(line for line in report.lines if line.startswith("action="))
    command = f"just gated-paths approve --issue 544 --path AGENTS.md --content-id {content_id}"
    assert command in action


def test_the_standalone_command_names_the_direct_approval_on_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """#583: the documented standalone path must not dead-end either."""
    monkeypatch.delenv("CTI_DISPATCH_ISSUE", raising=False)
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace("`just old-recipe`", "`just missing-recipe`"),
        encoding="utf-8",
    )
    delegated_record(repo)
    content_id = gated_paths.content_id_of(repo, "AGENTS.md")

    assert check_command_table.main(["--root", str(repo)]) == 1

    stderr = capsys.readouterr().err
    assert "refusal=command_table_recipe_unresolved" in stderr
    action = next(line for line in stderr.splitlines() if line.startswith("action="))
    command = f"just gated-paths approve --issue 544 --path AGENTS.md --content-id {content_id}"
    assert command in action


def test_an_unreadable_repository_names_the_repair_not_the_approval(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """#583 round 3: the CLI's unreadable-repository refusal printed no exit at all."""
    root = tmp_path / "not-a-repo"
    root.mkdir()

    assert check_command_table.main(["--root", str(root)]) == 1

    stderr = capsys.readouterr().err
    assert "refusal=command_table_unreadable" in stderr
    action = next(line for line in stderr.splitlines() if line.startswith("action="))
    assert "Restore a readable" in action
    # An unreadable repository is a repair problem, not an approval one: the
    # approval command needs a content_id no unreadable tree can produce.
    assert "gated-paths approve" not in action


def test_an_issueless_checkout_says_the_human_supplies_the_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """#583 round 4: `--issue <issue>` was a usage error, not a remedy."""
    monkeypatch.delenv("CTI_DISPATCH_ISSUE", raising=False)
    repo = repository(tmp_path, name="main-checkout")
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace("`just old-recipe`", "`just missing-recipe`"),
        encoding="utf-8",
    )
    delegated_record(repo)
    content_id = gated_paths.content_id_of(repo, "AGENTS.md")

    assert check_command_table.main(["--root", str(repo)]) == 1

    stderr = capsys.readouterr().err
    assert "refusal=command_table_recipe_unresolved" in stderr
    action = next(line for line in stderr.splitlines() if line.startswith("action="))
    assert "<issue>" not in action
    assert f"--issue N --path AGENTS.md --content-id {content_id}" in action
    assert "the issue this change lands under" in action


def test_a_conflicting_issue_environment_refuses_before_the_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """#583 round 4: a worktree/dispatch disagreement was silently discarded."""
    monkeypatch.setenv("CTI_DISPATCH_ISSUE", "999")
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace("`just old-recipe`", "`just missing-recipe`"),
        encoding="utf-8",
    )
    delegated_record(repo)

    assert check_command_table.main(["--root", str(repo)]) == 1

    stderr = capsys.readouterr().err
    assert "refusal=approval_issue_unknown" in stderr
    assert "worktree_issue=544 dispatch_issue=999 disagree" in stderr
    action = next(line for line in stderr.splitlines() if line.startswith("action="))
    assert "unmodified dispatch environment" in action


def _literal_text(node: ast.AST) -> str:
    """Concatenate a statement's string literals with no joiner.

    The empty joiner is deliberate (#583 round 4): ``"refusal" + "="`` must
    read as ``refusal=``. A marker with no literal text in the statement —
    one threaded through a variable — contributes nothing here.
    """
    return "".join(
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    )


def _is_exit_call(statement: ast.stmt) -> bool:
    """Whether a statement is a bare ``sys.exit(...)`` or ``exit(...)`` call."""
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return False
    func = statement.value.func
    if isinstance(func, ast.Attribute):
        return func.attr == "exit" and isinstance(func.value, ast.Name) and func.value.id == "sys"
    return isinstance(func, ast.Name) and func.id == "exit"


def _statement_blocks(tree: ast.AST) -> Iterator[list[ast.stmt]]:
    """Yield every statement list in the module, nested blocks included."""
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                yield block


def _refusal_audit(tree: ast.AST) -> tuple[list[int], list[int]]:
    """Return literal refusal-emission lines, and those with no paired remedy.

    A statement whose string literals spell ``refusal=`` must be joined by one
    spelling ``action=`` before its statement list meets a ``return``, ``raise``
    or ``sys.exit``/``exit`` call.
    """
    hits: list[int] = []
    missing: list[int] = []
    for block in _statement_blocks(tree):
        for index, statement in enumerate(block):
            if "refusal=" not in _literal_text(statement):
                continue
            hits.append(statement.lineno)
            window: list[ast.stmt] = []
            for later in block[index:]:
                window.append(later)
                if isinstance(later, (ast.Return, ast.Raise)) or _is_exit_call(later):
                    break
            if not any("action=" in _literal_text(later) for later in window):
                missing.append(statement.lineno)
    return hits, missing


def test_every_refusal_emission_pairs_a_remedy_in_source() -> None:
    """Pair every literal refusal emission with a remedy before an exit.

    #575 and both #583 rounds each hand-enumerated the refusal exits and each
    missed one, so `_refusal_audit` walks the source instead. Its scope, stated
    plainly (#583 round 4): it reads each statement's own string literals,
    concatenated — so it sees ``"refusal" + "="`` but not a marker that reaches
    the emission only through a variable — and its window is the linear
    statement list, not control flow, so a remedy skipped by a ``continue`` or
    an early branch still counts. Every current emission is a literal marker
    inside a self-pairing helper (`_refuse`/`_refused`), which is what keeps
    those blind spots empty; a runtime-composed marker would escape this test.
    """
    for name in ("check_command_table", "gated_paths"):
        tree = ast.parse((REPO / "tools" / f"{name}.py").read_text(encoding="utf-8"))
        hits, missing = _refusal_audit(tree)
        assert hits, f"tools/{name}.py: scan found no refusal emission"
        assert not missing, f"tools/{name}.py:{missing} emit refusal= with no action= remedy"


def test_the_scan_sees_a_concatenation_composed_marker() -> None:
    """#583 round 4: ``"refusal" + "="`` dodged the space-joined literal scan."""
    tree = ast.parse('def emit():\n    print("refusal" + "=x")\n    return 1\n')
    hits, missing = _refusal_audit(tree)
    # The enclosing def registers too — ast.walk reads its whole body — so the
    # claims are membership, not equality.
    assert 2 in hits
    assert 2 in missing


def test_the_scan_treats_sys_exit_as_an_exit_boundary() -> None:
    """#583 round 4: a remedy printed after ``sys.exit()`` is unreachable."""
    source = (
        'import sys\ndef emit():\n    print("refusal=x")\n    sys.exit(1)\n    print("action=y")\n'
    )
    hits, missing = _refusal_audit(ast.parse(source))
    assert 3 in hits
    assert 3 in missing


def test_a_variable_threaded_marker_stays_outside_the_scan() -> None:
    """The narrowed claim, pinned: a marker with no literal text is invisible.

    Seeing this emission needs dataflow analysis — a second parser with its own
    blind spots. Delete this pin only alongside such a detector.
    """
    source = 'def emit(kind):\n    print(kind + "=x")\n    return 1\n'
    hits, _missing = _refusal_audit(ast.parse(source))
    assert not hits


def test_just_check_runs_the_command_table_leg() -> None:
    completed = subprocess.run(
        ["just", "--dump", "--dump-format", "json"],  # noqa: S607 — required just binary
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    recipes = json.loads(completed.stdout)["recipes"]
    check_body = "\n".join(line[0] for line in recipes["check"]["body"])
    command_table_body = "\n".join(line[0] for line in recipes["check-command-table"]["body"])

    assert "--leg check-command-table" in check_body
    assert "tools/check_command_table.py" in command_table_body


def test_check_row_tracks_every_recipe_leg_in_order() -> None:
    """#545: derive the documented leg list from the parsed `just check` recipe."""
    completed = subprocess.run(
        ["just", "--dump", "--dump-format", "json"],  # noqa: S607 — required just binary
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    recipes = json.loads(completed.stdout)["recipes"]
    body = "\n".join(line[0] for line in recipes["check"]["body"])
    legs = tuple(re.findall(r"--leg ([a-z][a-z0-9-]*)", body))
    row = next(
        line
        for line in (REPO / "AGENTS.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("| `just check` |")
    )
    documented = tuple(re.findall(r"`(check-[a-z0-9-]+)`", row))

    assert legs
    assert documented == legs


def test_the_named_leg_checks_the_delegated_candidate_route(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace("`just old-recipe`", "`just new-recipe`"),
        encoding="utf-8",
    )
    (repo / "justfile").write_text(
        "old-recipe:\n    @true\n\nnew-recipe:\n    @true\n",
        encoding="utf-8",
    )
    delegated_record(repo)

    assert check_command_table.main(["--root", str(repo)]) == 0
