"""Shared arrangement for the unit tier (#89).

Six copies of `reply_to`, four of a telemetry-row filter under two divergent
spellings, five spellings of "a Campaign on the authored Stratis map", six
copies of the importlib boilerplate that loads a `tools/` script, `REPO` in ten
files and the thirteen-field casualty document in two — where a drift between
the two copies of that last one was undetectable by construction.

These are plain functions rather than fixtures on purpose. Every one of them
takes an argument the test varies (which daemon, which log, which tool), so a
fixture would be a factory returned by a fixture, which is one indirection
between a test and what it is arranging. `tests/unit` is on `sys.path` under
pytest's prepend import mode, so `from conftest import reply_to` works and reads
as what it is.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hypothesis import settings

from cti_daemon import campaign, economy, loadouts, manifest
from cti_daemon.outbox import Outbox

# No wall-clock deadline on hypothesis tests (#306). The default 200 ms deadline
# is a per-example bound on this box's scheduler, not on anything a property
# here asserts: the suite runs `-n auto` on a machine that also carries other
# agents' gates, and one descheduled example turns into DeadlineExceeded — or,
# when the replay is fast again, hypothesis's own FlakyFailure ("Unreliable
# test timings! ... consider turning deadlines off"). That is how the planner
# determinism property red once in four full-suite runs while 5,500 isolated
# examples of it found nothing. Every assertion in every property is untouched
# by this; pathological slowness still fails the suite via its wall clock.
settings.register_profile("arma-cti", deadline=None)
settings.load_profile("arma-cti")

if TYPE_CHECKING:
    from types import ModuleType

    from cti_daemon.daemon import Daemon

REPO = Path(__file__).resolve().parents[2]
ECONOMY = REPO / "config" / "economy.json"
# The authored manifests live inside the addon, because the addon ships and
# reads them verbatim (ADR-0017). There is no second copy to point at.
MANIFESTS = REPO / "addons" / "main" / "manifests"
# The curated loadout menu, inside the addon for the manifests' own reason: the
# addon ships and reads this same file (ADR-0017, ADR-0056).
LOADOUTS = REPO / "addons" / "main" / "catalogue" / "loadouts.json"
HOOKS = REPO / ".claude" / "hooks"


def load_tool(name: str) -> ModuleType:
    """Import a `tools/` script by path and return the module.

    `tools/` holds standalone scripts rather than an importable package, so
    there is no import statement that reaches them. Registered in `sys.modules`
    under its own name so that a script importing a sibling — `timeline` and
    `push_path_report` both import `telemetry_log` — finds the same module the
    caller does.
    """
    return _load_script(name, REPO / "tools" / f"{name}.py")


def load_hook(name: str) -> ModuleType:
    """Import a `.claude/hooks/` script by path and return the module.

    Same reason as `load_tool`, plus one of its own: hook filenames are
    hyphenated, so `block-no-verify` is not a module name any import statement
    could spell. The decision function is what the tests drive; running the
    script's stdin/exit-code contract is the harness's job.

    The hooks directory goes on `sys.path` first, because the Bash hooks import
    their shared reader (`shell_reading`) as a sibling — which resolves by
    itself when the harness runs a hook as a script, but not from here.
    """
    if str(HOOKS) not in sys.path:
        sys.path.insert(0, str(HOOKS))
    return _load_script(name.replace("-", "_"), HOOKS / f"{name}.py")


def _load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        message = f"no script at {path}"
        raise ModuleNotFoundError(message)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def no_lane_network(lane: str, credentials: Path, now: float) -> Any:  # noqa: ANN401 — see below
    """Refuse to be the quota reader: this is what every test of a lane bar hands in (#427).

    `dispatch.lane_bar`'s breaker rung is the one path from a dispatch's or a landing's
    decision to the network — `breaker.lane_verdict` asks z.ai's own quota endpoint for a
    lane held open on availability with no published boundary — and a unit test that reached
    a provider to decide a bar would pass slowly, or differently, according to this box's
    connectivity. Handed in wherever a bar is staged, so a test that reaches that branch
    without staging its own reader is red rather than online. The return type is `Any`
    because it never returns: annotating `breaker.QuotaReading` would make this the one
    place in `conftest` that imports a `tools/` module at collection time.
    """
    message = f"a lane bar reached the network for {lane} at {now} via {credentials}"
    raise AssertionError(message)


def reply_to(daemon: Daemon, **envelope: object) -> dict[str, Any]:
    """Send one request and return its decoded reply."""
    return json.loads(daemon.handle_line(json.dumps(envelope)))


def observe(daemon: Daemon, request_id: str, **payload: object) -> dict[str, Any]:
    """Report what the world can see, and take back the strategic picture."""
    return reply_to(daemon, id=request_id, verb="observe", payload={"time": 1, **payload})["result"]


def all_rows(log: Path) -> list[dict[str, Any]]:
    """Every telemetry row, in the order they were written.

    The whole log, for the tests whose subject is the sequence rather than one
    kind of event — how many rows a request wrote, or what order two daemons'
    records came out in. Eight copies of this comprehension before #157.
    """
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def rows(log: Path, event: str) -> list[dict[str, Any]]:
    """Every telemetry row of one kind, in the order they were written."""
    return [row for row in all_rows(log) if row["event"] == event]


def authored_economy() -> economy.EconomyTable:
    """Return the economy table this repository ships."""
    return economy.load(ECONOMY)


def starting_funds() -> int:
    """Return the Funds a side opens with, off the authored table."""
    return authored_economy().starting_funds


def funds_after_buying(squad_type: str) -> int:
    """Return the opening balance less what the authored table charges for that Squad.

    Derived rather than pinned, which `test_daemon_dispatch` had already written
    out by hand once — "an authored price change should move this test's
    arithmetic, not break it" — while three sibling assertions still carried a
    bare 200 or 300 and a fourth a bare 100 (#157).
    """
    table = authored_economy()
    price = table.price(squad_type)
    # A narrowing on the arrangement, not a claim about the code under test: a
    # Squad type the authored menu does not sell means this call is misspelt.
    assert price is not None, f"the authored economy sells no {squad_type!r} Squad"
    return table.starting_funds - price


def authored_stratis() -> manifest.MapManifest:
    """Return the Stratis manifest this repository ships."""
    return manifest.load(MANIFESTS / "stratis.json")


def authored_loadouts() -> loadouts.Catalogue:
    """Return the curated loadout menu this repository ships."""
    return loadouts.load(LOADOUTS)


def live() -> campaign.Campaign:
    """Return a Campaign on the authored Stratis map, everything Neutral."""
    table = authored_economy()
    return campaign.Campaign(
        map_manifest=authored_stratis(),
        table=table,
        ledger=economy.Ledger(table.starting_funds),
        outbox=Outbox(),
        # The authored menu, for the authored table's reason: this is the
        # Campaign the daemon builds, and one wired without a menu would offer
        # no kit at all (#172).
        catalogue=authored_loadouts(),
    )


def death(**fields: object) -> dict[str, Any]:
    """One death in the shape the world reports it, with the fields under test."""
    return {
        "at": 431.5,
        "unit": "2:14",
        "type": "B_Soldier_F",
        "squad": "WEST-1",
        "side": "WEST",
        "place": "agia_marina",
        "pos": [3421, 5122, 0],
        "by_unit": "3:2",
        "by_type": "O_Soldier_F",
        "by_squad": "EAST-2",
        "by_side": "EAST",
        "by_vehicle": "",
        **fields,
    }


def recorded_death(**fields: object) -> dict[str, Any]:
    """Return the same death as the daemon writes it down: a telemetry row.

    Built from `death` rather than beside it, which is what makes a schema drift
    between the reported shape and the recorded one impossible rather than
    merely unlikely — the two copies of this document used to be maintained by
    hand in two files.
    """
    return {"at_ns": 1, "event": "casualty", **death(**fields)}
