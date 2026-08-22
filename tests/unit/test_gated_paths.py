"""Lane-neutral gated-path approval records (#500).

The incident shape is an ordinary worktree edit with no Claude Code hook in the
loop.  These tests start there, then pin the record's exact-content binding, its
external store, the dispatched-session refusal, ADR-0013's surviving route and
the limit statement every verdict prints.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

gated_paths = load_tool("gated_paths")

ISSUE: Final = 500
STAMP: Final = "2026-08-22T06:00:00+00:00"


def git(repo: Path, *args: str) -> str:
    """Run fixture Git, with any failure visible in the assertion."""
    completed = subprocess.run(  # noqa: S603 — fixture Git argv only
        ["git", *args],  # noqa: S607 — Git resolves from the test toolchain
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def repository(root: Path) -> Path:
    """Create an issue-shaped worktree with a local ``origin/main`` baseline."""
    repo = root / f"issue-{ISSUE}"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "work")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "test")
    (repo / "AGENTS.md").write_text("base instructions\n", encoding="utf-8")
    (repo / "ordinary.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def approve(repo: Path, store: Path, path: str = "AGENTS.md") -> str:
    """Write the exact direct-approval record through the production writer."""
    content_id = gated_paths.content_id_of(repo, path)
    approval, _target, added = gated_paths.record_approval(
        repo,
        store,
        issue=ISSUE,
        path=path,
        expected_content_id=content_id,
        approved_at=STAMP,
        approved_by="andre",
        environ={},
    )
    assert added
    assert approval.content_id == content_id
    return content_id


def test_a_codex_shaped_agents_edit_is_caught_without_running_the_hook(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text("unauthorised codex edit\n", encoding="utf-8")

    report = gated_paths.check(repo, tmp_path / "approvals", issue=ISSUE)

    assert report.exit_code == 1
    assert "refusal=approval_missing" in report.lines
    assert "path=AGENTS.md" in report.lines


def test_a_committed_gated_edit_is_still_caught_at_the_landing_boundary(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text("committed codex edit\n", encoding="utf-8")
    git(repo, "add", "AGENTS.md")
    git(repo, "commit", "-q", "-m", "edit instructions")

    report = gated_paths.check(repo, tmp_path / "approvals", issue=ISSUE)

    assert report.exit_code == 1
    assert "refusal=approval_missing" in report.lines


def test_an_exact_tool_owned_approval_clears_the_gate(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    store = tmp_path / "approvals"
    (repo / "AGENTS.md").write_text("approved instructions\n", encoding="utf-8")
    content_id = approve(repo, store)

    report = gated_paths.check(repo, store, issue=ISSUE)

    assert report.exit_code == 0
    assert report.lines[0] == "gated_paths=ok changed=1 authorization=recorded"
    assert any(f"content_id={content_id}" in line for line in report.lines)


def test_an_approval_written_before_commit_still_binds_after_commit(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    store = tmp_path / "approvals"
    (repo / "AGENTS.md").write_text("approved instructions\n", encoding="utf-8")
    content_id = approve(repo, store)
    git(repo, "add", "AGENTS.md")
    git(repo, "commit", "-q", "-m", "approved edit")

    report = gated_paths.check(repo, store, issue=ISSUE)

    assert report.exit_code == 0
    assert any(f"content_id={content_id}" in line for line in report.lines)


def test_a_later_unrelated_edit_to_the_same_path_needs_another_approval(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    store = tmp_path / "approvals"
    (repo / "AGENTS.md").write_text("approved instructions\n", encoding="utf-8")
    earlier = approve(repo, store)
    (repo / "AGENTS.md").write_text(
        "approved instructions\nlater unrelated edit\n", encoding="utf-8"
    )

    report = gated_paths.check(repo, store, issue=ISSUE)

    assert report.exit_code == 1
    assert "refusal=approval_missing" in report.lines
    assert any(line.startswith("content_id=") and earlier not in line for line in report.lines)


def test_an_approval_for_another_issue_cannot_clear_identical_content(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    store = tmp_path / "approvals"
    (repo / "AGENTS.md").write_text("approved instructions\n", encoding="utf-8")
    approve(repo, store)

    report = gated_paths.check(repo, store, issue=ISSUE + 1)

    assert report.exit_code == 1
    assert "issue=501" in report.lines
    assert "refusal=approval_missing" in report.lines


def test_a_record_this_tool_did_not_write_is_not_an_approval(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    store = tmp_path / "approvals"
    (repo / "AGENTS.md").write_text("changed\n", encoding="utf-8")
    content_id = gated_paths.content_id_of(repo, "AGENTS.md")
    record = gated_paths.approval_path(store, ISSUE, content_id)
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"content_id": content_id}), encoding="utf-8")
    record.chmod(0o600)

    report = gated_paths.check(repo, store, issue=ISSUE)

    assert report.exit_code == 1
    assert "refusal=approval_unreadable" in report.lines


def test_a_dispatched_session_cannot_write_its_own_approval(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    store = tmp_path / "approvals"
    (repo / "AGENTS.md").write_text("changed\n", encoding="utf-8")
    content_id = gated_paths.content_id_of(repo, "AGENTS.md")

    with pytest.raises(gated_paths.ApprovalError, match="d-test") as refused:
        gated_paths.record_approval(
            repo,
            store,
            issue=ISSUE,
            path="AGENTS.md",
            expected_content_id=content_id,
            approved_at=STAMP,
            approved_by="andre",
            environ={"CTI_DISPATCH_ID": "d-test"},
        )

    assert refused.value.kind == "approval_from_dispatch"
    assert not store.exists()


def test_the_writer_refuses_an_identity_for_earlier_content(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text("first edit\n", encoding="utf-8")
    earlier = gated_paths.content_id_of(repo, "AGENTS.md")
    (repo / "AGENTS.md").write_text("second edit\n", encoding="utf-8")

    with pytest.raises(gated_paths.ApprovalError) as refused:
        gated_paths.record_approval(
            repo,
            tmp_path / "approvals",
            issue=ISSUE,
            path="AGENTS.md",
            expected_content_id=earlier,
            approved_at=STAMP,
            approved_by="andre",
            environ={},
        )

    assert refused.value.kind == "content_changed"


def test_a_changed_delegated_adr_keeps_adr_0013s_authorisation_route(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    adr = repo / "docs" / "adr" / "9999-delegated.md"
    adr.parent.mkdir(parents=True)
    adr.write_text(
        "# Delegated\n\nDelegated-decision: yes\nDate: 2026-08-22\n",
        encoding="utf-8",
    )
    (repo / "AGENTS.md").write_text("delegated instructions\n", encoding="utf-8")

    report = gated_paths.check(repo, tmp_path / "approvals", issue=ISSUE)

    assert report.exit_code == 0
    assert report.lines[0] == "gated_paths=ok changed=2 authorization=delegated_decision"
    assert "delegated_record=docs/adr/9999-delegated.md" in report.lines


def test_an_old_delegated_adr_does_not_authorise_a_new_edit(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    adr = repo / "docs" / "adr" / "9999-delegated.md"
    adr.parent.mkdir(parents=True)
    adr.write_text("Delegated-decision: yes\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "delegation already landed")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    (repo / "AGENTS.md").write_text("later edit\n", encoding="utf-8")

    report = gated_paths.check(repo, tmp_path / "approvals", issue=ISSUE)

    assert report.exit_code == 1
    assert "refusal=approval_missing" in report.lines


def test_every_stable_path_from_the_signoff_paragraph_uses_one_authority() -> None:
    paths = (
        "AGENTS.md",
        "CLAUDE.md",
        "CONTEXT.md",
        "docs/adr/0077.md",
        "tests/specs/campaign.yaml",
        ".claude/skills/retro/SKILL.md",
    )

    assert all(gated_paths.signoff_gate(path) is not None for path in paths)
    assert gated_paths.hook_denial("tests/specs/campaign.yaml") is not None
    assert gated_paths.hook_denial("addons/main/generated/commands.hpp") is not None


def test_an_untracked_acceptance_spec_is_in_the_gate_diff(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    spec = repo / "tests" / "specs" / "campaign.yaml"
    spec.parent.mkdir(parents=True)
    spec.write_text("given: intent\n", encoding="utf-8")

    report = gated_paths.check(repo, tmp_path / "approvals", issue=ISSUE)

    assert report.exit_code == 1
    assert "path=tests/specs/campaign.yaml" in report.lines


def test_a_gated_change_with_no_issue_is_refused_instead_of_borrowing_a_record(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    repo.rename(tmp_path / "hand-named-tree")
    repo = tmp_path / "hand-named-tree"
    (repo / "AGENTS.md").write_text("changed\n", encoding="utf-8")

    report = gated_paths.check(repo, tmp_path / "approvals", issue=None)

    assert report.exit_code == 1
    assert "refusal=approval_issue_unknown" in report.lines


def test_every_gate_verdict_states_what_it_does_not_verify(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    clean = gated_paths.check(repo, tmp_path / "approvals", issue=ISSUE)
    (repo / "AGENTS.md").write_text("changed\n", encoding="utf-8")
    refused = gated_paths.check(repo, tmp_path / "approvals", issue=ISSUE)

    for report in (clean, refused):
        assert gated_paths.LIMIT_LINE in report.lines
        assert any(
            "not_verified=content_or_quality,human_identity,semantic_gates" in line
            for line in report.lines
        )


def test_the_cli_writes_the_record_with_time_and_os_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = repository(tmp_path)
    store = tmp_path / "approvals"
    (repo / "AGENTS.md").write_text("approved\n", encoding="utf-8")
    content_id = gated_paths.content_id_of(repo, "AGENTS.md")

    result = gated_paths.main(
        [
            "approve",
            "--root",
            str(repo),
            "--issue",
            str(ISSUE),
            "--path",
            "AGENTS.md",
            "--content-id",
            content_id,
        ],
        approval_root=store,
        clock=lambda: datetime(2026, 8, 22, 6, tzinfo=UTC),
        environ={},
        approved_by="andre",
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "approval_recorded=yes" in output
    record = json.loads(
        gated_paths.approval_path(store, ISSUE, content_id).read_text(encoding="utf-8")
    )
    assert record["approved_at"] == STAMP
    assert record["approved_by"] == "andre"
    assert record["source"] == "declared_human"
