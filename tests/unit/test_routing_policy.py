"""The routing classes and their two enforcement points (#266), as re-founded by #326.

The table used to be the keep-on-Claude policy, every row resting on provenance. ADR-0071
ruling 1 withdrew provenance and #326 re-founded the rows one at a time, so what these tests
hold is no longer "seven rows all refuse a foreign route". It is a per-class claim: which
classes survive, what each one now rests on, which of them refuse a landing at all, and that
the two classes the re-founding deleted refuse nothing.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from functools import cache
from typing import TYPE_CHECKING, Any

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

routing_policy = load_tool("routing_policy")
escalation = load_tool("escalation")


@cache
def dispatch() -> Any:  # noqa: ANN401 — load_tool returns a runtime module type
    """Load `tools/dispatch.py` on demand rather than at collection.

    Deliberately not a module-scope `load_tool`. Importing `dispatch` reaches
    `tools/admission.py`, which parses the shipped policy at *its* import and raises when it
    cannot — so a mutation-smoke mutant that breaks `parse_policy` would make this whole
    module uncollectable, and the run comes back "could not run" rather than "the mutant was
    killed". Loading inside the three tests that need it turns that same mutant into the
    failure it is (#326).
    """
    return load_tool("dispatch")


POLICY = REPO / routing_policy.POLICY_RELATIVE
CONDITIONS = REPO / escalation.CONDITIONS_RELATIVE
NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)

# The ids ADR-0071's re-founding table retires. They are never reused, so a table that
# carried one again would be reviving a rule the record killed under its own old number.
RETIRED = (1, 7)


def route(*, seat: str = "implementer") -> object:
    return routing_policy.Route("zai", "zai-glm52-max", seat, NOW)


def policy() -> Any:  # noqa: ANN401 — load_tool returns a runtime module type
    read = routing_policy.read_policy(POLICY)
    assert read.policy is not None
    return read.policy


def landing(*paths: str) -> Any:  # noqa: ANN401 — load_tool returns a runtime module type
    """Return the enforcing verdict on a real diff from a non-exempt lane."""
    return routing_policy.enforcing_match(policy(), paths, "zai")


# --- what survived, and under whose number ------------------------------------------------


def test_the_surviving_classes_are_the_five_the_decision_record_names() -> None:
    """ADR-0071: "Five classes survive", and their ids are not renumbered around the gaps."""
    assert [rule.id for rule in policy().rules] == [2, 3, 4, 5, 6]
    assert [rule.name for rule in policy().rules] == [
        "orchestration",
        "adr_authorship",
        "plausible_wrong_fix_goes_green",
        "in_world_landings",
        "gates_themselves",
    ]


def test_a_retired_id_cannot_come_back_under_its_old_number() -> None:
    """The gap is the point: ids 1 and 7 are historical handles, not free slots."""
    assert not set(RETIRED) & {rule.id for rule in policy().rules}


def test_ids_need_not_be_contiguous_but_must_ascend_without_repeating() -> None:
    """What replaced the old ordered-1..7 rule, which a deletion could not survive."""
    base = json.loads(POLICY.read_text(encoding="utf-8"))
    for broken in ([6, 5, 4, 3, 2], [2, 3, 4, 5, 5], [0, 3, 4, 5, 6]):
        document = json.loads(json.dumps(base))
        for entry, new_id in zip(document["classes"], broken, strict=True):
            entry["id"] = new_id
        with pytest.raises(routing_policy.PolicyError, match="stable handle"):
            routing_policy.parse_policy(json.dumps(document))


def test_a_table_that_dropped_a_class_another_module_addresses_cannot_govern() -> None:
    """`REQUIRED_CLASSES` is what contiguity used to buy, now that ids may have gaps."""
    base = json.loads(POLICY.read_text(encoding="utf-8"))
    for class_id in routing_policy.REQUIRED_CLASSES:
        document = json.loads(json.dumps(base))
        document["classes"] = [row for row in document["classes"] if row["id"] != class_id]
        with pytest.raises(routing_policy.PolicyError):
            routing_policy.parse_policy(json.dumps(document))


# --- one landing under each surviving class ------------------------------------------------


def test_class_2_orchestration_still_refuses_a_landing_on_its_own_surface() -> None:
    """The one provenance rule ruling 1 left standing, and it is unchanged."""
    match = landing("docs/agents/orchestration.md")
    assert match is not None
    assert (match.rule.id, match.rule.name) == (2, "orchestration")


def test_class_3_adr_authorship_enforces_on_a_landing_path_not_issue_phrases_alone() -> None:
    """The surviving half gained `docs/adr/`; the retro half took `docs/process-log.md`.

    ADR-0071: the class's only landing path belonged to the half being killed, so without
    this the survivor "would enforce on issue phrases alone" — a class that catches nothing
    on the enforcing read.
    """
    match = landing("docs/adr/0072-a-later-record.md")
    assert match is not None
    assert (match.rule.id, match.rule.name) == (3, "adr_authorship")
    assert landing("docs/process-log.md") is None


def test_class_4_is_declaration_only_and_refuses_no_route() -> None:
    """Capability, not provenance: no path can prove the #181 shape, and none bars it.

    The row still classifies — that is how the escalation condition reaches it — but its
    remedy is addressed to whoever takes the work rather than to the router.
    """
    shape = next(rule for rule in policy().rules if rule.id == 4)
    assert shape.landing_path_prefixes == ()
    assert shape.refuses is False
    declared = "Routing-class: #181-shape"
    assert routing_policy.advisory_match(policy(), declared, route()) is None
    assert routing_policy.classify_issue(policy(), declared, "implementer").rule.id == 4


def test_class_4s_remedy_is_the_escalation_condition_that_actually_fires() -> None:
    """The match is real rather than asserted: one issue body, both mechanisms, same class.

    ADR-0071 ruling 5 seeds a condition on "an issue declaring routing class 4 … which that
    class's remedy orders and which must therefore be a condition this ruling permits". So
    the class an issue body classifies into is fed to the condition table, and the condition
    that fires is named by the same class.
    """
    declared = "Routing-class: #181-shape"
    match = routing_policy.classify_issue(policy(), declared, "implementer")
    assert match is not None
    outcome = escalation.evaluate(
        escalation.read_conditions(CONDITIONS),
        escalation.Context(escalation.ItemState(routing_class=match.rule.id)),
    )
    assert outcome.kind == escalation.FIRING
    fired = outcome.emissions[0].condition
    assert fired.name == match.rule.name == "plausible_wrong_fix_goes_green"
    assert match.rule.id == escalation.CLASS_FOUR


def test_class_5_narrowed_to_a_subagent_rule_and_no_longer_bars_a_landing() -> None:
    """The corpus wait is what the rule was ever about, and a dispatched session holds it.

    ADR-0071: `just dispatch` launches a top-level session, which the wait hook permits, "so
    the class does not restrict the dispatch route this ADR defines, and two drafts said it
    did". What survives is a rule about subagents, and the row's remedy carries it.
    """
    in_world = next(rule for rule in policy().rules if rule.id == 5)
    assert in_world.refuses is False
    assert "subagent" in in_world.remedy
    assert landing("addons/main/functions/fn_ui.sqf") is None


def test_class_5_goes_on_being_the_one_authority_for_the_in_world_surface() -> None:
    """Narrowing the routing rule left #302's second job untouched — the failure to avoid."""
    assert routing_policy.in_world_paths(policy(), ("addons/main/fn.sqf", "tools/land.py")) == (
        "addons/main/fn.sqf",
    )
    assert "extension/" in routing_policy.in_world_prefixes(policy())


def test_class_6_took_the_two_gate_paths_the_deleted_class_1_held() -> None:
    """The denial layer and the permission allowlist are gates, so they moved rather than fell.

    ADR-0071: "Deleting the class outright would let an instance author the hook that judges
    it with nothing firing, so both paths move to class 6 rather than falling out."
    """
    for path in (".claude/hooks/deny-subagent-waits.py", ".claude/settings.json"):
        match = landing(path)
        assert match is not None, path
        assert (match.rule.id, match.rule.name) == (6, "gates_themselves")


def test_class_6_binds_every_instance_and_therefore_carries_no_exception() -> None:
    """An instance that can except itself from the gate that judges it is the conflict."""
    conflict = next(rule for rule in policy().rules if rule.id == 6)
    assert conflict.binds_every_instance is True
    assert not any(6 in entry.classes for entry in policy().issue_exceptions)
    base = json.loads(POLICY.read_text(encoding="utf-8"))
    with pytest.raises(routing_policy.PolicyError, match="conflict of interest"):
        routing_policy.parse_policy(
            json.dumps(
                dict(
                    base,
                    issue_exceptions=[
                        {"marker": "Routing-exception: proposal-only", "classes": [6]}
                    ],
                )
            )
        )


# --- and one under each deleted class ------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "CLAUDE.md",
        "CONTEXT.md",
        "tests/specs/spec-0001.yaml",
        ".claude/skills/retro/SKILL.md",
        ".claude/agents/cti-implementer.md",
        "tools/quota_tap.sh",
        "tests/fixtures/claude-usage-poll.json",
    ],
)
def test_the_deleted_classes_refuse_nothing(path: str) -> None:
    """Every path the two withdrawn classes held, less the two that moved to class 6.

    Class 1 died because its basis was provenance and the human sign-off gate on those
    surfaces was never this file; class 7 because the plan meter is read over plain HTTP with
    no Claude session involved. Proven by attempting the landing that used to be refused.
    """
    assert landing(path) is None
    assert routing_policy.advisory_match(policy(), f"Change `{path}`.", route()) is None


def test_the_retired_exception_markers_no_longer_appear_anywhere() -> None:
    """Their classes are gone, and an orphaned marker reads as a live allowance.

    Read off the parsed exceptions, not the file's text: class 6's remedy names
    `proposal-only` on purpose, to say the marker was withdrawn rather than to offer it.
    """
    markers = [entry.marker for entry in policy().issue_exceptions]
    for marker in ("pure-transcription", "no-gated-landing", "proposal-only"):
        assert not any(marker in declared for declared in markers)
    body = "Change `tools/dispatch.py`.\n\nRouting-exception: proposal-only"
    assert routing_policy.advisory_match(policy(), body, route()) is not None


def test_an_exception_naming_a_retired_class_is_refused_rather_than_ignored() -> None:
    base = json.loads(POLICY.read_text(encoding="utf-8"))
    for document in (
        dict(base, issue_exceptions=[{"marker": "Routing-exception: x", "classes": [1]}]),
        dict(
            base,
            route_exceptions=[
                {
                    "class": 7,
                    "lane": "codex",
                    "profile": "codex-sol-max",
                    "seat": "fable",
                    "standing": True,
                }
            ],
        ),
    ):
        with pytest.raises(routing_policy.PolicyError, match="retired or absent"):
            routing_policy.parse_policy(json.dumps(document))


# --- coverage, said where a reader meets it ------------------------------------------------


def test_the_shipped_policy_states_its_own_incomplete_coverage() -> None:
    """Not the parser's job — the parser reads copies it did not write (see COVERAGE_UNSTATED)."""
    assert policy().coverage != routing_policy.COVERAGE_UNSTATED
    assert "uncovered" in policy().coverage


def test_a_policy_that_states_no_coverage_reads_as_incomplete_rather_than_complete() -> None:
    base = json.loads(POLICY.read_text(encoding="utf-8"))
    base.pop("coverage")
    assert routing_policy.parse_policy(json.dumps(base)).coverage == (
        routing_policy.COVERAGE_UNSTATED
    )


def test_the_advisory_refusal_carries_the_coverage_line_a_reader_meets() -> None:
    """The reader being routed by the table is the reader forming a belief about it."""
    args = type("Args", (), {"lane": "zai", "profile": "zai-glm52-max", "seat": "implementer"})()
    found = dispatch().Readiness(None, body="Change `tools/dispatch.py`.")
    refusal = dispatch().routing_refusal(args, found, REPO, NOW)
    assert refusal is not None
    assert f"coverage={policy().coverage}" in refusal.found


def test_class_6s_own_remedy_names_the_gates_it_does_not_cover() -> None:
    """ADR-0071 calls the class aspirational; the remedy the refusal prints says so too."""
    remedy = next(rule for rule in policy().rules if rule.id == 6).remedy
    assert "tools/check_adr_form.py" in remedy
    assert "uncovered, never cleared" in remedy


# --- unchanged behaviour the re-founding must not have broken -------------------------------


@pytest.mark.parametrize(
    ("class_id", "body", "seat"),
    [
        (2, "Routing-class: orchestration", "orchestrator"),
        (3, "Routing-class: adr-authorship", "implementer"),
        (6, "Change `tools/dispatch.py`.", "implementer"),
    ],
)
def test_every_refusing_class_row_refuses_by_name(class_id: int, body: str, seat: str) -> None:
    """Exercise the refusing rows' shape, not only the first one."""
    args = type("Args", (), {"lane": "zai", "profile": "zai-glm52-max", "seat": seat})()
    found = dispatch().Readiness(None, body=body)
    refusal = dispatch().routing_refusal(args, found, REPO, NOW)
    assert refusal is not None
    assert refusal.kind == "routing_policy_advisory"
    assert any(line.startswith(f"routing_class={class_id}:") for line in refusal.found)
    assert "check=advisory issue declaration" in refusal.found
    assert refusal.action


def test_work_outside_every_class_dispatches_unimpeded() -> None:
    body = "Implement `tools/worker.py`; prove it with `tests/unit/test_worker.py`."
    assert routing_policy.advisory_match(policy(), body, route()) is None


def test_the_live_map_ui_example_still_classifies_as_the_in_world_class() -> None:
    """It no longer refuses, but it must still classify — the observatory reads this."""
    body = "Build the client map UI through the mode=1 remoteExec whitelist."
    match = routing_policy.classify_issue(policy(), body, "implementer")
    assert match is not None
    assert match.rule.id == 5


def test_dispatch_reads_the_file_again_for_each_call(tmp_path: Path) -> None:
    """Two dispatch checks in one process see a policy edit between them."""
    policy_path = tmp_path / routing_policy.POLICY_RELATIVE
    policy_path.parent.mkdir(parents=True)
    shutil.copyfile(POLICY, policy_path)
    args = type("Args", (), {"lane": "zai", "profile": "zai-glm52-max", "seat": "implementer"})()
    found = dispatch().Readiness(None, body="Change `tools/dispatch.py`.")

    first = dispatch().routing_refusal(args, found, tmp_path, NOW)
    assert first is not None
    assert "routing_class=6:gates_themselves" in first.found

    document = json.loads(policy_path.read_text(encoding="utf-8"))
    conflict = next(entry for entry in document["classes"] if entry["id"] == 6)
    conflict["name"] = "gates_after_rebase"
    policy_path.write_text(json.dumps(document), encoding="utf-8")

    second = dispatch().routing_refusal(args, found, tmp_path, NOW)
    assert second is not None
    assert "routing_class=6:gates_after_rebase" in second.found


def test_the_advisory_refusal_has_no_failure_class() -> None:
    match = routing_policy.advisory_match(policy(), "Change `tools/dispatch.py`.", route())
    assert match is not None
    refusal = dispatch().Refusal(
        "routing_policy_advisory",
        (f"routing_class={match.rule.id}:{match.rule.name}",),
        match.rule.remedy,
    )
    assert refusal.failure_class == ""
    assert not any(line.startswith("class=") for line in refusal.lines())


def test_no_dispatch_flag_can_override_the_class_rule() -> None:
    for flag in ("--skip-routing", "--no-routing-policy", "--routing-override"):
        with pytest.raises(SystemExit):
            dispatch().parse_args([flag])


def test_a_route_exception_carries_exactly_one_of_expiry_or_standing() -> None:
    """An undated widening must say so deliberately; a dated one cannot also be standing.

    Route exceptions were built time-boxed on purpose (#270). The human's ruling of
    2026-08-09 (#299) created the first standing one, and #326 retired it with the retro half
    of the class it excepted — but the schema rule it established outlives the entry.
    """
    base = json.loads(POLICY.read_text(encoding="utf-8"))
    entry = {"class": 3, "lane": "codex", "profile": "codex-sol-xhigh", "seat": "fable"}

    standing = dict(base, route_exceptions=[dict(entry, standing=True)])
    parsed = routing_policy.parse_policy(json.dumps(standing))
    assert parsed.route_exceptions[0].expires_at is None

    dated = dict(base, route_exceptions=[dict(entry, expires_at="2026-08-10T14:00:00+00:00")])
    assert routing_policy.parse_policy(json.dumps(dated)).route_exceptions[0].expires_at

    for wrong in (
        dict(entry),  # neither: an undated widening that never said so
        dict(entry, standing=True, expires_at="2026-08-10T14:00:00+00:00"),  # both
    ):
        with pytest.raises(routing_policy.PolicyError):
            routing_policy.parse_policy(json.dumps(dict(base, route_exceptions=[wrong])))


def test_the_shipped_policy_carries_no_route_exception_for_a_dead_retro_rule() -> None:
    """The standing retro allowance excepted the half ruling 3 killed, so it excepts nothing.

    ADR-0071 ruling 3: a retro identifies, researches and files, and lands nothing. With no
    retro routing rule left there is nothing for a retro allowance to widen past, and leaving
    it would read as a live human allowance against a rule that no longer exists.
    """
    assert policy().route_exceptions == ()
