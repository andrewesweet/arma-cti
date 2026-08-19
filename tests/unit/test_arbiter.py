"""The arbiter rule: one walk, one answer, refusals by name (#333, per the ruling on #361).

The two live cases the walk must survive are pinned as themselves: #318 (a retro
escalation with the seat's own authors on the records — the head still answers, because
the table names the arbiter and the walk does not start at the preference list) and #326
(the implementer's entry head refused by routing on the branch's own files — fell through
to the entry tail, exclusion recorded). Around them: the registry's transcription of the
ruling's cells, the exhausted and no-entry refusals, the unchecked mark every incomplete
read leaves, the records read `resolve_for_issue` drives (reviewers included, #361's
criterion), the live dispatchability rungs `resolve_dispatchable` walks, and the event
that makes an invocation countable.
"""
# arbiter-rule: stated — the authority's own test module (#390). Each claim above is the
# subject of an assertion below, so it goes red rather than drifting; a pointer
# here would name the module the file already imports and tests (#390).

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

arbiter = load_tool("arbiter")
# A second exec of review_loop, not the copy arbiter imported: two copies hold different
# module objects, which is exactly what the journal-constant test needs to compare — the
# re-exec identity discipline both modules document, narrowed on values.
review_loop = load_tool("review_loop")
# The copies arbiter itself imported, for the same discipline's reasons.
dispatch = arbiter.dispatch
routing_policy = arbiter.routing_policy

POLICY_TEXT = (REPO / routing_policy.POLICY_RELATIVE).read_text(encoding="utf-8")


def shipped_policy() -> routing_policy.Policy:
    """Parse the shipped policy.

    Against it the routing rung excludes nobody, because since ADR-0073 no row refuses a
    landing. That is the rung's inert arrangement, the one every walk below starts from
    unless a test plants a refusing row.
    """
    return routing_policy.parse_policy(POLICY_TEXT)


def refusing_policy() -> routing_policy.Policy:
    """Plant class 6 back to refusing — #326's own arrangement.

    ADR-0073 (#406) retired the last row that refused a landing, so the #326 shape — a
    head refused on the branch's own gate paths — is unreachable against the shipped
    document. The rung is kept and reads the policy as data, so its tests plant the row
    the same way `tests/unit/test_land.py`'s `_plant_refusing_policy` does: everything
    about the row stays the shipped file's except the one flag.
    """
    document = json.loads(POLICY_TEXT)
    for row in document[routing_policy.REFOUNDED.classes]:
        if row["id"] == routing_policy.CONFLICT_OF_INTEREST_CLASS_ID:
            row["refuses"] = True
    return routing_policy.parse_policy(json.dumps(document))


breaker = load_tool("breaker")


def authorship(
    potential: tuple[str, ...] = (),
    records: tuple[str, ...] = (),
    why: str = "",
) -> dispatch.Authorship:
    return dispatch.Authorship(potential, records, why)


def trip(tmp_path: Path, lane: str) -> None:
    """Open a lane's breaker in this test's own store, never in the box's.

    Three gate failures is the quality trip, which is `test_dispatch_seat.trip`'s shape; the
    instant is stepped so each outcome is its own, and no clock of this box's is read.
    """
    store = breaker.Store(directory=tmp_path / "breaker", endpoint="http://127.0.0.1:2999/v1/logs")
    for step in range(3):
        breaker.record_outcome(store, lane, breaker.Outcome(breaker.GATE_FAILED), 1.0 + step)


def complete_read(*profiles: str) -> dispatch.Authorship:
    """Build an authorship every record of which read: the only `unchecked=False` state.

    The records are named `d1..dN` in order, the shape `dispatch.potential_authors` builds
    from dispatch directories it could read in full.
    """
    return authorship(profiles, tuple(f"d{i}" for i in range(1, len(profiles) + 1)))


def record(
    dispatch_dir: Path,
    name: str,
    *,
    issue: int,
    profile: str,
    seat: str,
) -> None:
    """Write one dispatch record in the shape `_read_record` reads: `dispatch.json`."""
    entry = dispatch_dir / name
    entry.mkdir(parents=True)
    (entry / "dispatch.json").write_text(
        json.dumps({"issue": issue, "profile": profile, "seat": seat, "dispatch_id": name}),
        encoding="utf-8",
    )


# A Sunday midday UTC: outside z.ai's Mon-Fri 14:00-18:00 SGT peak band, so the off-peak
# rung is a fact the test states rather than a coin the wall clock flips.
SUNDAY = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- the registry cells


def test_the_ruled_cells_are_transcribed_head_first() -> None:
    """The human ruling on #361 (2026-08-14) filled exactly these — data, not derivation."""
    assert dispatch.SEATS["retro"].escalation == ("opus-max", "fable-max")
    assert dispatch.SEATS["orchestrator"].escalation == ("opus-max", "fable-xhigh")
    # The two not-applicable rows stay empty, and so does the fable seat #329/#330 own.
    assert dispatch.SEATS["recon"].escalation == ()
    assert dispatch.SEATS["fable"].escalation == ()


# --------------------------------------------------------------------------- resolution


def test_the_entry_head_answers_when_nothing_excludes_it() -> None:
    resolution = arbiter.resolve(
        dispatch.SEATS["retro"], complete_read("zai-glm53-max"), shipped_policy(), ()
    )
    assert resolution.kind == arbiter.RESOLVED
    assert resolution.arbiter == "opus-max"
    assert resolution.unchecked is False
    assert resolution.passed_over == ()


def test_the_walk_does_not_start_at_the_preference_list() -> None:
    """#318's shape: the seat's own authors and reviewer on the records — head unaffected.

    `fable-high` authored every round and `opus-xhigh` reviewed them; neither is the
    tabled head, so the table's answer stands and the preference list is never reached.
    """
    resolution = arbiter.resolve(
        dispatch.SEATS["retro"],
        authorship(("fable-high", "opus-xhigh"), ("d1", "d2")),
        shipped_policy(),
        (),
    )
    assert resolution.kind == arbiter.RESOLVED
    assert resolution.arbiter == "opus-max"
    assert resolution.passed_over == ()


def test_a_routing_refused_head_falls_through_to_the_entry_tail() -> None:
    """Fall through on #326's shape, derived rather than flagged since #391.

    Class 6 refused the head on the branch's own files; `opus-high` took it. The policy
    is planted back to refusing because the shipped one retires that row (ADR-0073) —
    the rung still reads it as data, and the exclusion's detail names the class and the
    matched path, the facts a caller's flag used to assert by hand.
    """
    resolution = arbiter.resolve(
        dispatch.SEATS["implementer"],
        authorship(),
        refusing_policy(),
        ("tools/dispatch.py",),
    )
    assert resolution.kind == arbiter.RESOLVED
    assert resolution.arbiter == "opus-high"
    assert resolution.passed_over == (
        arbiter.Exclusion(
            "codex-sol-high",
            arbiter.ROUTING_EXCLUSION,
            "routing_class=6:gates_themselves path=tools/dispatch.py",
        ),
    )


def test_the_claude_lane_walks_past_a_refusing_row_the_policy_exempts_it_from() -> None:
    """Walk the Claude lane past a refusing row the policy exempts it from.

    The other half of the same read: `_refusing_rules` clears the Claude lane of every
    row that is not seat-bound, so `opus-high` — same diff, Claude's lane — is not
    excluded by the row that refused the codex head. One policy, two lanes, two answers.
    """
    seat = dispatch.Seat(
        "synthetic",
        claude_only=False,
        preference=("codex-sol-high",),
        escalation=("opus-high", "codex-sol-high"),
    )
    resolution = arbiter.resolve(seat, authorship(), refusing_policy(), ("tools/dispatch.py",))
    assert resolution.arbiter == "opus-high"
    assert resolution.passed_over == ()


def test_a_records_placed_head_falls_through_the_same_way() -> None:
    resolution = arbiter.resolve(
        dispatch.SEATS["implementer"],
        authorship(("codex-sol-high",), ("d7",)),
        shipped_policy(),
        (),
    )
    assert resolution.kind == arbiter.RESOLVED
    assert resolution.arbiter == "opus-high"
    assert resolution.passed_over == (
        arbiter.Exclusion("codex-sol-high", arbiter.RECORDS_EXCLUSION, "records=d7"),
    )


def test_a_retired_authors_successor_is_excluded_like_the_author() -> None:
    """#413: the records carry `zai-glm52-max`, and the successor must not judge what it replaced.

    The records rung asks who an arbiter must not be, and a name no registry walk can
    select — the retired one — still excludes the profile that took its place.
    """
    seat = dispatch.Seat(
        "synthetic",
        claude_only=False,
        preference=("opus-low",),
        escalation=("zai-glm53-max", "opus-max"),
    )
    resolution = arbiter.resolve(
        seat, authorship(("zai-glm52-max",), ("d7",)), shipped_policy(), ()
    )
    assert resolution.kind == arbiter.RESOLVED
    assert resolution.arbiter == "opus-max"
    assert resolution.passed_over == (
        arbiter.Exclusion("zai-glm53-max", arbiter.RECORDS_EXCLUSION, "records=d7"),
    )


def test_an_exhausted_entry_walks_the_preference_list() -> None:
    """The ruling's own #318 note: both tabled profiles conflicted, the walk goes on.

    Entry (`opus-max`, `fable-max`) both on the records, preference (`fable-high`,
    `opus-xhigh`) both on the records — the walk answers `codex-sol-xhigh`, which is the
    outcome the ruling recorded for exactly this arrangement rather than the `opus-max`
    the orchestrator picked in the moment.
    """
    resolution = arbiter.resolve(
        dispatch.SEATS["retro"],
        authorship(
            ("opus-max", "fable-max", "fable-high", "opus-xhigh"),
            ("d1", "d2", "d3", "d4"),
        ),
        shipped_policy(),
        (),
    )
    assert resolution.kind == arbiter.RESOLVED
    assert resolution.arbiter == "codex-sol-xhigh"
    assert [exclusion.profile for exclusion in resolution.passed_over] == [
        "opus-max",
        "fable-max",
        "fable-high",
        "opus-xhigh",
    ]
    assert all(e.reason == arbiter.RECORDS_EXCLUSION for e in resolution.passed_over)


def test_the_entry_is_walked_before_the_preference_list() -> None:
    """A deduped, order-preserving walk: entry head, entry tail, then preference."""
    seat = dispatch.Seat(
        "synthetic",
        claude_only=False,
        preference=("codex-luna-max", "opus-max"),
        escalation=("opus-max", "opus-low"),
    )
    resolution = arbiter.resolve(seat, authorship(("opus-max",), ("d1",)), shipped_policy(), ())
    assert resolution.arbiter == "opus-low"
    # The preference head was never needed, and the duplicate entry of it is not walked.
    assert [e.profile for e in resolution.passed_over] == ["opus-max"]


def test_an_exhausted_walk_refuses_by_name_with_every_exclusion_attached() -> None:
    """Refuse by name when the walk is exhausted, every exclusion attached.

    Every rung firing at once, the planted policy among them: routing takes every
    non-Claude candidate the walk reaches — the entry head and the codex/zai preference
    entries — records take the Claude ones, and the walk that remains refuses with all of
    it attached.
    """
    resolution = arbiter.resolve(
        dispatch.SEATS["implementer"],
        authorship(("codex-sol-high", "opus-high", "opus-low"), ("d1", "d2", "d3")),
        refusing_policy(),
        ("tools/dispatch.py",),
    )
    assert resolution.kind == arbiter.REFUSED
    assert resolution.refusal == arbiter.EXHAUSTED_REFUSAL
    assert resolution.arbiter == ""
    assert [e.profile for e in resolution.passed_over] == [
        "codex-sol-high",
        "opus-high",
        "codex-luna-max",
        "zai-glm53-max",
        "opus-low",
    ]
    assert [e.reason for e in resolution.passed_over] == [
        arbiter.ROUTING_EXCLUSION,
        arbiter.RECORDS_EXCLUSION,
        arbiter.ROUTING_EXCLUSION,
        arbiter.ROUTING_EXCLUSION,
        arbiter.RECORDS_EXCLUSION,
    ]


def test_an_empty_escalation_column_refuses_rather_than_defaulting() -> None:
    """The struck `fable-high` default's replacement: no entry, no arbiter, named refusal.

    `recon` and the fable seat carry empty columns in the live registry; the refusal is
    the correct answer for both, and the ruling's consequence is that a seat added without
    deciding its arbiter lands here too.
    """
    for seat in (dispatch.SEATS["recon"], dispatch.SEATS["fable"]):
        resolution = arbiter.resolve(seat, authorship(), shipped_policy(), ())
        assert resolution.kind == arbiter.REFUSED
        assert resolution.refusal == arbiter.NO_ENTRY_REFUSAL
        assert resolution.passed_over == ()
        # Refused before any walk: a preference list the seat does carry never runs.
        assert resolution.arbiter == ""


def test_an_unreadable_record_leaves_the_resolution_unchecked_but_taken() -> None:
    """#41's two halves, carried from `--reviewing`: exclude what was read, mark the rest.

    The profile a readable record placed is still excluded — an incomplete read narrows —
    and the resolution is still taken, but `unchecked` says the scan could not complete,
    so the caller records it unchecked rather than as verified.
    """
    resolution = arbiter.resolve(
        dispatch.SEATS["retro"],
        authorship(("opus-max",), ("d1",), why=arbiter.RECORDS_UNREADABLE),
        shipped_policy(),
        (),
    )
    assert resolution.kind == arbiter.RESOLVED
    assert resolution.arbiter == "fable-max"
    assert resolution.unchecked is True
    assert [e.profile for e in resolution.passed_over] == ["opus-max"]


def test_every_incomplete_read_leaves_the_resolution_unchecked() -> None:
    """#333 round 1, High 3: `records_unreadable` was never the only incomplete state.

    A dispatch directory that is absent and an issue no dispatch ever worked on are gaps
    the same way a record that would not open is — `Authorship.complete` is false for all
    three, and a read that could not establish the author set cannot verify the walk
    against it (#41: a check that could not run is not a check that passed).
    """
    for read in (
        authorship(("opus-max",), ("d1",), why=arbiter.RECORDS_UNREADABLE),
        authorship(why="no_dispatch_records"),
        authorship(why="no_authoring_dispatch"),
    ):
        resolution = arbiter.resolve(dispatch.SEATS["retro"], read, shipped_policy(), ())
        assert resolution.kind == arbiter.RESOLVED
        assert resolution.unchecked is True


# --------------------------------------------------------------------------- the records read


def test_the_production_read_sees_reviewers_and_excludes_them(tmp_path: Path) -> None:
    """#333 round 1, High 2: the reviewers are on the dispatch records, not in a parameter.

    #318's arrangement, read the way production reads it: `fable-high` authored the issue,
    `opus-max` reviewed it — the review record is where the reviewer actually is, and it
    holds the walk's head. The arbiter scan must see the reviewer, exclude it, and answer
    `fable-max`; the authorship-only scan the review seat uses walks past the same record,
    which would read `opus-max` as free and hand the walk its own reviewer.
    """
    dispatch_dir = tmp_path / "dispatches"
    record(dispatch_dir, "d1", issue=318, profile="fable-high", seat="retro")
    record(dispatch_dir, "d2", issue=318, profile="opus-max", seat="review")
    resolution = arbiter.resolve_for_issue(
        dispatch.SEATS["retro"], 318, dispatch_dir, shipped_policy(), ()
    )
    assert resolution.kind == arbiter.RESOLVED
    assert resolution.arbiter == "fable-max"
    assert resolution.unchecked is False
    assert [(e.profile, e.reason) for e in resolution.passed_over] == [
        ("opus-max", arbiter.RECORDS_EXCLUSION)
    ]
    # The contrast: the author scan the review seat uses still walks past the review
    # record, because a reviewer is not an author (#322 vs #361 — two questions, two scans).
    assert dispatch.potential_authors(318, dispatch_dir).potential == ("fable-high",)


def test_the_production_read_walks_past_a_refused_review_record(tmp_path: Path) -> None:
    """A review dispatch that ended in refusal authored nothing, whichever scan reads it.

    The refusal walked the reviewer's record past both scans, so `opus-max` is free to
    arbitrate — the retro walk's head, taken with nothing excluded.
    """
    dispatch_dir = tmp_path / "dispatches"
    record(dispatch_dir, "d1", issue=318, profile="fable-high", seat="retro")
    refused = dispatch_dir / "d2"
    refused.mkdir()
    (refused / "dispatch.json").write_text(
        json.dumps({"issue": 318, "profile": "opus-max", "seat": "review"}),
        encoding="utf-8",
    )
    (refused / "result.json").write_text(json.dumps({"refusal": "lane_off_peak"}), encoding="utf-8")
    resolution = arbiter.resolve_for_issue(
        dispatch.SEATS["retro"], 318, dispatch_dir, shipped_policy(), ()
    )
    assert resolution.arbiter == "opus-max"
    assert resolution.passed_over == ()


# --------------------------------------------------------------------------- live dispatchability


def test_a_profile_the_ladder_would_refuse_is_excluded(tmp_path: Path) -> None:
    """#333 round 1, High 4: a table cannot say whether a profile is dispatchable now.

    The implementer walk: `codex-sol-high` and `opus-high` on the records; then
    `codex-luna-max`, whose lane's breaker is open on this box; then `zai-glm53-max`, whose
    lane wants a key this credentials file does not carry. Each refusal the ladder would
    give is the exclusion's reason, and the walk lands on `opus-low`.

    Both live exclusions are facts of *this box* since #405 lifted the ceiling that used to
    hold `codex-luna-max` below the seat from the registry — which suits the claim better
    than the block did, since what this test is about is state no table can hold.
    """
    dispatch_dir = tmp_path / "scratch-dispatches"
    record(dispatch_dir, "d1", issue=333, profile="codex-sol-high", seat="implementer")
    record(dispatch_dir, "d2", issue=333, profile="opus-high", seat="review")
    trip(tmp_path, "codex")
    credentials = tmp_path / "credentials.env"
    credentials.write_text("# no z.ai key here\n", encoding="utf-8")
    credentials.chmod(0o600)
    resolution = arbiter.resolve_dispatchable(
        dispatch.SEATS["implementer"],
        dispatch.potential_authors_and_reviewers(333, dispatch_dir),
        SUNDAY,
        shipped_policy(),
        (),
        admission_dir=str(tmp_path / "admission"),
        breaker_dir=str(tmp_path / "breaker"),
        credentials=str(credentials),
    )
    assert resolution.kind == arbiter.RESOLVED
    assert resolution.arbiter == "opus-low"
    assert resolution.unchecked is False
    by_profile = {e.profile: e for e in resolution.passed_over}
    assert set(by_profile) == {"codex-sol-high", "opus-high", "codex-luna-max", "zai-glm53-max"}
    assert by_profile["codex-sol-high"].reason == arbiter.RECORDS_EXCLUSION
    assert by_profile["opus-high"].reason == arbiter.RECORDS_EXCLUSION
    assert by_profile["codex-luna-max"].reason == arbiter.DISPATCH_EXCLUSION
    assert by_profile["zai-glm53-max"].reason == arbiter.DISPATCH_EXCLUSION
    assert "credential_absent" in by_profile["zai-glm53-max"].detail


def test_a_dispatchable_profile_is_answered_not_excluded(tmp_path: Path) -> None:
    """The same walk with the key present and the clock off-peak: z.ai answers."""
    dispatch_dir = tmp_path / "scratch-dispatches"
    record(dispatch_dir, "d1", issue=333, profile="codex-sol-high", seat="implementer")
    record(dispatch_dir, "d2", issue=333, profile="opus-high", seat="review")
    trip(tmp_path, "codex")
    credentials = tmp_path / "credentials.env"
    credentials.write_text("ZAI_API_KEY=test-key\n", encoding="utf-8")
    credentials.chmod(0o600)
    resolution = arbiter.resolve_dispatchable(
        dispatch.SEATS["implementer"],
        dispatch.potential_authors_and_reviewers(333, dispatch_dir),
        SUNDAY,
        shipped_policy(),
        (),
        admission_dir=str(tmp_path / "admission"),
        breaker_dir=str(tmp_path / "breaker"),
        credentials=str(credentials),
    )
    assert resolution.kind == arbiter.RESOLVED
    assert resolution.arbiter == "zai-glm53-max"
    # `codex-luna-max` stays excluded on its open breaker, and `opus-low` behind z.ai is
    # never reached.
    assert [e.profile for e in resolution.passed_over] == [
        "codex-sol-high",
        "opus-high",
        "codex-luna-max",
    ]


def test_an_unregistered_candidate_is_excluded_and_the_walk_continues() -> None:
    seat = dispatch.Seat(
        "synthetic",
        claude_only=False,
        preference=("opus-high",),
        escalation=("no-such-profile",),
    )
    resolution = arbiter.resolve(seat, authorship(), shipped_policy(), ())
    assert resolution.arbiter == "opus-high"
    assert resolution.passed_over == (
        arbiter.Exclusion(
            "no-such-profile",
            arbiter.UNREGISTERED_EXCLUSION,
            "the registry carries no such profile",
        ),
    )


# --------------------------------------------------------------------------- the event


def test_a_resolution_renders_the_invocation_observable() -> None:
    seat = dispatch.SEATS["retro"]
    resolution = arbiter.resolve(seat, authorship(("opus-max",), ("d1",)), shipped_policy(), ())
    event = arbiter.resolution_event(resolution, seat, "#318", at=1.5)
    document = arbiter.otel_event.log_record(event)
    body = document["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    assert body["body"] == {"stringValue": arbiter.RESOLUTION_EVENT}
    rendered = {a["key"]: a["value"] for a in body["attributes"]}
    assert rendered["event.name"] == {"stringValue": arbiter.RESOLUTION_EVENT}
    assert rendered["cti.issue"] == {"stringValue": "#318"}
    assert rendered["cti.review.arbiter"] == {"stringValue": "fable-max"}
    # Identities, not a count (#333 round 1, Medium 6): which profile, and why.
    assert rendered["cti.review.arbiter.excluded"] == {
        "stringValue": "opus-max:records_place_on_work"
    }
    assert rendered["cti.review.arbiter.unchecked"] == {"boolValue": False}


def test_a_refusal_is_an_event_too(tmp_path: Path) -> None:
    """The #318 shape — a loop escalating into a refusal — leaves its own trace."""
    seat = dispatch.SEATS["recon"]
    resolution = arbiter.resolve(seat, authorship(), shipped_policy(), ())
    arbiter.emit_resolution(resolution, seat, "#318", at=1.5, journal=tmp_path / "journal.jsonl")
    line = json.loads((tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["event"] == arbiter.RESOLUTION_EVENT
    assert line["attributes"]["cti.review.arbiter.refusal"] == arbiter.NO_ENTRY_REFUSAL
    assert line["attributes"]["cti.review.arbiter"] == ""


def test_the_journal_constant_is_shared_with_the_loop() -> None:
    """One journal for the whole loop's observables, not one per module."""
    assert arbiter.review_loop.JOURNAL == review_loop.JOURNAL
