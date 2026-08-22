"""Whether a landing owes the in-world corpus, and whether a named run clears it (#302).

CLAUDE.md's `just regress` row owes the full corpus to any landing that touches an
in-world surface. Until now nothing read that row at landing time, and on 2026-08-09
`85dfb1b` landed 181 changed lines of `src/cti_daemon/transport.py` having run no corpus
at all — found three landings later by an unrelated dispatch. The rule was known, quoted,
and in the dispatch's own brief; both the agent and the orchestrator considered it and
answered wrongly, because neither checked the diff against the list. #209's ruling covers
exactly that shape: where a rule-table already decides, an agent is not handed the job of
remembering.

So this decides, and `tools/land.py` acts on it.

## What "owed" is computed from

The **landing diff against `origin/main`**, never the issue body: a body predicts a
surface and a diff is one. The surface list is class 5 of the routing policy, read from
fetched `origin/main` rather than from the tree being landed — the candidate diff must
not be able to widen the list that judges it — and it is the same row the routing gate,
`tools/gate.py`'s list — which `tools/brief.py`'s prediction and `tools/trial.py`'s
corpus check both call — read.

## What clears it, and what does not

A corpus run clears a landing only when the run is *about* that landing:

1. its `git_sha` resolves in this repository at all, so the claim can be checked;
2. it produced a verdict row for **every** probe in the corpus — a filtered run is
   `--issues` provenance, which CLAUDE.md is explicit is never a gate for your own issue,
   and a probe left in `not_run` was never measured at all;
3. **no in-world path differs between that commit and HEAD.** Not ancestry: `just land`
   rebases, so the commit a corpus ran over is orphaned by every landing that follows a
   sibling's, and an ancestry rule would make the gate unclearable in normal traffic.
   What matters is that the world the corpus measured is the world being pushed, so the
   test is a tree comparison over the in-world surfaces and nothing else. A rebase over
   somebody else's tooling commit still clears; a rebase over their in-world commit does
   not;
4. no probe recorded a dirty tree at run time, because then the SHA does not reproduce
   the run and what was measured is not what is being pushed;
5. and its worst class is `pass`.

Only 5 is about the code under test. 1 to 4 are about whether the evidence is evidence,
which is why they all come out as *still owed* rather than as a red: a run that does not
cover this landing says nothing about it, exactly as `infra_unavailable` says nothing.

The honestly stated limit of 3: coverage is judged over the same surface list that
decides the obligation, so a change to code that runs in-world without being *on* that
list — the planner, say — neither owes the corpus nor invalidates a run. That is the
list's meaning applied consistently rather than an oversight, and widening the list is
the way to change it.

## Two refusals, because they are two conversations

`corpus_owed` says the corpus has not been run over this tree — the remedy is a slot of
the Arma tier. `corpus_not_pass` says it has, and the world disagreed with the change —
the remedy is in the failure-class table's required-response column for the class named,
and the class is quoted rather than interpreted. Naming the second one `corpus_red` was
rejected: an `infra_unavailable` pool is not a red, and calling it one would tell a reader
a stop was a result, which is the misreading that row of the table exists to prevent.

A third, `corpus_check_unreadable`, is the fail-closed rung `tools/land.py` already has
twice (`gate_blocked`, `routing_policy_gate_unreadable`): a check that could not run is
not a check that passed (#41).

## What is deliberately absent

There is no flag, argument or environment variable that skips this. A landing's
`--corpus <pool>` *names* evidence, and every claim it makes is verified here against the
pool's own record
— so pointing it at the wrong run refuses rather than passes. The landing protocol's
refspec is a constant no argument reaches, and this belongs in that tradition (#213).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `land.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

import pool_comment
import pool_merge

if TYPE_CHECKING:
    from collections.abc import Iterable

# Where the corpus lives, relative to the tree being landed. The runner's own
# enumeration; `tests/unit/test_corpus_gate.py` runs `regress.sh --list` against this
# rather than trusting the mirror.
PROBE_DIR: Final = Path("spike") / "probes"
PROBE_SUFFIX: Final = "*.sqf"

# S105 on both: these are failure-class and refusal names from CLAUDE.md's table, and
# ruff's hardcoded-password heuristic matches on the substring rather than on any use.
PASS: Final = "pass"  # noqa: S105
STOP_CLASS: Final = "infra_unavailable"

OWED: Final = "corpus_owed"
NOT_PASS: Final = "corpus_not_pass"  # noqa: S105
UNREADABLE: Final = "corpus_check_unreadable"

HOW_MANY_SHOWN: Final = 10

# Who can clear it, said in the refusal rather than left to the reader's memory. A
# dispatched session genuinely cannot run the corpus — `just regress` is in no dispatch
# allowlist — so the honest instruction for that seat is to stop, not to try.
WHO_CAN_CLEAR: Final = (
    "The corpus needs a slot of the Arma tier on this machine, and a dispatched session "
    "cannot take one: `just regress` is in no dispatch allowlist, and widening it is a "
    "permissions decision (#296/#298), not yours. If you are a dispatched agent, stop "
    "here and hand back to the orchestrator with your branch and this tree's HEAD — the "
    "work is committed and nothing was pushed. The orchestrator runs `just regress` with "
    "no filter, then lands with `just land --audit-file <criterion audit file> --corpus "
    "<pool evidence directory>`, and "
    "quotes `just verdict`'s rendered body verbatim into the issue without retyping the "
    "SHA or the evidence path (#219, #235)."
)

READ_THE_TABLE: Final = (
    "The corpus ran over this tree and its worst class is above. Take the required "
    "response from CLAUDE.md's failure-class table for that class — nothing here "
    "interprets it, and an `infra_unavailable` pool is a stop rather than a result. "
    "Nothing was pushed."
)

CHECK_DID_NOT_RUN: Final = (
    "The corpus rung could not be run, so nothing was pushed. A check that could not run "
    "is not a check that passed (#41). Repair what is named above and run `just land "
    "--audit-file <criterion audit file>` again."
)


class Finding(NamedTuple):
    """One corpus-rung refusal: its kind, and the lines that show why."""

    kind: str
    found: tuple[str, ...]

    @property
    def action(self) -> str:
        """The instruction this kind of refusal carries."""
        if self.kind == NOT_PASS:
            return READ_THE_TABLE
        if self.kind == UNREADABLE:
            return CHECK_DID_NOT_RUN
        return WHO_CAN_CLEAR


class Outcome(NamedTuple):
    """The corpus rung's whole answer: a refusal or none, and what made it owed.

    Both halves, because a landing that cleared and one that never owed anything are
    the same exit and different facts, and the report says which.
    """

    finding: Finding | None
    in_world: tuple[str, ...] = ()

    def line(self, named: Path | None) -> str:
        """Render the report line for a landing this rung let through."""
        if not self.in_world:
            return "corpus=not_owed reason=no_in_world_path"
        return f"corpus=cleared run={named} in_world={len(self.in_world)} path(s)"


class Run(NamedTuple):
    """A named corpus run, as far as this rung has to know it.

    Everything git had to answer is already answered here, so the judgement below is a
    pure function over data and `tests/unit/test_corpus_gate.py` drives it without a
    repository — `test_land.py` covers the assembly against a real one.
    """

    path: Path
    document: dict[str, object]
    sha: str
    known: bool
    moved: tuple[str, ...]
    dirty: bool | None


def full_corpus(tree: Path) -> tuple[str, ...]:
    """Every probe `just regress` runs with no filter, read off the tree being landed.

    Mirrors `spike/regress.sh`'s own enumeration — every `spike/probes/*.sqf`, by stem,
    sorted. The mirror is proven rather than assumed: the test suite runs the runner's
    own `--list` against this.
    """
    return tuple(sorted(path.stem for path in (tree / PROBE_DIR).glob(PROBE_SUFFIX)))


def read_record(named: Path) -> tuple[dict[str, object] | None, str]:
    """Read the named pool's own record, or say why it cannot be believed.

    `pool_comment` already decides what a believable pool record is — a directory with no
    `pool.json` is a run that died before its merge, and a document recording no verdict
    measured nothing (ADR-0022). This calls that reader rather than growing a second one.
    """
    try:
        artefact = pool_comment.resolve(named)
        return pool_comment.read_pool(artefact), ""
    except pool_comment.RefusalError as refusal:
        return None, f"{refusal.kind}: {refusal}"


def pool_class(document: dict[str, object]) -> str:
    """Answer the class a reader must act on: the worse of the record's own and its rows'.

    `pool_comment.headline` is that reading — it takes the worse of the recorded and the
    derived answer, because a record below its own rows is a record disagreeing with
    itself. A `stopped_early` pool is raised to the stop class on top, for the same
    fail-closed reason `pool_reads_green` reads one as not green.
    """
    merged = pool_merge.merged_from_pool(document)
    worst, _notes = pool_comment.headline(merged.worst_class, pool_merge.worst_of(merged.rows))
    if document.get("stopped_early") and pool_merge.severity(STOP_CLASS) > pool_merge.severity(
        worst
    ):
        return STOP_CLASS
    return worst


def recorded_dirty(document: dict[str, object]) -> bool | None:
    """Whether any probe recorded a dirty tree at run time; `None` when none recorded it.

    `pool_comment.tree_state` answers the same question as prose for a human to read;
    this answers it as a decision. Nobody having recorded it is `None` rather than
    `False`, because the pass prune legitimately removes a green probe's evidence and
    reading that absence as clean would be the #41 shape pointing the wrong way.
    """
    flags = [
        bool(probe["git_dirty"])
        for row in pool_merge.merged_from_pool(document).rows
        if "git_dirty" in (probe := pool_comment.read_probe(row.evidence))
    ]
    return any(flags) if flags else None


def measured(document: dict[str, object]) -> frozenset[str]:
    """Name the probes this pool produced a verdict row for.

    Rows only. A probe the merge left in `not_run` never started, so a pool listing it is
    a pool that did not measure it — which is precisely the gap a filtered run leaves.
    """
    return frozenset(row.probe for row in pool_merge.merged_from_pool(document).rows)


def _capped(label: str, values: Iterable[str]) -> tuple[str, ...]:
    """Name the offenders, capped: a count is not something to judge on."""
    listed = list(values)
    lines = [f"{label}={value}" for value in listed[:HOW_MANY_SHOWN]]
    if len(listed) > HOW_MANY_SHOWN:
        lines.append(f"and={len(listed) - HOW_MANY_SHOWN} more")
    return tuple(lines)


def unreadable(found: tuple[str, ...]) -> Finding:
    """Build the fail-closed finding for a corpus rung that could not run."""
    return Finding(UNREADABLE, ("check=corpus over the real diff", *found))


def owed_with_no_run(in_world: tuple[str, ...]) -> Finding:
    """Build the refusal for an in-world landing that named no corpus run at all."""
    return Finding(OWED, (*_capped("in_world", in_world), "corpus_run=none"))


def judge(run: Run, corpus: Iterable[str]) -> Finding | None:
    """Decide whether this run clears the landing, naming what is wrong when it does not.

    Coverage first, verdict last. A run that is not about this tree says nothing about
    it whatever colour it came out, so reporting its class would invite a reader to act
    on a measurement of somebody else's code.
    """
    named = f"corpus_run={run.path}"
    sha = f"corpus_sha={run.sha or 'unrecorded'}"
    if not run.known:
        return Finding(OWED, (named, sha, "rejected=commit_not_in_this_repository"))
    missing = [name for name in corpus if name not in measured(run.document)]
    if missing:
        return Finding(OWED, (named, sha, "rejected=partial_corpus", *_capped("missing", missing)))
    if run.moved:
        return Finding(
            OWED, (named, sha, "rejected=superseded", *_capped("changed_since", run.moved))
        )
    if run.dirty:
        return Finding(OWED, (named, sha, "rejected=tree_dirty_at_run_time"))
    verdict = pool_class(run.document)
    if verdict != PASS:
        return Finding(NOT_PASS, (named, sha, f"corpus_class={verdict}"))
    return None
