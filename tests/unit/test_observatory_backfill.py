"""Historical observatory landing reconciliation (#572)."""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import pytest

observatory = load_tool("observatory")
backfill = load_tool("observatory_backfill")


def git(*args: str, cwd: Path, at: str = "") -> str:
    """Run Git against a staged repository."""
    environment = {**os.environ, "GIT_AUTHOR_DATE": at, "GIT_COMMITTER_DATE": at}
    completed = subprocess.run(  # noqa: S603 — fixed Git executable and tmp_path repo
        ["git", *args],  # noqa: S607 — Git is the staged repository authority
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    return completed.stdout.strip()


def staged_repo(tmp_path: Path) -> tuple[Path, str]:
    """Create an origin/main checkout with one base commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("config", "user.email", "test@example.com", cwd=repo)
    git("config", "user.name", "Test", cwd=repo)
    (repo / "base.txt").write_text("base", encoding="utf-8")
    git("add", "base.txt", cwd=repo)
    git("commit", "-qm", "chore: base", cwd=repo, at="2026-08-25T10:00:00+00:00")
    base = git("rev-parse", "HEAD", cwd=repo)
    git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo)
    return repo, base


def commit(repo: Path, name: str, message: str, at: str) -> str:
    """Add one commit and make it visible on origin/main."""
    (repo / name).write_text(name, encoding="utf-8")
    git("add", name, cwd=repo)
    git("commit", "-qm", message, cwd=repo, at=at)
    git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo)


def dispatch_root(tmp_path: Path, base: str, issue: int) -> Path:
    """Write the minimum landing-capable dispatch record."""
    root = tmp_path / "dispatches"
    record = root / "d-backfill-1"
    record.mkdir(parents=True)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": record.name,
                "lane": "codex",
                "profile": "codex-luna-max",
                "seat": "implementer",
                "issue": issue,
                "base_sha": base,
                "planned_at": "2026-08-25T11:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return root


def paths(tmp_path: Path, repo: Path, base: str, issue: int) -> backfill.BackfillPaths:
    """Arrange the backfill source roots."""
    dispatches = dispatch_root(tmp_path, base, issue)
    export = tmp_path / "export"
    review = tmp_path / "review"
    queue = tmp_path / "queue"
    export.mkdir()
    review.mkdir()
    queue.mkdir()
    spool = tmp_path / "statusline.jsonl"
    spool.write_text("", encoding="utf-8")
    return backfill.BackfillPaths(dispatches, export, review, spool, repo, queue)


def fake_projection(monkeypatch: pytest.MonkeyPatch, issue: int) -> None:
    """Make the candidate boundary explicit without rebuilding unrelated telemetry."""

    def rebuild(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"issue_summary": [{"issue": issue}]}

    monkeypatch.setattr(backfill.observatory, "rebuild", rebuild)


def tracker(
    issue: int, state: str, comments: tuple[Mapping[str, object], ...] = ()
) -> backfill.TrackerSnapshot:
    """Build the two tracker facts the reconciler is allowed to read."""
    return backfill.TrackerSnapshot({issue: state}, {issue: comments})


def test_only_exact_just_land_lines_become_audit_candidates() -> None:
    candidates = backfill.audit_candidates(
        (
            {"id": 1, "body": "Landed at `abcdef1` — prose, not a tool line."},
            {"id": 2, "body": ">pushed=abcdef2 origin/main"},
            {"id": 3, "body": "pushed=abcdef3 origin/main"},
            {"id": 4, "body": "Landed on `origin/main` as `abcdef4`."},
        )
    )
    assert [candidate.abbreviated_sha for candidate in candidates] == ["abcdef3", "abcdef4"]


def test_a_closed_issue_without_evidence_gets_a_reasoned_subject_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = 572
    repo, base = staged_repo(tmp_path)
    commit(repo, "fallback.txt", "chore: carry forward\n\nRefs #572", "2026-08-25T12:00:00+00:00")
    source_paths = paths(tmp_path, repo, base, issue)
    fake_projection(monkeypatch, issue)

    outcomes = backfill.reconcile(
        source_paths,
        fetch=lambda _repo: tracker(issue, "CLOSED"),
        now=lambda: 1_800_000_000.0,
    )

    assert outcomes[0].status == "unrecoverable"
    assert "no exact just-land SHA" in outcomes[0].reason
    read = observatory.read_landings(source_paths.review_root)
    assert read.landings[0]["issue"] == issue
    assert read.landings[0]["produced_commit"] is None
    assert "no exact just-land SHA" in read.landings[0]["produced_commit_reason"]


def test_an_open_issue_is_not_minted_and_can_later_recover_the_true_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The first run sees only the fallback-shaped history and leaves no marker. The
    # second sees the later just-land audit and records that SHA, so accidental truth
    # from a later genuine landing is never used to validate the earlier fallback.
    issue = 575
    repo, base = staged_repo(tmp_path)
    commit(
        repo,
        "intermediate.txt",
        "chore: carry forward\n\nRefs #562, #545, #575",
        "2026-08-25T12:00:00+00:00",
    )
    source_paths = paths(tmp_path, repo, base, issue)
    fake_projection(monkeypatch, issue)

    first = backfill.reconcile(
        source_paths,
        fetch=lambda _repo: tracker(issue, "OPEN"),
    )
    assert first[0].status == "not_landed"
    assert not (source_paths.review_root / str(issue)).exists()

    true_sha = commit(repo, "true.txt", "fix: the actual landing", "2026-08-25T13:00:00+00:00")
    comment = {
        "id": 99,
        "created_at": "2026-08-25T13:01:00+00:00",
        "body": f"Landed on `origin/main` as `{true_sha[:7]}`.",
    }
    second = backfill.reconcile(
        source_paths,
        fetch=lambda _repo: tracker(issue, "CLOSED", (comment,)),
    )
    assert second[0].status == "recovered"
    assert second[0].shas == (true_sha,)
    read = observatory.read_landings(source_paths.review_root)
    assert read.landings[0]["produced_commit"] == true_sha


def test_a_recovered_audit_sha_is_bounded_by_the_dispatch_window_and_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = 563
    repo, base = staged_repo(tmp_path)
    true_sha = commit(
        repo, "true.txt", "fix: no issue token in the commit", "2026-08-25T12:00:00+00:00"
    )
    false_sha = commit(
        repo, "later.txt", "chore: follow-up\n\nRefs #563", "2026-08-25T13:00:00+00:00"
    )
    source_paths = paths(tmp_path, repo, base, issue)
    fake_projection(monkeypatch, issue)
    comment = {
        "id": 100,
        "created_at": "2026-08-25T13:01:00+00:00",
        "body": f"pushed={true_sha[:7]} origin/main",
    }

    outcomes = backfill.reconcile(
        source_paths,
        fetch=lambda _repo: tracker(issue, "CLOSED", (comment,)),
    )

    assert outcomes[0].status == "recovered"
    assert outcomes[0].shas == (true_sha,)
    assert false_sha not in outcomes[0].shas
    read = observatory.read_landings(source_paths.review_root)
    assert read.landings[0]["produced_commit"] == true_sha
