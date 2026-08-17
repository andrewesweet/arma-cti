"""Post-landing review takes the dismissals, and loses the bar (#335, ADR-0071 rulings 4 and 6).

Two halves, and they meet different failures.

The **dismissal list** is the input ruling 4 promised that seat and never delivered:
`render_landing` shipped a writer with no reader at all, so "post-landing review is the
arbiter's appeal path" was as empty in the code as the ADR concedes it was in prose. The
reader's three states are pinned apart here — recorded, absent, unreadable — because the one
that matters is the third: an appeal path that could not be read must not compose as an
appeal path with nothing on it.

The **two rehomed operations** are ruling 6's. The withdrawn admission bar used to receive a
confirmed post-landing finding as an `unclean` reason and count the reviewer's citations
against a floor; #328 dropped the bar and left both objects produced and received by nothing.
They land on two *different* profiles — rework on the reviewed one, citations on the reviewing
one — and `docs/review-dispatch.md` states in as many words that whoever builds the
observatory must not collapse them, so the tests below assert the separation rather than the
pair.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

review_loop = load_tool("review_loop")
brief = load_tool("brief")

ISSUE: Final = 335
ARBITER: Final = "opus-xhigh"
REVIEWING_DISPATCH: Final = "d-post-1"
REVIEWED_PROFILE: Final = "opus-low"
REVIEWING_PROFILE: Final = "codex-sol-high"
REVIEWING_LANE: Final = "codex"
REVIEWED_SHA: Final = "e" * 40


def stepped_clock() -> Callable[[], float]:
    """A clock the tests own: every call advances one second, off any wall clock."""
    tick = [0.0]

    def now() -> float:
        tick[0] += 1.0
        return tick[0]

    return now


# --------------------------------------------------- the landing record, read back for the seat


def landing_document(
    issue: int = ISSUE,
    dismissals: tuple[tuple[str, str, int], ...] = (("F1", "critical", 3),),
) -> dict[str, object]:
    """A landing record in exactly the shape `render_landing` writes one."""
    return {
        "version": review_loop.LOOP_VERSION,
        "issue": issue,
        "review_rounds": 3,
        "default_applies": True,
        "arbiter": ARBITER,
        "arbiter_unchecked": False,
        "findings": [],
        "filings": [],
        "dismissals": [
            {"finding": name, "severity": severity, "round_raised": raised}
            for name, severity, raised in dismissals
        ],
    }


def write_landing(root: Path, document: object, issue: int = ISSUE) -> Path:
    target = root / str(issue) / review_loop.LANDING_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        document if isinstance(document, str) else json.dumps(document), encoding="utf-8"
    )
    return target


def test_the_writers_own_output_reads_back_as_the_dismissals_it_recorded(tmp_path: Path) -> None:
    """Writer and reader over one record, so the pair cannot drift on the shape between them."""
    loop = review_loop.adjudicate(
        review_loop.first_review((review_loop.Finding("F1", review_loop.CRITICAL, 0),)),
        "F1",
        review_loop.Adjudication(review_loop.ARBITER_DISMISSED, "", "", ARBITER),
    )
    end = review_loop.terminus(loop)
    write_landing(tmp_path, review_loop.render_landing(ISSUE, loop, end, arbiter=ARBITER))

    read = review_loop.read_landing(tmp_path, ISSUE)

    assert read.state == review_loop.LANDING_RECORDED
    assert read.dismissals == end.dismissals
    assert read.dismissals == (review_loop.Dismissal("F1", review_loop.CRITICAL, 0),)


def test_the_dismissal_carries_its_severity_and_the_round_it_was_raised_in(tmp_path: Path) -> None:
    """A count would say *a* Critical was dismissed while naming neither which nor when."""
    write_landing(tmp_path, landing_document(dismissals=(("F7", "high", 2), ("F9", "medium", 3))))

    assert review_loop.read_landing(tmp_path, ISSUE).dismissals == (
        review_loop.Dismissal("F7", review_loop.HIGH, 2),
        review_loop.Dismissal("F9", review_loop.MEDIUM, 3),
    )


def test_a_terminus_that_set_nothing_aside_reads_as_recorded_and_empty(tmp_path: Path) -> None:
    """Recorded-and-empty is a read of the record. Absent is the lack of one. Never the same."""
    write_landing(tmp_path, landing_document(dismissals=()))
    read = review_loop.read_landing(tmp_path, ISSUE)

    assert read.state == review_loop.LANDING_RECORDED
    assert read.dismissals == ()


def test_no_landing_record_is_absent_and_never_an_empty_dismissal_list(tmp_path: Path) -> None:
    """Every round inside the loop is this: the record's existence is what makes a review post."""
    read = review_loop.read_landing(tmp_path, ISSUE)

    assert read.state == review_loop.LANDING_ABSENT
    assert read.dismissals == ()
    assert review_loop.LANDING_FILE in read.detail


@pytest.mark.parametrize(
    ("document", "because"),
    [
        ("{not json", "a truncated record"),
        ({"version": 2, "issue": ISSUE, "dismissals": []}, "a record from another version"),
        ({"issue": ISSUE, "dismissals": []}, "a record with no version at all"),
        ({"version": 1, "issue": 999, "dismissals": []}, "a record naming another issue"),
        ({"version": 1, "issue": "335", "dismissals": []}, "an issue that is not an integer"),
        ({"version": 1, "issue": ISSUE}, "no dismissals key at all"),
        ({"version": 1, "issue": ISSUE, "dismissals": {}}, "dismissals that are not a list"),
        ({"version": 1, "issue": ISSUE, "dismissals": ["F1"]}, "a dismissal that is not an object"),
        (
            {
                "version": 1,
                "issue": ISSUE,
                "dismissals": [{"finding": "F1", "severity": "critical"}],
            },
            "a dismissal naming no round",
        ),
        (
            {
                "version": 1,
                "issue": ISSUE,
                "dismissals": [{"finding": "", "severity": "critical", "round_raised": 1}],
            },
            "a dismissal naming no finding",
        ),
        (
            {
                "version": 1,
                "issue": ISSUE,
                "dismissals": [{"finding": "F1", "severity": "urgent", "round_raised": 1}],
            },
            "a severity outside the four",
        ),
        (
            {
                "version": 1,
                "issue": ISSUE,
                "dismissals": [{"finding": "F1", "severity": "critical", "round_raised": -1}],
            },
            "a round before round zero",
        ),
    ],
)
def test_an_unreadable_landing_record_is_never_an_empty_appeal_path(
    tmp_path: Path, document: object, because: str
) -> None:
    """#41's mark: a check that could not run is not a check that passed.

    Every document here is a record that *exists*, so absence is not the honest answer for
    any of them, and the empty tuple beside `UNREADABLE` is what stops a consumer reading
    the dismissals without reading the state.
    """
    target = write_landing(tmp_path, document)
    read = review_loop.read_landing(tmp_path, ISSUE)

    assert read.state == review_loop.LANDING_UNREADABLE, because
    assert read.dismissals == ()
    assert str(target) in read.detail


def test_the_record_is_read_from_the_issues_own_directory(tmp_path: Path) -> None:
    """One issue's dismissals, never another's: the loop root holds a directory per issue."""
    write_landing(tmp_path, landing_document(issue=999, dismissals=(("F1", "critical", 0),)), 999)

    assert review_loop.read_landing(tmp_path, ISSUE).state == review_loop.LANDING_ABSENT
    assert review_loop.read_landing(tmp_path, 999).state == review_loop.LANDING_RECORDED


# ------------------------------------------------- the list as the briefing hands it to the seat


def composed(read: review_loop.LandingRead, seat: str = "review") -> str:
    """Render a brief whose only varied part is the landing record behind it."""
    return brief.compose(
        brief.Briefing(
            issue=ISSUE,
            title="Post-landing review takes the dismissals",
            gate=brief.derive_gate("touch tools/review_loop.py", ("commander",)),
            flakes=(),
            seat=brief.derive_seat(seat, REVIEWED_PROFILE),
            tree=brief.Tree(Path("/tmp/issue-335"), "0f21191", "worktree"),  # noqa: S108 — a rendered string, never opened
            assessment=brief.readiness.assess("- [ ] one\nGate: `just fast`\n"),
            dismissals=read,
        )
    )


def recorded(*dismissals: review_loop.Dismissal) -> review_loop.LandingRead:
    return review_loop.LandingRead(review_loop.LANDING_RECORDED, dismissals)


def test_the_seat_is_handed_every_dismissal_with_the_reason_it_is_being_handed_them() -> None:
    """Ruling 4's appeal path, in the one surface every dispatched agent reads first."""
    rendered = composed(
        recorded(
            review_loop.Dismissal("F1", review_loop.CRITICAL, 3),
            review_loop.Dismissal("F4", review_loop.MEDIUM, 1),
        )
    )

    assert "## Dismissals handed to this review (2)" in rendered
    assert "`F1` (critical, raised round 3)" in rendered
    assert "`F4` (medium, raised round 1)" in rendered
    assert "only appeal path" in rendered


def test_a_landing_that_dismissed_nothing_says_so_rather_than_saying_nothing() -> None:
    """An empty appeal path is a fact the seat should be told, not a section to omit."""
    rendered = composed(recorded())

    assert "## Dismissals handed to this review (0)" in rendered
    assert "no finding set aside" in rendered


def test_a_review_inside_the_loop_composes_no_dismissal_section_at_all() -> None:
    """No terminus, no landing record, nothing to hand — and no permanently empty heading."""
    assert "Dismissals" not in composed(review_loop.LandingRead(review_loop.LANDING_ABSENT))


def test_an_unreadable_record_composes_under_its_own_heading_never_in_the_empty_lists_place() -> (
    None
):
    """The third state renders third. Rendering it as "(0)" is the whole defect one step on."""
    rendered = composed(
        review_loop.LandingRead(review_loop.LANDING_UNREADABLE, (), "/x/landing.json: truncated")
    )

    assert "## Dismissals — UNREADABLE" in rendered
    assert "unknown rather than empty" in rendered
    assert "/x/landing.json: truncated" in rendered
    assert "Dismissals handed to this review" not in rendered


def test_an_unrecognised_state_raises_rather_than_composing_silence() -> None:
    """The last place a distinction can be lost before an agent reads the brief."""
    with pytest.raises(review_loop.ReviewLoopError):
        brief.render_dismissals(review_loop.LandingRead("invented"))


def test_only_a_seat_that_reviews_is_handed_them() -> None:
    """On any other seat they are noise about a judgement that seat does not make."""
    for name, seat in brief.dispatch.SEATS.items():
        if seat.reviews:
            continue
        assert "Dismissals" not in composed(
            recorded(review_loop.Dismissal("F1", review_loop.CRITICAL, 3)), name
        ), name


def test_the_composer_reads_the_record_through_a_real_option(tmp_path: Path) -> None:
    """A real flag on the real parser, so `main`'s read is the one the tests exercise."""
    assert brief.parse_args([str(ISSUE), "--review-root", str(tmp_path)]).review_root == str(
        tmp_path
    )


def test_main_hands_a_real_record_to_a_real_review_briefing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end through the seam `just brief` actually runs, not the composer alone."""
    write_landing(tmp_path, landing_document(dismissals=(("F1", "critical", 3),)))

    assert (
        brief.main(
            [
                str(ISSUE),
                "--seat",
                "review",
                "--reviewing",
                REVIEWED_PROFILE,
                "--review-root",
                str(tmp_path),
            ],
            read_issue=lambda *_: {"title": "a title", "body": "touch tools/review_loop.py"},
            read_open=lambda *_: [],
            read_prior=lambda *_: (),
            read_handoff=lambda *_: brief.Handoff(brief.HANDOFF_ABSENT),
        )
        == 0
    )
    assert "`F1` (critical, raised round 3)" in capsys.readouterr().out


def test_main_says_on_stderr_that_an_appeal_path_went_unread(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate and the handoff both warn out of band when they could not read; so does this."""
    write_landing(tmp_path, "{truncated")

    brief.main(
        [
            str(ISSUE),
            "--seat",
            "review",
            "--reviewing",
            REVIEWED_PROFILE,
            "--review-root",
            str(tmp_path),
        ],
        read_issue=lambda *_: {"title": "a title", "body": "touch tools/review_loop.py"},
        read_open=lambda *_: [],
        read_prior=lambda *_: (),
        read_handoff=lambda *_: brief.Handoff(brief.HANDOFF_ABSENT),
    )

    assert "dismissals=unreadable for #335" in capsys.readouterr().err


# ------------------------------------- the two operations the dropped bar used to receive (#335)


def write_review_dispatch(  # noqa: PLR0913 — one parameter per field of the record under test
    dispatch_root: Path,
    name: str = REVIEWING_DISPATCH,
    *,
    issue: int = ISSUE,
    seat: str = "review",
    reviewing: str = REVIEWED_PROFILE,
    profile: str = REVIEWING_PROFILE,
    lane: str = REVIEWING_LANE,
    base_sha: str = REVIEWED_SHA,
) -> Path:
    """One review dispatch record, in the shape `tools/dispatch.py` writes it."""
    entry = dispatch_root / name
    entry.mkdir(parents=True, exist_ok=True)
    document: dict[str, object] = {
        "issue": issue,
        "seat": seat,
        "profile": profile,
        "lane": lane,
        "dispatch_id": name,
        "base_sha": base_sha,
        "route": {
            "seat": seat,
            "chosen": profile,
            "lane": lane,
            "named": False,
            "reviewing": reviewing,
        },
    }
    (entry / "dispatch.json").write_text(json.dumps(document), encoding="utf-8")
    return entry


def journal_records(journal: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]


def part(journal: Path, key: str, index: int = 0) -> dict[str, object]:
    """One journal record's `attributes` or `resource`, asserted to be the object it must be."""
    found = journal_records(journal)[index][key]
    assert isinstance(found, dict), found
    return found


def run_post_landing(tmp_path: Path, *extra: str, dispatch_root: Path | None = None) -> int:
    root = dispatch_root if dispatch_root is not None else tmp_path / "dispatches"
    return review_loop.main(
        [
            "post-landing",
            "--dispatch",
            REVIEWING_DISPATCH,
            "--dispatch-dir",
            str(root),
            "--journal",
            str(tmp_path / "journal.jsonl"),
            *extra,
        ],
        now=stepped_clock(),
    )


def test_the_two_rehomed_operations_land_on_two_different_profiles(tmp_path: Path) -> None:
    """Ruling 6's rehoming, and the warning `docs/review-dispatch.md` attaches to it.

    Rework is booked against the profile whose work was reviewed; the citations are reported
    against the profile that reviewed it. One dispatch, two subjects, named apart on the
    record so the observatory (#336) meets the distinction rather than re-derives it.
    """
    write_review_dispatch(tmp_path / "dispatches")

    assert run_post_landing(tmp_path, "--confirmed", "412", "--citations", "9/10") == review_loop.OK
    attributes = part(tmp_path / "journal.jsonl", "attributes")

    assert attributes["cti.review.reviewed_profile"] == REVIEWED_PROFILE
    assert attributes["cti.review.confirmed"] == "#412"
    assert attributes["cti.review.reviewing_profile"] == REVIEWING_PROFILE
    assert attributes["cti.review.reviewing_lane"] == REVIEWING_LANE
    assert attributes["cti.review.reviewing_dispatch"] == REVIEWING_DISPATCH
    assert attributes["cti.review.citations_resolved"] == 9
    assert attributes["cti.review.citations_total"] == 10
    assert attributes["cti.issue"] == str(ISSUE)
    assert attributes["cti.review.reviewed_sha"] == REVIEWED_SHA


def test_every_confirmed_finding_is_named_by_the_issue_it_became(tmp_path: Path) -> None:
    """Identities rather than a count — the terminus rule, applied to the finding's afterlife."""
    write_review_dispatch(tmp_path / "dispatches")
    run_post_landing(tmp_path, "--confirmed", "412", "--confirmed", "418", "--citations", "9/10")
    attributes = part(tmp_path / "journal.jsonl", "attributes")

    assert attributes["cti.review.confirmed"] == "#412,#418"


def test_a_post_landing_review_that_confirmed_nothing_is_still_recorded(tmp_path: Path) -> None:
    """The gap the dropped bar left: reviewed-and-clean must not look like nobody reviewed.

    An event emitted only where something was found rebuilds Part B's blindness — the #41
    shape — one record along.
    """
    write_review_dispatch(tmp_path / "dispatches")

    assert run_post_landing(tmp_path, "--citations", "4/4") == review_loop.OK
    attributes = part(tmp_path / "journal.jsonl", "attributes")

    assert attributes["cti.review.confirmed"] == ""
    assert attributes["cti.review.citations_resolved"] == 4
    assert attributes["cti.review.reviewed_profile"] == REVIEWED_PROFILE


def test_the_record_carries_no_floor_and_compares_the_citations_to_nothing(tmp_path: Path) -> None:
    """Ruling 6 dropped the bar; a threshold reintroduced here would be that bar renamed."""
    write_review_dispatch(tmp_path / "dispatches")

    assert run_post_landing(tmp_path, "--citations", "1/10") == review_loop.OK
    journal = tmp_path / "journal.jsonl"

    assert journal_records(journal)[0]["event"] == review_loop.POST_LANDING_EVENT
    assert not [key for key in part(journal, "attributes") if "floor" in key or "admission" in key]


def test_a_second_record_of_one_review_is_refused_rather_than_doubling_the_rework(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One review is one observation: a duplicate line is a wrong number, not a duplicate line."""
    write_review_dispatch(tmp_path / "dispatches")
    assert run_post_landing(tmp_path, "--confirmed", "412", "--citations", "9/10") == review_loop.OK
    capsys.readouterr()

    assert run_post_landing(tmp_path, "--confirmed", "412", "--citations", "9/10") == (
        review_loop.REFUSED
    )
    assert "already carries a post-landing record" in capsys.readouterr().err
    assert len(journal_records(tmp_path / "journal.jsonl")) == 1


def test_a_second_lens_over_the_same_diff_is_its_own_dispatch_and_its_own_record(
    tmp_path: Path,
) -> None:
    """Two lenses are one review pass and two dispatches, so the key is the dispatch, not the issue."""
    write_review_dispatch(tmp_path / "dispatches")
    write_review_dispatch(tmp_path / "dispatches", "d-post-2", profile="glm-4-6", lane="zai")
    run_post_landing(tmp_path, "--citations", "9/10")

    assert (
        review_loop.main(
            [
                "post-landing",
                "--dispatch",
                "d-post-2",
                "--dispatch-dir",
                str(tmp_path / "dispatches"),
                "--journal",
                str(tmp_path / "journal.jsonl"),
                "--citations",
                "5/5",
            ],
            now=stepped_clock(),
        )
        == review_loop.OK
    )
    lanes = [
        part(tmp_path / "journal.jsonl", "attributes", index)["cti.review.reviewing_lane"]
        for index in (0, 1)
    ]
    assert lanes == [REVIEWING_LANE, "zai"]


def test_a_journal_line_that_is_not_json_is_walked_past_rather_than_blocking_the_record(
    tmp_path: Path,
) -> None:
    """`otel_event.journal_line` writes JSON, so a line that is not was not a record of ours."""
    write_review_dispatch(tmp_path / "dispatches")
    (tmp_path / "journal.jsonl").write_text("not a record at all\n", encoding="utf-8")

    assert run_post_landing(tmp_path, "--citations", "9/10") == review_loop.OK
    assert len(journal_records(tmp_path / "journal.jsonl")[1:]) == 0


def test_a_journal_that_will_not_open_is_not_a_record_that_is_absent(tmp_path: Path) -> None:
    """ "No record found" read off a file nobody could read is absence-as-clearance."""
    unreadable = tmp_path / "journal.jsonl"
    unreadable.mkdir()

    with pytest.raises(review_loop.ExternalError):
        review_loop.post_landing_recorded(unreadable, REVIEWING_DISPATCH)


def test_a_dispatch_on_a_seat_that_reviews_nothing_produced_no_review_to_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Read off the registry's `reviews` column, never a comparison against the name."""
    write_review_dispatch(tmp_path / "dispatches", seat="implementer", reviewing="")

    assert run_post_landing(tmp_path, "--citations", "1/1") == review_loop.REFUSED
    assert "produced no review to record" in capsys.readouterr().err
    assert not (tmp_path / "journal.jsonl").exists()


def test_a_record_naming_no_reviewed_profile_is_refused_rather_than_booked_against_nobody(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Booking against nobody is not the cheaper answer, it is the wrong one.

    The arrangement is real rather than invented: a record written before #322 carries no
    `reviewing` at all, and ADR-0071 calls same-model review the finding it does precisely
    because none of those dispatches declared a subject.
    """
    write_review_dispatch(tmp_path / "dispatches", reviewing="")

    assert run_post_landing(tmp_path, "--citations", "1/1") == review_loop.REFUSED
    assert "no profile to book the rework against" in capsys.readouterr().err
    assert not (tmp_path / "journal.jsonl").exists()


def test_a_record_naming_no_commit_reviewed_nothing_identified(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A review that names no SHA is an observation about no landing."""
    write_review_dispatch(tmp_path / "dispatches", base_sha="")

    assert run_post_landing(tmp_path, "--citations", "1/1") == review_loop.REFUSED
    assert "reviewed no identified commit" in capsys.readouterr().err
    assert not (tmp_path / "journal.jsonl").exists()


@pytest.mark.parametrize("body", ["{truncated", '"a string"', '{"seat": "review"}'])
def test_an_unreadable_dispatch_record_is_not_a_result_rather_than_a_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], body: str
) -> None:
    """The handoff tool's split: "I could not look" is exit 3, never a negative answer."""
    entry = tmp_path / "dispatches" / REVIEWING_DISPATCH
    entry.mkdir(parents=True)
    (entry / "dispatch.json").write_text(body, encoding="utf-8")

    assert run_post_landing(tmp_path, "--citations", "1/1") == review_loop.NO_RESULT
    assert "could not be read as a plan" in capsys.readouterr().err


def test_a_dispatch_directory_that_does_not_exist_is_not_a_result_either(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An identity read off a record that is not there is an identity nobody wrote."""
    assert run_post_landing(tmp_path, "--citations", "1/1") == review_loop.NO_RESULT
    assert "could not be read as a plan" in capsys.readouterr().err


@pytest.mark.parametrize("spec", ["9", "10/9", "a/b", "9/", "/9", "-1/9", "9/10/11"])
def test_the_citation_pair_refuses_a_shape_that_is_not_resolved_over_total(spec: str) -> None:
    """`resolved` over `total`, both counted: a shrunk denominator flatters the reviewer."""
    with pytest.raises(SystemExit):
        review_loop.parse_args(["post-landing", "--dispatch", "d", "--citations", spec])


def test_the_citation_pair_takes_the_boundary_cases_it_should(tmp_path: Path) -> None:
    """Nothing cited and nothing resolving are both legal readings, and neither is a floor."""
    write_review_dispatch(tmp_path / "dispatches")

    assert run_post_landing(tmp_path, "--citations", "0/0") == review_loop.OK
    attributes = part(tmp_path / "journal.jsonl", "attributes")
    assert attributes["cti.review.citations_total"] == 0


def test_the_two_subjects_are_printed_on_lines_of_their_own(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The surface a reader quotes keeps the two records apart, as the doc asks of a rollup."""
    write_review_dispatch(tmp_path / "dispatches")
    run_post_landing(tmp_path, "--confirmed", "412", "--citations", "9/10")
    rework, citations = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("[review-loop]")
    ]

    assert f"reviewed_profile={REVIEWED_PROFILE}" in rework
    assert "confirmed=1" in rework
    assert "#412" in rework
    assert "reviewing_profile" not in rework
    assert f"reviewing_profile={REVIEWING_PROFILE}" in citations
    assert "resolved=9/10" in citations
    assert "never a floor" in citations
    assert "reviewed_profile" not in citations


def test_the_event_is_the_review_journals_own_family(tmp_path: Path) -> None:
    """One journal, one service, one issue key — so #336 reads rounds and outcomes together."""
    write_review_dispatch(tmp_path / "dispatches")
    run_post_landing(tmp_path, "--citations", "9/10")
    journal = tmp_path / "journal.jsonl"

    assert journal_records(journal)[0]["event"] == "cti.review.post_landing"
    assert part(journal, "resource")["service.name"] == "arma-cti-review-loop"
    assert part(journal, "resource")["cti.issue"] == str(ISSUE)
