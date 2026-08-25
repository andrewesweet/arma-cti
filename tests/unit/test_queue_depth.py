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
from test_queue import in_flight_of, package_document, parsed, store_at

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
    candidate_refusal: Any = None,  # noqa: ANN401 — a tools/ module loads dynamically, so its type is not named here
    policy: Any = None,  # noqa: ANN401 — a tools/ module loads dynamically, so its types are not names here
    in_flight: Any = None,  # noqa: ANN401 — same
    review_root: Path,
    dispatch_dir: Path,
    approvals: Path,
    at: float = OFF_BAND,
    terminus_lines: list[str] | None = None,
) -> tuple[queue_depth.Sample, ...]:
    """Run one sample over a review root, dispatch dir and approvals dir of the test's own."""
    return queue_depth.sample(
        store_at(Path(review_root).parent),
        parsed() if policy is None else policy,
        in_flight_of() if in_flight is None else in_flight,
        candidates,
        candidate_refusal=candidate_refusal,
        dispatch_dir=dispatch_dir,
        review_root=review_root,
        approvals=approvals,
        at=at,
        terminus_lines=terminus_lines,
    )


def journalled_samples(store_directory: Path) -> list[dict[str, Any]]:
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


def test_dispatch_slot_counts_wip_refused_candidates_at_full_capacity(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    samples = sample_with(
        candidates=candidates_of(301, 302),
        policy=parsed(state="open", limit=2),
        in_flight=in_flight_of(299, 300),
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
    )
    slot = samples_by_queue(samples)["dispatch_slot"]
    assert (slot.state, slot.count, slot.oldest) == ("counted", 2, "unrecorded")


def test_a_package_reservation_holds_eligible_work_the_room_arithmetic_missed(
    tmp_path: Path,
) -> None:
    # One reservation unexhausted against issue 301, which no package carries:
    # limit 3, in flight 221 (the package's) and 299, so the rung's available is
    # 3 - 2 - 1 = 0 while the bare room arithmetic said 3 - 2 = 1 slot open.
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    policy = parsed(state="open", limit=3, packages=[package_document(wip_reserved=2)])
    in_flight = in_flight_of(221, 299)
    candidates = candidates_of(301)
    samples = sample_with(
        candidates=candidates,
        policy=policy,
        in_flight=in_flight,
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
    )
    slot = samples_by_queue(samples)["dispatch_slot"]
    assert (slot.state, slot.count, slot.oldest) == ("counted", 1, "unrecorded")
    # Parity with `select` itself: the same inputs, and the rung that refuses
    # there is the rung that counted here.
    selection = queue_policy.select(policy, candidates, in_flight, 1)
    assert "considered.301=reserved-for-package" in selection.considered


def test_a_frozen_candidate_waits_on_no_slot(tmp_path: Path) -> None:
    # Frozen policy, two candidates carved out and one not: the full list holds
    # the carved-out candidates, and the frozen one must not join them — the same
    # drop `select` states, staged through the sampler.
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    policy = parsed(limit=2, packages=[package_document(issues=[302, 303])])
    in_flight = in_flight_of(299, 300)
    candidates = candidates_of(301, 302, 303)
    samples = sample_with(
        candidates=candidates,
        policy=policy,
        in_flight=in_flight,
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
    )
    slot = samples_by_queue(samples)["dispatch_slot"]
    assert (slot.state, slot.count, slot.oldest) == ("counted", 2, "unrecorded")
    selection = queue_policy.select(policy, candidates, in_flight, 1)
    assert "considered.301=frozen-and-not-carved-out" in selection.considered
    assert "considered.302=eligible" in selection.considered


def test_a_blocked_candidate_waits_on_no_slot(tmp_path: Path) -> None:
    # The blocked boundary, same parity: a full list holds the two clean
    # candidates, while the blocked candidate never counts even with room at zero.
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    policy = parsed(state="open", limit=2)
    in_flight = in_flight_of(299, 300)
    candidates = (
        queue_policy.Candidate(301, "issue 301", "Blocked-by: #9"),
        queue_policy.Candidate(302, "issue 302"),
        queue_policy.Candidate(303, "issue 303"),
    )
    samples = sample_with(
        candidates=candidates,
        policy=policy,
        in_flight=in_flight,
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
    )
    slot = samples_by_queue(samples)["dispatch_slot"]
    assert (slot.state, slot.count, slot.oldest) == ("counted", 2, "unrecorded")
    selection = queue_policy.select(policy, candidates, in_flight, 1)
    assert "considered.301=blocked-by-9" in selection.considered
    assert "considered.302=eligible" in selection.considered


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


def test_a_candidate_refusal_is_unrecorded_and_carries_its_reason(tmp_path: Path) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    refusal = queue_policy.Refusal(
        "github_unreadable",
        ("read=failed",),
        "restore the tracker read",
        failure_class="infra_unavailable",
    )
    samples = sample_with(
        candidates=None,
        candidate_refusal=refusal,
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
        at=IN_BAND,
    )
    by_queue = samples_by_queue(samples)
    for name in ("ready_work", "dispatch_slot", "lane_window"):
        assert (
            by_queue[name].state,
            by_queue[name].count,
            by_queue[name].oldest,
            by_queue[name].reason,
        ) == ("unrecorded", None, "unrecorded", "github_unreadable")

    lines = journalled_samples(store_at(tmp_path).directory)
    for line in lines:
        if line["attributes"]["cti.queue.depth.queue"] in {
            "ready_work",
            "dispatch_slot",
            "lane_window",
        }:
            assert line["attributes"]["cti.queue.depth.state"] == "unrecorded"
            assert line["attributes"]["cti.queue.depth.reason"] == "github_unreadable"


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


def test_terminus_prompt_rendering_distinguishes_due_blocked_and_incomplete() -> None:
    prompts = (
        review_loop.TerminusPrompt(issue=301, findings=1, open_above_low=0, incomplete=False),
        review_loop.TerminusPrompt(issue=302, findings=2, open_above_low=1, incomplete=False),
        review_loop.TerminusPrompt(issue=303, findings=2, open_above_low=0, incomplete=True),
    )

    assert queue_depth.render_terminus_prompts(prompts) == (
        (
            "review_terminus=due issue=301 findings=1 open_above_low=0 "
            'action="just review-loop terminus --issue 301"'
        ),
        (
            "review_terminus=blocked issue=302 findings=2 open_above_low=1 "
            'action="adjudicate or escalate before terminus"'
        ),
        (
            "review_terminus=incomplete issue=303 findings=2 open_above_low=0 "
            'action="account for pending posts before retrying"'
        ),
    )
    assert queue_depth.render_terminus_prompts(None) == (
        'review_terminus=unreadable action="repair review state before relying on closeout prompt"',
    )


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


def test_an_unreadable_rounds_journal_renders_a_failed_source_not_an_absent_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The journal is present and carries the raising round — only the read
    # fails — so the age's source failed rather than went missing, and the
    # sample must say unreadable where `or {}` once rendered every age
    # `unrecorded` beside a counted depth.
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    open_loop(review_root, 301, findings=1)
    journal = review_root / queue_depth.REVIEW_JOURNAL_NAME
    journal.write_text(round_line(301, 0, OFF_BAND - 1_800) + "\n", encoding="utf-8")
    real_read_text = Path.read_text

    def unreadable(
        target: Path,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> str:
        if target == journal:
            raise OSError
        return real_read_text(target, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "read_text", unreadable)
    lines: list[str] = []
    samples = sample_with(
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
        terminus_lines=lines,
    )

    ruling = samples_by_queue(samples)["human_ruling"]
    assert (ruling.state, ruling.count, ruling.oldest) == ("unreadable", None, "unrecorded")
    # The prompts the loops did read still render beside the failed source.
    assert lines == [
        (
            "review_terminus=blocked issue=301 findings=1 open_above_low=1 "
            'action="adjudicate or escalate before terminus"'
        )
    ]


def test_one_unreadable_loop_neither_suppresses_the_readable_prompts_nor_hides_its_name(
    tmp_path: Path,
) -> None:
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    open_loop(review_root, 301, findings=1)
    open_loop(review_root, 303, findings=0)
    damaged = review_root / "302"
    damaged.mkdir()
    (damaged / review_loop.LOOP_FILE).write_text("{ not json", encoding="utf-8")
    lines: list[str] = []

    samples = sample_with(
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
        terminus_lines=lines,
    )

    assert samples_by_queue(samples)["human_ruling"].state == "unreadable"
    assert tuple(lines) == (
        (
            "review_terminus=blocked issue=301 findings=1 open_above_low=1 "
            'action="adjudicate or escalate before terminus"'
        ),
        (
            "review_terminus=due issue=303 findings=0 open_above_low=0 "
            'action="just review-loop terminus --issue 303"'
        ),
        (
            "review_terminus=unreadable path=302/loop.json "
            'action="repair this loop before relying on its closeout prompt"'
        ),
    )
    # The per-file action distrusts the loop the path names, not the whole
    # read — the root-level line keeps that wider wording (#567).
    assert (
        queue_depth.render_terminus_prompts(None)[0].split("action=")[1]
        != lines[-1].split("action=")[1]
    )


def test_an_exception_escaping_the_walk_fails_open_not_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `sample()` computes this reading above its per-queue catch, so the reader
    # holds the fail-open contract `sample()`'s docstring advertises: what
    # escapes the walk's own `(OSError, ValueError)` ladder is one unreadable
    # queue and an absent terminus, never the loss of all seven samples (#567).
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    open_loop(review_root, 301, findings=1)

    def exploding(*_args: object, **_kwargs: object) -> object:
        message = "past the walk's own ladders"
        raise RuntimeError(message)

    monkeypatch.setattr(queue_depth.review_loop, "terminus_prompt", exploding)
    lines: list[str] = []
    samples = sample_with(
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
        terminus_lines=lines,
    )

    assert [sample.queue for sample in samples] == list(attribute_registry.QUEUES)
    assert samples_by_queue(samples)["human_ruling"].state == "unreadable"
    assert tuple(lines) == queue_depth.render_terminus_prompts(None)


def test_prompts_render_in_numeric_issue_order_across_the_width_boundary(
    tmp_path: Path,
) -> None:
    # "1000" sorts before "999" lexicographically, so the first issue past
    # three digits is where directory order stops being issue order (#567).
    review_root, dispatch_dir, approvals = empty_sources(tmp_path)
    open_loop(review_root, 999, findings=0)
    open_loop(review_root, 1000, findings=0)
    lines: list[str] = []

    sample_with(
        review_root=review_root,
        dispatch_dir=dispatch_dir,
        approvals=approvals,
        terminus_lines=lines,
    )

    assert [line.split(" ")[1] for line in lines] == ["issue=999", "issue=1000"]


def test_a_missing_review_root_surfaces_an_unreadable_terminus_prompt(tmp_path: Path) -> None:
    dispatch_dir = tmp_path / "dispatches"
    dispatch_dir.mkdir()
    approvals = tmp_path / "approvals"
    approvals.mkdir()
    lines: list[str] = []

    samples = sample_with(
        review_root=tmp_path / "missing-review",
        dispatch_dir=dispatch_dir,
        approvals=approvals,
        terminus_lines=lines,
    )

    assert samples_by_queue(samples)["human_ruling"].state == "unreadable"
    assert tuple(lines) == queue_depth.render_terminus_prompts(None)


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
