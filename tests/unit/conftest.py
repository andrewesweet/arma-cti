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

import contextlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
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

# Every emission the suite makes resolves its endpoint here, not at the box's real
# loopback collector (#484 round 2, finding 1). `otel_event.emit` with no explicit
# endpoint falls back through `endpoint_from_environment()` to `DEFAULT_ENDPOINT` —
# a live collector on 127.0.0.1:4318 — so a test that forgot to point its emission
# somewhere dead exported for real, and did, on every run: wait records for live
# issues landed in the very JSONL `just ledger-sync` materialises. Hermeticity is
# structural rather than remembered (#458): the standard OTLP variable the module
# already documents as its redirection seam is forced to a port nothing listens on,
# so an unset endpoint is a refused connection and a journalled `exported: false`,
# never a write to the real collector. The dead port matches the test modules' own
# `DEAD_ENDPOINT`, and `tests/unit/test_attribute_registry.py` pins this line's
# presence so removing it reddens a suite, not a box.
os.environ["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] = "http://127.0.0.1:2999/v1/logs"


@pytest.fixture(scope="session", autouse=True)
def hermetic_review_root(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Point the review state root at pytest's own tmp, never at `~/.arma-cti` (#484 round 2).

    `review_loop.review_root()` reads `CTI_REVIEW_DIR` at call time the way the queue
    reads `CTI_QUEUE_DIR`, so a success-path test that forgot to arrange a journal
    still writes inside a throwaway directory instead of the box's real review root.
    Session-scoped and autouse because the default needs holding for the whole run,
    not arranging per test; a test that wants its own root sets the same variable
    with `monkeypatch.setenv`, which restores this one afterwards. Under `-n auto`
    each worker gets its own directory, so concurrent workers never share a journal.
    """
    os.environ["CTI_REVIEW_DIR"] = str(tmp_path_factory.mktemp("review-root"))


@pytest.fixture(scope="session", autouse=True)
def no_stage_arrival_reaches_the_real_review_root() -> Iterator[None]:
    """No stage arrival reaches `~/.arma-cti/review` while the suite runs (#677 round 2).

    `hermetic_review_root` above holds the suite off the box's real review root by
    holding the variable, and `seam_env` stages its fork the same way — but a guard over
    the two values those writers already read is a guard over the writers already found.
    This sentinel asserts about the real path the constant names, whatever any test or
    forked child does: the stage-arrival journals under it are listed before the first
    test runs and again at teardown, and a journal that appeared or grew fails the run
    and names the issue. The subject is the stage journal and not the whole tree,
    because the root is live shared state — another agent's landing grows rebases and
    landing records here while the gate runs, and that is this box working, not a test
    leaking; a red naming an issue a concurrent dispatch really arrived for is re-run,
    never debugged. Under `-n auto` each worker pairs its own before and after, so a
    write is caught by any worker whose span covers it.
    """
    real = load_tool("review_loop").REVIEW_ROOT
    journal = load_tool("attribute_registry").STAGE_JOURNAL

    def arrivals() -> dict[str, int]:
        if not real.exists():
            return {}
        return {
            str(path.relative_to(real)): path.stat().st_size
            for path in sorted(real.rglob(journal))
            if path.is_file()
        }

    before = arrivals()
    yield
    after = arrivals()
    grown = sorted(path for path in (*after, *before) if after.get(path) != before.get(path))
    assert not grown, f"a test wrote a stage arrival into the real review root {real}: {grown}"


@pytest.fixture(scope="session", autouse=True)
def hermetic_dispatch_records(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Point the dispatch records' root at pytest's own tmp too (#490 round 2).

    `attribute_registry.dispatch_records_root()` reads `CTI_DISPATCH_DIR` at call
    time — the spelling `tools/dispatch_follow.py` and the observatory already
    use — to check, where an issue has no stage journal yet, whether a dispatch
    record names it. Without this fixture that check would read the box's real
    records, so an absent-journal test on an issue this box really dispatched
    (490 itself, the moment these lines run) would flip from `first_time` to
    `undetermined` according to the live store. An empty throwaway root makes
    absence the default a test arranges away, never one it inherits.
    """
    os.environ["CTI_DISPATCH_DIR"] = str(tmp_path_factory.mktemp("dispatch-records"))


@pytest.fixture(scope="session", autouse=True)
def hermetic_dispatch_assignment() -> None:
    """Strip dispatch identity from the unit suite unless a test arranges it (#573).

    `just dispatch` exports the issue, dispatch id and seat to every child. Production
    uses those values for issue resolution, run attribution and the implementer's
    observatory repair path, so inheriting them makes a test depend on who launched
    pytest. Tests that exercise dispatched behaviour set the variables deliberately
    with `monkeypatch`, which restores this unset baseline afterwards.
    """
    for variable in (
        "CTI_DISPATCH_ISSUE",
        "CTI_DISPATCH_ID",
        "CTI_DISPATCH_SEAT",
    ):
        os.environ.pop(variable, None)


if TYPE_CHECKING:
    from collections.abc import Iterator
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


def codex_guidance_proof_document(
    guidance: ModuleType,
    launch_directory: Path,
    *,
    source_sha: str = "a" * 64,
) -> dict[str, Any]:
    """Build one content-free #502 proof at its dispatch-record seam."""
    return {
        "schema": guidance.CODEX_GUIDANCE_SCHEMA,
        "normalization": guidance.CODEX_GUIDANCE_NORMALIZATION,
        "codex_version": "codex-cli 0.147.0",
        "launch_directory": str(launch_directory.resolve()),
        "project_doc_max_bytes": 98304,
        "source_paths": ["AGENTS.md"],
        "sources": [{"path": "AGENTS.md", "raw_bytes": 6, "sha256": source_sha}],
        "raw_project_bytes": 6,
        "expected_project_bytes": 6,
        "expected_project_sha256": source_sha,
        "delivered_project_bytes": 6,
        "delivered_project_sha256": source_sha,
        "global_expected_bytes": 0,
        "global_expected_sha256": "b" * 64,
        "global_delivered_bytes": 0,
        "global_delivered_sha256": "b" * 64,
        "combined_delivered_sha256": "c" * 64,
    }


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


def pytest_collection_finish(session: Any) -> None:  # noqa: ANN401 — pytest's hook signature, not ours to narrow
    """Hand the suite's collected test count to the gate-duration recorder (#446).

    Each recorded gate run carries how many tests it collected, so a duration
    change can be told apart from a suite that simply grew. The count is written
    to the path the recording recipes exported in `CTI_GATE_CLOCK_COLLECTED_FILE`
    — and nowhere when it is unset, so a bare `uv run pytest` and `just
    mutation`'s own runs leave no file behind. Under `-n auto` the controller
    collects nothing at all (xdist prohibits it) and every worker collects the
    full suite, so the write comes from exactly one process: worker gw0 under
    xdist, the single process of a plain run. The worker test is on
    `session.config` — pytest's own plugins (`cacheprovider`, `junitxml`) test
    `config.workerinput`, and `Session` never carries the attribute. A failed
    write records `None`: the count is provenance for a later investigation,
    not an input to any decision, so it must not redden a run that already
    finished green.
    """
    worker = getattr(session.config, "workerinput", None)
    if worker is not None and worker.get("workerid") != "gw0":
        return
    named = os.environ.get("CTI_GATE_CLOCK_COLLECTED_FILE", "")
    if not named:
        return
    with contextlib.suppress(OSError):
        Path(named).write_text(f"{len(session.items)}\n", encoding="utf-8")


def pytest_terminal_summary(terminalreporter: Any, config: Any) -> None:  # noqa: ANN401 — pytest's hook objects, not ours to narrow
    """Name this run's failures for the gate-duration recorder (#576).

    A red unit leg used to leave only a status integer on the gate-clock row:
    pytest's own `lastfailed` cache is erased by the next green run, which is
    exactly when someone looks. When the recording runner exported
    `CTI_GATE_CLOCK_FAILED_FILE`, the failed and errored node ids are written
    there, one per line — and nowhere when it is unset, so a bare `uv run
    pytest` leaves nothing behind. Under `-n auto` the controller's terminal
    reporter aggregates every worker's reports, so the write comes from the
    controller alone. Written only when there are failures, so a green run
    adds nothing to any record. A failed write is silent for the collected
    count's reason: this is provenance for a later investigation, and it must
    never redden or alter the run it describes.
    """
    named = os.environ.get("CTI_GATE_CLOCK_FAILED_FILE", "")
    if not named or getattr(config, "workerinput", None) is not None:
        return
    seen: dict[str, None] = {}
    for kind in ("failed", "error"):
        for report in terminalreporter.stats.get(kind, []):
            nodeid = getattr(report, "nodeid", "")
            if nodeid:
                seen.setdefault(nodeid)
    if not seen:
        return
    with contextlib.suppress(OSError):
        Path(named).write_text("".join(f"{nodeid}\n" for nodeid in seen), encoding="utf-8")
