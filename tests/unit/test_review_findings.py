"""The review seat's verbatim return channel (#393).

Two properties carry the issue, and every test here is one of them or a refusal that
protects one:

- **Verbatim.** What reaches the issue is the reviewer's own bytes. The extraction is
  asserted byte-for-byte against a block carrying the things a relay damages — fenced code,
  indentation, blank lines, a Markdown heading, trailing whitespace — because the two
  truncated reports of 2026-08-15 were a slicing bug and not a judgement one.
- **Attributed.** No verdict reaches an issue carrying gate figures whose runner is
  unrecorded. A block with no `gate_ran_by=` line is refused rather than posted, and the
  rendered header says whether the gate's commit is the reviewed one.

Posting is driven through a fake poster, so no test touches `gh`, and the refusal paths
assert that nothing was posted at all rather than that something harmless was.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    import pytest

review_findings = load_tool("review_findings")
pool_comment = load_tool("pool_comment")

REVIEWED_SHA = "a" * 40
OTHER_SHA = "b" * 40
DISPATCH_ID = "d-20260815-200723-4f5b78"
ISSUE = 328

# A findings block with everything a relay has been measured to damage in it.
BLOCK = "\n".join(
    [
        "## Review of #328 — 2 findings",
        "",
        "gate_ran_by=implementer sha=" + REVIEWED_SHA + " (just fast, 1041 passed, sampled)",
        "",
        "**High 1** — `tools/dispatch.py:2365` reads the breaker twice.",
        "",
        "```python",
        "    if refusal is not None:",
        "        return refusal          # trailing spaces below this line matter   ",
        "```",
        "",
        "  - indented continuation",
        "**Low 2** — a docstring names a retired seat.",
    ]
)


def log_with(block: str, *, before: str = "", after: str = "") -> str:
    """A dispatch log shaped like a real one: runner noise, then the delimited block."""
    return "\n".join(
        [
            "[dispatch] starting d-20260815-200723-4f5b78",
            before,
            review_findings.OPEN_SENTINEL,
            block,
            review_findings.CLOSE_SENTINEL,
            after,
        ]
    )


def record_at(
    tmp_path: Path,
    *,
    log: str,
    issue: object = ISSUE,
    base_sha: str = REVIEWED_SHA,
    seat: str = "review",
) -> Path:
    """Write the two files the channel reads: the dispatcher's plan and the run's log."""
    record = tmp_path / "dispatches" / DISPATCH_ID
    record.mkdir(parents=True)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": DISPATCH_ID,
                "issue": issue,
                "seat": seat,
                "profile": "opus-low",
                "lane": "claude-native",
                "permission_mode": "plan",
                "base_sha": base_sha,
                "route": {"reviewing": "codex-luna-max"},
            }
        ),
        encoding="utf-8",
    )
    (record / "dispatch.log").write_text(log, encoding="utf-8")
    return record


class Poster:
    """A fake `pool_comment.post`: records the exact bytes, or refuses like `gh` does."""

    def __init__(self, *, refuse: str = "") -> None:
        self.calls: list[tuple[int, str]] = []
        self.refuse = refuse

    def __call__(self, issue: int, body: str) -> None:
        self.calls.append((issue, body))
        if self.refuse:
            raise pool_comment.refuse("gh_failure", self.refuse)


# ------------------------------------------------------------------------- the extraction


def test_the_block_between_the_sentinels_is_returned_byte_for_byte() -> None:
    found = review_findings.extract(log_with(BLOCK))

    assert found.refusal == ""
    assert found.block == BLOCK, "the reviewer's bytes are the product; nothing may reflow them"


def test_a_log_with_no_sentinel_at_all_refuses_by_name() -> None:
    found = review_findings.extract("[dispatch] the review ran and reported in prose\n")

    assert found.refusal == review_findings.BLOCK_ABSENT
    assert found.block == ""


def test_the_last_complete_pair_wins_over_an_earlier_one() -> None:
    """A second block is a corrected block, and the correction is the answer."""
    first = "gate_ran_by=not_run reason=no paste on the thread\nsuperseded"
    log = log_with(first) + "\n" + log_with(BLOCK)

    assert review_findings.extract(log).block == BLOCK


def test_an_unterminated_final_sentinel_refuses_rather_than_falling_back(tmp_path: Path) -> None:
    """A run that died mid-report must not be published as a finished earlier one."""
    log = log_with(BLOCK) + "\n" + review_findings.OPEN_SENTINEL + "\n## Review of #328\n"

    found = review_findings.extract(log)
    assert found.refusal == review_findings.BLOCK_UNTERMINATED
    assert found.block == ""

    poster = Poster()
    outcome = review_findings.publish(record_at(tmp_path, log=log), post=poster)
    assert outcome.refusal == review_findings.BLOCK_UNTERMINATED
    assert poster.calls == []


def test_a_block_of_whitespace_is_no_findings_at_all() -> None:
    found = review_findings.extract(log_with("   \n\n"))

    assert found.refusal == review_findings.BLOCK_EMPTY


def test_sentinels_are_matched_as_whole_lines_not_as_substrings() -> None:
    """A brief quoting the contract inside the block cannot close it early."""
    quoting = "\n".join(
        [
            "gate_ran_by=orchestrator sha=" + REVIEWED_SHA,
            "The brief says to emit " + review_findings.CLOSE_SENTINEL + " on its own line.",
            "and that is not its own line",
        ]
    )

    assert review_findings.extract(log_with(quoting)).block == quoting


# ------------------------------------------------------------------------ the attribution


def test_the_gate_attribution_carries_the_runner_and_the_commit_it_ran_on() -> None:
    claim = review_findings.attribution(BLOCK)

    assert claim.refusal == ""
    assert claim.runner == review_findings.IMPLEMENTER
    assert claim.sha == REVIEWED_SHA


def test_a_block_with_no_attribution_is_refused_and_never_posted(tmp_path: Path) -> None:
    """The whole point: a gate figure whose runner is unrecorded does not reach an issue."""
    block = "## Review of #328\n\nTwo findings, and the commit's own counts look green."
    record = record_at(tmp_path, log=log_with(block))
    poster = Poster()

    outcome = review_findings.publish(record, post=poster)

    assert outcome.kind == review_findings.NOT_POSTED
    assert outcome.refusal == review_findings.ATTRIBUTION_MISSING
    assert poster.calls == []
    # The report still exists outside the log, which is the other half of the defect: one
    # round could not proceed because its report lived only in `dispatch.log`.
    kept = (record / review_findings.FINDINGS_NAME).read_text(encoding="utf-8")
    assert block in kept
    receipt = json.loads((record / review_findings.RECEIPT_NAME).read_text(encoding="utf-8"))
    assert receipt["kind"] == review_findings.NOT_POSTED
    assert receipt["refusal"] == review_findings.ATTRIBUTION_MISSING


def test_not_run_is_a_sayable_answer_and_needs_a_reason(tmp_path: Path) -> None:
    """`not_run` must be sayable, or the two runners become the only sayable answers."""
    stated = review_findings.attribution("gate_ran_by=not_run reason=the paste was absent")
    assert stated.refusal == ""
    assert stated.runner == review_findings.NOT_RUN

    bare = review_findings.attribution("gate_ran_by=not_run")
    assert bare.refusal == review_findings.ATTRIBUTION_MALFORMED

    poster = Poster()
    outcome = review_findings.publish(
        record_at(tmp_path, log=log_with("findings\ngate_ran_by=not_run reason=no paste")),
        post=poster,
    )
    assert outcome.kind == review_findings.POSTED
    assert len(poster.calls) == 1


def test_an_unknown_runner_or_a_missing_sha_is_malformed() -> None:
    unknown = review_findings.attribution("gate_ran_by=reviewer sha=" + REVIEWED_SHA)
    assert unknown.refusal == review_findings.ATTRIBUTION_MALFORMED

    shaless = review_findings.attribution("gate_ran_by=implementer just fast green")
    assert shaless.refusal == review_findings.ATTRIBUTION_MALFORMED

    short = review_findings.attribution("gate_ran_by=orchestrator sha=" + "c" * 12)
    assert short.refusal == review_findings.ATTRIBUTION_MALFORMED, "a short SHA names many commits"


def test_two_disagreeing_attributions_refuse_rather_than_pick_one() -> None:
    block = "\n".join(
        [
            "gate_ran_by=implementer sha=" + REVIEWED_SHA,
            "on reflection:",
            "gate_ran_by=not_run reason=the paste was from another branch",
        ]
    )

    assert review_findings.attribution(block).refusal == review_findings.ATTRIBUTION_REPEATED


# ----------------------------------------------------------------------------- publishing


def test_the_posted_body_is_the_block_plus_a_header_that_composes_nothing(
    tmp_path: Path,
) -> None:
    record = record_at(tmp_path, log=log_with(BLOCK))
    poster = Poster()

    outcome = review_findings.publish(record, post=poster)

    assert outcome.kind == review_findings.POSTED
    assert outcome.code == 0
    assert len(poster.calls) == 1
    issue, body = poster.calls[0]
    assert issue == ISSUE
    assert body.endswith(BLOCK + "\n"), "the block is the tail of the comment, untouched"
    assert DISPATCH_ID in body
    assert "opus-low" in body
    assert "codex-luna-max" in body
    assert REVIEWED_SHA in body
    assert "gate_sha_matches_reviewed=yes" in body
    assert str(record / "dispatch.log") in body, "a reader can check the transcription"
    assert body == (record / review_findings.FINDINGS_NAME).read_text(encoding="utf-8")
    receipt = json.loads((record / review_findings.RECEIPT_NAME).read_text(encoding="utf-8"))
    assert receipt["kind"] == review_findings.POSTED
    assert receipt["gate_ran_by"] == review_findings.IMPLEMENTER
    assert receipt["gate_sha"] == REVIEWED_SHA
    assert receipt["issue"] == ISSUE


def test_a_gate_run_on_another_commit_is_printed_rather_than_refused(tmp_path: Path) -> None:
    """#396's defect — a count from a different SHA — is said out loud, not refused on.

    Refusing would strand a real finding on a mistyped SHA. Saying it puts the
    disagreement in front of every later reader of the thread.
    """
    block = "findings\ngate_ran_by=implementer sha=" + OTHER_SHA
    poster = Poster()

    outcome = review_findings.publish(record_at(tmp_path, log=log_with(block)), post=poster)

    assert outcome.kind == review_findings.POSTED
    assert "gate_sha_matches_reviewed=no" in poster.calls[0][1]


def test_a_gh_that_could_not_post_keeps_the_body_and_names_the_retry(tmp_path: Path) -> None:
    record = record_at(tmp_path, log=log_with(BLOCK))
    poster = Poster(refuse="could not post to issue #328: gh: network is unreachable")

    outcome = review_findings.publish(record, post=poster)

    assert outcome.refusal == review_findings.POST_FAILED
    assert outcome.code == 1
    assert (record / review_findings.FINDINGS_NAME).exists()
    assert any("just review findings" in line for line in outcome.lines)


def test_a_dry_run_renders_the_body_and_posts_nothing(tmp_path: Path) -> None:
    poster = Poster()

    outcome = review_findings.publish(
        record_at(tmp_path, log=log_with(BLOCK)), post=poster, dry_run=True
    )

    assert outcome.code == 0
    assert outcome.kind == review_findings.NOT_POSTED
    assert poster.calls == []
    assert any(BLOCK in line for line in outcome.lines)


def test_a_record_that_cannot_be_read_refuses_without_posting(tmp_path: Path) -> None:
    absent = tmp_path / "dispatches" / DISPATCH_ID
    absent.mkdir(parents=True)
    poster = Poster()

    outcome = review_findings.publish(absent, post=poster)

    assert outcome.refusal == review_findings.RECORD_UNREADABLE
    assert poster.calls == []


def test_a_record_naming_no_issue_refuses_rather_than_guessing(tmp_path: Path) -> None:
    poster = Poster()

    outcome = review_findings.publish(
        record_at(tmp_path, log=log_with(BLOCK), issue=0), post=poster
    )

    assert outcome.refusal == review_findings.RECORD_UNREADABLE
    assert poster.calls == []


def test_a_seat_that_reviews_nothing_returns_nothing(tmp_path: Path) -> None:
    """The dispatcher's door is registry-driven: only a seat marked `reviews` uses it."""
    record = record_at(tmp_path, log=log_with(BLOCK), seat="implementer")

    outcome = review_findings.publish_for_seat(record, reviews=False)

    assert outcome.refusal == review_findings.NOT_A_REVIEW
    assert outcome.code == 0, "a non-review dispatch is not a failure"
    assert not (record / review_findings.RECEIPT_NAME).exists()


def test_the_seam_reads_the_channel_through_the_module_it_lives_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`publish_for_seat` with no poster passed uses `pool_comment.post` and nothing else."""
    record = record_at(tmp_path, log=log_with(BLOCK))
    poster = Poster()
    monkeypatch.setattr(pool_comment, "post", poster)

    outcome = review_findings.publish_for_seat(record, reviews=True)

    assert outcome.kind == review_findings.POSTED
    assert len(poster.calls) == 1


# --------------------------------------------------------------------------------- the CLI


def test_the_cli_prints_by_default_and_posts_only_when_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    record_at(tmp_path, log=log_with(BLOCK))
    poster = Poster()
    monkeypatch.setattr(pool_comment, "post", poster)
    argv = [DISPATCH_ID, "--dispatch-dir", str(tmp_path / "dispatches")]

    assert review_findings.main(argv) == 0
    assert poster.calls == []
    assert BLOCK in capsys.readouterr().out

    assert review_findings.main([*argv, "--post"]) == 0
    assert len(poster.calls) == 1


def test_the_cli_exits_one_on_a_named_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record_at(tmp_path, log="[dispatch] no block here\n")

    assert review_findings.main([DISPATCH_ID, "--dispatch-dir", str(tmp_path / "dispatches")]) == 1
    assert review_findings.BLOCK_ABSENT in capsys.readouterr().err


def test_the_review_group_reaches_the_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`just review findings <id>` is the surface an orchestrator has; it prints and reads."""
    review_exchange = load_tool("review_exchange")
    record_at(tmp_path, log=log_with(BLOCK))
    poster = Poster()
    monkeypatch.setattr(pool_comment, "post", poster)

    code = review_exchange.main(
        ["findings", DISPATCH_ID, "--dispatch-dir", str(tmp_path / "dispatches")]
    )

    assert code == 0
    assert poster.calls == []
    assert BLOCK in capsys.readouterr().out


# ------------------------------------------------------------------- the brief's own half


def test_the_brief_contract_names_the_sentinels_the_extractor_matches() -> None:
    """One home for the contract: a brief that taught a different pair would post nothing."""
    contract = "\n".join(review_findings.BRIEF_CONTRACT)

    assert review_findings.OPEN_SENTINEL in contract
    assert review_findings.CLOSE_SENTINEL in contract
    assert review_findings.ATTRIBUTION_PREFIX in contract
    for runner in review_findings.RUNNERS:
        assert runner in contract
