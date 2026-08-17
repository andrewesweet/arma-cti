"""The review seat's verbatim return channel (#393, human ruling of 2026-08-15).

A review dispatch is contained by a forced `plan` mode (`tools/dispatch.py`'s `SEATS`,
ADR-0071 ruling 4), so it cannot post its own findings. Until now that meant the
orchestrator read the run's transcript, composed a comment and posted it — the
propose-and-approve shape ruling 4 exists to keep apart, since the seat relaying a
verdict is the seat that dispatched the round being judged. It cost accuracy as well as
independence: three review reports were posted late on 2026-08-15, one late enough that
the fix round it fed had to be re-dispatched because the report *"lived only in
`~/.arma-cti/dispatches/…/dispatch.log`"*, and two earlier ones were posted truncated
because the relay sliced the transcript wrongly. The four dispatches that provoked the
issue: `d-20260815-200723-4f5b78` (#328's re-review), `d-20260815-193957-77c841` (#334
round 3), `d-20260815-203651-520173` (#334's compliance check), `d-20260815-203712-0fe148`
(#329's re-review).

The ruling: **the review seat writes its findings to a known place, and the dispatch
machinery posts them verbatim.** Not widening the seat's permissions, and not keeping the
relay. *"The defect is the composition step, not the write bar."*

## The known place is the seat's own output, not a file it writes

The seat need not — and under `plan` mode may not reliably — write anything. Its final
message already lands byte-for-byte in a file the machinery owns: `claude --print` writes
the final message to stdout and `tools/dispatch.sh` redirects the runner's stdout into
`<record>/dispatch.log`. So the channel is a **delimiter contract over output the seat
already produces**: the review brief tells it to emit its findings between two sentinel
lines, and this module extracts the bytes between them.

That choice costs nothing in permissions and works on every lane — `codex exec`'s stdout
reaches the same log — where a written file would have to clear whatever a lane's sandbox
allows outside the worktree, which is measured as unsettled (`docs/agents/dispatched-session-commands.md`).

Extraction is byte-exact and takes the **last** complete pair, and a trailing unterminated
sentinel refuses rather than falling back to an earlier pair: a run that died mid-report
must not be published as if it had finished. Nothing here summarises, re-flows or
truncates; the only composed text is this module's fixed header, and it names the log it
read so a reader can check the transcription — option 3's one virtue, kept for free.

## The gate: not this channel's cargo, and the record names who ran it

`#353`'s ruling of 2026-08-14 already settled the gate question this issue reopened: *"the
review seat gets no executable mode. It reads the implementer's pasted gate output; it does
not check out, does not run a gate, does not mutate."* So gate evidence does **not** travel
back through this channel — the reviewer produces none — and what travels instead is the
**attribution**: a required `gate_ran_by=` line inside the block, naming who ran the gate
the review is judging.

The line is required, not encouraged: a block without it is refused
`gate_attribution_missing` and not posted. A gate figure whose runner is unrecorded is the
defect this project keeps paying for — a check that did not run reading as one that passed
— and the mechanical floor against it is that no review verdict reaches an issue without
saying whose hands produced the figures it trusted. `implementer` and `orchestrator` must
carry the `sha=` the run was made on, because a count from a different commit is the
sharper version of the same defect; `not_run` must carry a reason. The rendered header
compares that SHA against the reviewed commit on the dispatch record and says whether they
agree — a printed disagreement rather than a refusal, because a real finding must not be
stranded by a mistyped SHA.

The independent re-execution stays where #353's ruling left it: `just land` re-runs
`just fast` on the rebased tree, after review rather than before, and no flag skips it.

## What this module does not do

It does not adjudicate, rank or judge, and it writes no verdict: the verdict record is
`tools/review_exchange.py`'s and the loop over findings is `tools/review_loop.py`'s. It
posts one comment and leaves a receipt beside the dispatch record. A refusal still writes
what it extracted, so no report ever lives only in a log again.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `dispatch.py`, `brief.py` and
# `review_exchange.py` all use.
sys.path.insert(0, str(Path(__file__).parent))

import pool_comment

# The delimiter contract. Two distinct lines rather than one repeated marker, so a half
# written block is a different fact from a whole one; `<<<`/`>>>` because neither string
# contains the other, so scanning for the opener can never match the closer.
OPEN_SENTINEL: Final = "<<<CTI-REVIEW-FINDINGS"
CLOSE_SENTINEL: Final = "CTI-REVIEW-FINDINGS>>>"

LOG_NAME: Final = "dispatch.log"
PLAN_NAME: Final = "dispatch.json"
FINDINGS_NAME: Final = "findings.md"
RECEIPT_NAME: Final = "findings.json"
DISPATCH_ROOT: Final = Path.home() / ".arma-cti" / "dispatches"

# Who can have run the gate a review judges. `implementer` is #353's ruled shape — the
# reviewer reads a paste; `orchestrator` is the eleven runs of 2026-08-15 that the
# orchestrator executed because nobody else could; `not_run` is the honest third answer,
# which the record must be able to carry or the other two become the only sayable ones.
IMPLEMENTER: Final = "implementer"
ORCHESTRATOR: Final = "orchestrator"
NOT_RUN: Final = "not_run"
RUNNERS: Final = (IMPLEMENTER, ORCHESTRATOR, NOT_RUN)
ATTRIBUTION_PREFIX: Final = "gate_ran_by="
SHA_FIELD: Final = re.compile(r"\bsha=([0-9a-f]{40})\b")
REASON_FIELD: Final = re.compile(r"\breason=(\S.*)")

BLOCK_ABSENT: Final = "findings_block_absent"
BLOCK_UNTERMINATED: Final = "findings_block_unterminated"
BLOCK_EMPTY: Final = "findings_block_empty"
ATTRIBUTION_MISSING: Final = "gate_attribution_missing"
ATTRIBUTION_MALFORMED: Final = "gate_attribution_malformed"
ATTRIBUTION_REPEATED: Final = "gate_attribution_repeated"
RECORD_UNREADABLE: Final = "record_unreadable"
NOT_A_REVIEW: Final = "not_a_review_dispatch"
POST_FAILED: Final = "post_failed"

POSTED: Final = "posted"
NOT_POSTED: Final = "not_posted"

# The one line a brief has to carry for the channel to work at all, and the one line this
# module has to be able to parse. Held here so the brief composer and the extractor cannot
# drift; `tools/brief.py` renders it into every review briefing.
BRIEF_CONTRACT: Final = (
    f"Emit your findings between `{OPEN_SENTINEL}` and `{CLOSE_SENTINEL}`, each on its own"
    " line, as the last thing you output. `tools/review_findings.py` posts those bytes to"
    " the issue verbatim when the dispatch ends — you do not post, and nothing composes"
    " them for you (#393).",
    f"Inside the block, one line must read `{ATTRIBUTION_PREFIX}implementer sha=<40-char"
    f" sha>`, `{ATTRIBUTION_PREFIX}orchestrator sha=<40-char sha>` or"
    f" `{ATTRIBUTION_PREFIX}not_run reason=<why>` — who ran the gate you are judging. A"
    " block without it is refused and not posted. You run no gate yourself (#353's ruling"
    " of 2026-08-14): you read the paste and say whose it is.",
)


class Extract(NamedTuple):
    """The bytes between the sentinels, or the named reason there are none."""

    block: str
    refusal: str
    detail: str


class Attribution(NamedTuple):
    """Who ran the gate this review judged, off the block's own required line."""

    line: str
    runner: str
    sha: str
    refusal: str
    detail: str


class Outcome(NamedTuple):
    """What the channel did, in the shape the seam prints and the receipt keeps."""

    kind: str
    refusal: str
    lines: tuple[str, ...]
    code: int


def extract(log: str) -> Extract:
    """Take the last complete sentinel pair's bytes, exactly as the seat wrote them.

    An opener with no closer after it refuses rather than falling back to an earlier pair:
    the newest block is the seat's answer, and a truncated newest block means the run died
    mid-report — which is a thing to see, not to paper over with a superseded one.
    """
    lines = log.splitlines()
    opened = [index for index, line in enumerate(lines) if line.strip() == OPEN_SENTINEL]
    if not opened:
        return Extract("", BLOCK_ABSENT, f"sentinel={OPEN_SENTINEL} occurrences=0")
    start = opened[-1]
    closed = [
        index
        for index, line in enumerate(lines[start + 1 :], start + 1)
        if line.strip() == CLOSE_SENTINEL
    ]
    if not closed:
        return Extract("", BLOCK_UNTERMINATED, f"opened_at_line={start + 1} closed=never")
    block = "\n".join(lines[start + 1 : closed[0]])
    if not block.strip():
        return Extract("", BLOCK_EMPTY, f"opened_at_line={start + 1}")
    return Extract(block, "", f"opened_at_line={start + 1} block_lines={closed[0] - start - 1}")


def attribution(block: str) -> Attribution:
    """Read the block's required gate attribution, or name why it cannot be read.

    Exactly one claim, because two disagreeing claims leave a reader guessing which figure
    the verdict rested on, and guessing is the thing this line exists to remove.
    """
    claims = [
        line.strip() for line in block.splitlines() if line.strip().startswith(ATTRIBUTION_PREFIX)
    ]
    if not claims:
        return Attribution("", "", "", ATTRIBUTION_MISSING, f"expected={ATTRIBUTION_PREFIX}…")
    if len(claims) > 1:
        return Attribution(claims[0], "", "", ATTRIBUTION_REPEATED, f"claims={len(claims)}")
    line = claims[0]
    runner, _, tail = line.removeprefix(ATTRIBUTION_PREFIX).partition(" ")
    if runner not in RUNNERS:
        return Attribution(line, "", "", ATTRIBUTION_MALFORMED, f"runner={runner or '<absent>'}")
    if runner == NOT_RUN:
        if not REASON_FIELD.search(tail):
            return Attribution(line, runner, "", ATTRIBUTION_MALFORMED, "reason=<absent>")
        return Attribution(line, runner, "", "", f"runner={runner}")
    found = SHA_FIELD.search(tail)
    if found is None:
        return Attribution(line, runner, "", ATTRIBUTION_MALFORMED, "sha=<absent or not 40 hex>")
    return Attribution(line, runner, found.group(1), "", f"runner={runner}")


def _sha_agreement(gate_sha: str, reviewed_sha: str) -> str:
    """Whether the gate's commit is the reviewed one — printed, never refused on."""
    if not gate_sha:
        return "not_applicable"
    if not reviewed_sha:
        return "unstated_on_record"
    return "yes" if gate_sha == reviewed_sha else "no"


def render(plan: dict[str, object], found: Extract, claim: Attribution, source: Path) -> str:
    """Render the comment: a fixed header this module owns, then the block untouched."""
    route = plan.get("route")
    reviewing = str(route.get("reviewing", "")) if isinstance(route, dict) else ""
    reviewed_sha = str(plan.get("base_sha", ""))
    header = [
        f"## Review findings — `{plan.get('dispatch_id', '')}`",
        "",
        "Posted verbatim by `tools/review_findings.py` from the review dispatch's own output"
        " (#393). The bytes below the rule are the reviewer's, extracted between its"
        f" sentinels from `{source}`; nothing composed them and nothing sliced them.",
        "",
        f"- profile `{plan.get('profile', '')}` on lane `{plan.get('lane', '')}`,"
        f" reviewing `{reviewing or 'unstated'}`, permission mode"
        f" `{plan.get('permission_mode', '')}` (forced by the seat; a review lands nothing)",
        f"- reviewed commit `{reviewed_sha or 'unstated'}`",
        f"- `{claim.line}` — gate_sha_matches_reviewed="
        f"{_sha_agreement(claim.sha, reviewed_sha)}."
        " The reviewer ran no gate (#353's ruling of 2026-08-14); `just land` re-runs"
        " `just fast` on the rebased tree after this verdict.",
        f"- extraction: {found.detail}",
        "",
        "---",
        "",
    ]
    return "\n".join([*header, found.block, ""])


def _receipt(
    plan: dict[str, object], outcome: Outcome, claim: Attribution, at: datetime
) -> dict[str, object]:
    """The fact of the channel having run, beside the record it read."""
    return {
        "dispatch_id": plan.get("dispatch_id", ""),
        "issue": plan.get("issue"),
        "kind": outcome.kind,
        "refusal": outcome.refusal,
        "gate_ran_by": claim.runner,
        "gate_sha": claim.sha,
        "gate_sha_matches_reviewed": _sha_agreement(claim.sha, str(plan.get("base_sha", ""))),
        "at": at.isoformat(),
    }


def _refused(kind: str, detail: str, remedy: str) -> Outcome:
    return Outcome(
        NOT_POSTED,
        kind,
        (f"review_findings=not_posted refusal={kind}", f"found={detail}", f"remedy={remedy}"),
        1,
    )


NO_ISSUE: Final = 0


def publish(
    record: Path,
    *,
    post: Callable[[int, str], object] | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> Outcome:
    """Extract, check the attribution, post once, and leave the receipt either way.

    Everything is written before the post is attempted and the extracted block is written
    even when the channel refuses, because the failure this closes is a report that existed
    only inside a log nobody read.

    The poster is resolved here rather than bound as a default, so the one mutation this
    module makes is reachable by a test through the module it lives in — `pool_comment.post`
    validates the issue and gives `gh` the exact bytes, and there is no second copy of that.
    """
    at = now or datetime.now(tz=UTC)
    try:
        plan = json.loads((record / PLAN_NAME).read_text(encoding="utf-8"))
        log = (record / LOG_NAME).read_text(encoding="utf-8")
    except (OSError, ValueError) as unreadable:
        return _refused(
            RECORD_UNREADABLE,
            f"{type(unreadable).__name__}: {unreadable}",
            f"the channel reads {PLAN_NAME} and {LOG_NAME} under the dispatch record.",
        )
    if not isinstance(plan, dict):
        return _refused(
            RECORD_UNREADABLE, "dispatch.json is not an object", "re-read the dispatch record."
        )
    found = extract(log)
    outcome, claim = _decide(
        record, plan, found, at=at, post=post or pool_comment.post, dry_run=dry_run
    )
    (record / RECEIPT_NAME).write_text(
        json.dumps(_receipt(plan, outcome, claim, at), indent=2) + "\n", encoding="utf-8"
    )
    return outcome


def _decide(  # noqa: PLR0913 — the whole decision in one place, each input read once
    record: Path,
    plan: dict[str, object],
    found: Extract,
    *,
    at: datetime,
    post: Callable[[int, str], object],
    dry_run: bool,
) -> tuple[Outcome, Attribution]:
    """The ladder from extracted bytes to a posted comment, one return per ending."""
    none = Attribution("", "", "", "", "")
    if found.refusal:
        return _refused(
            found.refusal,
            found.detail,
            f"a review's findings go between `{OPEN_SENTINEL}` and `{CLOSE_SENTINEL}`"
            " (the brief carries the contract); re-dispatch the review.",
        ), none
    claim = attribution(found.block)
    body = render(plan, found, claim, record / LOG_NAME)
    (record / FINDINGS_NAME).write_text(body, encoding="utf-8")
    if claim.refusal:
        return _refused(
            claim.refusal,
            claim.detail,
            f"the block carries one `{ATTRIBUTION_PREFIX}` line naming who ran the gate;"
            f" the extracted block is kept at {record / FINDINGS_NAME}.",
        ), claim
    issue = plan.get("issue")
    if not isinstance(issue, int) or issue <= NO_ISSUE:
        return _refused(
            RECORD_UNREADABLE,
            f"issue={issue!r}",
            "the dispatch record names the issue a review's findings belong to.",
        ), claim
    if dry_run:
        return Outcome(
            NOT_POSTED,
            "",
            (f"review_findings=rendered issue=#{issue} gate_ran_by={claim.runner}", body),
            0,
        ), claim
    try:
        post(issue, body)
    except pool_comment.RefusalError as failure:
        return _refused(
            POST_FAILED,
            str(failure),
            f"the body is kept at {record / FINDINGS_NAME};"
            f" re-post with `just review findings {plan.get('dispatch_id', '')} --post`.",
        ), claim
    return Outcome(
        POSTED,
        "",
        (
            f"review_findings=posted issue=#{issue} gate_ran_by={claim.runner} at={at.isoformat()}",
            f"body={record / FINDINGS_NAME}",
        ),
        0,
    ), claim


def publish_for_seat(record: Path, *, reviews: bool) -> Outcome:
    """The dispatcher's door: run the channel for a review dispatch, and nothing else.

    Called from the detached child after the run ends, so the findings reach the issue with
    no turn in between — the lateness half of #393. A seat that reviews nothing has no
    findings to return and gets a named no-op rather than an extraction attempt.
    """
    if not reviews:
        return Outcome(
            NOT_POSTED,
            NOT_A_REVIEW,
            (f"review_findings=skipped refusal={NOT_A_REVIEW}",),
            0,
        )
    return publish(record)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Read a dispatch id; print by default, post only when asked."""
    parser = argparse.ArgumentParser(prog="just review findings", description=__doc__)
    parser.add_argument("dispatch_id", help="the review dispatch whose findings to read")
    parser.add_argument(
        "--post", action="store_true", help="post the rendered body to the dispatch's issue"
    )
    parser.add_argument(
        "--dispatch-dir", default=str(DISPATCH_ROOT), help="the dispatch records' root"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print what the channel would post, or post it; refusals are named and exit 1."""
    args = parse_args(argv)
    outcome = publish(Path(args.dispatch_dir) / args.dispatch_id, dry_run=not args.post)
    stream = sys.stdout if outcome.code == 0 else sys.stderr
    for line in outcome.lines:
        print(line, file=stream)
    return outcome.code


if __name__ == "__main__":
    sys.exit(main())
