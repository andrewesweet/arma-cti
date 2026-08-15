"""The review branch exchange and the verdict record (#332, ADR-0071 ruling 4).

The exchange half — a pushed ref rather than a shared tree — and the verdict half —
a record beside its dispatch, identity derived from the records the dispatcher
wrote, SHA bound — pinned here against the two failures the issue names: a verdict
for one commit satisfying another, and a reviewing identity read back from a field
the reviewed side could have written. Every derive-binding test builds its dispatch
records inside the test body, because the mutation tier reads a collection-time
breakage as no verdict rather than as a red.

Real-git tests use throwaway repositories under `tmp_path` with a bare `origin`,
the same pattern `test_worktree.py` uses for its end-to-end actions.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

review_exchange = load_tool("review_exchange")
worktree = load_tool("worktree")

SHA = "a" * 40
OTHER_SHA = "b" * 40
COMPLETED = {"returncode": 0, "ended_at": "2026-08-15T09:00:00+00:00"}
REFUSED = {"refusal": "quota_exhausted", "failure_class": "quota_exhausted", "ended_at": "..."}


def dispatch_dir(  # noqa: PLR0913 — one parameter per field of the record under test
    root: Path,
    dispatch_id: str,
    *,
    seat: str = "review",
    issue: int = 332,
    base_sha: str = SHA,
    profile: str = "opus-high",
    lane: str = "claude-native",
    planned_at: str = "2026-08-15T09:00:00+00:00",
    plan: bool = True,
    result: str | None = "completed",
) -> Path:
    """Write one dispatch directory; `plan=False` or odd `result` shapes corrupt it on purpose."""
    entry = root / dispatch_id
    entry.mkdir(parents=True, exist_ok=True)
    if plan:
        document = {
            "dispatch_id": dispatch_id,
            "lane": lane,
            "profile": profile,
            "seat": seat,
            "issue": issue,
            "base_sha": base_sha,
            "planned_at": planned_at,
        }
        (entry / "dispatch.json").write_text(json.dumps(document), encoding="utf-8")
    if result == "completed":
        (entry / "result.json").write_text(json.dumps(COMPLETED), encoding="utf-8")
    elif result == "refused":
        (entry / "result.json").write_text(json.dumps(REFUSED), encoding="utf-8")
    elif result == "garbage":
        (entry / "result.json").write_text("{not json", encoding="utf-8")
    elif result is not None:
        (entry / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return entry


def refused_binding(root: Path, issue: int = 332, sha: str = SHA) -> str:
    """Return the refusal kind a binding derivation returned, asserting it refused at all."""
    binding = review_exchange.derive_binding(issue, sha, root)
    assert binding.kind != review_exchange.BOUND, "expected a refusal"
    return binding.kind


def init_repo(tmp_path: Path) -> Path:
    """Build a committed repository whose `origin` is a bare throwaway, as `exchange` needs."""
    repo = tmp_path / "repo"
    origin = tmp_path / "origin.git"
    repo.mkdir()
    origin.mkdir()
    worktree.git("init", "-q", cwd=repo)
    worktree.git("init", "-q", "--bare", cwd=origin)
    worktree.git("remote", "add", "origin", str(origin), cwd=repo)
    commit(repo, "README", "one", "one")
    return repo


def commit(repo: Path, name: str, content: str, message: str) -> None:
    """Make one commit with throwaway identity, so no test depends on this box's git config."""
    (repo / name).write_text(content, encoding="utf-8")
    worktree.git("add", ".", cwd=repo)
    worktree.git(
        "-c", "user.email=t@example", "-c", "user.name=t", "commit", "-q", "-m", message, cwd=repo
    )


def head_of(repo: Path) -> str:
    """Return the full HEAD of a repository, the string the exchange reports and binds."""
    return worktree.git("rev-parse", "HEAD", cwd=repo).strip()


# ------------------------------------------------------------------------ the ref


def test_review_ref_names_the_issue_branch() -> None:
    assert review_exchange.review_ref(332) == "refs/heads/issue-332"


@pytest.mark.parametrize("issue", [0, -1])
def test_review_ref_refuses_a_non_positive_issue(issue: int) -> None:
    with pytest.raises(review_exchange.ReviewExchangeError):
        review_exchange.review_ref(issue)


# --------------------------------------------------------------------- findings


def test_findings_roundtrip_id_and_severity() -> None:
    text = json.dumps([{"id": "f1", "severity": "critical"}, {"id": "f2", "severity": "low"}])
    findings = review_exchange.parse_findings(text)
    assert findings == (
        review_exchange.ReportedFinding("f1", "critical"),
        review_exchange.ReportedFinding("f2", "low"),
    )


@pytest.mark.parametrize(
    "text",
    [
        json.dumps({"id": "f1", "severity": "low"}),  # not a list
        json.dumps(["f1"]),  # not an object entry
        json.dumps([{"severity": "low"}]),  # no id
        json.dumps([{"id": "", "severity": "low"}]),  # empty id
        json.dumps([{"id": "f1", "severity": "catastrophic"}]),  # not one of the four
        json.dumps([{"id": "f1", "severity": "low"}, {"id": "f1", "severity": "high"}]),  # twice
    ],
)
def test_findings_refuse_every_shape_that_cannot_govern(text: str) -> None:
    with pytest.raises(review_exchange.ReviewExchangeError):
        review_exchange.parse_findings(text)


# ------------------------------------------------------------- the derived identity


def test_bound_from_a_completed_review_dispatch(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    binding = review_exchange.derive_binding(332, SHA, root)
    assert binding.kind == "bound"
    assert binding.dispatch_id == "d-1"
    assert binding.profile == "opus-high"
    assert binding.lane == "claude-native"
    assert binding.alternates == ()


def test_no_records_at_all(tmp_path: Path) -> None:
    assert refused_binding(tmp_path / "dispatches") == "no_dispatch_records"


def test_implementer_seat_is_walked_past(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", seat="implementer")
    assert refused_binding(root) == "no_review_dispatch"


def test_wrong_sha_is_walked_past(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", base_sha=OTHER_SHA)
    assert refused_binding(root) == "no_review_dispatch"


def test_wrong_issue_is_walked_past(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", issue=331)
    assert refused_binding(root) == "no_review_dispatch"


def test_refused_result_is_not_completed(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", result="refused")
    assert refused_binding(root) == "no_review_dispatch"


def test_live_run_without_result_is_not_completed(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", result=None)
    assert refused_binding(root) == "no_review_dispatch"


def test_unreadable_result_refuses_closed(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", result="garbage")
    assert refused_binding(root) == "records_unreadable"


def test_unreadable_plan_refuses_even_beside_a_good_binding(tmp_path: Path) -> None:
    # The fail-closed contrast with #322: an exclusion scan continues past a record it
    # cannot read, a binding scan cannot — the unreadable record could be the binding
    # one, so the good candidate answers nothing.
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", plan=False)
    dispatch_dir(root, "d-2", planned_at="2026-08-15T10:00:00+00:00")
    assert refused_binding(root) == "records_unreadable"


def test_latest_planned_at_wins_and_names_alternates(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", planned_at="2026-08-15T09:00:00+00:00")
    dispatch_dir(root, "d-2", planned_at="2026-08-15T10:00:00+00:00", profile="opus-xhigh")
    binding = review_exchange.derive_binding(332, SHA, root)
    assert binding.dispatch_id == "d-2"
    assert binding.profile == "opus-xhigh"
    assert binding.alternates == ("d-1",)


def test_a_stray_file_is_not_a_record(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    (root / "notes.txt").write_text("stray", encoding="utf-8")
    binding = review_exchange.derive_binding(332, SHA, root)
    assert binding.dispatch_id == "d-1"


# ------------------------------------------------------------------ the record


def test_record_writes_the_derived_identity_beside_the_dispatch(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", profile="opus-xhigh")
    outcome = review_exchange.record_verdict(
        332, SHA, json.dumps([{"id": "f1", "severity": "high"}]), root
    )
    assert outcome.verdict.review_dispatch == "d-1"
    assert outcome.verdict.reviewer_profile == "opus-xhigh"
    assert outcome.verdict.reviewer_lane == "claude-native"
    recorded = json.loads(outcome.path.read_text(encoding="utf-8"))
    assert recorded["review_dispatch"] == "d-1"
    assert recorded["reviewed_sha"] == SHA
    assert recorded["findings"] == [{"id": "f1", "severity": "high"}]


def test_a_second_record_of_the_same_dispatch_refuses_and_swaps_nothing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    first = review_exchange.record_verdict(
        332, SHA, json.dumps([{"id": "f1", "severity": "low"}]), root
    )
    second = review_exchange.record_verdict(
        332, SHA, json.dumps([{"id": "f2", "severity": "low"}]), root
    )
    assert second.kind == "verdict_exists"
    # The existing record is untouched — the findings were not swapped.
    again = json.loads(first.path.read_text(encoding="utf-8"))
    assert again["findings"] == [{"id": "f1", "severity": "low"}]


def test_record_without_a_binding_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", result=None)
    outcome = review_exchange.record_verdict(332, SHA, "[]", root)
    assert outcome.kind == "no_review_dispatch"
    assert not (root / "d-1" / review_exchange.VERDICT_NAME).is_file()


def test_record_refuses_a_short_sha_and_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    outcome = review_exchange.record_verdict(332, "abc123", "[]", root)
    assert outcome.kind == "invalid_sha"
    assert not (root / "d-1" / review_exchange.VERDICT_NAME).is_file()


# ------------------------------------------------------------- the record's shape


def verdict(**overrides: object) -> review_exchange.Verdict:
    """Build one well-formed verdict, with any field overridden to test the floor."""
    fields: dict[str, object] = {
        "issue": 332,
        "reviewed_sha": SHA,
        "review_dispatch": "d-1",
        "reviewer_profile": "opus-high",
        "reviewer_lane": "claude-native",
        "findings": (review_exchange.ReportedFinding("f1", "medium"),),
        "recorded_at": "2026-08-15T12:00:00+00:00",
        "alternates": ("d-0",),
    }
    return review_exchange.Verdict(**{**fields, **overrides})  # type: ignore[arg-type]


def test_verdict_document_roundtrips() -> None:
    again = review_exchange.parse_verdict(json.dumps(review_exchange.verdict_document(verdict())))
    assert again == verdict()


@pytest.mark.parametrize(
    "overrides",
    [
        {"reviewed_sha": "abc"},  # a short SHA names several commits
        {"reviewed_sha": OTHER_SHA.upper()},  # uppercase is not the form git prints
        {"issue": 0},
        {"review_dispatch": ""},
        {"reviewer_profile": ""},
        {"recorded_at": ""},
        {"alternates": ("d-0", 7)},
    ],
)
def test_verdict_parsing_refuses_every_shape_below_the_floor(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(review_exchange.ReviewExchangeError):
        review_exchange.parse_verdict(
            json.dumps(review_exchange.verdict_document(verdict(**overrides)))
        )


def test_verdict_parsing_refuses_a_false_version() -> None:
    document = review_exchange.verdict_document(verdict())
    document["version"] = True  # bool is not version 1, whatever == says
    with pytest.raises(review_exchange.ReviewExchangeError):
        review_exchange.parse_verdict(json.dumps(document))


def test_verdict_parsing_refuses_a_severity_outside_the_four() -> None:
    document = review_exchange.verdict_document(verdict())
    document["findings"] = [{"id": "f1", "severity": "nonsense"}]
    with pytest.raises(review_exchange.ReviewExchangeError):
        review_exchange.parse_verdict(json.dumps(document))


# ------------------------------------------------------------ the SHA binding


def test_satisfies_the_named_commit() -> None:
    assert review_exchange.satisfies(verdict(), SHA) is None


def test_satisfies_another_commit_refuses_and_names_both() -> None:
    mismatch = review_exchange.satisfies(verdict(), OTHER_SHA)
    assert mismatch is not None
    assert mismatch.kind == "sha_mismatch"
    found = " ".join(mismatch.found)
    assert OTHER_SHA in found
    assert SHA in found


def test_verify_re_derives_a_recorded_verdict(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    outcome = review_exchange.record_verdict(332, SHA, "[]", root)
    binding = review_exchange.verify(outcome.verdict, root)
    assert binding.kind == "bound"
    assert binding.dispatch_id == "d-1"


def test_verify_refuses_a_hand_written_identity_claim(tmp_path: Path) -> None:
    # Criterion three, made mechanical: the record may claim any dispatch, and only
    # the derivation over the dispatcher's records settles the claim.
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    forged = verdict(review_dispatch="d-not-the-binding-one")
    refusal = review_exchange.verify(forged, root)
    assert refusal.kind == "identity_mismatch"


def test_scan_collects_verdicts_and_names_the_unreadable(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    dispatch_dir(root, "d-2", result=None)
    review_exchange.record_verdict(332, SHA, "[]", root)
    (root / "d-2" / review_exchange.VERDICT_NAME).write_text("{broken", encoding="utf-8")
    scanned = review_exchange.scan_verdicts(root)
    assert [dispatch for dispatch, _ in scanned.verdicts] == ["d-1"]
    assert scanned.unreadable == (root / "d-2" / review_exchange.VERDICT_NAME,)


def test_scan_of_an_empty_root_is_empty(tmp_path: Path) -> None:
    scanned = review_exchange.scan_verdicts(tmp_path / "dispatches")
    assert scanned.verdicts == ()
    assert scanned.unreadable == ()


# --------------------------------------------------------------- the exchange


def test_exchange_pushes_and_the_remote_holds_the_sha(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    head = head_of(repo)
    report = review_exchange.exchange(repo, 332)
    assert report.code == 0
    assert "ok=review_branch_exchanged" in report.lines
    assert f"reviewed_sha={head}" in report.lines
    assert worktree.remote_ref_sha(repo, "refs/heads/issue-332") == head


def test_exchange_refuses_a_dirty_tree_and_pushes_nothing(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "dirty").write_text("uncommitted", encoding="utf-8")
    report = review_exchange.exchange(repo, 332)
    assert report.code == 1
    assert report.lines[0] == "refusal=dirty_tree"
    assert worktree.remote_ref_sha(repo, "refs/heads/issue-332") is None


def test_exchange_force_moves_the_ref_for_an_amended_round(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    review_exchange.exchange(repo, 332)
    first = head_of(repo)
    (repo / "README").write_text("two", encoding="utf-8")
    worktree.git("add", ".", cwd=repo)
    worktree.git(
        "-c",
        "user.email=t@example",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--amend",
        "-m",
        "two",
        cwd=repo,
    )
    second = review_exchange.exchange(repo, 332)
    assert second.code == 0
    moved = head_of(repo)
    assert moved != first
    assert worktree.remote_ref_sha(repo, "refs/heads/issue-332") == moved


def test_exchange_refuses_a_non_repository(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    report = review_exchange.exchange(empty, 332)
    assert report.code == 1
    assert report.lines[0] == "refusal=git_failed"


def test_exchange_refuses_a_non_positive_issue_before_git(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    report = review_exchange.exchange(repo, 0)
    assert report.code == 1
    assert report.lines[0] == "refusal=invalid_issue"


# ------------------------------------------------------------------ invocation


def cli_record(tmp_path: Path, root: Path, sha: str = SHA) -> int:
    """Record one verdict through the CLI, as the orchestrator would."""
    findings = tmp_path / "findings.json"
    findings.write_text(json.dumps([{"id": "f1", "severity": "medium"}]), encoding="utf-8")
    return review_exchange.main(
        [
            "record",
            "--issue",
            "332",
            "--reviewed-sha",
            sha,
            "--findings",
            str(findings),
            "--dispatch-dir",
            str(root),
        ]
    )


def test_cli_records_shows_and_prints_the_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    assert cli_record(tmp_path, root) == 0
    assert review_exchange.SAME_USER_LIMIT in capsys.readouterr().out
    shown_ok = review_exchange.main(
        ["show", "d-1", "--satisfies", SHA, "--dispatch-dir", str(root)]
    )
    assert shown_ok == 0
    shown = capsys.readouterr().out
    assert f"satisfies={SHA} yes" in shown
    assert review_exchange.SAME_USER_LIMIT in shown


def test_cli_show_of_a_mismatched_sha_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    assert cli_record(tmp_path, root) == 0
    capsys.readouterr()
    code = review_exchange.main(
        ["show", "d-1", "--satisfies", OTHER_SHA, "--dispatch-dir", str(root)]
    )
    assert code == 1
    assert "refusal=sha_mismatch" in capsys.readouterr().err


def test_cli_show_of_an_unknown_dispatch_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = review_exchange.main(["show", "d-none", "--dispatch-dir", str(tmp_path)])
    assert code == 1
    assert "refusal=no_verdict" in capsys.readouterr().err


def test_cli_show_refuses_a_path_like_dispatch_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = review_exchange.main(["show", "../elsewhere", "--dispatch-dir", str(tmp_path)])
    assert code == 1
    assert "refusal=unknown_dispatch" in capsys.readouterr().err


def test_cli_record_without_a_binding_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "dispatches"
    root.mkdir()
    assert cli_record(tmp_path, root) == 1
    assert "refusal=no_review_dispatch" in capsys.readouterr().err
    assert list(root.iterdir()) == []
