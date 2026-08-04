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
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

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


def test_the_follow_up_sigkill_is_the_same_watchdog_story() -> None:
    typed = probe_verdict.type_verdict(outcome(run_status=137, results={}))
    assert typed.class_ == "infra_unavailable"
    assert "watchdog" in typed.detail


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
        results.write_text("verdict=PASS\nserver_version=2.20\nlegs=client:ran\n", encoding="utf-8")
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
    assert document["arma_version"] == "2.20"
    assert lines["class"] == "pass"
    assert lines["verdict"] == "PASS"
    assert lines["legs"] == "client:ran"
    # The stable evidence rendering: no in-repo reader depends on these bytes
    # since #185, but stored runs are grepped by humans, so the format is
    # pinned rather than free to drift.
    text = (tmp_path / "verdict.json").read_text(encoding="utf-8")
    assert '"verdict": "PASS"' in text
    assert '\n  "class": "pass",' in text


def test_main_survives_a_detail_full_of_json_poison(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The escaping `json_string` existed for, without the hand-rolled escaping."""
    results = tmp_path / "results.env"
    results.write_text(
        'verdict=FAIL\nfailure_class=timeout\nfailure_detail=saw "x\\y"\tand stalled\n',
        encoding="utf-8",
    )
    document, lines = run_main(tmp_path, capsys, **{"--run-status": "1"})
    assert document["class"] == "timeout"
    assert document["detail"] == 'saw "x\\y"\tand stalled'
    assert lines["class"] == "timeout"
