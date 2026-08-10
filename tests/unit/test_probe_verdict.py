"""How one probe's outcome becomes the verdict the pool records (#171, ADR-0049).

The ladder lived in `spike/regress.sh` as sixty lines of bash — watchdog kill,
expect-inversion, quarantine, the untyped-red rule, and a hand-rolled JSON
heredoc — which is exactly the shape that produced #83: decision logic in the
harness's shell, testable only by a bring-up. `tools/probe_verdict.py` is that
ladder as a pure function plus one writer, so a wrong class is a red
`just unit` here rather than an in-world discovery.

The behaviour asserted is the one `regress.sh` had, byte-for-byte where a
reader depends on the bytes: `tests/unit/test_pool_slots.py` asserts
"watchdog" appears in a watchdog kill's detail, and the rendered document is
pinned as the stable evidence format — the merge and the pruner read it as
JSON now (#185, `tools/pool_merge.py`), so the bytes serve the human grepping
stored runs rather than any in-repo reader.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    import pytest

probe_verdict = load_tool("probe_verdict")


def outcome(**overrides: object) -> object:
    """One probe outcome, with only the fields under test varied."""
    fields: dict[str, object] = {
        "run_status": 0,
        "results": {"verdict": "PASS"},
        "expect": "",
        "quarantined": "",
        "window_secs": 150,
        "watchdog_secs": 750,
        "margin_secs": 600,
        "evidence": "/runs/20260804T000000Z-contacts",
        **overrides,
    }
    return probe_verdict.Outcome(**fields)


def test_a_pass_is_typed_pass() -> None:
    typed = probe_verdict.type_verdict(outcome())
    assert typed.verdict == "PASS"
    assert typed.class_ == "pass"
    assert typed.raw_class == "pass"


def test_a_declared_class_is_kept() -> None:
    """The #23/#83 rule: the class the world declared is the class reported."""
    typed = probe_verdict.type_verdict(
        outcome(
            run_status=1,
            results={
                "verdict": "FAIL",
                "failure_class": "oracle_disagreement",
                "failure_detail": "capture layer disagrees",
            },
        )
    )
    assert typed.verdict == "FAIL"
    assert typed.class_ == "oracle_disagreement"
    assert typed.detail == "capture layer disagrees"


def test_an_untyped_red_is_a_harness_bug() -> None:
    """run.sh died without typing itself; the table says fix the harness first."""
    typed = probe_verdict.type_verdict(outcome(run_status=70, results={}))
    assert typed.class_ == "untyped_harness_failure"
    assert "exited 70 without recording a class" in typed.detail
    assert "/runs/20260804T000000Z-contacts/regress.log" in typed.detail


def test_a_declared_detail_survives_the_untyped_rule() -> None:
    typed = probe_verdict.type_verdict(
        outcome(run_status=3, results={"verdict": "FAIL", "failure_detail": "half a story"})
    )
    assert typed.class_ == "untyped_harness_failure"
    assert typed.detail == "half a story"


def test_the_watchdog_outranks_whatever_the_run_left() -> None:
    """A killed run's half-written results.env is not evidence of anything (#144)."""
    typed = probe_verdict.type_verdict(outcome(run_status=124, results={"verdict": "PASS"}))
    assert typed.verdict == "FAIL"
    assert typed.class_ == "infra_unavailable"
    assert "killed at the 750s watchdog" in typed.detail
    assert "window 150s plus 600s" in typed.detail


def test_the_follow_up_sigkill_at_the_deadline_is_the_same_watchdog_story() -> None:
    """A SIGKILL landing after the watchdog's deadline is the follow-up kill."""
    typed = probe_verdict.type_verdict(outcome(run_status=137, elapsed_secs=812, results={}))
    assert typed.class_ == "infra_unavailable"
    assert "killed at the 750s watchdog" in typed.detail


def test_a_sigkill_before_the_deadline_is_the_machine_not_the_watchdog() -> None:
    """#147: an OOM kill — #125's scenario — used to wear the watchdog's detail.

    The class was already right; the recorded story fabricated a deadline that
    never fired. A SIGKILL forty seconds into a 750 s watchdog cannot be the
    watchdog's.
    """
    typed = probe_verdict.type_verdict(
        outcome(run_status=137, elapsed_secs=44, results={"verdict": "PASS"})
    )
    assert typed.verdict == "FAIL"
    assert typed.class_ == "infra_unavailable"
    assert "SIGKILL" in typed.detail
    assert "OOM" in typed.detail
    assert "killed at the" not in typed.detail


def test_a_starved_flight_is_infra_unavailable_whatever_it_recorded() -> None:
    """The floor under a granted run (#182, ADR-0055).

    The starvation watch stopped this probe mid-flight; whatever its world was
    about to report — the episodes wore `timeout` and `node_crashed` — was
    measured on a machine at the running floor, which is not a condition anyone
    can interpret. The marker outranks even the class the run declared.
    """
    typed = probe_verdict.type_verdict(
        outcome(
            run_status=143,
            starved="97 MiB available, under the 512 MiB running floor",
            results={
                "verdict": "FAIL",
                "failure_class": "timeout",
                "failure_detail": "never closed on the objective",
            },
        )
    )
    assert typed.verdict == "FAIL"
    assert typed.class_ == "infra_unavailable"
    assert "starved" in typed.detail
    assert "97 MiB available, under the 512 MiB running floor" in typed.detail
    assert "/runs/20260804T000000Z-contacts/regress.log" in typed.detail


def test_a_starved_marker_outranks_even_a_recorded_pass() -> None:
    """Fail-closed picks the discarded pass over the forged one.

    A run that squeaked a PASS out while the box was under the floor measured
    it under the same uninterpretable conditions as the forged reds; a pass
    discarded as infra_unavailable costs a re-run, a forged pass costs a false
    green.
    """
    typed = probe_verdict.type_verdict(
        outcome(run_status=0, starved="40 MiB available, under the 512 MiB running floor")
    )
    assert typed.verdict == "FAIL"
    assert typed.class_ == "infra_unavailable"
    assert "starved" in typed.detail


def test_a_starved_marker_outranks_the_watchdog_story() -> None:
    """A starved world that then blew its watchdog is still the starvation's red."""
    typed = probe_verdict.type_verdict(
        outcome(
            run_status=124,
            elapsed_secs=812,
            starved="19 MiB available, under the 512 MiB running floor",
            results={},
        )
    )
    assert typed.class_ == "infra_unavailable"
    assert "starved" in typed.detail
    assert "killed at the" not in typed.detail


def test_a_starved_expected_red_probe_does_not_invert_to_a_pass() -> None:
    """A red-by-design probe starved mid-flight measured nothing it expects."""
    typed = probe_verdict.type_verdict(
        outcome(
            run_status=143,
            expect="node_crashed",
            starved="20 MiB available, under the 512 MiB running floor",
            results={"verdict": "FAIL", "failure_class": "node_crashed"},
        )
    )
    assert typed.verdict == "FAIL"
    assert typed.class_ == "infra_unavailable"
    assert "expects node_crashed, got infra_unavailable" in typed.detail


def test_a_signal_killed_run_is_the_machines_doing_not_a_harness_bug() -> None:
    """#147 item 2: a 128+SIG exit used to fold into `untyped_harness_failure`.

    That sent the reader to fix the harness for a machine event; the honest
    class is `infra_unavailable` — stop, not a result.
    """
    typed = probe_verdict.type_verdict(outcome(run_status=143, results={}))
    assert typed.class_ == "infra_unavailable"
    assert "SIGTERM" in typed.detail
    assert "/runs/20260804T000000Z-contacts/regress.log" in typed.detail


def test_an_exit_past_the_signal_range_is_still_an_untyped_red() -> None:
    """255 is a process's own exit, not a signal death; the untyped rule stands."""
    typed = probe_verdict.type_verdict(outcome(run_status=255, results={}))
    assert typed.class_ == "untyped_harness_failure"
    assert "exited 255 without recording a class" in typed.detail


def test_an_expected_red_inverts_to_a_pass() -> None:
    """A probe red by design passes by producing exactly the class it names."""
    typed = probe_verdict.type_verdict(
        outcome(
            run_status=1,
            expect="node_crashed",
            results={
                "verdict": "FAIL",
                "failure_class": "node_crashed",
                "failure_detail": "the daemon went away",
            },
        )
    )
    assert typed.verdict == "PASS"
    assert typed.class_ == "pass"
    assert typed.raw_class == "node_crashed"
    assert typed.detail == "expected-red: the daemon went away"


def test_a_green_run_of_an_expected_red_probe_is_the_bug() -> None:
    typed = probe_verdict.type_verdict(outcome(expect="schema_stale"))
    assert typed.verdict == "FAIL"
    assert typed.class_ == "assertion_failed"
    assert "expects schema_stale and passed instead" in typed.detail


def test_an_expected_red_failing_differently_keeps_its_class() -> None:
    """A negative probe failing for the wrong reason is still a failure."""
    typed = probe_verdict.type_verdict(
        outcome(
            run_status=1,
            expect="node_crashed",
            results={
                "verdict": "FAIL",
                "failure_class": "timeout",
                "failure_detail": "never saw the crash line",
            },
        )
    )
    assert typed.verdict == "FAIL"
    assert typed.class_ == "timeout"
    assert typed.detail == "probe expects node_crashed, got timeout: never saw the crash line"


def test_quarantine_covers_any_red_and_names_what_it_covered() -> None:
    typed = probe_verdict.type_verdict(
        outcome(
            run_status=1,
            quarantined="#181",
            results={
                "verdict": "FAIL",
                "failure_class": "assertion_failed",
                "failure_detail": "mass_probe_mass_unpicked",
            },
        )
    )
    assert typed.verdict == "FAIL"
    assert typed.class_ == "flake_quarantine"
    assert "quarantined #181 (not gating): assertion_failed" in typed.detail
    assert "mass_probe_mass_unpicked" in typed.detail


def test_quarantine_does_not_touch_a_pass() -> None:
    typed = probe_verdict.type_verdict(outcome(quarantined="#181"))
    assert typed.verdict == "PASS"
    assert typed.class_ == "pass"


def test_the_last_write_wins_in_results_env(tmp_path: Path) -> None:
    """run.sh appends; the reader believes the final word, as the old seds did."""
    results = tmp_path / "results.env"
    results.write_text("verdict=FAIL\nfailure_class=timeout\nverdict=PASS\n", encoding="utf-8")
    read = probe_verdict.read_results(results)
    assert read["verdict"] == "PASS"
    assert read["failure_class"] == "timeout"


def test_a_missing_results_env_reads_as_nothing_declared(tmp_path: Path) -> None:
    assert probe_verdict.read_results(tmp_path / "absent.env") == {}


def run_main(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], **overrides: str
) -> tuple[dict, dict[str, str]]:
    """Drive the CLI once; give back verdict.json and the stdout lines."""
    results = tmp_path / "results.env"
    if not results.exists():
        results.write_text(
            "verdict=PASS\nserver_version=2.20.152984\nlegs=client:ran\n",
            encoding="utf-8",
        )
    verdict_json = tmp_path / "verdict.json"
    argv_pairs = {
        "--probe": "contacts",
        "--results": str(results),
        "--verdict-json": str(verdict_json),
        "--run-status": "0",
        "--window": "240",
        "--watchdog": "840",
        "--margin": "600",
        "--elapsed": "97",
        "--expect": "",
        "--quarantined": "",
        "--issues": "28",
        "--stamp": "20260804T101112Z",
        "--git-sha": "deadbeef",
        "--git-dirty": "false",
        "--slot": "1",
        "--host": "local",
        "--evidence": str(tmp_path),
        **overrides,
    }
    argv = [item for pair in argv_pairs.items() for item in pair]
    assert probe_verdict.main(argv) == 0
    document = json.loads(verdict_json.read_text(encoding="utf-8"))
    lines = dict(
        line.split("=", 1)
        for line in capsys.readouterr().out.splitlines()  # type: ignore[attr-defined]
    )
    return document, lines


def test_main_writes_the_document_the_merge_reads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document, lines = run_main(tmp_path, capsys)
    assert document["probe"] == "contacts"
    assert document["verdict"] == "PASS"
    assert document["class"] == "pass"
    assert document["legs"] == "client:ran"
    assert document["window_secs"] == 240
    assert document["elapsed_secs"] == 97
    assert document["slot"] == 1
    assert document["git_dirty"] is False
    assert document["arma_version"] == "2.20.152984"
    assert lines["class"] == "pass"
    assert lines["verdict"] == "PASS"
    assert lines["legs"] == "client:ran"
    # The stable evidence rendering: no in-repo reader depends on these bytes
    # since #185, but stored runs are grepped by humans, so the format is
    # pinned rather than free to drift.
    text = (tmp_path / "verdict.json").read_text(encoding="utf-8")
    assert '"verdict": "PASS"' in text
    assert '\n  "class": "pass",' in text


def test_main_rejects_an_engine_version_other_than_the_pin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = tmp_path / "results.env"
    results.write_text("verdict=PASS\nserver_version=2.22.999999\n", encoding="utf-8")

    document, lines = run_main(tmp_path, capsys)

    assert document["verdict"] == "FAIL"
    assert document["class"] == "engine_drift"
    assert document["raw_class"] == "engine_drift"
    assert document["detail"] == (
        "Arma server version drift: expected 2.20.152984, observed 2.22.999999; "
        "update tools/arma_server_version.txt only after accepting the engine update"
    )
    assert lines["class"] == "engine_drift"


def test_engine_drift_outranks_the_probe_result_and_its_treatments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = tmp_path / "results.env"
    results.write_text(
        "verdict=FAIL\nfailure_class=timeout\nserver_version=2.22.999999\n",
        encoding="utf-8",
    )

    document, _lines = run_main(
        tmp_path,
        capsys,
        **{"--run-status": "2", "--expect": "timeout", "--quarantined": "#233"},
    )

    assert document["class"] == "engine_drift"
    assert document["detail"].startswith(
        "Arma server version drift: expected 2.20.152984, observed 2.22.999999"
    )


def test_main_fails_closed_when_the_engine_version_was_not_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = tmp_path / "results.env"
    results.write_text("verdict=PASS\n", encoding="utf-8")

    document, lines = run_main(tmp_path, capsys)

    assert document["verdict"] == "FAIL"
    assert document["class"] == "infra_unavailable"
    assert document["raw_class"] == "infra_unavailable"
    assert document["detail"] == (
        "Arma server version was not recorded; expected 2.20.152984, observed <missing>; "
        "the engine identity could not be checked"
    )
    assert lines["class"] == "infra_unavailable"


def test_main_fails_closed_when_the_engine_version_is_unreadable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = tmp_path / "results.env"
    results.write_text("verdict=PASS\nserver_version=not-a-version\n", encoding="utf-8")

    document, lines = run_main(tmp_path, capsys)

    assert document["class"] == "infra_unavailable"
    assert document["detail"] == (
        "Arma server version is unreadable; expected 2.20.152984, "
        "observed not-a-version; the engine identity could not be checked"
    )
    assert lines["class"] == "infra_unavailable"


def test_main_survives_a_detail_full_of_json_poison(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The escaping `json_string` existed for, without the hand-rolled escaping."""
    results = tmp_path / "results.env"
    results.write_text(
        "server_version=2.20.152984\n"
        'verdict=FAIL\nfailure_class=timeout\nfailure_detail=saw "x\\y"\tand stalled\n',
        encoding="utf-8",
    )
    document, lines = run_main(tmp_path, capsys, **{"--run-status": "1"})
    assert document["class"] == "timeout"
    assert document["detail"] == 'saw "x\\y"\tand stalled'
    assert lines["class"] == "timeout"


STALL_FIXTURES = Path(__file__).parent.parent / "fixtures" / "client-rpt-stall"
STALL_FAIL_RPTS = [STALL_FIXTURES / "fail-20260803.rpt", STALL_FIXTURES / "fail-20260810.rpt"]
STALL_PASS_RPTS = [STALL_FIXTURES / "pass-20260805.rpt", STALL_FIXTURES / "pass-20260810.rpt"]


def client_timeout_outcome(rpt: Path) -> object:
    """Return a client-leg probe outcome that timed out waiting for a player to join."""
    return outcome(
        run_status=0,
        results={
            "verdict": "FAIL",
            "failure_class": "timeout",
            "failure_detail": (
                "FAIL class=timeout client_port_probe_no_client_assigned waited=240 players=0"
            ),
            "windows_client_rpt": str(rpt),
        },
    )


def test_both_archived_stall_episodes_type_as_infra_not_timeout() -> None:
    """The Windows-host stall wears the honest class (#304).

    Both archived episodes red as `class=timeout` because no player joined the
    server within the window; each client RPT reaches the SimulWeather cloud
    renderer and stops, never loading move types. `timeout`'s required response
    is "investigate synchronisation", which is exactly the wrong instruction for
    a host that has stopped — `infra_unavailable` is the honest class, and the
    run says nothing about the code under test.
    """
    for rpt in STALL_FAIL_RPTS:
        typed = probe_verdict.type_verdict(client_timeout_outcome(rpt))
        assert typed.verdict == "FAIL", rpt
        assert typed.class_ == "infra_unavailable", rpt
        assert typed.raw_class == "infra_unavailable", rpt
        assert "SimulWeather cloud renderer" in typed.detail, rpt
        assert "restarting the Windows host" in typed.detail, rpt
        assert str(rpt) in typed.detail, rpt


def test_both_archived_passing_rpts_do_not_match_the_stall() -> None:
    """A real client-leg timeout keeps its class — the failing side is not weakened.

    The discriminator keys on the content transition (cloud renderer reached,
    move types never loaded), not on the probe name or the line count. A client
    whose RPT loaded `CfgGesturesMale` got past the stall point, so a timeout on
    that probe is a genuine synchronisation-shaped failure and keeps `timeout`.
    """
    for rpt in STALL_PASS_RPTS:
        typed = probe_verdict.type_verdict(client_timeout_outcome(rpt))
        assert typed.class_ == "timeout", rpt
        assert typed.raw_class == "timeout", rpt
        assert "no_client_assigned" in typed.detail, rpt


def test_an_assertion_failed_client_probe_keeps_its_class() -> None:
    """An assertion failure is not swallowed as a stall.

    The six client probes also red for real reasons (#304); the detection fires
    only when the recorded class is `timeout`, so an `assertion_failed` is left
    untouched even with a stalling RPT present — a different failure wearing the
    same probe name.
    """
    rpt = STALL_FAIL_RPTS[0]
    typed = probe_verdict.type_verdict(
        outcome(
            run_status=1,
            results={
                "verdict": "FAIL",
                "failure_class": "assertion_failed",
                "failure_detail": "client misbehaved on connect",
                "windows_client_rpt": str(rpt),
            },
        )
    )
    assert typed.class_ == "assertion_failed"
    assert typed.detail == "client misbehaved on connect"


def test_a_timeout_with_no_client_rpt_is_not_a_host_stall() -> None:
    """A non-client probe (no RPT in evidence) timing out is not the stall."""
    typed = probe_verdict.type_verdict(
        outcome(
            run_status=0,
            results={
                "verdict": "FAIL",
                "failure_class": "timeout",
                "failure_detail": "contacts never closed on the objective",
            },
        )
    )
    assert typed.class_ == "timeout"
    assert typed.raw_class == "timeout"


def test_the_stall_is_resolved_from_the_evidence_dir_when_unrecorded(tmp_path: Path) -> None:
    """Resolve the stall from the evidence dir when the recorded path is absent.

    `client_rpt.py` records the path, but the same file also lives in evidence as
    `windows-client.rpt`; the resolver falls back to it (#73).
    """
    evidence = tmp_path
    (evidence / "windows-client.rpt").write_text(
        (STALL_FIXTURES / "fail-20260810.rpt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    typed = probe_verdict.type_verdict(
        outcome(
            run_status=0,
            evidence=str(evidence),
            results={
                "verdict": "FAIL",
                "failure_class": "timeout",
                "failure_detail": "no client assigned",
            },
        )
    )
    assert typed.class_ == "infra_unavailable"
    assert str(evidence / "windows-client.rpt") in typed.detail
