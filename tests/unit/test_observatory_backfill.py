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


def commit_without_origin(repo: Path, name: str, message: str, at: str) -> str:
    """Add a commit without moving the staged origin/main ref."""
    (repo / name).write_text(name, encoding="utf-8")
    git("add", name, cwd=repo)
    git("commit", "-qm", message, cwd=repo, at=at)
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


def test_rejected_audit_candidates_are_typed_and_the_true_sha_has_a_start_floor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = 563
    repo, base = staged_repo(tmp_path)
    early_sha = commit(repo, "early.txt", "chore: before the dispatch", "2026-08-25T10:30:00+00:00")
    true_sha = commit(
        repo, "true.txt", "fix: no issue token in the commit", "2026-08-25T12:00:00+00:00"
    )
    git("checkout", "-q", "-b", "off-origin", cwd=repo)
    not_origin_sha = commit_without_origin(
        repo, "off-origin.txt", "chore: divergent history", "2026-08-25T12:30:00+00:00"
    )
    git("checkout", "-q", "main", cwd=repo)
    source_paths = paths(tmp_path, repo, base, issue)
    fake_projection(monkeypatch, issue)

    windows = backfill.dispatch_windows(source_paths.dispatch_root, issue)
    ambiguous = backfill.AuditCandidate("abcdef1", "ambiguous", None, 0)
    actual_resolve = backfill._resolve_commit  # noqa: SLF001 — preserve real Git resolution for the other candidates

    def resolve(repo_path: Path, abbreviated_sha: str) -> str | None:
        if abbreviated_sha == ambiguous.abbreviated_sha:
            return None
        return actual_resolve(repo_path, abbreviated_sha)

    monkeypatch.setattr(backfill, "_resolve_commit", resolve)
    rejected = (
        (
            ambiguous,
            "audit SHA abcdef1 is not an unambiguous commit",
        ),
        (
            backfill.AuditCandidate(not_origin_sha[:7], "not-origin", None, 1),
            f"audit SHA {not_origin_sha} is not on origin/main",
        ),
        (
            backfill.AuditCandidate(early_sha[:7], "before-window", None, 2),
            f"audit SHA {early_sha} is outside every dispatch base/start floor",
        ),
    )
    for candidate, expected_reason in rejected:
        resolved, reason = backfill.resolve_candidate(repo, issue, candidate, windows)
        assert resolved is None
        assert reason == expected_reason

    comment = {
        "id": 100,
        "created_at": "2026-08-25T13:01:00+00:00",
        "body": "\n".join(
            (
                f"pushed={ambiguous.abbreviated_sha} origin/main",
                f"pushed={not_origin_sha[:7]} origin/main",
                f"pushed={early_sha[:7]} origin/main",
                f"pushed={true_sha[:7]} origin/main",
            )
        ),
    }

    outcomes = backfill.reconcile(
        source_paths,
        fetch=lambda _repo: tracker(issue, "CLOSED", (comment,)),
    )

    assert outcomes[0].status == "recovered"
    assert outcomes[0].shas == (true_sha,)
    read = observatory.read_landings(source_paths.review_root)
    assert read.landings[0]["produced_commit"] == true_sha


def test_an_on_origin_post_dispatch_sha_must_descend_from_the_window_base(
    tmp_path: Path,
) -> None:
    issue = 585
    repo, _main_base = staged_repo(tmp_path)
    git("checkout", "-q", "-b", "review-work", cwd=repo)
    review_base = commit_without_origin(
        repo,
        "review.txt",
        "fix: reviewed work",
        "2026-08-25T10:30:00+00:00",
    )
    git("checkout", "-q", "main", cwd=repo)
    candidate_sha = commit(
        repo,
        "cross-issue.txt",
        "fix: another issue landing",
        "2026-08-25T12:00:00+00:00",
    )
    source_paths = paths(tmp_path, repo, review_base, issue)
    windows = backfill.dispatch_windows(source_paths.dispatch_root, issue)
    candidate = backfill.AuditCandidate(candidate_sha[:7], "cross-issue", None, 0)

    assert candidate_sha == git("rev-parse", "origin/main", cwd=repo)
    assert not backfill._is_ancestor(  # noqa: SLF001 — prove staged candidate misses ancestry floor
        repo, review_base, candidate_sha
    )
    committed_at = backfill._commit_time(  # noqa: SLF001 — prove candidate clears date floor
        repo, candidate_sha
    )
    assert committed_at is not None
    assert committed_at >= windows[0].started_at.replace(microsecond=0)

    resolved, reason = backfill.resolve_candidate(repo, issue, candidate, windows)

    assert resolved is None
    assert reason == f"audit SHA {candidate_sha} is outside every dispatch base/start floor"
