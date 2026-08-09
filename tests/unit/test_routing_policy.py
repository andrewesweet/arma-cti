"""The seven-row keep-on-Claude policy and its two enforcement points (#266)."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

routing_policy = load_tool("routing_policy")
dispatch = load_tool("dispatch")

POLICY = REPO / routing_policy.POLICY_RELATIVE
NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def route(*, seat: str = "implementer") -> object:
    return routing_policy.Route("zai", "zai-glm52-max", seat, NOW)


@pytest.mark.parametrize(
    ("class_id", "body", "seat"),
    [
        (1, "Invent wording in `CLAUDE.md`.", "implementer"),
        (2, "Routing-class: orchestration", "orchestrator"),
        (3, "Routing-class: retros-and-adr-authorship", "fable"),
        (4, "Routing-class: #181-shape", "implementer"),
        (5, "Change `addons/main/functions/fn_ui.sqf`.", "implementer"),
        (6, "Change `tools/dispatch.py`.", "implementer"),
        (7, "Measure the Anthropic plan meter.", "implementer"),
    ],
)
def test_every_class_row_refuses_by_name(class_id: int, body: str, seat: str) -> None:
    """Exercise the table's shape, not only the first row."""
    args = type(
        "Args",
        (),
        {"lane": "zai", "profile": "zai-glm52-max", "seat": seat},
    )()
    found = dispatch.Readiness(None, body=body)
    refusal = dispatch.routing_refusal(args, found, REPO, NOW)
    assert refusal is not None
    assert refusal.kind == "routing_policy_advisory"
    assert any(line.startswith(f"routing_class={class_id}:") for line in refusal.found)
    assert "check=advisory issue declaration" in refusal.found
    assert refusal.action


def test_work_outside_every_class_dispatches_unimpeded() -> None:
    read = routing_policy.read_policy(POLICY)
    assert read.policy is not None
    body = "Implement `tools/worker.py`; prove it with `tests/unit/test_worker.py`."
    assert routing_policy.advisory_match(read.policy, body, route()) is None


def test_the_live_map_ui_example_matches_the_in_world_class() -> None:
    read = routing_policy.read_policy(POLICY)
    assert read.policy is not None
    body = "Build the client map UI through the mode=1 remoteExec whitelist."
    match = routing_policy.advisory_match(read.policy, body, route())
    assert match is not None
    assert match.rule.id == 5


def test_dispatch_reads_the_file_again_for_each_call(tmp_path: Path) -> None:
    """Two dispatch checks in one process see a policy edit between them."""
    policy_path = tmp_path / routing_policy.POLICY_RELATIVE
    policy_path.parent.mkdir(parents=True)
    shutil.copyfile(POLICY, policy_path)
    args = type(
        "Args",
        (),
        {"lane": "zai", "profile": "zai-glm52-max", "seat": "implementer"},
    )()
    found = dispatch.Readiness(None, body="Change `addons/main/functions/fn_ui.sqf`.")

    first = dispatch.routing_refusal(args, found, tmp_path, NOW)
    assert first is not None
    assert "routing_class=5:in_world_landings" in first.found

    document = json.loads(policy_path.read_text(encoding="utf-8"))
    document["classes"][4]["name"] = "in_world_after_rebase"
    policy_path.write_text(json.dumps(document), encoding="utf-8")

    second = dispatch.routing_refusal(args, found, tmp_path, NOW)
    assert second is not None
    assert "routing_class=5:in_world_after_rebase" in second.found


def test_the_advisory_refusal_has_no_failure_class() -> None:
    read = routing_policy.read_policy(POLICY)
    assert read.policy is not None
    match = routing_policy.advisory_match(read.policy, "Change `tools/dispatch.py`.", route())
    assert match is not None
    refusal = dispatch.Refusal(
        "routing_policy_advisory",
        (f"routing_class={match.rule.id}:{match.rule.name}",),
        match.rule.remedy,
    )
    assert refusal.failure_class == ""
    assert not any(line.startswith("class=") for line in refusal.lines())


def test_pure_transcription_is_the_class_1_exception_only() -> None:
    read = routing_policy.read_policy(POLICY)
    assert read.policy is not None
    body = "Edit `CLAUDE.md`.\n\nRouting-exception: pure-transcription"
    assert routing_policy.advisory_match(read.policy, body, route()) is None
    assert (
        routing_policy.advisory_match(
            read.policy,
            body + "\nRouting-class: gates-themselves",
            route(),
        )
        is not None
    )


def test_no_dispatch_flag_can_override_the_class_rule() -> None:
    for flag in ("--skip-routing", "--no-routing-policy", "--routing-override"):
        with pytest.raises(SystemExit):
            dispatch.parse_args([flag])


def test_no_gated_landing_is_a_class_1_exception_that_must_be_declared() -> None:
    """A body that only *mentions* a gated path, and lands nothing there, may declare it.

    The exception is per-issue and visible in the body — there is still no flag on
    `just dispatch` that skips the class rule (#266, human instruction 2026-08-09).
    """
    read = routing_policy.read_policy(POLICY)
    assert read.policy is not None
    mentions = "Compare adapters against the gate ADR-0064 in `docs/adr/`."
    assert routing_policy.advisory_match(read.policy, mentions, route()) is not None
    declared = mentions + "\n\nRouting-exception: no-gated-landing"
    assert routing_policy.advisory_match(read.policy, declared, route()) is None
    # It excepts class 1 only: an in-world landing still refuses with it declared.
    in_world = declared + "\nA probe issues `remoteExec` orders from a map UI."
    assert routing_policy.advisory_match(read.policy, in_world, route()) is not None


def test_proposal_only_excepts_class_6_and_must_be_declared() -> None:
    """A lane may study the gate that judges it when it can only propose.

    Human ruling 2026-08-09 on #296: the conflict `gates_themselves` names is a
    foreign lane *authoring* the mechanism that judges it. An issue that may only
    propose — the human ruling on whatever it recommends — does not author, so it
    may declare the exception and run on a foreign lane. Declared per issue and
    visible in the body; there is still no flag that skips the class rule.
    """
    read = routing_policy.read_policy(POLICY)
    assert read.policy is not None
    studies_the_gate = "Design experiments over `config/dispatch-routing-policy.json`."
    assert routing_policy.advisory_match(read.policy, studies_the_gate, route()) is not None
    declared = studies_the_gate + "\n\nRouting-exception: proposal-only"
    assert routing_policy.advisory_match(read.policy, declared, route()) is None
    # It excepts class 6 only: a gated-surface landing still refuses with it declared.
    also_gated = declared + "\nRecord the outcome in `CLAUDE.md`."
    assert routing_policy.advisory_match(read.policy, also_gated, route()) is not None
