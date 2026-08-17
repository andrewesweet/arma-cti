"""The interactive authorship record, and the deadlock it closes (#398).

#294 bars a dispatched session from writing under `.claude/`, so a change there is
authored interactively by construction — and an interactive session writes no dispatch
record, so `just land`'s never-alone rung read an empty author set and refused every
such landing (`authorship_unrecorded`). Both halves were right; together they left no
route, which is where #330 sat at `c380689`: five review rounds, verdict recorded,
gates green, refused at the landing.

What is asserted here is the whole of the fix and, more importantly, that it is not a
weakening of the rung it unblocks:

- the record's own reader and writer, including every way a stored record refuses to
  be read — an author set is what the never-alone check runs against, so a record that
  will not open is an unperformable read rather than an empty answer (#41);
- the merge, which only ever *adds* names and clears the "no records" states without
  ever clearing `records_unreadable`;
- both ends of the landing rung: an interactively authored change reaching a clearance,
  **and the same-session arrangement still refused** — a declared author reviewing its
  own diff meets `review_same_profile` exactly as a dispatched one does.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

dispatch = load_tool("dispatch")
review_loop = load_tool("review_loop")
land_review = load_tool("land_review")

ISSUE: Final = 398
SHA: Final = "c" * 40
STAMP: Final = "20260817T0000Z"
AUTHOR: Final = "opus-high"
REVIEWER: Final = "codex-luna-max"


def _record(root: Path, issue: int, document: object) -> Path:
    """Plant a stored authorship record by hand, the shape a hand-edit would leave it."""
    target = review_loop.authorship_path(root, issue)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def _author(root: Path, profile: str = AUTHOR, *, issue: int = ISSUE) -> bool:
    """Declare one interactive author through the writer under test."""
    return review_loop.store_authorship(root, issue, profile, SHA, STAMP)


# ------------------------------------------------------------------ the record's own reader


def test_a_declaration_reads_back_as_the_author_it_named(tmp_path: Path) -> None:
    """The round trip, through the writer and the reader a landing calls."""
    assert _author(tmp_path) is True

    assert review_loop.recorded_authors(tmp_path, ISSUE) == (AUTHOR,)


def test_no_record_at_all_is_an_answer_rather_than_a_gap(tmp_path: Path) -> None:
    """Most issues are authored through a dispatch and carry no such record."""
    assert review_loop.recorded_authors(tmp_path, ISSUE) == ()


def test_declaring_the_same_profile_twice_records_it_once(tmp_path: Path) -> None:
    """The same claim twice is the same claim: idempotent, not a refusal and not two rows."""
    assert _author(tmp_path) is True
    assert _author(tmp_path) is False

    assert review_loop.recorded_authors(tmp_path, ISSUE) == (AUTHOR,)
    stored = json.loads(review_loop.authorship_path(tmp_path, ISSUE).read_text(encoding="utf-8"))
    assert len(stored["authors"]) == 1


def test_a_second_profile_joins_the_first(tmp_path: Path) -> None:
    """Two interactive sessions on one issue are two authors, and both exclude a reviewer."""
    _author(tmp_path)
    _author(tmp_path, "opus-xhigh")

    assert review_loop.recorded_authors(tmp_path, ISSUE) == (AUTHOR, "opus-xhigh")


def test_a_declaration_carries_its_provenance_and_its_commit(tmp_path: Path) -> None:
    """`declared` is on the record as well as on the clearance; the SHA is the audit trail."""
    _author(tmp_path)

    entry = json.loads(review_loop.authorship_path(tmp_path, ISSUE).read_text(encoding="utf-8"))
    assert entry["authors"][0]["source"] == review_loop.DECLARED
    assert entry["authors"][0]["sha"] == SHA
    assert entry["authors"][0]["recorded_at"] == STAMP


def test_a_declaration_with_no_commit_in_hand_omits_the_field(tmp_path: Path) -> None:
    """A record says what it knows: an absent SHA is absent, never an empty claim."""
    review_loop.store_authorship(tmp_path, ISSUE, AUTHOR, "", STAMP)

    entry = json.loads(review_loop.authorship_path(tmp_path, ISSUE).read_text(encoding="utf-8"))
    assert "sha" not in entry["authors"][0]


@pytest.mark.parametrize(
    ("document", "described"),
    [
        ({"version": 2, "issue": ISSUE, "authors": [{"profile": AUTHOR}]}, "another version"),
        ({"version": 1, "issue": ISSUE + 1, "authors": [{"profile": AUTHOR}]}, "another issue"),
        ({"version": 1, "issue": ISSUE, "authors": []}, "no author at all"),
        ({"version": 1, "issue": ISSUE, "authors": [{"profile": ""}]}, "a blank profile"),
        ({"version": 1, "issue": ISSUE, "authors": [{"profile": None}]}, "no profile"),
        ({"version": 1, "issue": ISSUE, "authors": [AUTHOR]}, "an entry that is not an object"),
        ({"version": 1, "issue": ISSUE}, "no authors key"),
        ([{"profile": AUTHOR}], "a document that is not an object"),
    ],
)
def test_a_record_this_tool_did_not_write_is_never_read_as_an_answer(
    tmp_path: Path, document: object, described: str
) -> None:
    """Validated, never coerced: `str(None)` in an author set is an author nobody can be.

    Each of these would otherwise clear the never-alone check by supplying an author the
    reviewer is guaranteed not to be — the failure `recorded_arbiter` documents, arriving
    at the record that decides whether the check has a set to run against at all.
    """
    _record(tmp_path, ISSUE, document)

    with pytest.raises(review_loop.ExternalError, match=f"#{ISSUE}"):
        review_loop.recorded_authors(tmp_path, ISSUE)
    assert described  # the parametrisation's own label, kept in the failure output


def test_a_record_that_will_not_parse_is_unperformable_rather_than_empty(tmp_path: Path) -> None:
    """A truncated record could be naming this reviewer; nothing is taken from it."""
    target = review_loop.authorship_path(tmp_path, ISSUE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"version": 1, "issue"', encoding="utf-8")

    with pytest.raises(review_loop.ExternalError, match="will not read"):
        review_loop.recorded_authors(tmp_path, ISSUE)


def test_the_writer_refuses_to_append_to_a_record_it_cannot_read(tmp_path: Path) -> None:
    """A declaration must not silently overwrite the authors a broken record still names."""
    _record(tmp_path, ISSUE, {"version": 1, "issue": ISSUE, "authors": [{"profile": 12}]})

    with pytest.raises(review_loop.ExternalError):
        _author(tmp_path)


# ------------------------------------------------------------------ the command surface


def _author_command(root: Path, profile: str = AUTHOR, *, issue: int = ISSUE) -> int:
    return review_loop.main(
        ["author", "--issue", str(issue), "--root", str(root), "--profile", profile, "--sha", SHA],
        now=lambda: 0.0,
    )


def test_the_command_records_the_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route the refusal names, end to end from the command line."""
    monkeypatch.delenv("CTI_DISPATCH_ID", raising=False)

    assert _author_command(tmp_path) == review_loop.OK
    assert review_loop.recorded_authors(tmp_path, ISSUE) == (AUTHOR,)


def test_a_dispatched_session_may_not_declare_interactive_authorship(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one provenance fact this command can actually check, and it checks it.

    A dispatched session's profile is already on its own dispatch record, and the work
    this record exists for is work #294 says a dispatched session must not have done —
    so a declaration from inside a dispatch is a second author nothing corroborates.
    """
    monkeypatch.setenv("CTI_DISPATCH_ID", "d-20260817-000000-abc123")

    assert _author_command(tmp_path) == review_loop.REFUSED
    assert review_loop.recorded_authors(tmp_path, ISSUE) == ()


def test_an_unregistered_profile_is_refused_rather_than_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typo names an author no reviewer could ever be, which clears the check silently."""
    monkeypatch.delenv("CTI_DISPATCH_ID", raising=False)

    assert _author_command(tmp_path, "opus-hihg") == review_loop.REFUSED
    assert review_loop.recorded_authors(tmp_path, ISSUE) == ()


# ------------------------------------------------------------------ the merge


def test_a_declaration_fills_the_set_the_dispatch_records_left_empty() -> None:
    """The deadlock's mechanism: an empty scan plus a declaration is a complete read."""
    merged = dispatch.with_declared_authors(
        dispatch.Authorship(why=dispatch.NO_AUTHORING_DISPATCH), (AUTHOR,), "record.json"
    )

    assert merged.potential == (AUTHOR,)
    assert merged.records == ("record.json",)
    assert merged.complete is True


def test_a_declaration_never_repairs_a_record_that_would_not_open() -> None:
    """#41's rule survives the fix: an unread record stays unread whatever anybody declares."""
    merged = dispatch.with_declared_authors(
        dispatch.Authorship(("opus-xhigh",), ("d-1",), why=dispatch.RECORDS_UNREADABLE),
        (AUTHOR,),
        "record.json",
    )

    assert merged.potential == ("opus-xhigh", AUTHOR)
    assert merged.why == dispatch.RECORDS_UNREADABLE
    assert merged.complete is False


def test_a_declaration_of_a_profile_the_records_already_place_adds_nothing() -> None:
    """One profile, one entry: the set is what a reviewer is checked against, not a tally."""
    scanned = dispatch.Authorship((AUTHOR,), ("d-1",))

    assert dispatch.with_declared_authors(scanned, (AUTHOR,), "record.json") == scanned


def test_no_declaration_leaves_the_scan_exactly_as_it_stood() -> None:
    """Every issue authored through a dispatch reads as it did before #398."""
    empty = dispatch.Authorship(why=dispatch.NO_DISPATCH_RECORDS)

    assert dispatch.with_declared_authors(empty, (), "record.json") == empty


# ------------------------------------------------------------------ the landing rung, both ends


def _stage(tmp_path: Path, *, reviewer: str = REVIEWER) -> tuple[Path, Path]:
    """Stage a bound, completed, clean review over work no dispatch record claims.

    The #330 arrangement exactly: the review is dispatched and on the record, and the
    implementing work is not, because it was written under `.claude/` in an interactive
    session.
    """
    dispatch_root = tmp_path / "dispatches"
    review_root = tmp_path / "review"
    record = dispatch_root / "d-review-1"
    record.mkdir(parents=True, exist_ok=True)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "seat": "review",
                "issue": ISSUE,
                "base_sha": SHA,
                "profile": reviewer,
                "lane": "codex",
                "planned_at": STAMP,
                "dispatch_id": "d-review-1",
            }
        ),
        encoding="utf-8",
    )
    (record / "result.json").write_text(
        json.dumps({"returncode": 0, "outcome": "ok", "ended_at": STAMP}), encoding="utf-8"
    )
    (record / "verdict.json").write_text(
        json.dumps(
            {
                "version": 1,
                "issue": ISSUE,
                "reviewed_sha": SHA,
                "review_dispatch": "d-review-1",
                "reviewer_profile": reviewer,
                "reviewer_lane": "codex",
                "findings": [],
                "recorded_at": STAMP,
                "alternates": [],
            }
        ),
        encoding="utf-8",
    )
    return dispatch_root, review_root


def _rung(roots: tuple[Path, Path]) -> land_review.Outcome:
    dispatch_root, review_root = roots
    return land_review.review_finding(
        ISSUE, SHA, (".claude/skills/retro/SKILL.md",), None, dispatch_root, review_root
    )


def test_an_interactively_authored_change_is_refused_until_it_is_declared(
    tmp_path: Path,
) -> None:
    """The deadlock, and the refusal now naming the route out of it."""
    refusal = _rung(_stage(tmp_path)).refusal

    assert refusal.kind == "authorship_unrecorded"
    assert "just review-loop author" in refusal.action
    assert "#294" in refusal.action


def test_a_declared_author_clears_the_landing_the_records_could_not(tmp_path: Path) -> None:
    """The acceptance criterion: a `.claude/` change reaches `origin/main` through `just land`."""
    roots = _stage(tmp_path)
    _author(roots[1])

    outcome = _rung(roots)

    assert outcome.refusal is None
    assert f"authorship=checked potential={AUTHOR} declared={AUTHOR}" in outcome.cleared
    assert land_review.DECLARED_AUTHOR_LIMIT in outcome.cleared


def test_the_declared_author_reviewing_its_own_diff_is_still_refused(tmp_path: Path) -> None:
    """The failure mode this fix must not have: clearing the deadlock by clearing the check.

    One instance authors the change in its own session and dispatches the review on its
    own profile. The declaration is the only record of the authorship, and it is the
    record that catches it — `review_same_profile`, the same refusal a dispatched author
    would have met.
    """
    roots = _stage(tmp_path, reviewer=AUTHOR)
    _author(roots[1])

    refusal = _rung(roots).refusal

    assert refusal.kind == "review_same_profile"
    assert f"reviewer_profile={AUTHOR}" in refusal.found


def test_a_declaration_that_will_not_read_refuses_the_landing_by_name(tmp_path: Path) -> None:
    """The record that would not open could be this reviewer's own, so nothing clears."""
    roots = _stage(tmp_path)
    _record(roots[1], ISSUE, {"version": 1, "issue": ISSUE, "authors": [{}]})

    refusal = _rung(roots).refusal

    assert refusal.kind == "authorship_unreadable"
    assert f"record={review_loop.authorship_path(roots[1], ISSUE)}" in refusal.found
