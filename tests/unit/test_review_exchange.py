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
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

review_exchange = load_tool("review_exchange")
worktree = load_tool("worktree")

SHA = "a" * 40
OTHER_SHA = "b" * 40
THIRD_SHA = "e" * 40
DIFF_ID = "c" * 64
OTHER_DIFF_ID = "d" * 64
# `write_result`'s two shapes, field for field: a run that ran is typed by its
# outcome (`classify_run` ties `ok` to a zero exit), and a dispatch that never
# reached a lane carries its refusal and no returncode at all.
COMPLETED = {
    "returncode": 0,
    "outcome": "ok",
    "started_at": "2026-08-15T09:00:00+00:00",
    "ended_at": "2026-08-15T09:05:00+00:00",
}
REFUSED = {"refusal": "infra_unavailable", "failure_class": "infra_unavailable", "ended_at": "..."}


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
    result: str | dict[str, object] | None = "completed",
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


def ahead_repo(tmp_path: Path) -> tuple[Path, str]:
    """Build a repository whose HEAD is one work commit ahead of its own `origin/main`.

    The state `diff_id_of` hashes (#417): a base pushed to `origin/main`, then the
    reviewed work on top of it, so `git diff origin/main...HEAD` is the diff a
    landing lands and never the empty diff a fresh clone would give.
    """
    repo = init_repo(tmp_path)
    worktree.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=repo)
    worktree.git("fetch", "-q", "origin", cwd=repo)
    commit(repo, "README", "two", "work")
    return repo, head_of(repo)


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


@pytest.mark.parametrize(
    "outcome", ["quota_exhausted", "provider_error", "provider_refused", "unclassified"]
)
def test_a_run_that_ended_in_a_typed_non_result_is_not_completed(
    tmp_path: Path, outcome: str
) -> None:
    # High 1, round 1: a refused run still carries a returncode and an `ended_at`,
    # so timestamps cannot mean completion. The dispatcher types every finished
    # run, and only `outcome=ok` completed — the failure-class table's own line,
    # read here rather than re-derived from exit codes.
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", result={**COMPLETED, "returncode": 1, "outcome": outcome})
    assert refused_binding(root) == "no_review_dispatch"


def test_a_ran_result_without_a_typed_outcome_refuses_closed(tmp_path: Path) -> None:
    # Not a shape `write_result` produces beside a returncode, so not a fact this
    # scan reads — the binding one could be it, and an answer cannot degrade.
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", result={"returncode": 0, "ended_at": "2026-08-15T09:05:00+00:00"})
    assert refused_binding(root) == "records_unreadable"


def test_an_ok_outcome_without_an_end_refuses_closed(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", result={"returncode": 0, "outcome": "ok"})
    assert refused_binding(root) == "records_unreadable"


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
        332, SHA, json.dumps([{"id": "f1", "severity": "high"}]), root, diff_id=DIFF_ID
    )
    assert outcome.verdict.review_dispatch == "d-1"
    assert outcome.verdict.reviewer_profile == "opus-xhigh"
    assert outcome.verdict.reviewer_lane == "claude-native"
    recorded = json.loads(outcome.path.read_text(encoding="utf-8"))
    assert recorded["review_dispatch"] == "d-1"
    assert recorded["reviewed_sha"] == SHA
    assert recorded["diff_id"] == DIFF_ID
    assert recorded["findings"] == [{"id": "f1", "severity": "high"}]


def test_a_second_record_of_the_same_dispatch_refuses_and_swaps_nothing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    first = review_exchange.record_verdict(
        332, SHA, json.dumps([{"id": "f1", "severity": "low"}]), root, diff_id=DIFF_ID
    )
    second = review_exchange.record_verdict(
        332, SHA, json.dumps([{"id": "f2", "severity": "low"}]), root, diff_id=DIFF_ID
    )
    assert second.kind == "verdict_exists"
    # The existing record is untouched — the findings were not swapped.
    again = json.loads(first.path.read_text(encoding="utf-8"))
    assert again["findings"] == [{"id": "f1", "severity": "low"}]


def test_concurrent_records_cannot_both_write_the_one_slot(tmp_path: Path) -> None:
    # Medium 4, round 1: the existence check and the write are one atomic act, so
    # two records racing on one dispatch leave one verdict and one `verdict_exists`
    # — never one verdict quietly overwritten by the other's findings.
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    payloads = (
        json.dumps([{"id": "first", "severity": "low"}]),
        json.dumps([{"id": "second", "severity": "low"}]),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda findings: review_exchange.record_verdict(
                    332, SHA, findings, root, diff_id=DIFF_ID
                ),
                payloads,
            )
        )
    written = [outcome for outcome in outcomes if not isinstance(outcome, review_exchange.Refusal)]
    refused = [outcome for outcome in outcomes if isinstance(outcome, review_exchange.Refusal)]
    assert len(written) == 1
    assert len(refused) == 1
    assert refused[0].kind == "verdict_exists"
    # Whichever won, the file holds that one's findings and parses as a verdict.
    recorded = json.loads(written[0].path.read_text(encoding="utf-8"))
    assert recorded["findings"] in (
        [{"id": "first", "severity": "low"}],
        [{"id": "second", "severity": "low"}],
    )


def test_record_refuses_a_partial_file_in_the_slot_and_overwrites_nothing(
    tmp_path: Path,
) -> None:
    # The other way to be occupied: an interrupted write leaves a partial, and the
    # recovery is named rather than the slot being declared unwritable.
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    path = root / "d-1" / review_exchange.VERDICT_NAME
    path.write_text('{"version": 1, "revie', encoding="utf-8")
    outcome = review_exchange.record_verdict(332, SHA, "[]", root, diff_id=DIFF_ID)
    assert outcome.kind == "verdict_unreadable"
    assert path.read_text(encoding="utf-8") == '{"version": 1, "revie'


def test_record_that_fails_mid_write_leaves_no_partial_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")

    def failing_fsync(_fileno: int) -> None:
        failure = OSError("no space left on device")
        raise failure

    monkeypatch.setattr(review_exchange.os, "fsync", failing_fsync)
    outcome = review_exchange.record_verdict(332, SHA, "[]", root, diff_id=DIFF_ID)
    assert outcome.kind == "verdict_unwritten"
    # Neither a verdict nor the staged attempt is left behind.
    assert sorted(entry.name for entry in (root / "d-1").iterdir()) == [
        "dispatch.json",
        "result.json",
    ]


def test_record_refuses_an_unwritable_dispatch_directory(tmp_path: Path) -> None:
    # Medium 1, round 2: the staged write is the first act that needs the
    # dispatch directory to be writable — the binding derivation only reads it —
    # so an unwritable one is a verdict-write failure like any other:
    # `verdict_unwritten`, never an escaping traceback, and nothing left behind.
    root = tmp_path / "dispatches"
    entry = dispatch_dir(root, "d-1")
    entry.chmod(0o500)
    try:
        outcome = review_exchange.record_verdict(332, SHA, "[]", root, diff_id=DIFF_ID)
        assert outcome.kind == "verdict_unwritten"
        assert sorted(item.name for item in entry.iterdir()) == [
            "dispatch.json",
            "result.json",
        ]
    finally:
        # Restored so pytest's own cleanup can remove the directory.
        entry.chmod(0o700)


def test_record_refuses_a_dispatch_directory_removed_under_the_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The race the unwritable case cannot reach: the directory was there when
    # the binding read it and is gone when the write stages. The removal is
    # driven for real (`shutil.rmtree`), between the derivation and the
    # staging, through the one seam they share — so `mkstemp` meets a genuinely
    # missing directory, refuses `verdict_unwritten`, and recreates nothing.
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    real_verdict_path = review_exchange.verdict_path

    def path_then_remove(dispatch_root: Path, dispatch_id: str) -> Path:
        verdict_file = real_verdict_path(dispatch_root, dispatch_id)
        shutil.rmtree(dispatch_root / dispatch_id)
        return verdict_file

    monkeypatch.setattr(review_exchange, "verdict_path", path_then_remove)
    outcome = review_exchange.record_verdict(332, SHA, "[]", root, diff_id=DIFF_ID)
    assert outcome.kind == "verdict_unwritten"
    assert not (root / "d-1").exists()


def test_record_without_a_binding_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", result=None)
    outcome = review_exchange.record_verdict(332, SHA, "[]", root, diff_id=DIFF_ID)
    assert outcome.kind == "no_review_dispatch"
    assert not (root / "d-1" / review_exchange.VERDICT_NAME).is_file()


def test_record_refuses_a_short_sha_and_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    outcome = review_exchange.record_verdict(332, "abc123", "[]", root, diff_id=DIFF_ID)
    assert outcome.kind == "invalid_sha"
    assert not (root / "d-1" / review_exchange.VERDICT_NAME).is_file()


def test_record_refuses_a_shapeless_diff_id_and_writes_nothing(tmp_path: Path) -> None:
    # #417's floor at the write side too: a record without a diff identity can never
    # carry across a rebase, and an unreadable one is a refusal, never a pass.
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    outcome = review_exchange.record_verdict(332, SHA, "[]", root, diff_id="nope")
    assert outcome.kind == "invalid_diff_id"
    assert not (root / "d-1" / review_exchange.VERDICT_NAME).is_file()


# ------------------------------------------------------------- the record's shape


def verdict(**overrides: object) -> review_exchange.Verdict:
    """Build one well-formed verdict, with any field overridden to test the floor."""
    fields: dict[str, object] = {
        "issue": 332,
        "reviewed_sha": SHA,
        "diff_id": DIFF_ID,
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
        {"diff_id": "c" * 63},  # a short identity is not one the hash printed
        {"diff_id": ""},  # nor is an empty one — #417's floor is 64 lowercase hex
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


def test_satisfies_a_moved_sha_on_an_identical_diff_over_a_recorded_clean_rebase() -> None:
    """#417's carry, and it takes all three facts or none of it.

    The SHA the rebase produced, the diff the review judged, and the rebase's own
    outcome recorded as clean.
    """
    assert review_exchange.satisfies(verdict(), OTHER_SHA, DIFF_ID, clean_rebase=True) is None


def test_satisfies_a_moved_sha_on_another_diff_refuses_and_names_both_halves() -> None:
    mismatch = review_exchange.satisfies(verdict(), OTHER_SHA, OTHER_DIFF_ID, clean_rebase=True)
    assert mismatch is not None
    assert mismatch.kind == "sha_mismatch"
    found = " ".join(mismatch.found)
    assert OTHER_SHA in found
    assert SHA in found
    assert f"diff_id=mismatch asked={OTHER_DIFF_ID} reviewed={DIFF_ID}" in mismatch.found


def test_satisfies_a_moved_sha_without_a_landing_diff_id_never_clears() -> None:
    # The half of the binding that carries across a rebase could not run, so it
    # did not pass — #41, in #417's own shape.
    unreadable = review_exchange.satisfies(verdict(), OTHER_SHA)
    assert unreadable is not None
    assert unreadable.kind == "diff_id_unreadable"


def test_satisfies_refuses_an_invalid_landing_diff_id_even_matching() -> None:
    # `None` is "not asked for"; anything unreadable or malformed on the landing
    # side is a refusal, so a caller's mistake cannot read as a narrower question.
    malformed = review_exchange.satisfies(verdict(), OTHER_SHA, "nope", clean_rebase=True)
    assert malformed is not None
    assert malformed.kind == "diff_id_unreadable"
    assert "landing_diff_id='nope'" in " ".join(malformed.found)


def test_satisfies_a_moved_sha_without_a_recorded_clean_rebase_refuses() -> None:
    """The rework's core: an identity match alone proves nothing about the replay.

    Hashing the output cannot tell whether a conflict was resolved by hand, so a
    moved SHA with no recorded clean-rebase chain is `rebase_unproven` even where
    the diff is byte-identical.
    """
    unproven = review_exchange.satisfies(verdict(), OTHER_SHA, DIFF_ID, clean_rebase=False)
    assert unproven is not None
    assert unproven.kind == "rebase_unproven"
    assert "diff_id=match" in " ".join(unproven.found)


def test_satisfies_passes_an_unreadable_rebase_record_through_untouched() -> None:
    # The links file that cannot be read is the walk's own refusal, and `satisfies`
    # returns it as-is rather than re-wording it — one kind, `rebase_unproven`,
    # with the cause on its `found` lines.
    unreadable_links = review_exchange.Refusal(
        "rebase_unproven", ("cause=links_unreadable",), "Fail closed."
    )
    through = review_exchange.satisfies(
        verdict(), OTHER_SHA, DIFF_ID, clean_rebase=unreadable_links
    )
    assert through is unreadable_links


def test_satisfies_refuses_an_unreadable_recorded_diff_id_whatever_the_sha() -> None:
    """The rework's fail-closed ordering, asserted where it was got wrong.

    The verdict's own identity is validated before the SHA-match early return, so a
    corrupt record never clears on the SHA alone — the review's Medium, where a
    missing identity passed because the field was never read.
    """
    unreadable = review_exchange.satisfies(verdict(diff_id="nope"), SHA)
    assert unreadable is not None
    assert unreadable.kind == "diff_id_unreadable"


def test_verify_re_derives_a_recorded_verdict(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    outcome = review_exchange.record_verdict(332, SHA, "[]", root, diff_id=DIFF_ID)
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


def test_verify_refuses_a_hand_edited_profile(tmp_path: Path) -> None:
    # Medium 3, round 1: the dispatch id is one of three identity fields the
    # derivation owns. A profile the records never derived is the same forgery
    # wearing two of its three names correctly, and `show` must not print it.
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", profile="opus-high")
    forged = verdict(reviewer_profile="codex-sol-max")
    refusal = review_exchange.verify(forged, root)
    assert refusal.kind == "identity_mismatch"


def test_verify_refuses_a_hand_edited_lane(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", lane="claude-native")
    forged = verdict(reviewer_lane="zai")
    refusal = review_exchange.verify(forged, root)
    assert refusal.kind == "identity_mismatch"


def test_bound_verdict_carries_a_review_across_a_moved_sha(tmp_path: Path) -> None:
    """The landing's ladder (#417): a rebase that moved the SHA keeps its review.

    The dispatch record binds the pre-rebase commit — that is what the reviewer
    was dispatched at — and the landing asks about the commit the rebase produced,
    carrying the diff's identity with it and the rebase's own record of a clean
    replay. The identity derives against the verdict's own SHA, so the reviewer of
    record is the one who reviewed the diff.
    """
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", base_sha=OTHER_SHA)
    recorded = review_exchange.record_verdict(332, OTHER_SHA, "[]", root, diff_id=DIFF_ID)
    assert not isinstance(recorded, review_exchange.Refusal)
    review_root = tmp_path / "review"
    review_exchange.record_rebase(
        review_root,
        332,
        review_exchange.RebaseLink(OTHER_SHA, SHA, THIRD_SHA, "2026-08-18T10:00:00+00:00"),
    )

    bound = review_exchange.bound_verdict(
        332, SHA, root, DIFF_ID, review_exchange.read_rebases(review_root, 332)
    )

    assert isinstance(bound, review_exchange.BoundVerdict)
    assert bound.verdict == recorded.verdict
    assert bound.binding.dispatch_id == "d-1"
    assert bound.carried_by_diff is True


def test_bound_verdict_walks_past_a_newer_verdict_that_does_not_satisfy(
    tmp_path: Path,
) -> None:
    """Latest-first, but satisfaction decides: an older review of this diff clears.

    The newer dispatch reviewed another commit — the re-review a conflict-resolved
    rebase owes, say — and its verdict satisfies neither half for the diff being
    landed. The older one judged this diff and is the one that carries, identity
    and all, derived against the SHA it actually reviewed, over the recorded chain.
    """
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", base_sha=SHA, planned_at="2026-08-15T08:00:00+00:00")
    older = review_exchange.record_verdict(
        332, SHA, "[]", root, diff_id=DIFF_ID, now="2026-08-15T08:30:00+00:00"
    )
    dispatch_dir(root, "d-2", base_sha=OTHER_SHA, planned_at="2026-08-15T09:00:00+00:00")
    newer = review_exchange.record_verdict(
        332, OTHER_SHA, "[]", root, diff_id=OTHER_DIFF_ID, now="2026-08-15T09:30:00+00:00"
    )
    assert not isinstance(older, review_exchange.Refusal)
    assert not isinstance(newer, review_exchange.Refusal)
    review_root = tmp_path / "review"
    review_exchange.record_rebase(
        review_root,
        332,
        review_exchange.RebaseLink(SHA, THIRD_SHA, OTHER_SHA, "2026-08-18T10:00:00+00:00"),
    )

    bound = review_exchange.bound_verdict(
        332, THIRD_SHA, root, DIFF_ID, review_exchange.read_rebases(review_root, 332)
    )

    assert isinstance(bound, review_exchange.BoundVerdict)
    assert bound.verdict.review_dispatch == "d-1"
    assert bound.carried_by_diff is True


def test_bound_verdict_where_no_candidate_satisfies_returns_the_mismatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", base_sha=OTHER_SHA)
    recorded = review_exchange.record_verdict(332, OTHER_SHA, "[]", root, diff_id=OTHER_DIFF_ID)
    assert not isinstance(recorded, review_exchange.Refusal)
    review_root = tmp_path / "review"
    review_exchange.record_rebase(
        review_root,
        332,
        review_exchange.RebaseLink(OTHER_SHA, SHA, THIRD_SHA, "2026-08-18T10:00:00+00:00"),
    )

    mismatch = review_exchange.bound_verdict(
        332, SHA, root, DIFF_ID, review_exchange.read_rebases(review_root, 332)
    )

    assert isinstance(mismatch, review_exchange.Refusal)
    assert mismatch.kind == "sha_mismatch"


def test_bound_verdict_without_a_recorded_chain_refuses_rebase_unproven(
    tmp_path: Path,
) -> None:
    """The carry test's tree, minus the recorded link.

    The diff matches and it still refuses, because an identity match alone cannot
    prove whether a conflict was resolved by hand.
    """
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", base_sha=OTHER_SHA)
    recorded = review_exchange.record_verdict(332, OTHER_SHA, "[]", root, diff_id=DIFF_ID)
    assert not isinstance(recorded, review_exchange.Refusal)

    unproven = review_exchange.bound_verdict(332, SHA, root, DIFF_ID, ())

    assert isinstance(unproven, review_exchange.Refusal)
    assert unproven.kind == "rebase_unproven"


@pytest.mark.parametrize(
    "verdict_body",
    [
        '{"version": 1, "patch_id": "' + "c" * 40 + '"}',  # the first build's field
        '{"version": 1}',  # a verdict older than either build's floor
        '{"version": 1, "diff_id": "short"}',  # neither build's shape
    ],
)
def test_a_pre_rework_verdict_takes_the_one_time_rereview(
    tmp_path: Path, verdict_body: str
) -> None:
    """#417's migration, named as itself rather than as a corrupt record.

    A verdict recorded before the rework parses to no valid diff identity, and
    refuses `diff_id_unreadable` — the one-time re-review — whatever the SHA.
    """
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    (root / "d-1" / review_exchange.VERDICT_NAME).write_text(verdict_body, encoding="utf-8")

    refused = review_exchange.bound_verdict(332, SHA, root)

    assert isinstance(refused, review_exchange.Refusal)
    assert refused.kind == "diff_id_unreadable"


# ------------------------------------------------------------- the rebase links


def test_record_rebase_appends_and_reads_back(tmp_path: Path) -> None:
    review_root = tmp_path / "review"
    first = review_exchange.RebaseLink(SHA, OTHER_SHA, THIRD_SHA, "2026-08-18T10:00:00+00:00")
    second = review_exchange.RebaseLink(OTHER_SHA, THIRD_SHA, SHA, "2026-08-18T11:00:00+00:00")
    review_exchange.record_rebase(review_root, 332, first)
    review_exchange.record_rebase(review_root, 332, second)
    read = review_exchange.read_rebases(review_root, 332)
    assert isinstance(read, tuple)
    assert read == (first, second)


def test_read_rebases_of_an_absent_file_is_empty_never_a_refusal(tmp_path: Path) -> None:
    read = review_exchange.read_rebases(tmp_path / "review", 332)
    assert read == ()


def test_read_rebases_refuses_an_unreadable_or_malformed_file(tmp_path: Path) -> None:
    review_root = tmp_path / "review"
    path = review_exchange.rebase_links_path(review_root, 332)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    refused = review_exchange.read_rebases(review_root, 332)
    assert isinstance(refused, review_exchange.Refusal)
    assert refused.kind == "rebase_unproven"
    path.write_text(json.dumps([{"before": "short"}]), encoding="utf-8")
    malformed = review_exchange.read_rebases(review_root, 332)
    assert isinstance(malformed, review_exchange.Refusal)
    assert malformed.kind == "rebase_unproven"


def test_carried_by_clean_rebase_walks_a_chain_and_stops_where_none_was_recorded() -> None:
    links = (
        review_exchange.RebaseLink(SHA, OTHER_SHA, THIRD_SHA, "2026-08-18T10:00:00+00:00"),
        review_exchange.RebaseLink(OTHER_SHA, THIRD_SHA, SHA, "2026-08-18T11:00:00+00:00"),
    )
    # Direct hop, and two hops through a middle the walk must discover.
    assert review_exchange.carried_by_clean_rebase(links, SHA, OTHER_SHA)
    assert review_exchange.carried_by_clean_rebase(links, SHA, THIRD_SHA)
    # The landing commit no link reaches — a new commit or an amend after the
    # recorded rebase — is not carried, and neither is a chain walked backwards.
    assert not review_exchange.carried_by_clean_rebase(links, SHA, "f" * 40)
    assert not review_exchange.carried_by_clean_rebase(links, THIRD_SHA, SHA)


def test_scan_collects_verdicts_and_names_the_unreadable(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1")
    dispatch_dir(root, "d-2", result=None)
    review_exchange.record_verdict(332, SHA, "[]", root, diff_id=DIFF_ID)
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


def test_exchange_refuses_when_status_fails_for_real_and_pushes_nothing(
    tmp_path: Path,
) -> None:
    # High 2, round 1 — re-pinned round 2 after review: the stub the first pin
    # used raised for every caller of `worktree.git`, so it passed against the
    # pre-fix `check=False` code as readily as against the fix. This one drives
    # a genuinely failing command: a corrupted index makes the real `git status
    # --porcelain` exit non-zero with empty stdout while `rev-parse HEAD` still
    # answers, and the failure travels through `worktree.git`'s own check
    # handling — the exact code the fix changed. A status that fails and prints
    # nothing is an unestablished clean tree, not a clean one (#105's invariant:
    # a manufactured absence must never read as absence of dirt), so the
    # exchange refuses `git_failed` and pushes nothing.
    repo = init_repo(tmp_path)
    (repo / ".git" / "index").write_bytes(b"not an index file")
    report = review_exchange.exchange(repo, 332)
    assert report.code == 1
    assert report.lines[0] == "refusal=git_failed"
    assert worktree.remote_ref_sha(repo, "refs/heads/issue-332") is None


def test_exchange_refuses_a_non_positive_issue_before_git(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    report = review_exchange.exchange(repo, 0)
    assert report.code == 1
    assert report.lines[0] == "refusal=invalid_issue"


# ------------------------------------------------------------- the diff identity


def test_diff_id_of_hashes_the_range_a_landing_lands(tmp_path: Path) -> None:
    repo, head = ahead_repo(tmp_path)
    identity = review_exchange.diff_id_of(repo, head)
    assert isinstance(identity, str)
    assert review_exchange.DIFF_ID.fullmatch(identity)


def test_diff_id_of_refuses_what_git_cannot_reach(tmp_path: Path) -> None:
    repo, _head = ahead_repo(tmp_path)
    unknown = review_exchange.diff_id_of(repo, "9" * 40)
    assert isinstance(unknown, review_exchange.Refusal)
    assert unknown.kind == "diff_id_unreadable"


def staged_review(tmp_path: Path, *, readme: str) -> tuple[Path, str]:
    """Push a base, commit work on top, and return the repo and the reviewed HEAD."""
    repo = init_repo(tmp_path)
    (repo / "README").write_text(readme, encoding="utf-8")
    worktree.git("add", ".", cwd=repo)
    worktree.git(
        "-c", "user.email=t@example", "-c", "user.name=t", "commit", "-q", "-m", "base", cwd=repo
    )
    worktree.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=repo)
    worktree.git("fetch", "-q", "origin", cwd=repo)
    worktree.git("checkout", "-q", "-b", "work", cwd=repo)
    commit(repo, "README", "two\nline 2\nline 3\nline 4\nline 5\nline 6", "work")
    return repo, head_of(repo)


def move_main(repo: Path, *, readme: str) -> None:
    """Advance `origin/main` one commit, as a sibling landing would."""
    worktree.git("checkout", "-q", "-b", "main-ahead", "origin/main", cwd=repo)
    commit(repo, "README", readme, "main moves")
    worktree.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=repo)
    worktree.git("fetch", "-q", "origin", cwd=repo)
    worktree.git("checkout", "-q", "work", cwd=repo)


def test_a_clean_rebase_over_another_file_keeps_the_diff_id(tmp_path: Path) -> None:
    """#417's ground: the range hashed is the range landed, and a clean replay is byte-equal."""
    repo = init_repo(tmp_path)
    worktree.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=repo)
    worktree.git("fetch", "-q", "origin", cwd=repo)
    worktree.git("checkout", "-q", "-b", "work", cwd=repo)
    commit(repo, "README", "two", "work")
    reviewed = head_of(repo)
    reviewed_id = review_exchange.diff_id_of(repo, reviewed)
    assert isinstance(reviewed_id, str)

    # `origin/main` moves on a file the work never touches, and the rebase replays.
    worktree.git("checkout", "-q", "-b", "main-ahead", "origin/main", cwd=repo)
    commit(repo, "elsewhere", "unrelated", "main moves on")
    worktree.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=repo)
    worktree.git("fetch", "-q", "origin", cwd=repo)
    worktree.git("checkout", "-q", "work", cwd=repo)
    worktree.git(
        "-c", "user.email=t@example", "-c", "user.name=t", "rebase", "origin/main", cwd=repo
    )

    rebased = head_of(repo)
    assert rebased != reviewed  # the SHA moved...
    assert review_exchange.diff_id_of(repo, rebased) == reviewed_id  # ...the diff did not


def test_a_clean_rebase_keeps_the_diff_id_where_main_edits_the_context(
    tmp_path: Path,
) -> None:
    """The review's High disproof, held as a test.

    An upstream edit inside the lines a context-bearing hash would fold in must not
    refuse the carry. The first build hashed `git patch-id`, which hashes context, so a sibling
    landing three lines away in the same file changed the id though the branch's
    own edit was untouched — refusing the very carry the mechanism existed to
    grant. `-U0` carries no context: only the added and removed lines are hashed,
    so this rebase keeps the identity and the review carries.
    """
    repo, reviewed = staged_review(tmp_path, readme="one\nline 2\nline 3\nline 4\nline 5\nline 6")
    reviewed_id = review_exchange.diff_id_of(repo, reviewed)
    assert isinstance(reviewed_id, str)

    # Main rewrites line 4 — three lines below the work's line-1 edit, inside the
    # three context lines `git patch-id` hashes, outside every `-U0` hunk.
    move_main(repo, readme="one\nline 2\nline 3\nLINE FOUR\nline 5\nline 6")
    worktree.git(
        "-c", "user.email=t@example", "-c", "user.name=t", "rebase", "origin/main", cwd=repo
    )

    rebased = head_of(repo)
    assert rebased != reviewed
    assert review_exchange.diff_id_of(repo, rebased) == reviewed_id


def test_a_conflict_resolved_rebase_changes_the_diff_id(tmp_path: Path) -> None:
    """A hand that resolved a conflict changed the diff, and the binding notices.

    The one rebase that must force a re-review rather than carry one across.
    """
    repo, reviewed = staged_review(tmp_path, readme="one\nline 2\nline 3\nline 4\nline 5\nline 6")
    reviewed_id = review_exchange.diff_id_of(repo, reviewed)
    assert isinstance(reviewed_id, str)

    # `origin/main` takes the same line, the rebase conflicts, a hand resolves it.
    move_main(repo, readme="three\nline 2\nline 3\nline 4\nline 5\nline 6")
    worktree.git(
        "-c",
        "user.email=t@example",
        "-c",
        "user.name=t",
        "rebase",
        "origin/main",
        cwd=repo,
        check=False,
    )  # conflicts, as staged
    (repo / "README").write_text("a hand resolved it", encoding="utf-8")
    worktree.git("add", ".", cwd=repo)
    worktree.git(
        "-c",
        "user.email=t@example",
        "-c",
        "user.name=t",
        "-c",
        "core.editor=true",
        "rebase",
        "--continue",
        cwd=repo,
    )

    resolved = head_of(repo)
    assert resolved != reviewed
    changed = review_exchange.diff_id_of(repo, resolved)
    assert isinstance(changed, str)
    assert changed != reviewed_id


def test_a_whitespace_only_resolution_changes_the_diff_id(tmp_path: Path) -> None:
    """The first build's Critical disproof, held as a test that holds it.

    Round 3's Medium: the first draft of this test compared `one`→`two` against
    `three`→`a hand resolved it   `, whose non-whitespace content already
    differs — strip the spaces and it still passed, so it pinned nothing. Here
    the reviewed diff and the resolved one differ by whitespace alone: the
    sibling change on `origin/main` is itself whitespace-only, the hand keeps
    the work's line exactly, and the only byte distance between the two diffs is
    the trailing spaces on the removed line. `git patch-id --stable` strips
    whitespace, so under the first build this resolution cleared as "unchanged"
    and carried a review across a diff no reviewer had judged. The identity
    hashes the diff's bytes exactly, so it refuses here — and the
    recorded-clean-rebase half refuses it too, because no tool ran this rebase
    to completion on its own.
    """
    repo, reviewed = staged_review(tmp_path, readme="one\nline 2\nline 3\nline 4\nline 5\nline 6")
    reviewed_id = review_exchange.diff_id_of(repo, reviewed)
    assert isinstance(reviewed_id, str)

    # The sibling change rewrites the same line by whitespace alone, so the
    # conflict is real but the two bases differ only in trailing spaces.
    move_main(repo, readme="one  \nline 2\nline 3\nline 4\nline 5\nline 6")
    worktree.git(
        "-c",
        "user.email=t@example",
        "-c",
        "user.name=t",
        "rebase",
        "origin/main",
        cwd=repo,
        check=False,
    )  # conflicts, as staged
    # The hand keeps the work's line exactly: the resolved diff differs from the
    # reviewed one by the removed line's trailing spaces and nothing else.
    (repo / "README").write_text("two\nline 2\nline 3\nline 4\nline 5\nline 6", encoding="utf-8")
    worktree.git("add", ".", cwd=repo)
    worktree.git(
        "-c",
        "user.email=t@example",
        "-c",
        "user.name=t",
        "-c",
        "core.editor=true",
        "rebase",
        "--continue",
        cwd=repo,
    )

    resolved = head_of(repo)
    assert resolved != reviewed
    changed = review_exchange.diff_id_of(repo, resolved)
    assert isinstance(changed, str)
    assert changed != reviewed_id
    # And the carry would refuse on both halves, not only the identity: no tool
    # recorded this replay as clean.
    unproven = review_exchange.satisfies(
        review_exchange.Verdict(
            issue=332,
            reviewed_sha=reviewed,
            diff_id=reviewed_id,
            review_dispatch="d-1",
            reviewer_profile="opus-high",
            reviewer_lane="claude-native",
            findings=(),
            recorded_at="2026-08-18T10:00:00+00:00",
            alternates=(),
        ),
        resolved,
        changed,
        clean_rebase=False,
    )
    assert unproven is not None
    assert unproven.kind == "rebase_unproven"


def test_the_same_edit_in_a_different_function_changes_the_diff_id(tmp_path: Path) -> None:
    """Round 3's Critical disproof, anchor half, held as a test.

    Flattening the whole hunk header erased the section anchor after the line
    numbers, so the same one-line edit made in a different function hashed equal
    to the reviewed one — a recorded clean rebase could then satisfy the
    provenance half while the identity hid a changed diff. Only the ranges name
    the base; the anchor is content.
    """
    code = "def alpha():\n    return 1\n\n\ndef beta():\n    return 1\n"
    repo = init_repo(tmp_path)
    commit(repo, "code.py", code, "code")
    worktree.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=repo)
    worktree.git("fetch", "-q", "origin", cwd=repo)
    base = head_of(repo)

    ids = []
    for which in ("alpha", "beta"):
        worktree.git("checkout", "-q", base, cwd=repo)
        worktree.git("checkout", "-q", "-b", which, cwd=repo)
        (repo / "code.py").write_text(
            code.replace(f"def {which}():\n    return 1", f"def {which}():\n    return 2", 1),
            encoding="utf-8",
        )
        worktree.git("add", ".", cwd=repo)
        worktree.git(
            "-c", "user.email=t@example", "-c", "user.name=t", "commit", "-q", "-m", which, cwd=repo
        )
        identity = review_exchange.diff_id_of(repo, head_of(repo))
        assert isinstance(identity, str)
        ids.append(identity)

    # Both diffs carry the same removed and added lines; only the anchor names
    # which function each sits in, and the identity must hear it.
    assert ids[0] != ids[1]


def test_different_binary_changes_to_one_path_change_the_diff_id(tmp_path: Path) -> None:
    """Round 3's Critical disproof, binary half, held as a test.

    A binary change's diff has no content lines: the changed bytes exist only as
    blob hashes on the `index` line, which the previous normalisation flattened
    whole — so two different binary changes to the same path hashed equal, and a
    changed diff could hide behind a recorded clean rebase. Where what follows
    the `index` line says the change is binary, the line stays byte for byte.
    """
    repo = init_repo(tmp_path)
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02")
    worktree.git("add", ".", cwd=repo)
    worktree.git(
        "-c", "user.email=t@example", "-c", "user.name=t", "commit", "-q", "-m", "bin", cwd=repo
    )
    worktree.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=repo)
    worktree.git("fetch", "-q", "origin", cwd=repo)
    base = head_of(repo)

    ids = []
    for content in (b"\x00\x01\x03", b"\x00\x01\x05"):
        worktree.git("checkout", "-q", base, cwd=repo)
        worktree.git("checkout", "-q", "-b", f"b{content[-1]}", cwd=repo)
        (repo / "blob.bin").write_bytes(content)
        worktree.git("add", ".", cwd=repo)
        worktree.git(
            "-c",
            "user.email=t@example",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "bytes",
            cwd=repo,
        )
        identity = review_exchange.diff_id_of(repo, head_of(repo))
        assert isinstance(identity, str)
        ids.append(identity)

    assert ids[0] != ids[1]


def test_a_binary_change_never_carries_though_a_clean_rebase_keeps_its_diff_id(
    tmp_path: Path,
) -> None:
    """A sibling landing elsewhere leaves a binary identity alone — and it still refuses.

    The identity half is unchanged: the pre-image blob names the base, only a
    same-file edit rewrites it, and a sibling landing elsewhere leaves both blobs
    what they were. What is gone is the argument that made the kept line safe (#419)
    — the carry refuses `binary_diff_uncarried` whatever the identity says, which is
    what this arrangement asserts, because this is the arrangement that carried.
    """
    repo = init_repo(tmp_path)
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02")
    worktree.git("add", ".", cwd=repo)
    worktree.git(
        "-c", "user.email=t@example", "-c", "user.name=t", "commit", "-q", "-m", "bin", cwd=repo
    )
    worktree.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=repo)
    worktree.git("fetch", "-q", "origin", cwd=repo)
    worktree.git("checkout", "-q", "-b", "work", cwd=repo)
    (repo / "blob.bin").write_bytes(b"\x00\x01\x07")
    worktree.git("add", ".", cwd=repo)
    worktree.git(
        "-c", "user.email=t@example", "-c", "user.name=t", "commit", "-q", "-m", "work", cwd=repo
    )
    reviewed = head_of(repo)
    reviewed_id = review_exchange.diff_id_of(repo, reviewed)
    assert isinstance(reviewed_id, str)

    # `origin/main` moves on a file the work never touches, and the rebase replays.
    worktree.git("checkout", "-q", "-b", "main-ahead", "origin/main", cwd=repo)
    commit(repo, "elsewhere", "unrelated", "main moves on")
    worktree.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=repo)
    worktree.git("fetch", "-q", "origin", cwd=repo)
    worktree.git("checkout", "-q", "work", cwd=repo)
    worktree.git(
        "-c", "user.email=t@example", "-c", "user.name=t", "rebase", "origin/main", cwd=repo
    )

    rebased = head_of(repo)
    landing_id = review_exchange.diff_id_of(repo, rebased)
    assert rebased != reviewed
    assert landing_id == reviewed_id

    refusal = review_exchange.satisfies(
        verdict(reviewed_sha=reviewed, diff_id=reviewed_id), rebased, landing_id, clean_rebase=True
    )
    assert refusal is not None
    assert refusal.kind == "binary_diff_uncarried"


def test_a_same_file_binary_edit_replays_clean_and_moves_both_blobs(tmp_path: Path) -> None:
    """The counter-example that took the exemption out (#419, fourth review of #417).

    `.gitattributes` decides both what git compares as bytes and how git merges it,
    and the two are independent: `*.bin -diff merge=union` gives a path git calls
    binary in every diff and merges line-wise anyway. So a same-file binary edit on
    both sides of a rebase **does** replay clean, and it rewrites both blob hashes
    of the very `index` line the normalisation keeps — the base-dependence the
    identity exists to remove. The carry is refused by name rather than left to
    whatever those hashes happen to say.
    """
    lines = "a\nb\nc\nd\ne\nf\ng\nh\n"
    repo = init_repo(tmp_path)
    (repo / ".gitattributes").write_text("*.bin -diff merge=union\n", encoding="utf-8")
    commit(repo, "blob.bin", lines, "bin")
    worktree.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=repo)
    worktree.git("fetch", "-q", "origin", cwd=repo)
    base_blob = worktree.git("rev-parse", "HEAD:blob.bin", cwd=repo).strip()

    worktree.git("checkout", "-q", "-b", "work", cwd=repo)
    commit(repo, "blob.bin", lines.replace("a\n", "A2\n", 1), "work edits the head")
    reviewed = head_of(repo)
    reviewed_id = review_exchange.diff_id_of(repo, reviewed)
    reviewed_blob = worktree.git("rev-parse", "HEAD:blob.bin", cwd=repo).strip()

    # `origin/main` moves on the *same* file, at the other end of it.
    worktree.git("checkout", "-q", "-b", "main-ahead", "origin/main", cwd=repo)
    commit(repo, "blob.bin", lines.replace("h\n", "H2\n", 1), "main edits the tail")
    worktree.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=repo)
    worktree.git("fetch", "-q", "origin", cwd=repo)
    worktree.git("checkout", "-q", "work", cwd=repo)
    worktree.git(
        "-c", "user.email=t@example", "-c", "user.name=t", "rebase", "origin/main", cwd=repo
    )

    # The replay ran clean and both blobs moved: the merged file carries both edits,
    # so neither the pre-image nor the post-image of the kept `index` line survives.
    rebased = head_of(repo)
    merged = (repo / "blob.bin").read_text(encoding="utf-8")
    assert "A2" in merged
    assert "H2" in merged
    assert worktree.git("rev-parse", "origin/main:blob.bin", cwd=repo).strip() != base_blob
    assert worktree.git("rev-parse", "HEAD:blob.bin", cwd=repo).strip() != reviewed_blob

    landing_id = review_exchange.diff_id_of(repo, rebased)
    assert isinstance(reviewed_id, str)
    assert isinstance(landing_id, str)
    assert landing_id.startswith(review_exchange.BINARY_DIFF_TAG)
    refusal = review_exchange.satisfies(
        verdict(reviewed_sha=reviewed, diff_id=reviewed_id), rebased, landing_id, clean_rebase=True
    )
    assert refusal is not None
    assert refusal.kind == "binary_diff_uncarried"


def test_a_binary_identity_refuses_a_carry_whichever_side_carries_the_tag() -> None:
    # The tag rides the recorded value as well as the landing one, so a verdict
    # recorded over a binary diff refuses even where the asking side reads as
    # textual — and the exact SHA still clears, which is the fresh review's path.
    tagged = review_exchange.BINARY_DIFF_TAG + DIFF_ID
    for recorded, asked in ((tagged, DIFF_ID), (DIFF_ID, tagged), (tagged, tagged)):
        refusal = review_exchange.satisfies(
            verdict(diff_id=recorded), OTHER_SHA, asked, clean_rebase=True
        )
        assert refusal is not None
        assert refusal.kind == "binary_diff_uncarried"
    assert review_exchange.satisfies(verdict(diff_id=tagged), SHA) is None


# ------------------------------------------------------------------ invocation


def cli_record(tmp_path: Path, root: Path, sha: str) -> int:
    """Record one verdict through the CLI, as the orchestrator would.

    `record` computes the diff identity itself from `--repo` (#417), so every CLI
    test drives it against a throwaway repository whose `origin/main` exists —
    never this checkout, whose fetch would reach the real remote.
    """
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
            "--repo",
            str(tmp_path / "repo"),
            "--dispatch-dir",
            str(root),
        ]
    )


def cli_stage(tmp_path: Path) -> tuple[Path, Path, str]:
    """Build the repository and records a CLI record needs: a real reviewed commit."""
    repo, head = ahead_repo(tmp_path)
    root = tmp_path / "dispatches"
    dispatch_dir(root, "d-1", base_sha=head)
    return repo, root, head


def test_cli_records_shows_and_prints_the_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo, root, head = cli_stage(tmp_path)
    assert cli_record(tmp_path, root, sha=head) == 0
    assert review_exchange.SAME_USER_LIMIT in capsys.readouterr().out
    # The diff identity on the record is the one the hash computed, never a typed value.
    recorded = json.loads((root / "d-1" / "verdict.json").read_text(encoding="utf-8"))
    assert review_exchange.DIFF_ID.fullmatch(recorded["diff_id"])
    shown_ok = review_exchange.main(
        ["show", "d-1", "--satisfies", head, "--dispatch-dir", str(root)]
    )
    assert shown_ok == 0
    shown = capsys.readouterr().out
    assert f"satisfies={head} yes" in shown
    assert review_exchange.SAME_USER_LIMIT in shown


def test_cli_record_refuses_a_sha_that_names_no_commit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, root, _reachable = cli_stage(tmp_path)

    assert cli_record(tmp_path, root, sha="f" * 40) == 1
    assert "refusal=commit_not_found" in capsys.readouterr().err
    assert not (root / "d-1" / review_exchange.VERDICT_NAME).exists()


def test_cli_record_pins_the_shared_invalid_sha_refusal_before_fetch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, root, head = cli_stage(tmp_path)
    worktree.git("remote", "set-url", "origin", str(tmp_path / "missing.git"), cwd=repo)

    assert cli_record(tmp_path, root, sha=head[:32]) == 1
    refusal = capsys.readouterr().err
    assert "refusal=invalid_sha" in refusal
    assert (
        "action=Name the reviewed commit in full — a commit is named by its full"
        " 40-character SHA, never a shortened form."
    ) in refusal
    assert "git_failed" not in refusal
    assert not (root / "d-1" / review_exchange.VERDICT_NAME).exists()


def test_cli_record_refuses_an_orphaned_commit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, root, referenced = cli_stage(tmp_path)
    commit(repo, "README", "orphaned", "orphaned")
    orphaned = head_of(repo)
    worktree.git("reset", "-q", "--hard", referenced, cwd=repo)

    assert cli_record(tmp_path, root, sha=orphaned) == 1
    assert "refusal=commit_unreachable" in capsys.readouterr().err
    assert not (root / "d-1" / review_exchange.VERDICT_NAME).exists()


def test_cli_record_reports_a_failed_ref_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, root, head = cli_stage(tmp_path)

    def fail(_repo: Path, _sha: str) -> None:
        raise review_exchange.worktree.GitError(("for-each-ref",), "broken ref store")

    monkeypatch.setattr(review_exchange.worktree, "validate_referenced_commit", fail)

    assert cli_record(tmp_path, root, sha=head) == 1
    refusal = capsys.readouterr().err
    assert "refusal=git_failed" in refusal
    assert "broken ref store" in refusal
    assert not (root / "d-1" / review_exchange.VERDICT_NAME).exists()


def cli_rebased(tmp_path: Path, head: str) -> Path:
    """Return a review root whose recorded clean rebase carries `head` to the landing SHA."""
    review_root = tmp_path / "review"
    review_exchange.record_rebase(
        review_root,
        332,
        review_exchange.RebaseLink(head, OTHER_SHA, THIRD_SHA, "2026-08-18T10:00:00+00:00"),
    )
    return review_root


def test_cli_show_carries_a_moved_sha_on_a_recorded_clean_rebase(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo, root, head = cli_stage(tmp_path)
    assert cli_record(tmp_path, root, sha=head) == 0
    recorded = json.loads((root / "d-1" / "verdict.json").read_text(encoding="utf-8"))
    capsys.readouterr()
    code = review_exchange.main(
        [
            "show",
            "d-1",
            "--satisfies",
            OTHER_SHA,
            "--diff-id",
            recorded["diff_id"],
            "--review-root",
            str(cli_rebased(tmp_path, head)),
            "--dispatch-dir",
            str(root),
        ]
    )
    assert code == 0
    shown = capsys.readouterr().out
    assert f"satisfies={OTHER_SHA} yes carried_by=diff_id" in shown
    assert review_exchange.DIFF_ID_LIMIT in shown


def test_cli_show_of_a_moved_sha_without_a_recorded_clean_rebase_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo, root, head = cli_stage(tmp_path)
    assert cli_record(tmp_path, root, sha=head) == 0
    recorded = json.loads((root / "d-1" / "verdict.json").read_text(encoding="utf-8"))
    capsys.readouterr()
    code = review_exchange.main(
        [
            "show",
            "d-1",
            "--satisfies",
            OTHER_SHA,
            "--diff-id",
            recorded["diff_id"],
            "--review-root",
            str(tmp_path / "review"),
            "--dispatch-dir",
            str(root),
        ]
    )
    assert code == 1
    assert "refusal=rebase_unproven" in capsys.readouterr().err


def test_cli_show_of_a_mismatched_sha_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo, root, head = cli_stage(tmp_path)
    assert cli_record(tmp_path, root, sha=head) == 0
    capsys.readouterr()
    code = review_exchange.main(
        [
            "show",
            "d-1",
            "--satisfies",
            OTHER_SHA,
            "--diff-id",
            OTHER_DIFF_ID,
            "--review-root",
            str(cli_rebased(tmp_path, head)),
            "--dispatch-dir",
            str(root),
        ]
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
    _repo, head = ahead_repo(tmp_path)
    root = tmp_path / "dispatches"
    root.mkdir()
    assert cli_record(tmp_path, root, sha=head) == 1
    assert "refusal=no_review_dispatch" in capsys.readouterr().err
    assert list(root.iterdir()) == []
