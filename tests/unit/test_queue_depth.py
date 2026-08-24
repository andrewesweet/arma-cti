"""The seven-queue depth sampler (#492).

Every test's arrangement stages the records one queue reads, and the claim is
the sample those records make: counted depths — zero included — ages only where
a record carries the entry instant, and `unrecorded`/`unreadable` where no
number exists to read. The one defect this suite exists to falsify is the one
this store has hit three times in two days (#485, #490, #491): absence
rendering as a healthy value, so an idle or damaged source reads as zero.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from conftest import load_tool
from test_queue import in_flight_of, parsed, store_at

attribute_registry = load_tool("attribute_registry")
breaker = load_tool("breaker")
gated_paths = load_tool("gated_paths")
queue_depth = load_tool("queue_depth")
queue_policy = load_tool("queue_policy")
review_loop = load_tool("review_loop")

# Two fixed instants on Monday 2026-08-24: 15:30 SGT is inside the zai peak
# band, 10:30 SGT is outside it. The band membership is asserted as arrangement,
# never assumed — the constants are the clock's, and the sampler reads the
# breaker's own schedule.
IN_BAND = datetime(2026, 8, 24, 7, 30, tzinfo=UTC).timestamp()
OFF_BAND = datetime(2026, 8, 24, 2, 30, tzinfo=UTC).timestamp()

GATED_FILE = "CONTEXT.md"


def wait_line(reason: str, at: float, *, issue: int | None = None) -> str:
    """One waits-journal line, in the shape `otel_event.emit` writes."""
    attributes: dict[str, object] = {
        "cti.wait.block_reason": reason,
        "cti.wait.surface": "dispatch",
    }
    if issue is not None:
        attributes["cti.issue"] = issue
    return json.dumps(
        {
            "event": attribute_registry.WAIT_EVENT,
            "at": at,
            "attributes": attributes,
            "resource": {"service.name": "test"},
            "exported": False,
            "export_detail": "test",
        },
        sort_keys=True,
    )


def round_line(issue: int, number: int, at: float) -> str:
    """One review-journal round event, in the shape `emit_round` writes."""
    return json.dumps(
        {
            "event": review_loop.ROUND_EVENT,
            "at": at,
            "attributes": {
                "cti.issue": str(issue),
                "cti.review.round": number,
                "cti.review.raised": 0,
                "cti.review.open_above_low": 0,
                "cti.review.holding_above_low": False,
            },
            "resource": {"service.name": "test"},
            "exported": False,
            "export_detail": "test",
        },
        sort_keys=True,
    )


def candidates_of(*issues: int) -> tuple[queue_policy.Candidate, ...]:
    """One ready candidate per issue, with nothing else on its body."""
    return tuple(queue_policy.Candidate(issue, f"issue {issue}") for issue in issues)


def samples_by_queue(samples: tuple[queue_depth.Sample, ...]) -> dict[str, queue_depth.Sample]:
    """Return the samples as a map, so a test names the queue it is reading."""
    return {sample.queue: sample for sample in samples}


def sample_with(  # noqa: PLR0913 — the parameters are the seven queues' sources, staged whole so each test states only what it varies
    *,
    candidates: tuple[queue_policy.Candidate, ...] | None = (),
    policy: Any = None,  # noqa: ANN401 — a tools/ module loads dynamically, so its types are not names here
    in_flight: Any = None,  # noqa: ANN401 — same
    review_root: Path,
    dispatch_dir: Path,
    approvals: Path,
    at: float = OFF_BAND,
) -> tuple[queue_depth.Sample, ...]:
    """Run one sample over a review root, dispatch dir and approvals dir of the test's own."""
    return queue_depth.sample(
        store_at(Path(review_root).parent),
        parsed() if policy is None else policy,
        in_flight_of() if in_flight is None else in_flight,
        candidates,
        dispatch_dir=dispatch_dir,
        review_root=review_root,
        approvals=approvals,
        at=at,
    )


def journalled_samples(store_directory: Path) -> list[dict[str, object]]:
    """Read the sampler's own journal back as documents."""
    path = store_directory / attribute_registry.QUEUE_DEPTH_JOURNAL
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def empty_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Return a review root, dispatch dir and approvals dir holding nothing at all."""
    review_root = tmp_path / "review"
    review_root.mkdir()
    dispatch_dir = tmp_path / "dispatches"
    dispatch_dir.mkdir()
    approvals = tmp_path / "approvals"
    approvals.mkdir()
    return review_root, dispatch_dir, approvals


# ------------------------------------------------------------------ the closed set


def test_every_queue_of_the_closed_set_samples_every_time(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    samples = sample_with(review_root=review_root, dispatch_dir=dispatch_dir, approvals=approvals)
    assert [sample.queue for sample in samples] == list(attribute_registry.QUEUES)


def test_an_idle_system_records_seven_empty_queues_not_nothing(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    samples = sample_with(review_root=review_root, dispatch_dir=dispatch_dir, approvals=approvals)
    by_queue = samples_by_queue(samples)
    # Six queues counted empty; the slot queue is the one queue with no source,
    # and it says so rather than wearing a zero.
    for name, sample in by_queue.items():
        if name == "slot_lock":
            assert (sample.state, sample.count, sample.oldest) == (
                "unrecorded",
                None,
                "unrecorded",
            )
        else:
            assert (sample.state, sample.count, sample.oldest) == ("counted", 0, "none")
    # And the journal carries one line per queue, so an un-sampled queue is a
    # missing line a reader can see, never a silence indistinguishable from zero.
    directory = store_at(tmp_path).directory
    lines = journalled_samples(directory)
    assert len(lines) == len(attribute_registry.QUEUES)
    assert {line["event"] for line in lines} == {attribute_registry.QUEUE_DEPTH_EVENT}


# ------------------------------------------------------------------ the ready queues


def test_ready_work_counts_labelled_issues_beyond_the_in_flight_set(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    samples = sample_with(
        candidates=candidates_of(301, 302, 303),
        in_flight=in_flight_of(302),
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
    )
    ready = samples_by_queue(samples)["ready_work"]
    assert (ready.state, ready.count) == ("counted", 2)
    # The label instant lives in the tracker's timeline, which no local record
    # carries — stated, never invented.
    assert ready.oldest == "unrecorded"


def test_dispatch_slot_holds_eligible_work_beyond_the_limit_s_room(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    samples = sample_with(
        candidates=candidates_of(301, 302),
        policy=parsed(state="open", limit=3),
        in_flight=in_flight_of(299, 300),
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
    )
    slot = samples_by_queue(samples)["dispatch_slot"]
    assert (slot.state, slot.count) == ("counted", 1)


def test_the_slot_queue_reads_zero_where_room_exists(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    samples = sample_with(
        candidates=candidates_of(301),
        policy=parsed(state="open", limit=3),
        in_flight=in_flight_of(299),
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
    )
    slot = samples_by_queue(samples)["dispatch_slot"]
    assert (slot.state, slot.count, slot.oldest) == ("counted", 0, "none")


def test_unreadable_candidates_render_unreadable_never_zero(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    samples = sample_with(
        candidates=None,
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
        at=IN_BAND,
    )
    by_queue = samples_by_queue(samples)
    for name in ("ready_work", "dispatch_slot", "lane_window"):
        assert by_queue[name].state == "unreadable"
        assert by_queue[name].count is None


# ------------------------------------------------------------------ the reviewer queue


def test_the_reviewer_queue_ages_from_the_exchange_s_own_wait(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    waits = review_root / "waits.jsonl"
    waits.write_text(
        wait_line(
            attribute_registry.REASON_WAITING_REVIEWER,
            OFF_BAND - 3_600,
            issue=301,
        )
        + "\n",
        encoding="utf-8",
    )
    samples = sample_with(review_root=review_root, dispatch_dir=dispatch_dir, approvals=approvals)
    reviewer = samples_by_queue(samples)["reviewer"]
    assert (reviewer.state, reviewer.count, reviewer.oldest) == ("counted", 1, "measured")
    assert reviewer.oldest_age_s == pytest.approx(3_600)


def test_a_round_after_the_wait_ends_it(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    (review_root / "waits.jsonl").write_text(
        wait_line(
            attribute_registry.REASON_WAITING_REVIEWER,
            OFF_BAND - 7_200,
            issue=301,
        )
        + "\n",
        encoding="utf-8",
    )
    (review_root / "journal.jsonl").write_text(
        round_line(301, 1, OFF_BAND - 3_600) + "\n", encoding="utf-8"
    )
    samples = sample_with(review_root=review_root, dispatch_dir=dispatch_dir, approvals=approvals)
    reviewer = samples_by_queue(samples)["reviewer"]
    assert (reviewer.state, reviewer.count, reviewer.oldest) == ("counted", 0, "none")


# ------------------------------------------------------------------ the human-ruling queue


def open_loop(review_root: Path, issue: int, *, findings: int = 1) -> None:
    """Write one running loop whose round-0 review raised the findings named."""
    raised = tuple(
        review_loop.Finding(f"f-{number}", review_loop.HIGH, 0) for number in range(findings)
    )
    directory = review_root / str(issue)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / review_loop.LOOP_FILE).write_text(
        json.dumps(review_loop.render_loop(issue, review_loop.first_review(raised))),
        encoding="utf-8",
    )


def landed_loop(review_root: Path, issue: int) -> None:
    """Write one closed loop — a terminus has run, so nothing there waits."""
    open_loop(review_root, issue, findings=0)
    directory = review_root / str(issue)
    (directory / review_loop.LANDING_FILE).write_text("{}", encoding="utf-8")


def test_open_above_low_findings_wait_and_age_from_the_raising_round(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    open_loop(review_root, 301, findings=2)
    (review_root / "journal.jsonl").write_text(
        round_line(301, 0, OFF_BAND - 1_800) + "\n", encoding="utf-8"
    )
    samples = sample_with(review_root=review_root, dispatch_dir=dispatch_dir, approvals=approvals)
    ruling = samples_by_queue(samples)["human_ruling"]
    assert (ruling.state, ruling.count, ruling.oldest) == ("counted", 2, "measured")
    assert ruling.oldest_age_s == pytest.approx(1_800)


def test_a_terminated_loop_waits_on_nothing(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    landed_loop(review_root, 301)
    samples = sample_with(review_root=review_root, dispatch_dir=dispatch_dir, approvals=approvals)
    ruling = samples_by_queue(samples)["human_ruling"]
    assert (ruling.state, ruling.count, ruling.oldest) == ("counted", 0, "none")


def test_findings_whose_raising_round_no_journal_carries_age_unrecorded(
    tmp_path: Path,
) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    open_loop(review_root, 301)
    samples = sample_with(review_root=review_root, dispatch_dir=dispatch_dir, approvals=approvals)
    ruling = samples_by_queue(samples)["human_ruling"]
    assert (ruling.state, ruling.count, ruling.oldest) == ("counted", 1, "unrecorded")
    assert ruling.oldest_age_s is None


def test_a_loop_that_will_not_read_renders_the_queue_unreadable(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    directory = review_root / "301"
    directory.mkdir()
    (directory / review_loop.LOOP_FILE).write_text("{ not json", encoding="utf-8")
    samples = sample_with(review_root=review_root, dispatch_dir=dispatch_dir, approvals=approvals)
    ruling = samples_by_queue(samples)["human_ruling"]
    assert ruling.state == "unreadable"
    assert ruling.count is None


# ------------------------------------------------------------------ the lane-window queue


def test_an_open_band_holds_nothing_even_where_waits_stand(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    (dispatch_dir / "waits.jsonl").write_text(
        wait_line(attribute_registry.REASON_LANE_PEAK_BAND, IN_BAND - 600, issue=301) + "\n",
        encoding="utf-8",
    )
    samples = sample_with(
        candidates=candidates_of(301),
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
        at=OFF_BAND,
    )
    window = samples_by_queue(samples)["lane_window"]
    assert (window.state, window.count, window.oldest) == ("counted", 0, "none")


def test_a_closed_band_holds_ready_work_the_dispatcher_was_refused_for(
    tmp_path: Path,
) -> None:
    assert breaker.zai_is_peak(IN_BAND)  # the arrangement, asserted rather than assumed
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    band_start = breaker.zai_off_peak_opens_at(IN_BAND) - queue_depth.PEAK_BAND_HOURS * 3_600
    (dispatch_dir / "waits.jsonl").write_text(
        wait_line(attribute_registry.REASON_LANE_PEAK_BAND, band_start + 600, issue=301)
        + "\n"
        + wait_line(attribute_registry.REASON_LANE_PEAK_BAND, band_start + 900, issue=302)
        + "\n"
        # Before this band began: a wait from yesterday's band, not this one's.
        + wait_line(attribute_registry.REASON_LANE_PEAK_BAND, band_start - 600, issue=303)
        + "\n",
        encoding="utf-8",
    )
    samples = sample_with(
        candidates=candidates_of(301),
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
        at=IN_BAND,
    )
    window = samples_by_queue(samples)["lane_window"]
    # 302 is no longer a candidate — it moved on, and only 301 waits.
    assert (window.state, window.count, window.oldest) == ("counted", 1, "measured")


# ------------------------------------------------------------------ the landing queue


def gated_repo(tmp_path: Path, *paths: str) -> Path:
    """Stage a repo whose working tree touches the named paths against a clean origin/main."""
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "t@example.com"),
        ("config", "user.name", "T"),
    ):
        subprocess.run(["git", *args], cwd=repo, check=True)  # noqa: S603, S607 — fixture argv
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    for args in (
        ("add", "."),
        ("commit", "-qm", "chore: base"),
        ("update-ref", "refs/remotes/origin/main", "HEAD"),
    ):
        subprocess.run(["git", *args], cwd=repo, check=True)  # noqa: S603, S607 — the fixture's own argv
    for path in paths:
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"touched {path}\n", encoding="utf-8")
    return repo


def test_a_tree_touching_a_gated_path_without_an_approval_awaits_landing(
    tmp_path: Path,
) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    repo = gated_repo(tmp_path, GATED_FILE)
    in_flight = queue_policy.InFlight(
        holders=(queue_policy.Holder(301, ("worktree",), repo),),
        owed=(),
        github="read",
    )
    samples = sample_with(
        in_flight=in_flight,
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
    )
    landing = samples_by_queue(samples)["landing"]
    assert (landing.state, landing.count, landing.oldest) == ("counted", 1, "unrecorded")


def test_a_tree_touching_no_gated_path_awaits_no_landing(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    repo = gated_repo(tmp_path, "README.md")
    in_flight = queue_policy.InFlight(
        holders=(queue_policy.Holder(301, ("worktree",), repo),),
        owed=(),
        github="read",
    )
    samples = sample_with(
        in_flight=in_flight,
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
    )
    landing = samples_by_queue(samples)["landing"]
    assert (landing.state, landing.count, landing.oldest) == ("counted", 0, "none")


# ------------------------------------------------------------------ the slot-lock queue


def test_the_slot_queue_states_its_missing_source_rather_than_a_depth() -> None:
    sample = queue_depth._slot_lock_sample()  # noqa: SLF001 — the reader is the subject
    assert sample.queue == "slot_lock"
    assert (sample.state, sample.count, sample.oldest) == ("unrecorded", None, "unrecorded")
