"""The host guard's answer→verdict mapping, in its one home (#161, ADR-0049).

The free/running/unavailable → proceed/`infra_unavailable` ladder had grown
three near-verbatim bash copies — `cti_host_guard_main` in spike/host-guard.sh,
`cti_host_guard` in spike/hosts.sh, and inline above spike/run.sh's launch —
differing only in prefix and one sentence of wording, which is exactly how a
rung changed in one copy drifts from the other two. The mapping is decision
logic, so ADR-0049 puts it in `tools/host_guard_verdict.py`, and this file pins
it byte-for-byte: the block lines are what `test_host_guard.py` and
`test_host_seam.py` read off the real guards' stderr, and the env lines are
what the harness folds into `results.env` (`test_bringup_guards.py` reads
"play session" and "cannot check" out of the recorded details).

The default rung is fail-closed on purpose (#41): a state this ladder has never
heard of — garbage, an empty answer, a truncated line — is a check that could
not run, and that is a stop, never a proceed.
"""

from __future__ import annotations

import re

from conftest import REPO, load_tool

host_guard_verdict = load_tool("host_guard_verdict")

FREE = "free arma3_x64.exe is not in the Windows process list"
RUNNING = "running arma3_x64.exe is in the Windows process list"
UNAVAILABLE = "unavailable no executable Windows process list at /mnt/c/tasklist.exe"

HOST_GUARD_SH = REPO / "spike" / "host-guard.sh"
SPIKE = REPO / "spike"


# ------------------------------------------------------------------ the ladder


def test_free_proceeds_and_prints_the_detail() -> None:
    verdict = host_guard_verdict.decide(FREE)
    assert verdict.proceed
    assert verdict.block == ("[host-guard] arma3_x64.exe is not in the Windows process list",)


def test_free_with_a_host_names_it() -> None:
    verdict = host_guard_verdict.decide(FREE, host="local")
    assert verdict.proceed
    assert verdict.block == (
        "[host-guard] local: arma3_x64.exe is not in the Windows process list",
    )


def test_running_stops_and_says_a_play_session_may_be_live() -> None:
    """The stop `test_host_guard.py` reads off the command form's stderr."""
    verdict = host_guard_verdict.decide(RUNNING)
    assert not verdict.proceed
    assert verdict.block == (
        "[host-guard] arma3_x64.exe is in the Windows process list — a play session may be live.",
        "[host-guard] verdict=FAIL failure_class=infra_unavailable",
        "[host-guard] This is a stop, not a result. Nothing was launched.",
    )


def test_running_with_a_host_carries_it_on_the_verdict_line() -> None:
    """`test_host_seam.py` greps `failure_class=infra_unavailable host=local`."""
    verdict = host_guard_verdict.decide(RUNNING, host="local")
    assert verdict.block == (
        (
            "[host-guard] local: arma3_x64.exe is in the Windows process list "
            "— a play session may be live."
        ),
        "[host-guard] verdict=FAIL failure_class=infra_unavailable host=local",
        "[host-guard] This is a stop, not a result. Nothing was launched.",
    )


def test_unavailable_stops_with_the_could_not_run_sentence() -> None:
    verdict = host_guard_verdict.decide(UNAVAILABLE)
    assert not verdict.proceed
    assert verdict.block == (
        "[host-guard] no executable Windows process list at /mnt/c/tasklist.exe",
        "[host-guard] verdict=FAIL failure_class=infra_unavailable",
        "[host-guard] A check that could not run is not a check that passed.",
    )


def test_an_unknown_state_takes_the_fail_closed_rung() -> None:
    """The default rung refuses; it never proceeds on a word it cannot read."""
    verdict = host_guard_verdict.decide("wedged something nobody has seen")
    assert not verdict.proceed
    assert (
        verdict.block[-1] == "[host-guard] A check that could not run is not a check that passed."
    )


def test_an_empty_answer_is_a_stop_not_a_proceed() -> None:
    verdict = host_guard_verdict.decide("")
    assert not verdict.proceed


def test_a_one_word_answer_reads_as_the_shell_expansions_did() -> None:
    """A spaceless answer is state and detail at once, as it was in the shell.

    `${answer%% *}` and `${answer#* }` both give the whole string back when
    there is no space; the mirror keeps the ladders' behaviour identical.
    """
    state, detail = host_guard_verdict.split_answer("running")
    assert state == "running"
    assert detail == "running"


# ------------------------------------------------------------------ env format


def test_env_running_detail_is_what_run_sh_recorded() -> None:
    """`test_bringup_guards.py` reads "play session" out of `failure_detail`."""
    verdict = host_guard_verdict.decide(RUNNING, host="local")
    assert verdict.env == (
        "verdict=FAIL",
        "failure_class=infra_unavailable",
        (
            "failure_detail=arma3_x64.exe is in the Windows process list "
            "— that is a play session, not ours"
        ),
    )


def test_env_unavailable_detail_refuses_a_machine_it_cannot_check() -> None:
    """`test_bringup_guards.py` reads "cannot check" out of `failure_detail`."""
    verdict = host_guard_verdict.decide(UNAVAILABLE)
    assert verdict.env == (
        "verdict=FAIL",
        "failure_class=infra_unavailable",
        (
            "failure_detail=no executable Windows process list at /mnt/c/tasklist.exe"
            "; refusing to take a machine I cannot check"
        ),
    )


def test_env_free_says_proceed() -> None:
    verdict = host_guard_verdict.decide(FREE)
    assert verdict.env == (
        "verdict=proceed",
        "detail=arma3_x64.exe is not in the Windows process list",
    )


# ------------------------------------------------------------------------- CLI


def test_the_cli_prints_the_block_and_exits_the_verdict(capsys) -> None:  # noqa: ANN001
    status = host_guard_verdict.main(["--host", "local", "--", RUNNING])
    assert status == host_guard_verdict.EXIT_INFRA_UNAVAILABLE
    out = capsys.readouterr().out.splitlines()
    assert out == list(host_guard_verdict.decide(RUNNING, host="local").block)


def test_the_cli_env_format_prints_the_env_lines(capsys) -> None:  # noqa: ANN001
    status = host_guard_verdict.main(["--format", "env", "--", FREE])
    assert status == 0
    assert capsys.readouterr().out.splitlines() == list(host_guard_verdict.decide(FREE).env)


# ----------------------------------------------------- the exit code's one home


def test_the_exit_code_agrees_with_the_bash_home() -> None:
    """5 in Python and 5 in spike/host-guard.sh are one number, asserted."""
    match = re.search(
        r"^CTI_EXIT_INFRA_UNAVAILABLE=(\d+)$", HOST_GUARD_SH.read_text(), re.MULTILINE
    )
    assert match is not None, "spike/host-guard.sh no longer defines the exit code"
    assert int(match.group(1)) == host_guard_verdict.EXIT_INFRA_UNAVAILABLE == 5


def test_the_exit_code_has_exactly_one_bash_home() -> None:
    """#161: the number was defined in three files under three names.

    `spike/regress.sh` is exempt because what it carries is the whole class→exit
    table (`CLASS_RANK`), of which this number is one row — the table's own
    consolidation is #92/#147's seam, not this one.
    """
    definers = [
        script.name
        for script in sorted(SPIKE.glob("*.sh"))
        if re.search(r"^\s*CTI_EXIT_INFRA_UNAVAILABLE=", script.read_text(), re.MULTILINE)
    ]
    assert definers == ["host-guard.sh"], definers
    for dead_name in (r"^\s*EXIT_INFRA_UNAVAILABLE=", r"^\s*CTI_SLOT_EXIT_INFRA="):
        offenders = [
            script.name
            for script in sorted(SPIKE.glob("*.sh"))
            if re.search(dead_name, script.read_text(), re.MULTILINE)
        ]
        assert not offenders, f"{dead_name} is back in {offenders}; one home (#161)"
