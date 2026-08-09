"""The mutation smoke's Rust rung: `cargo-mutants` over the shim, when the shim changes (#246).

The shim is one crate, one file and seventeen tests, and it is the only Rust this
project ships. That smallness is what decides both halves of the design.

## Why it is wired at all

Measured on this box, 2026-08-09, against `cargo-mutants` 27.1.0 and the tree at
`576eead`:

* 53 mutants generated. **34 caught, 1 timeout, 18 unviable, 0 missed** — the
  shim's own tests already kill everything this engine can plant, so the rung
  says nothing about the tree it lands on. That is the right way round: a gate
  whose first act is to red a tree it did not write is #137/#186's false red.
* Whole crate, serial: **124.5 s**. At four jobs: **52.7 s**.
* `extension/` has been touched by **6 of the 418 commits** on `main`. So the
  measured cost of this rung on an average landing is nothing at all, and 52.7 s
  on the one landing in seventy that touches the shim.
* It does catch a real weakening: gutting the two `assert_eq!` calls in
  `error_json_survives_a_detail_that_is_not_plain_text` and
  `error_json_leaves_ordinary_text_alone` — leaving the calls, removing the
  assertions — leaves `replace match guard (c as u32) < 0x20 with false in
  escape_json` alive, and the rung reds.

A 52.7 s rung that runs on 1.4% of landings and reds a gutted test earns its
runtime. If `extension/` ever grows to the point where it does not, the number to
re-measure is the one above, not the argument.

## Why there is no bounded sample and no floor

Both are answers to a corpus too big to run whole, and this one is not. Fifty-three
mutants is the entire population, so there is nothing to sample and no denominator
to set a rate against: the verdict is simply whether any viable mutant survived.
`SURVIVES_BY_DESIGN` is the escape, and it is the same escape
`NO_MUTABLE_SUBJECT` is — a named mutant with its reason beside it, in the diff.
It ships empty, because on the tree this landed against nothing survives.

## What a timeout means here, and why the exit code is not read

`cargo-mutants` exits 3 when a mutant timed out and 2 when one was missed, and it
counts a timeout as a problem. This project counts it as a **kill** — "the mutant
changed what the code does so plainly that the tests could not finish saying so",
which is `tools/mutation_smoke.py`'s rule and applies unchanged here. The tree has
one: `replace Connection::arm -> Result<(), String> with Ok(())` removes the read
deadline, and the test that waits for one then waits forever. So the verdict is
read out of `missed.txt` rather than off the exit code, and `unviable.txt` — 18 of
the 53, mutants that do not compile — is excluded from the count rather than
scored either way.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Final, NamedTuple

# The crate. One, and named here rather than discovered, because a second one
# appearing is a decision somebody should have to write down.
MANIFEST: Final = "extension/Cargo.toml"

# The engine this rung's numbers were measured against. Named rather than
# floating, because an operator set that moves under a "no survivor" rung moves
# the verdict with it — the version is not enforced (that would red on every
# upgrade), it is what a reader compares against when a verdict surprises them.
VERSION: Final = "27.1.0"

# The tree whose change makes this rung run at all.
SCOPE: Final = "extension/"

# Mutants that survive and are not a finding, each with the reason. The escape,
# and deliberately the only one: there is no flag, no attribute on the Rust side
# and no environment variable, so a survivor can be excused only by a line here,
# in the diff, with its reason next to it — the same discipline
# `NO_MUTABLE_SUBJECT` carries in `tools/mutation_smoke.py`.
#
# Empty, and that is a measurement rather than an aspiration: on the tree this
# landed against, 0 of 35 viable mutants survived.
SURVIVES_BY_DESIGN: Final[dict[str, str]] = {}

# Four was measured: 124.5 s serial against 52.7 s at four jobs on a six-core
# box. Above four the crate is too small to fill the jobs and the baseline build
# dominates, and the cap keeps a `just fast` from taking the machine the human
# also plays on.
JOBS: Final = 4

# The whole rung's wall clock, well above the 52.7 s measured, so that this bound
# only ever catches a run that has gone wrong rather than a slow one.
BUDGET_S: Final = 600.0


class Refusal(Exception):  # noqa: N818 — the repo names this shape `Refusal`, and a refusal is not an error
    """The rung could not run, which is not the same as the shim failing it."""


class Outcome(NamedTuple):
    """What one `cargo-mutants` run found."""

    caught: int
    missed: tuple[str, ...]
    timeouts: tuple[str, ...]
    unviable: int
    seconds: float

    @property
    def run(self) -> int:
        """Mutants that reached a verdict: everything the compiler accepted."""
        return self.caught + len(self.missed) + len(self.timeouts)

    @property
    def ok(self) -> bool:
        """Whether every viable mutant was noticed."""
        return not self.missed

    def __str__(self) -> str:
        """One line, in the shape `tools/mutation_smoke.py`'s reader already scans."""
        mark = "ok" if self.ok else "RED"
        return (
            f"{mark} {MANIFEST} arm=rust "
            f"killed={self.caught + len(self.timeouts)}/{self.run} "
            f"unviable={self.unviable} {self.seconds:.1f}s"
        )


def in_scope(changed: list[str]) -> bool:
    """Whether this landing touches the shim at all."""
    return any(name.replace(os.sep, "/").startswith(SCOPE) for name in changed)


def _read(path: Path) -> tuple[str, ...]:
    """Lines of one of `cargo-mutants`' outcome files, or none when it wrote none."""
    if not path.exists():
        return ()
    return tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def read_outcome(output: Path, seconds: float) -> Outcome:
    """Turn a `mutants.out` directory into a verdict.

    Read from the files rather than from the exit code, because the exit code
    disagrees with this project about what a timeout is (see the module
    docstring), and because `unviable` has to be taken out of the count rather
    than scored — a mutant that does not compile is a mutant that did not run.
    """
    out = output / "mutants.out"
    if not out.exists():
        message = (
            f"cargo-mutants wrote no {out}: the run did not get as far as a verdict, so there "
            f"is nothing here to read as one"
        )
        raise Refusal(message)
    missed = tuple(name for name in _read(out / "missed.txt") if name not in SURVIVES_BY_DESIGN)
    return Outcome(
        caught=len(_read(out / "caught.txt")),
        missed=missed,
        timeouts=_read(out / "timeout.txt"),
        unviable=len(_read(out / "unviable.txt")),
        seconds=seconds,
    )


def _binary() -> str:
    """Locate `cargo`, refusing by name when the subcommand is not installed."""
    cargo = shutil.which("cargo")
    if cargo is None:
        message = "cargo is not on PATH, so the Rust rung cannot run"
        raise Refusal(message)
    probe = subprocess.run(  # noqa: S603 — a fixed argv
        [cargo, "mutants", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        message = (
            f"cargo-mutants is not installed, so the Rust rung cannot run. A check that could "
            f"not run is not a check that passed (#41). Install it with "
            f"`cargo install --locked --version {VERSION} cargo-mutants`, or take the release "
            f"binary from https://github.com/sourcefrog/cargo-mutants/releases/tag/v{VERSION}. "
            f"It is deliberately not in `just prereqs tools` yet: that installer verifies every "
            f"download against a published checksums file and cargo-mutants ships none (#246)"
        )
        raise Refusal(message)
    return cargo


def run(root: Path, *, jobs: int = JOBS, budget: float = BUDGET_S) -> Outcome:
    """Mutate the shim and report what its tests noticed."""
    cargo = _binary()
    with tempfile.TemporaryDirectory(prefix="cti-mutants-") as workspace:
        output = Path(workspace)
        started = os.times().elapsed
        try:
            subprocess.run(  # noqa: S603 — argv built here from constants and a path
                [
                    cargo,
                    "mutants",
                    "--manifest-path",
                    MANIFEST,
                    "--output",
                    str(output),
                    "--jobs",
                    str(jobs),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                timeout=budget,
            )
        except subprocess.TimeoutExpired as expired:
            message = f"cargo-mutants did not finish within {budget:.0f}s"
            raise Refusal(message) from expired
        return read_outcome(output, os.times().elapsed - started)


def report(outcome: Outcome) -> str:
    """Say what survived, in the terms the remedy is written in."""
    if outcome.ok:
        return ""
    listed = "\n".join(f"    survived: {name}" for name in outcome.missed)
    return (
        f"{len(outcome.missed)} mutant(s) in the shim went unnoticed by its tests. Strengthen "
        f"the assertions that let them through — never weaken the rung.\n{listed}"
    )


def outcome_json(outcome: Outcome) -> str:
    """Render one verdict as JSON, for a caller that wants the numbers rather than the line."""
    return json.dumps(
        {
            "caught": outcome.caught,
            "missed": list(outcome.missed),
            "timeouts": list(outcome.timeouts),
            "unviable": outcome.unviable,
            "seconds": round(outcome.seconds, 1),
            "ok": outcome.ok,
        },
        indent=2,
    )
