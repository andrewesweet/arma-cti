"""TCP transport for the daemon.

Newline-delimited JSON on 127.0.0.1, one persistent connection reused across
calls (ADR-0005: unix sockets do not cross the WSL2/Windows boundary, and
reconnecting per call costs about three times as much).
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import socketserver
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Final

from cti_daemon import campaign as campaign_module
from cti_daemon import commands, economy, loadouts, manifest, planner, report_cycle
from cti_daemon.daemon import Daemon, Wiring
from cti_daemon.outbox import Outbox
from cti_daemon.port import CommandPort
from cti_daemon.telemetry import Telemetry

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 9099
# Where a *play* session's evidence lands when nobody says otherwise. Not
# `.spike-out/` any more (#103): that directory belongs to the harness, which
# truncates it at the start of every run because per-run evidence is what it
# holds (ADR-0023 says so of the file by name). A Play Session's telemetry is the
# record of a Campaign that was actually played, and the harness deleting it on
# its next run would be the loss nobody noticed until they went looking.
#
# Retention: kept until the human deletes it, and appended to across sessions.
# Nothing truncates this file — the archive of a finished Campaign is written
# beside it under `campaigns/` (ADR-0023) and is the durable record; this is the
# raw account the archive is summarised from.
DEFAULT_TELEMETRY: Final = Path(".cti-play/daemon-telemetry.jsonl")

# Where this checkout keeps its authored files. Here rather than in `daemon.py`
# because this module is Main (#76): knowing the repo layout is a composition
# root's job, and a daemon that resolved `config/` from its own `__file__` was
# an adapter bound to a source tree.
REPO: Final = Path(__file__).parents[2]
DEFAULT_ECONOMY: Final = REPO / "config" / "economy.json"
DEFAULT_MANIFESTS: Final = REPO / "addons" / "main" / "manifests"
# The curated loadout menu (#172, ADR-0056). Under `addons/` rather than beside
# the economy table because the addon ships and parses this same file (ADR-0017):
# the world applies a kit and the daemon records which one, and two copies would
# be two menus.
DEFAULT_LOADOUTS: Final = REPO / "addons" / "main" / "catalogue" / "loadouts.json"
DEFAULT_MAP: Final = "stratis"


def ready_line(host: str, port: int, epoch: str) -> str:
    """Build the line the Arma tier waits for instead of sleeping.

    The epoch rides along because a harness that restarts the daemon mid-run
    (#96) otherwise has only the world's word for which process answered which
    request. Appended rather than inserted: `spike/run.sh` and
    `spike/cycle/cycle.sh` grep for the prefix.
    """
    return f"CTI_DAEMON_READY {host}:{port} epoch={epoch}"


# How long a connection may say nothing before the daemon closes it (#142, and
# #73's last bullet, which is the same surface).
#
# A half-open peer — a client whose host vanished without a FIN, or a diagnostic
# connection somebody opened and walked away from — otherwise parks a handler
# thread until the process exits, and the threading server puts no bound on how
# many of those it will hold. The close *is* the whole response: there is
# nothing to report to a peer that is not listening.
#
# Two orders of magnitude above the traffic it must not interrupt. The effect
# pump polls every 2 s (`fn_effectPump.sqf`) down the one connection the shim
# caches (ADR-0005), so a live world is never silent this long, and a client
# that is wrongly closed on reconnects in silence anyway — which is what makes a
# bound safe to have here at all rather than a thing to be careful with.
IDLE_SECONDS: Final = 120.0


def _handler_for(daemon: Daemon) -> type[socketserver.StreamRequestHandler]:
    """Bind one daemon to a connection handler, one instance per connection."""

    class Handler(socketserver.StreamRequestHandler):
        # Read at class-creation time, which is once per `serve` — so a test
        # that shortens the bound sets it before bring-up and gets it.
        timeout = IDLE_SECONDS

        def handle(self) -> None:
            try:
                for raw in self.rfile:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    self.wfile.write(daemon.handle_line(line).encode("utf-8") + b"\n")
                    self.wfile.flush()
            except TimeoutError:
                # Returning closes the connection and ends this thread, which is
                # the point. Caught rather than left to `handle_error`, which
                # would print a traceback for the ordinary end of an idle
                # connection and bury a real one.
                return

    return Handler


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def wire(  # noqa: PLR0913 — see the comment below: every argument is one
    # authored input, and a config object would be one indirection more.
    # Every argument is one authored input this wiring is built from, all
    # keyword-only: folding them into a config object would be one more
    # indirection between a caller and what it varies.
    *,
    telemetry_path: Path,
    economy_path: Path | None = None,
    manifests_path: Path | None = None,
    loadouts_path: Path | None = None,
    map_id: str = DEFAULT_MAP,
    archive_path: Path | None = None,
) -> Wiring:
    """Load this checkout's authored files and assemble a Campaign in play (#164).

    Main's own work. The one place default paths are resolved (#76), and the one
    place the object graph is built: the Campaign the rules are judged against,
    the port that judges them, the cycle that plays one report, and the telemetry
    sink all three write to. `Daemon` is handed the result and answers a socket
    with it, so what a Campaign in play is made of is decided here rather than
    inside an adapter — and a Phase-2 caller that wants a *loaded* Campaign
    rather than a fresh one has one function to change (ADR-0008).

    Separate from `build_daemon` so that a caller which is not building a stock
    daemon — the tier's instrumented subclasses, and whatever Phase 2 loads a
    snapshot into — takes the same wiring rather than restating it.
    """
    table = economy.load(economy_path or DEFAULT_ECONOMY)
    map_manifest = manifest.load_all(manifests_path or DEFAULT_MANIFESTS)[map_id]
    catalogue = loadouts.load(loadouts_path or DEFAULT_LOADOUTS)
    telemetry = Telemetry(telemetry_path)
    # One campaign object holds ownership, Funds and Squads, and the port judges
    # against it: two of anything here would be two answers to how much a side
    # has or what it owns. The outbox is the Campaign's because the domain is
    # what puts an Effect on it; the daemon drains it.
    campaign = campaign_module.Campaign(
        map_manifest=map_manifest,
        table=table,
        ledger=economy.Ledger(table.starting_funds),
        outbox=Outbox(),
        catalogue=catalogue,
    )
    port = CommandPort(campaign=campaign)
    return Wiring(
        campaign=campaign,
        port=port,
        # The Campaign in play, and everything one report does to it (#75). The
        # daemon holds it rather than is it: that object answers a socket, this
        # one plays a Campaign, and Phase 2's `save` lands there because what it
        # persists is what this object holds (ADR-0008).
        cycle=report_cycle.ReportCycle(
            campaign=campaign,
            port=port,
            telemetry=telemetry,
            telemetry_path=telemetry_path,
            # Where a won Campaign's record lands, and where its summary is read
            # from (#35, ADR-0023). Beside the telemetry by default, because the
            # two are one run's evidence and separating them would be one more
            # path for a session to get wrong.
            archive_path=archive_path or telemetry_path.parent / "campaigns",
        ),
        telemetry=telemetry,
    )


def build_daemon(  # noqa: PLR0913 — see `wire`, whose arguments these are.
    *,
    telemetry_path: Path,
    economy_path: Path | None = None,
    manifests_path: Path | None = None,
    loadouts_path: Path | None = None,
    map_id: str = DEFAULT_MAP,
    archive_path: Path | None = None,
    epoch: str | None = None,
) -> Daemon:
    """Build a stock daemon on this checkout's authored files (#76, #164).

    A caller that has its own files says so here rather than reaching past a
    default. The epoch is this daemon's identity rather than one of the wiring's
    parts, which is why it stops here instead of going into `wire`.
    """
    return Daemon(
        wiring=wire(
            telemetry_path=telemetry_path,
            economy_path=economy_path,
            manifests_path=manifests_path,
            loadouts_path=loadouts_path,
            map_id=map_id,
            archive_path=archive_path,
        ),
        epoch=epoch,
    )


def build(  # noqa: PLR0913 — `wire`'s arguments plus who is under AI command.
    telemetry_path: Path,
    ai: Iterable[tuple[str, int]] | None,
    *,
    economy_path: Path | None = None,
    manifests_path: Path | None = None,
    loadouts_path: Path | None = None,
    map_id: str = DEFAULT_MAP,
) -> Daemon:
    """Build the daemon this process will serve, under command or not (#16, #17).

    `ai` is one `(side, seed)` per side an AI Commander plays — none, one, or
    both. A planner apiece rather than one asked twice: a planner holds its seed,
    and a pair of seeds is what a two-sided Campaign replays from (#17).

    The planners are built here rather than inside the daemon because they read
    the manifest and the economy table `build_daemon` has just loaded — read
    back off the Campaign it wired — and loading them twice would be two answers
    to what the map is.
    """
    daemon = build_daemon(
        telemetry_path=telemetry_path,
        economy_path=economy_path,
        manifests_path=manifests_path,
        loadouts_path=loadouts_path,
        map_id=map_id,
    )
    for side, seed in ai or ():
        daemon.commanded_by(
            side,
            planner.UtilityPlanner(
                map_manifest=daemon.campaign.map_manifest,
                table=daemon.campaign.table,
                seed=seed,
            ),
        )
    return daemon


class NonLoopbackBindError(Exception):
    """The daemon was asked to listen somewhere off this machine (ADR-0044)."""


def check_loopback(host: str) -> None:
    """Refuse a bind address that is not this machine's own loopback.

    The socket carries no authentication and ADR-0044 decides it will not grow
    any: what makes it safe is that nothing off this machine can reach it, so
    the bind address *is* the boundary and a widened one is the whole guarantee
    gone. `spike/run.sh` used to widen it to 0.0.0.0 for hold mode, which was
    the Phase-0 mission's clients calling the shim directly and has had no
    caller since `missions/cti.Stratis` (ADR-0018: a client never speaks to the
    daemon). Fail-closed rather than warn, per ADR-0033.

    #53's remote slots do not overturn this: an SSH-carried transport is
    loopback at both ends, which is the point of carrying it over SSH.
    """
    try:
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError as exc:
        message = f"{host!r} is not an address this daemon can bind"
        raise NonLoopbackBindError(message) from exc
    if not loopback:
        message = (
            f"the daemon binds loopback only and was asked for {host!r} (ADR-0044): "
            f"the socket is unauthenticated, so its address is the whole of the "
            f"boundary. Carry it over SSH rather than widening the bind"
        )
        raise NonLoopbackBindError(message)


def serve(  # noqa: PLR0913 — Main's knobs, one parameter apiece: where to listen,
    # where the evidence goes, who is under AI command, and which authored files
    # to play on. Folding them into a config object would put one indirection
    # between the command line and what it varies (`build_daemon` says the same).
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    telemetry_path: Path = DEFAULT_TELEMETRY,
    on_ready: Callable[[int, str], None] | None = None,
    ai: Iterable[tuple[str, int]] | None = None,
    economy_path: Path | None = None,
    manifests_path: Path | None = None,
    loadouts_path: Path | None = None,
    map_id: str = DEFAULT_MAP,
) -> None:
    """Serve until interrupted. Calls `on_ready` with the bound port and epoch."""
    check_loopback(host)
    daemon = build(
        telemetry_path,
        ai,
        economy_path=economy_path,
        manifests_path=manifests_path,
        loadouts_path=loadouts_path,
        map_id=map_id,
    )
    with _Server((host, port), _handler_for(daemon)) as server:
        if on_ready is not None:
            on_ready(int(server.server_address[1]), daemon.epoch)
        server.serve_forever()


class DaemonNeverCameUpError(Exception):
    """The background daemon did not bind inside its bring-up window (#88)."""


# How long bring-up waits for the socket to bind. Generous: binding a loopback
# port is microseconds, so anything approaching this is a failure rather than a
# slow machine, and the wait exists only so a bind that never happens says so
# instead of hanging.
BRING_UP_SECONDS: Final = 5.0


def serve_in_thread(
    host: str = DEFAULT_HOST, port: int = 0, *, telemetry_path: Path = DEFAULT_TELEMETRY
) -> int:
    """Start the daemon on a background thread and return the bound port.

    Raises rather than indexing an empty list: a bind failure used to surface as
    a bare `IndexError` out of `bound[0]`, which says nothing about a daemon.
    """
    # Asked here as well as inside `serve`, because a refusal raised on the
    # background thread would reach the caller as "nothing bound in five
    # seconds" — a bind that was never attempted reported as a slow one.
    check_loopback(host)
    ready = threading.Event()
    bound: list[int] = []

    def _record(bound_port: int, _epoch: str) -> None:
        bound.append(bound_port)
        ready.set()

    thread = threading.Thread(
        target=serve,
        args=(host, port),
        kwargs={"telemetry_path": telemetry_path, "on_ready": _record},
        daemon=True,
    )
    thread.start()
    if not ready.wait(timeout=BRING_UP_SECONDS) or not bound:
        message = (
            f"daemon never came up: nothing bound on {host}:{port} "
            f"within {BRING_UP_SECONDS} seconds"
        )
        raise DaemonNeverCameUpError(message)
    return bound[0]


# What a seed may read as. Matched whole rather than stripped of its sign
# (#155): `seed.lstrip("-").isdigit()` let `"--5"` through to `int()`, which
# raised argparse's generic "invalid value" where this module's own refusal —
# the one that says what a seed is — had been promised.
SEED_TEXT: Final = re.compile(r"-?[0-9]+")


def parse_commander_flag(text: str) -> tuple[str, int]:
    """Read one `SIDE[:SEED]` bring-up flag, or refuse it.

    Side and seed travel together rather than as two parallel lists, because a
    seed belongs to the Commander it plays and a session that brought up two
    sides against one list of seeds would have to keep the order straight in its
    head. The seed is fixed rather than drawn: the same pair of seeds and the
    same reports have to produce the same Campaign, which is not a property a
    clock can hold.
    """
    side, _, seed = text.partition(":")
    side = side.upper()
    if side not in commands.SIDES:
        message = f"no side named {side!r} is playing; expected one of {list(commands.SIDES)}"
        raise argparse.ArgumentTypeError(message)
    if seed and not SEED_TEXT.fullmatch(seed):
        message = f"{text!r}: a seed is a whole number, got {seed!r}"
        raise argparse.ArgumentTypeError(message)
    return side, int(seed or 0)


def main(argv: list[str] | None = None) -> int:
    """Run the daemon from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY)
    # One flag per side under AI command, each carrying its own seed (#17).
    # None of them, and nobody is under AI command — a world brought up for a
    # human Commander is not quietly played by one.
    parser.add_argument(
        "--ai",
        type=parse_commander_flag,
        action="append",
        default=[],
        metavar="SIDE[:SEED]",
    )
    # The authored files this daemon plays on (#164). `build_daemon` has taken
    # these since #76 and nothing could reach them from a command line, so
    # booting a non-default map or a hand-authored fixture economy meant editing
    # the composition root — which is exactly what #4's "a hand-authored fixture
    # boots directly" criterion may not require of whoever is booting it.
    # Defaulting to `None` rather than to the constants keeps one answer to
    # where the authored files live: `build_daemon`'s.
    parser.add_argument("--economy", type=Path, default=None, metavar="PATH")
    parser.add_argument("--manifests", type=Path, default=None, metavar="DIR")
    parser.add_argument("--loadouts", type=Path, default=None, metavar="PATH")
    parser.add_argument("--map", dest="map_id", default=DEFAULT_MAP, metavar="MAP_ID")
    args = parser.parse_args(argv)
    # Before the telemetry directory is made, so a run that will not start
    # leaves nothing behind: the harness reads a missing readiness line as
    # infra_unavailable, and this says on stderr why there will never be one.
    try:
        check_loopback(args.host)
    except NonLoopbackBindError as exc:
        print(f"cti-daemon: {exc}", file=sys.stderr)  # noqa: T201 — the operator reads stderr
        return 2
    args.telemetry.parent.mkdir(parents=True, exist_ok=True)

    def announce(port: int, epoch: str) -> None:
        line = ready_line(args.host, port, epoch)
        print(line, flush=True)  # noqa: T201 — the harness reads stdout

    try:
        serve(
            args.host,
            args.port,
            telemetry_path=args.telemetry,
            on_ready=announce,
            ai=args.ai,
            economy_path=args.economy,
            manifests_path=args.manifests,
            loadouts_path=args.loadouts,
            map_id=args.map_id,
        )
    except KeyboardInterrupt:
        return 0
    # A map id no manifest in the directory carries is the operator's mistake
    # rather than a crash to read a traceback out of: `load_all` keys on the id
    # each manifest declares, so this is the one lookup a flag can miss.
    except KeyError:
        looked = args.manifests or DEFAULT_MANIFESTS
        print(  # noqa: T201 — the operator reads stderr
            f"cti-daemon: no manifest in {looked} describes a map called {args.map_id!r}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
