"""Render a finished pool's own record as the lines a close quotes (#199, ADR-0049).

Every corpus run that gates an issue is quoted into that issue before the issue
closes — verdict lines, worst class, evidence path, git SHA (`CLAUDE.md`,
`docs/regression-tier.md`). Until now that quote was composed by hand off 25
per-probe lines on stderr, at about eight orchestrator wakes per corpus (#181),
and once it cost worse than tokens: #134 quoted a "full corpus 20/20" banner —
figures, wall, evidence paths — before any tool result contained one, every
figure matching by luck. A rendered quote cannot be hallucinated. It matters
more than it looks, because the pool prune deletes passes and keeps failures,
so pass evidence outlives its own directory only in the quote.

So this reads, and it renders. It does not decide, and it does not post. The
failure-class table's required-response column is the agent's work;
`infra_unavailable` is printed as the stop it is rather than interpreted; and
the body goes to stdout for an agent to read, judge and paste (criterion 7).
Nor does it say "full corpus": a record cannot tell a whole corpus from an
`--issues` selection, and claiming the wrong one is exactly the unearned
figure this exists to stop.

Three rules keep the rendered body honest:

- The per-probe block is `pool_merge.render_summary` verbatim, prefix included,
  so the runner's own summary and the quote of it cannot drift (criterion 2).
  The reader that rebuilds the merge from the document lives in `pool_merge`
  for the same reason — one schema, one reader.
- A record that cannot be believed is refused rather than partly rendered
  (criterion 3). A pool directory with no `pool.json` is a run that died before
  its merge, and an evidence directory with no verdict is not a result
  (ADR-0022); a half-written document is the same non-result; a record with no
  verdict, no unrun probe and no stop measured nothing.
- The banner never understates its own rows. A `worst_class` below the worst
  verdict present is the record disagreeing with itself, and the banner takes
  the worse of the two and says so, because a quote reading green over a red
  row is #134's hole with a tool's authority behind it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

# tools/ holds standalone scripts rather than an importable package, so a
# sibling import needs the script's own directory on the path — the device
# `stall_watch.py` uses to reach this same module.
sys.path.insert(0, str(Path(__file__).parent))

from pool_merge import ProbeRow, merged_from_pool, render_summary, severity, worst_of

DEFAULT_RUNS_DIR: Final = Path.home() / ".arma-cti" / "runs"
POOL_GLOB: Final = "*-pool"

# What the failure-class table requires of a reader who meets this class, said
# in the banner rather than left to the reader's memory: it is not a result, so
# there is nothing here to interpret.
STOP_CLASS: Final = "infra_unavailable"


class RefusalError(Exception):
    """A record this tool will not render, and the reason a reader needs."""


def _text(document: dict[str, object], key: str) -> str:
    """One string field, empty for anything that is not one."""
    value = document.get(key)
    return value if isinstance(value, str) else ""


def _number(document: dict[str, object], key: str) -> int:
    """One integer field, zero for anything that is not one."""
    value = document.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def newest_pool(runs_dir: Path) -> Path | None:
    """Find the most recently written `pool.json` under the runs directory."""
    best: Path | None = None
    best_mtime = 0.0
    for candidate in runs_dir.glob(POOL_GLOB):
        artefact = candidate / "pool.json"
        try:
            mtime = artefact.stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            best, best_mtime = artefact, mtime
    return best


def resolve(target: Path) -> Path:
    """Find the `pool.json` a caller meant, or refuse with why it is not there.

    A pool directory with no record is a run that died before its merge: no
    verdict was written, nothing was measured under conditions anyone can
    interpret, and a partial banner over it would be the untyped green this
    tier exists to refuse (ADR-0022).
    """
    if target.is_file():
        return target
    artefact = target / "pool.json"
    if artefact.is_file():
        return artefact
    if not target.exists():
        message = f"no such path: {target}"
        raise RefusalError(message)
    if (target / "verdict.json").is_file():
        message = (
            f"{target} is one probe's evidence, not a pool's: it carries a verdict.json "
            f"and no pool.json. Point at the {POOL_GLOB} directory the run wrote beside it."
        )
        raise RefusalError(message)
    if not target.name.endswith("-pool"):
        message = (
            f"{target} is not a pool evidence directory: no pool.json, and the name is not "
            f"the {POOL_GLOB} a run writes."
        )
        raise RefusalError(message)
    message = (
        f"no pool.json in {target} — the run died before its merge, so no verdict set was "
        f"ever written. An evidence directory with no verdict is not a result (ADR-0022), "
        f"and nothing has been rendered."
    )
    raise RefusalError(message)


def read_pool(artefact: Path) -> dict[str, object]:
    """Read one pool record, refusing anything that is not a believable one."""
    try:
        document = json.loads(artefact.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as failure:
        message = (
            f"{artefact} is not a readable JSON document ({failure}) — a half-written "
            f"record is not a result, and nothing has been rendered."
        )
        raise RefusalError(message) from failure
    if not isinstance(document, dict):
        message = f"{artefact} is not a readable JSON object, so there is nothing to quote."
        raise RefusalError(message)
    if not (document.get("verdicts") or document.get("not_run") or document.get("stopped_early")):
        message = (
            f"{artefact} records no verdict, no unrun probe and no stop: nothing was "
            f"measured, so there is nothing to quote."
        )
        raise RefusalError(message)
    return document


def read_probe(evidence: str) -> dict[str, object]:
    """One probe's own `verdict.json`, empty when it is gone or unreadable.

    Empty is the common case on an old record rather than an error: the runner
    prunes passes to the last three per probe, which is precisely why the quote
    has to carry what the directory will not.
    """
    if not evidence:
        return {}
    try:
        document = json.loads((Path(evidence) / "verdict.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def tree_state(probes: dict[str, dict[str, object]]) -> str:
    """Say what the probes recorded about the working tree the run measured.

    A dirty tree is stated loudly, because the SHA in the banner is what a
    later session re-runs at and a dirty run is not at that SHA. Nobody having
    recorded it is said as that, never as clean.
    """
    flags = [document["git_dirty"] for document in probes.values() if "git_dirty" in document]
    if not flags:
        return "tree state unrecorded (probe evidence pruned or absent)"
    if any(flags):
        return "**tree dirty at run time — this sha does not reproduce the run**"
    return "tree clean"


def class_tally(rows: list[ProbeRow]) -> str:
    """Every class present and how many carried it, worst first."""
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.class_] = counts.get(row.class_, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-severity(item[0]), item[0]))
    return ", ".join(f"{count} {class_}" for class_, count in ordered)


def headline(recorded: str, derived: str) -> tuple[str, list[str]]:
    """Choose the banner's worst class, and say whatever has to be said about it.

    Taking the worse of the recorded and the derived answer is the fail-closed
    direction: the mem-stop overlay legitimately raises the record above its
    rows, while a record below its rows is a record that disagrees with itself
    and must not be quoted as the better of the two.
    """
    if not recorded:
        return derived, [
            (
                "the record carries no `worst_class`, so this is derived from its own "
                "verdicts (pool.json predates the field)"
            )
        ]
    if severity(derived) > severity(recorded):
        return derived, [
            (
                f"the record's own `worst_class` says `{recorded}`, which understates its "
                f"rows — the banner takes the worst verdict present, and the two disagree"
            )
        ]
    return recorded, []


def banner(
    document: dict[str, object], pool_dir: Path, probes: dict[str, dict[str, object]]
) -> list[str]:
    """Render the block a close quotes: what happened, at what SHA, and where it lives."""
    merged = merged_from_pool(document)
    worst, notes = headline(merged.worst_class, worst_of(merged.rows))
    passes = sum(1 for row in merged.rows if row.class_ == "pass")
    slots = document.get("slots")
    slot_count = len(slots) if isinstance(slots, list) else 0

    counts = f"{passes} of {len(merged.rows)} pass"
    if merged.not_run:
        counts += f", {len(merged.not_run)} probe(s) never run"
    stop = (
        " — a stop, not a result. Do not interpret it (CLAUDE.md failure-class table)"
        if worst == STOP_CLASS
        else ""
    )

    wall = f"wall {_number(document, 'wall_secs')} s across {slot_count} slot(s)"
    provenance = (
        f"sha `{_text(document, 'git_sha')[:12]}`, {tree_state(probes)}, "
        f"started {_text(document, 'started_at')}"
    )
    lines = [f"> **worst class `{worst}`{stop}** — {counts}, {wall}", f"> {provenance}"]
    if worst != "pass":
        lines.append(f"> classes: {class_tally(merged.rows)}")
    lines.extend(f"> {note}" for note in notes)
    stopped_early = _text(document, "stopped_early")
    if stopped_early:
        lines.append(f"> stopped early: {stopped_early}")
    lines.extend(dirty_slot_lines(document))
    lines.append(f"> pool evidence `{pool_dir}`")
    return lines


def dirty_slot_lines(document: dict[str, object]) -> list[str]:
    """Slots this run held, could not clear, and therefore never used."""
    dirty = document.get("dirty_slots")
    if not isinstance(dirty, list):
        return []
    return [
        f"> slot {entry.get('slot')} held and never used: {entry.get('detail')} "
        f"(`{entry.get('class', STOP_CLASS)}`)"
        for entry in dirty
        if isinstance(entry, dict)
    ]


def detail_lines(rows: list[ProbeRow], probes: dict[str, dict[str, object]]) -> list[str]:
    """One line per probe that did not pass, carrying what it recorded and where."""
    failures = [row for row in rows if row.class_ != "pass"]
    if not failures:
        return []
    lines = ["", "Non-pass probes:", ""]
    for row in sorted(failures, key=lambda row: severity(row.class_), reverse=True):
        document = probes.get(row.probe, {})
        detail = _text(document, "detail")
        if not document:
            said = (
                f"no verdict.json at `{row.evidence}` — pruned, or the worker died before "
                f"writing one (ADR-0022)"
            )
        else:
            said = f"`{detail}`" if detail else "no detail recorded"
        lines.append(
            f"- **`{row.probe}` {row.class_}** — {row.elapsed_secs} s, slot {row.slot} — {said}"
        )
        lines.append(f"  evidence `{row.evidence}`")
    return lines


def comment_for(artefact: Path) -> list[str]:
    """Render the whole body: banner, the runner's own verdict block, then the reds."""
    document = read_pool(artefact)
    merged = merged_from_pool(document)
    probes = {row.probe: read_probe(row.evidence) for row in merged.rows}
    slots = document.get("slots")
    summary = render_summary(
        merged,
        started_at=_text(document, "started_at"),
        git_sha=_text(document, "git_sha"),
        slot_count=len(slots) if isinstance(slots, list) else 0,
    )
    return [
        *banner(document, artefact.parent, probes),
        "",
        "```",
        *(line for line in summary if line),
        "```",
        *detail_lines(merged.rows, probes),
    ]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """One door: a pool to read, defaulting to the newest one on this machine."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pool",
        nargs="?",
        default="",
        help="a pool evidence directory or its pool.json; default is the newest pool",
    )
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print the body an agent reads, judges and pastes. Never post it."""
    args = parse_args(argv)
    try:
        if args.pool:
            artefact = resolve(Path(args.pool))
        else:
            artefact = newest_pool(args.runs_dir)
            if artefact is None:
                message = f"no pool evidence under {args.runs_dir}, so there is nothing to quote."
                raise RefusalError(message)  # noqa: TRY301 — one refusal path, one handler
        body = comment_for(artefact)
    except RefusalError as refusal:
        print(f"[verdict] {refusal}", file=sys.stderr)  # noqa: T201 — a CLI's refusal channel
        return 2
    for line in body:
        print(line)  # noqa: T201 — the body IS this script's output
    return 0


if __name__ == "__main__":
    sys.exit(main())
