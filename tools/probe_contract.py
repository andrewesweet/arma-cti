"""Print the probe↔harness contract, derived from the runner (#215, ADR-0049).

The largest "agent reads prose to operate the process" surface in the project is
not a document — it is agents reading ~1,000 lines of bash to work out what a
probe owes the harness, because that contract was written down nowhere (#209's
interface study). A contract read wrong out of bash is a probe that tests the
wrong thing, and the project has the recorded instance: #150/#191's
`ai-reinforce` timed out in its own scaffold while the decision under test had
already fired.

This prints the contract by reading it off the runner rather than restating a
second copy beside it, so it cannot drift: the header keys come from the
`header_of` call sites and the validation block in `spike/regress.sh`, the
completion sentinel and the window binding come from the same, and the classes
the runner emits come from its own `fail`/`failure_class=` sites. A header key
added to `regress.sh` without appearing here is a bug, and
`tests/unit/test_probe_contract.py` plants exactly that mutation to prove the
derivation is live rather than decorative.

What each failure class *means* is deliberately not here. CLAUDE.md's "Failure
classes" table owns verdict semantics; this output points at it and restates
none of it (#209's non-negotiable, and the recipe most tempted to break it).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGRESS_SH = REPO / "spike" / "regress.sh"
RUN_SH = REPO / "spike" / "run.sh"

# A `header_of "<anything>" <key>` call site: every header key the runner reads
# appears this way, so the key set is recovered without a hand-maintained list.
# The first argument varies (`$file`, `$PROBE_DIR/$name.sqf`), so it matches any
# quoted form; the key is always a bare lowercase word.
_HEADER_OF_CALL = re.compile(r'header_of\s+"[^"]*"\s+([a-z]+)')
# The documented `// key:` block in regress.sh: `#   // probe: contacts  name…`.
# Example is the first token after the key; purpose is whatever follows, so the
# runner's own uneven column alignment is not load-bearing here.
_DOC_KEY_LINE = re.compile(r"^#\s+//\s*([a-z]+):\s+(\S.*)$")
# The completion sentinel the run waits on, and the header field that bounds it.
_AWAIT_SENTINEL = re.compile(r"CTI_HARNESS_AWAIT=(\S+)")
_PROBE_TIMEOUT_SOURCE = re.compile(r'CTI_PROBE_TIMEOUT="\$(\w+)"')
# The completion wait collapses a FAIL into an early end: its pattern alternates
# the sentinel with FAIL. Read off run.sh so a probe that short-circuits is not
# misread as one that ran out its window.
_AWAIT_WITH_FAIL = re.compile(r"CTI_HARNESS_AWAIT\|FAIL")
# The classes the runner emits directly: a `fail "<class>"` call (run.sh) or a
# `failure_class=<class>` line a refusal prints (regress.sh). These are the
# runner's own words, not the table's, so listing them is not restating it.
_FAIL_CLASS = re.compile(r'\bfail "([a-z_]+)"')
_FAILURE_CLASS_EMIT = re.compile(r"failure_class=([a-z_]+)")


@dataclass(frozen=True)
class HeaderKey:
    """One header field, with what the runner enforces and says it is for."""

    name: str
    required: bool
    example: str
    purpose: str


def derive_header_keys(regress: str) -> list[str]:
    """Every header key the runner reads, in first-seen order, de-duplicated.

    A key is in the contract because `regress.sh` calls `header_of` for it; this
    is the set the drift test pins, so it is the one place a new key has to land
    to be surfaced here.
    """
    keys: list[str] = []
    for match in _HEADER_OF_CALL.finditer(regress):
        key = match.group(1)
        if key not in keys:
            keys.append(key)
    return keys


def derive_doc_block(regress: str) -> dict[str, tuple[str, str]]:
    """Each documented key's `(example, purpose)`, from the `// key:` comment block.

    The purpose prose lives in `regress.sh` itself, so reading it is deriving
    from the runner rather than maintaining a second copy. Only the first line
    of a field's prose is taken; a field whose runner doc continues on later
    lines keeps its summary here and its detail in the source.
    """
    docs: dict[str, tuple[str, str]] = {}
    for line in regress.splitlines():
        match = _DOC_KEY_LINE.match(line)
        if not match or match.group(1) in docs:
            continue
        rest = match.group(2).strip()
        head, _, tail = rest.partition(" ")
        docs[match.group(1)] = (head, tail.strip())
    return docs


def _validation_block(regress: str) -> str:
    """The `for name in CORPUS` loop that dies on a malformed header.

    Anchored on its comment rather than the loop header, because a second
    `for name in "${CORPUS[@]}"` loop (the `--list` print) would otherwise be a
    false match.
    """
    marker = "Validate every selected probe's header"
    start_comment = regress.find(marker)
    if start_comment < 0:
        return ""
    start = regress.find("for name in", start_comment)
    if start < 0:
        return ""
    end = regress.find("\ndone\n", start)
    return regress[start : end if end >= 0 else len(regress)]


def derive_required_keys(regress: str) -> set[str]:
    """Keys the validation block kills the run for when missing or malformed.

    Required is what the code enforces, not what a comment claims: a key whose
    `die` sits inside an `if [[ -n … ]]; then … fi` is optional (validated if
    present, never demanded), and a key the block never mentions is optional too
    (consumed downstream, not gated at bring-up). The two enforcement shapes are
    a header read inline in the test (`[[ -n "$(header_of …)" ]]`) and a test on
    a variable that was assigned from a header read.
    """
    block = _validation_block(regress)
    if not block:
        return set()
    # `var="$(header_of "$file" key)"` — map the variable a check might use back
    # to the key it was read from.
    var_to_key = {
        var: key for var, key in re.findall(r'(\w+)="\$\(\s*header_of "\$file" ([a-z]+)', block)
    }
    # Drop the if-present guards wholesale; whatever enforcement remains is
    # unconditional, and an unconditional enforcement is what "required" means.
    unguarded = re.sub(r"if \[\[ -n[^\n]*\]\];\s*then\b.*?\bfi", "", block, flags=re.S)
    required: set[str] = set()
    # Inline: the header read is the test's own operand.
    required.update(re.findall(r'\[\[ -n "\$\(\s*header_of "\$file" ([a-z]+)', unguarded))
    # Via variable: `[[ "$var" … ]] || die`, where `var` was a header read.
    for var in re.findall(r'\[\[ "\$(\w+)"', unguarded):
        if var in var_to_key:
            required.add(var_to_key[var])
    return required


def derive_completion_sentinel(regress: str) -> str | None:
    """The log token the run waits on (`probe_done`), or None if unreadable."""
    match = _AWAIT_SENTINEL.search(regress)
    return match.group(1).strip('"') if match else None


def derive_window_source(regress: str) -> str | None:
    """The header field the probe timeout is bound to (`window`), or None."""
    match = _PROBE_TIMEOUT_SOURCE.search(regress)
    return match.group(1) if match else None


def derive_fail_short_circuits(run: str) -> bool:
    """Whether a FAIL line ends the completion wait early rather than timing out."""
    return bool(_AWAIT_WITH_FAIL.search(run))


def derive_runner_classes(regress: str, run: str) -> list[str]:
    """The classes the runner emits directly, de-duplicated, in first-seen order.

    Drawn from the runner's own `fail "<class>"` and `failure_class=<class>`
    sites — its vocabulary, not the table's — so a class that appears here but
    not in CLAUDE.md is a real signal, and the table's full set (which the merge
    and the verdict typer widen) is the reader's to consult.
    """
    tokens: list[str] = []
    for source in (run, regress):
        tokens.extend(_FAIL_CLASS.findall(source))
        tokens.extend(_FAILURE_CLASS_EMIT.findall(source))
    seen: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    return seen


def header_keys(regress: str) -> list[HeaderKey]:
    """The contract's header fields, in the runner's documented order.

    Documented keys come first in the order the `// key:` block writes them; any
    key the runner reads but nobody documented follows, so an undocumented key is
    visible rather than silently dropped.
    """
    keys = set(derive_header_keys(regress))
    docs = derive_doc_block(regress)
    required = derive_required_keys(regress)
    ordered: list[str] = [k for k in docs if k in keys]
    ordered.extend(sorted(k for k in keys if k not in docs))
    table: list[HeaderKey] = []
    for name in ordered:
        example, purpose = docs.get(name, ("", ""))
        table.append(HeaderKey(name, name in required, example, purpose))
    return table


def render_contract(regress: str, run: str) -> str:
    """Render the contract text. Derived parts cite the runner; narrated parts say so."""
    keys = header_keys(regress)
    sentinel = derive_completion_sentinel(regress)
    window_src = derive_window_source(regress)
    fail_short = derive_fail_short_circuits(run)
    classes = derive_runner_classes(regress, run)

    name_w = max((len(k.name) for k in keys), default=0)
    kind_w = max(len("required"), len("optional"))
    lines: list[str] = [
        "just probe-contract — the probe↔harness contract",
        "",
        "Derived from spike/regress.sh and spike/run.sh. The runner is the source of",
        "truth: if it gains a header key and this output does not, that is a bug",
        "(tests/unit/test_probe_contract.py plants that mutation). What each failure",
        'class *means* is not here — CLAUDE.md\'s "Failure classes" table owns that,',
        "and this output restates none of it.",
        "",
        "=== Header keys ===",
        "A probe's facts live in its leading `//` comment block. `regress.sh` parses",
        "them with `header_of` and validates the required ones before any world is",
        "brought up.",
        "",
    ]
    for key in keys:
        kind = "required" if key.required else "optional"
        purpose = key.purpose or "(undocumented — see spike/regress.sh)"
        lines.append(f"  {key.name:<{name_w}}  {kind:<{kind_w}}  {purpose}")
    lines.extend(
        [
            "",
            "=== Completion and the window ===",
        ]
    )
    if sentinel and window_src:
        lines.extend(
            [
                f"The run waits on a log line containing `{sentinel}` "
                f"(regress.sh sets CTI_HARNESS_AWAIT={sentinel}), within the probe's own",
                f"`{window_src}:` header (regress.sh binds CTI_PROBE_TIMEOUT to it). A probe",
                "still working when the window closes is a `timeout`, never a pass.",
            ]
        )
    else:  # pragma: no cover - the runner unreadable is a harness bug, not a path
        lines.append("(could not derive the completion line — see spike/regress.sh)")
    if fail_short:
        lines.append(
            "A probe may end early by logging a `FAIL` line: the completion wait treats"
            " FAIL as done."
        )
    lines.extend(
        [
            "",
            "=== What the runner waits on and scores (narrated — read run.sh for the lines) ===",
            "The deadlines `run.sh` bounds are boot and synchronisation, never the probe's",
            "subject. `wait_for`/`await_or_fail` wait on log lines; `extract_spike_lines`",
            "and `assert_clean_run` sweep what a probe writes under the `CTI|` prefix. Beyond",
            "its header, a probe owes the harness:",
            "  - one `CTI|...probe_done` line to end the wait (or `cti_probe_fnc_done`);",
            "  - `CTI|FAIL class=<class> ...` to fail with a typed class (optional);",
            "  - `CTI|LEG name=<leg> status=ran|unverified` per optional leg (ADR-0037).",
            "The environment the world hands a probe is its own `env:` header (exported by",
            "regress.sh) plus the SQF globals `stage_mission` writes into the generated",
            "harness (CTI_SPIKE_DAEMON_ADDRS, CTI_PROBE_SOAK, CTI_PROBE_CLIENT).",
            "",
            "=== Verdict ===",
            "Every run leaves a typed `failure_class` (or `pass`). The classes this runner",
            "emits directly, read off its `fail`/`failure_class=` sites:",
            f"  {', '.join(classes) if classes else '(none derived — see run.sh)'}",
            "The complete set of classes — and the required response to each — is CLAUDE.md's",
            '"Failure classes" table. Consult it; this output restates none of it.',
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """No arguments today: the contract prints whole, like `just regress --list`."""
    parser = argparse.ArgumentParser(
        description="Print the probe↔harness contract, derived from the runner.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print the contract and exit 0. No Arma, no lock, no port, no world."""
    parse_args(argv)
    regress = REGRESS_SH.read_text(encoding="utf-8")
    run = RUN_SH.read_text(encoding="utf-8")
    sys.stdout.write(render_contract(regress, run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
