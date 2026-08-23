"""`just check`'s `check-attributes` leg: every emitted name is a registered one (#484).

The attribute registry's mechanical half. `tools/attribute_registry.py` is the
one home for every `cti.*` and `gen_ai.*` name; this leg derives, from the
tracked Python itself, every name a string or f-string piece carries, and reds
on one the registry does not. A registry nothing enforces is a fourth copy —
#483 landed exactly this discipline for the justfile's recipe call sites, and
#537's retention rule is what drifts without it.

**Why derived from tokens, not remembered paths.** `just check-arbiter`'s
lesson: the subject set is every tracked file from `git ls-files`, with no path
list to be incomplete — the sweep that hunted #361's copies omitted `tests/`,
where one sat. So every tracked `.py` is tokenised here, comments and code
alike in scope by construction, and a name in a docstring counts the same as a
name in a call: both are spellings a reader may copy.

**What counts as a name.** Three forms, because that is how names are actually
written:

- a string that *is* a name (`TRANSITION_EVENT = "cti.queue.transition"`), or a
  name quoted inside a larger string (the collector config's
  `resource.attributes["cti.dispatch_id"]`) — an exact name;
- a name followed by `=`, the `key=value` form every refusal and record line
  renders (`f"cti.issue={n}"`, `cti.base_sha=` mid-string) — an exact name;
- a dotted prefix followed directly by `{`, the one dynamic construction
  (`f"cti.queue.{k}"` in the queue's transition emission) — a prefix, which
  must be the prefix of at least one registered name.

The prefix form is the honest ceiling: a typo in the *suffix* a comprehension
substitutes is not visible to any static read, and the queue's detail keys are
pinned instead by the exact names the tests quote. Stated here rather than
papered over.

**What this deliberately does not check.** Whether a registered name is still
emitted — the registry keeps names forever (#480 user story 22), so rows
outliving their emitters are the design, not drift. And whether a row's reason
is true: the reason is read by humans, the same division `just check-arbiter`
draws.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Final, NamedTuple

sys.path.insert(0, str(Path(__file__).parent))

import attribute_registry  # the path insert above is what makes this importable

# A whole string that is nothing but a name — the registry's own rows, the event
# constants, attribute keys in an `Event(...)` mapping.
WHOLE_NAME: Final = re.compile(r"^(?:cti|gen_ai)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$")
# A name quoted inside a larger string — the collector config is the live case.
QUOTED_NAME: Final = re.compile(r"""['"]((?:cti|gen_ai)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*)['"]""")
# A name in the `key=value` form, anywhere in a piece. The boundary behind stops
# `arcti.x=` reading as a name; the `=` ahead is what makes this a rendering of
# a name rather than prose about one.
KEY_VALUE_NAME: Final = re.compile(
    r"(?<![a-z0-9_.])((?:cti|gen_ai)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*)(?==)"
)
# A dotted prefix whose continuation an f-string substitutes — the queue's
# `f"cti.queue.{k}"`. A prefix, never an exact name: what follows it is not
# spelled here, and only its home is checkable. In a whole string the
# interpolation must be visible ahead; an f-string middle that *ends* on the
# dotted prefix is one by construction, because the `{` that follows is the
# tokeniser's own next token and never part of the middle.
INTERPOLATED_PREFIX: Final = re.compile(r"(?<![a-z0-9_.])((?:cti|gen_ai)\.[a-z0-9_.]*\.)(?=\{)")
FSTRING_PREFIX_TAIL: Final = re.compile(r"^(?:cti|gen_ai)\.[a-z0-9_.]*\.$")


class Finding(NamedTuple):
    """One unchecked name: where, what, and the form it was found in."""

    path: str
    line: int
    name: str
    form: str


def _pieces(text: str, path: str) -> tuple[list[tuple[str, bool]], list[Finding]]:
    """Every string content and f-string middle in a file, middles flagged.

    A `.py` that does not tokenise is a finding in itself: a file this leg
    cannot read is a file whose names it cannot check, and silence there would
    read as green.
    """
    pieces: list[tuple[str, bool]] = []
    failures: list[Finding] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.STRING:
                pieces.append((token.string, False))
            elif token.type == tokenize.FSTRING_MIDDLE:
                pieces.append((token.string, True))
    except tokenize.TokenError as failure:
        failures.append(Finding(path, 0, f"unparseable ({failure.args[0]})", "source"))
    return pieces, failures


def _strip_quotes(token_text: str) -> str:
    """A STRING token's content: prefix letters and both quote halves removed."""
    body = token_text.strip()
    while body and body[0] not in "\"'":
        body = body[1:]
    return body[1:-1] if len(body) >= 2 else body


def names_in(text: str, path: str = "<text>") -> tuple[set[str], set[str], list[Finding]]:
    """Return the exact names and interpolated prefixes a Python source carries.

    Pure, so a test can point it at one string and assert what it finds — the
    assertable half of this leg, in `tools/otel_event.py`'s split.
    """
    exact: set[str] = set()
    prefixes: set[str] = set()
    findings: list[Finding] = []
    pieces, failures = _pieces(text, path)
    findings += failures
    for piece, is_middle in pieces:
        candidates = (piece,) if is_middle else (piece, _strip_quotes(piece))
        for candidate in candidates:
            if WHOLE_NAME.fullmatch(candidate):
                exact.add(candidate)
            for found in QUOTED_NAME.finditer(candidate):
                exact.add(found.group(1))
            for found in KEY_VALUE_NAME.finditer(candidate):
                exact.add(found.group(1))
            for found in INTERPOLATED_PREFIX.finditer(candidate):
                prefixes.add(found.group(1))
            if is_middle and FSTRING_PREFIX_TAIL.fullmatch(candidate):
                prefixes.add(candidate)
    return exact, prefixes, findings


def check(files: dict[str, str]) -> list[Finding]:
    """Every finding across `path -> source`, against the real registry."""
    findings: list[Finding] = []
    registered = attribute_registry.NAMES
    for path in sorted(files):
        exact, prefixes, failures = names_in(files[path], path)
        findings += failures
        for name in sorted(exact):
            if name not in registered:
                findings.append(Finding(path, 0, name, "exact"))
        for prefix in sorted(prefixes):
            if not any(key.startswith(prefix) for key in registered):
                findings.append(Finding(path, 0, prefix.rstrip("."), "prefix"))
    return findings


def tracked_sources(root: Path) -> dict[str, str]:
    """Every tracked *or uncommitted* `.py`'s source — no path list to be incomplete.

    Untracked-but-present files are included on purpose: `just check` runs before
    the commit that would make `git ls-files` see a new emitter, and a name typed
    into a file the leg cannot yet see is exactly the hand-typed name this leg
    exists to catch. `just check-arbiter` shares the tracked-only derivation and
    its pre-commit gap; this leg's subject is new spellings, so it closes the gap
    rather than inheriting it.
    """
    done = subprocess.run(  # noqa: S603 — argv is fixed here
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--deduplicate",
            "--",
            "*.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        return {}
    sources: dict[str, str] = {}
    for name in done.stdout.splitlines():
        path = root / name
        try:
            sources[name] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            sources[name] = ""
    return sources


def main(argv: list[str] | None = None) -> int:
    """Check every tracked `.py`, and exit non-zero naming every violation."""
    parser = argparse.ArgumentParser(
        prog="check-attributes",
        description="Every cti.*/gen_ai.* name in the tracked Python is a registered one.",
    )
    parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    sources = tracked_sources(root)
    if not sources:
        print("check-attributes: no tracked sources read — refusing to claim green")
        return 1
    findings = check(sources)
    for finding in findings:
        print(
            f"check-attributes: {finding.path}: {finding.name} ({finding.form}) is not in the registry"
        )
    print(
        f"attributes: files={len(sources)} registry={len(attribute_registry.NAMES)}"
        f" findings={len(findings)}"
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
