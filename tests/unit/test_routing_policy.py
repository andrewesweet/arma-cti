"""The routing classes and their two enforcement points (#266), as re-founded by #326.

The table used to be the keep-on-Claude policy, every row resting on provenance. ADR-0071
ruling 1 withdrew provenance and #326 re-founded the rows one at a time, so what these tests
hold is no longer "seven rows all refuse a foreign route". It is a per-class claim: which
classes survive, what each one now rests on, which of them refuse a landing at all, and that
the two classes the re-founding deleted refuse nothing.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from functools import cache
from typing import TYPE_CHECKING, Any, Final

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
# Read to prove the gates class 6 names as omissions are gates this project actually runs; a
# name in that list that `just check` never reaches would be a reassurance about nothing.
JUSTFILE = REPO / "justfile"
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


def test_class_3_admits_the_seat_its_own_remedy_prescribes_on_a_foreign_lane() -> None:
    """The defect this row was re-founded to remove: it refused the route it appoints.

    ADR-0071 ruling 2 puts `codex-sol-xhigh` at the head of the `planner` seat's preferences
    and the re-founding table binds ADR authorship "to the planner's list rather than to
    Claude". Founded on the lane, the class refused that exact triple — measured in review
    round 1, claim 2 — so the rule forbade the route the ADR appoints. Founded on the seat, it
    clears it.
    """
    appointed = routing_policy.Route("codex", "codex-sol-xhigh", "planner", NOW)
    assert routing_policy.advisory_match(policy(), "ADR authorship for #999.", appointed) is None
    assert dispatch().SEATS["planner"].preference[0] == "codex-sol-xhigh"


def test_class_3_refuses_an_unappointed_seat_on_the_claude_lane_too() -> None:
    """Eligibility stopped being a property of provenance, so the Claude lane is not exempt.

    ADR-0071 ruling 1. A seat-founded row has nothing to say about which provider answered,
    so exempting it by lane would have cleared any Claude seat whatever while refusing the
    appointed foreign one — provenance wearing a capability remedy.
    """
    for lane, profile in (("claude-native", "opus-low"), ("codex", "codex-luna-max")):
        unappointed = routing_policy.Route(lane, profile, "recon", NOW)
        match = routing_policy.advisory_match(policy(), "ADR authorship for #999.", unappointed)
        assert match is not None, lane
        assert (match.rule.id, match.rule.name) == (3, "adr_authorship")
        assert "seat=recon" in match.evidence
        assert "required_seats=planner implementer review" in match.evidence


# The seats an ADR issue must be able to reach, and why each is required by a landed ruling.
# `planner` authors (ruling 2), `implementer` lands (ruling 2 again — the planner "neither
# gates nor lands"), `review` reviews that landing (ruling 4 — no change lands alone).
ADR_ROUTE: Final = ("planner", "implementer", "review")


def test_every_seat_is_walked_against_class_3_rather_than_the_row_being_read() -> None:
    """Round 1's deadlock was invisible to inspection and visible to a walk (round 2 claim 1).

    It admitted `planner` alone — the one seat ADR-0071 ruling 2 defines as neither gating nor
    landing — so on an ADR issue every seat that could have finished the work was refused, on
    every lane, and ruling 4's reviewing instance could not be dispatched at all. The finding
    is not "the row names the wrong seat"; it is that nobody walked the row. So this walks it:
    every seat in the dispatch registry, on both a Claude and a foreign lane, with the verdict
    asserted for each rather than for the ones that came to mind.
    """
    body = "ADR authorship for #999."
    for lane, profile in (("claude-native", "opus-low"), ("codex", "codex-luna-max")):
        for seat in dispatch().SEATS:
            match = routing_policy.advisory_match(
                policy(), body, routing_policy.Route(lane, profile, seat, NOW)
            )
            admitted = match is None
            assert admitted == (seat in ADR_ROUTE), f"{lane}/{seat}"


def test_the_admitted_set_is_a_whole_route_and_names_the_ruling_each_seat_comes_from() -> None:
    """Author, land, review — the three ruling 2 and ruling 4 require between them.

    The planner is deliberately not alone and the row's remedy says why. `retro` is deliberately
    absent: ruling 3 hands retros their own seat and that seat files and lands nothing, which is
    the half of this class ruling 3 withdrew along with its `docs/process-log.md` path.
    """
    authorship = next(rule for rule in policy().rules if rule.id == 3)
    assert authorship.required_seats == ADR_ROUTE
    assert set(ADR_ROUTE) <= set(dispatch().SEATS)
    assert "retro" not in authorship.required_seats
    assert "neither gates nor lands" in authorship.remedy
    assert "ruling 4 lands no change alone" in authorship.remedy


def test_class_3_is_unenforced_at_landing_because_a_landing_has_no_seat() -> None:
    """Stated, not silent: an ADR landing from an unappointed seat is uncaught, not cleared.

    `just land` is handed a lane and a diff. A row whose whole basis is which seat took the
    work has nothing to test there, and testing it on the lane instead is exactly the
    provenance rule the re-founding withdrew. The gap is named in the row's own remedy and in
    the policy's `coverage` sentence rather than left for a reader to discover.
    """
    authorship = next(rule for rule in policy().rules if rule.id == 3)
    assert authorship.required_seats == ADR_ROUTE
    assert authorship.landing_path_prefixes == ()
    assert landing("docs/adr/0072-a-later-record.md") is None
    assert landing("docs/process-log.md") is None
    assert "no landing prefixes" in authorship.remedy
    assert "checked at dispatch only" in policy().coverage


def test_the_departure_from_the_adrs_prescribed_landing_path_is_flagged_in_the_row() -> None:
    """CLAUDE.md: binding decisions are flagged explicitly, never silently overridden.

    ADR-0071's re-founding table prescribes `docs/adr/` as this row's landing path, and the
    row has none, because a `required_seats` row carrying landing prefixes is the shape
    `parse_policy` refuses. The two cannot both hold as written, so the conflict is stated on
    the row a reader consults rather than in a commit message (review round 2 claim 3); which
    of the ADR or the row gives way is the human's, and the flag is what makes the question
    reachable.
    """
    authorship = next(rule for rule in policy().rules if rule.id == 3)
    assert "ADR-0071's re-founding table prescribes `docs/adr/`" in authorship.remedy
    assert "is the human's" in authorship.remedy
    # The flag is about a real conflict, not a remembered one: the shape the ADR asks for is
    # still refused by the parser today.
    document = json.loads(POLICY.read_text(encoding="utf-8"))
    next(entry for entry in document["classes"] if entry["id"] == 3)["landing_path_prefixes"] = [
        "docs/adr/"
    ]
    with pytest.raises(routing_policy.PolicyError, match="enforceable only where a seat exists"):
        routing_policy.parse_policy(json.dumps(document))


def test_a_seat_bound_class_may_not_also_carry_landing_prefixes() -> None:
    """Fail closed on the shape that would quietly reinstate the lane bar.

    Such a row would clear at dispatch for the seat it appoints and then refuse that same
    route at landing, where no seat is knowable — the two rungs disagreeing about what the
    class means, which is the defect in a second costume.
    """
    base = json.loads(POLICY.read_text(encoding="utf-8"))
    document = json.loads(json.dumps(base))
    next(entry for entry in document["classes"] if entry["id"] == 3)["landing_path_prefixes"] = [
        "docs/adr/"
    ]
    with pytest.raises(routing_policy.PolicyError, match="enforceable only where a seat exists"):
        routing_policy.parse_policy(json.dumps(document))


def test_the_landing_rung_skips_a_seat_bound_row_by_rule_not_by_empty_list() -> None:
    """The guard is the rule, so a future row carrying both is skipped rather than enforced.

    Planted directly on a parsed policy rather than through `parse_policy`, which refuses the
    shape one test above: the point here is that `enforcing_match` would still not enforce it
    if it ever arrived by another door.
    """
    parsed = policy()
    authorship = next(rule for rule in parsed.rules if rule.id == 3)
    planted = parsed._replace(
        rules=tuple(
            rule._replace(landing_path_prefixes=("docs/adr/",)) if rule.id == 3 else rule
            for rule in parsed.rules
        )
    )
    assert authorship.required_seats
    # The plant is real: the same paths under a row without `required_seats` do refuse, so a
    # `None` above is the guard and not an empty prefix list quietly agreeing with it.
    control = parsed._replace(
        rules=tuple(
            rule._replace(landing_path_prefixes=("docs/adr/",), required_seats=())
            if rule.id == 3
            else rule
            for rule in parsed.rules
        )
    )
    assert routing_policy.enforcing_match(control, ("docs/adr/0072-x.md",), "zai") is not None
    assert routing_policy.enforcing_match(planted, ("docs/adr/0072-x.md",), "zai") is None


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


def test_binds_every_instance_does_not_reach_the_claude_lane_and_required_seats_does() -> None:
    """The fact two docstrings asserted wrongly, now pinned by behaviour (round 2 claim 2).

    A future row author wanting a class that binds Claude was told by the module docstring and
    by `Rule`'s that the field for it is `binds_every_instance`. It is not — `_refusing_rules`
    consults `refuses` and `required_seats` and nothing else — so they would have set a field
    that does nothing and shipped a silently Claude-exempt row. Asserted on the two fields in
    isolation, planted on a parsed policy, so neither can be inferred from the shipped rows.
    """
    parsed = policy()
    gate = "tools/mutation_smoke.py"

    def planted(**fields: object) -> Any:  # noqa: ANN401 — a NamedTuple `_replace` result
        return parsed._replace(
            rules=tuple(rule._replace(**fields) if rule.id == 6 else rule for rule in parsed.rules)
        )

    binding = planted(binds_every_instance=True, required_seats=())
    assert routing_policy.enforcing_match(binding, (gate,), "zai") is not None
    assert routing_policy.enforcing_match(binding, (gate,), "claude-native") is None

    # `required_seats` is what reaches the lane, and it does so on the seat-checked rung —
    # `enforcing_match` skips such a row by rule, because a landing has no seat.
    seat_bound = planted(binds_every_instance=False, required_seats=("planner",))
    body = "Change `tools/mutation_smoke.py`."
    for lane, profile in (("claude-native", "opus-low"), ("zai", "zai-glm52-max")):
        unadmitted = routing_policy.Route(lane, profile, "implementer", NOW)
        assert routing_policy.advisory_match(seat_bound, body, unadmitted) is not None, lane
        admitted = routing_policy.Route(lane, profile, "planner", NOW)
        assert routing_policy.advisory_match(seat_bound, body, admitted) is None, lane


def test_a_seat_bound_rows_evidence_names_the_seat_once() -> None:
    """Round 2 claim 11: a row matching on a seat *and* appointing one printed `seat=` twice.

    No shipped row carries both `seats` and `required_seats`, so this plants the shape rather
    than waiting for someone to write it — the de-duplication is by rule, not by absence.
    """
    parsed = policy()
    both = parsed._replace(
        rules=tuple(
            rule._replace(seats=("implementer",), required_seats=("planner",))
            if rule.id == 3
            else rule
            for rule in parsed.rules
        )
    )
    route_taken = routing_policy.Route("zai", "zai-glm52-max", "implementer", NOW)
    match = routing_policy.advisory_match(both, "ADR authorship for #999.", route_taken)
    assert match is not None
    assert match.evidence.count("seat=implementer") == 1
    assert "required_seats=planner" in match.evidence


def test_a_route_exception_cannot_except_the_class_that_binds_every_instance() -> None:
    """The guard's second door, which round 1 left unpinned (review round 1 claim 9).

    `_check_exception_classes` is shared, so the behaviour is right today and the issue
    exception above proves the helper. What was untested is that `_route_exceptions` still
    calls it — a future edit dropping that call would leave a route exception able to except
    an instance from the gate that judges it, with the issue-exception test still green.
    """
    base = json.loads(POLICY.read_text(encoding="utf-8"))
    with pytest.raises(routing_policy.PolicyError, match="conflict of interest"):
        routing_policy.parse_policy(
            json.dumps(
                dict(
                    base,
                    route_exceptions=[
                        {
                            "class": 6,
                            "lane": "codex",
                            "profile": "codex-luna-max",
                            "seat": "implementer",
                            "standing": True,
                        }
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


def just_check_tools() -> frozenset[str]:
    """Every `tools/*.py` the `just check` recipe actually reaches, derived from the justfile.

    Round 1's version asserted only that each named tool appeared *somewhere* in the
    justfile, which `tools/breaker.py` satisfies through its own `just breaker` recipe while
    no `check-*` recipe runs it — so the remedy's claim that all nine are reached by
    `just check` passed a test written to catch exactly that (review round 2 claim 4). This
    walks `check`'s dependency list and reads those recipes' bodies, so a tenth gate joining
    `just check` reds the assertions below instead of ageing quietly, and a gate leaving
    `just check` does too.
    """
    text = JUSTFILE.read_text(encoding="utf-8")
    recipe = re.compile(r"^([a-z0-9-]+):([^\n]*)\n((?:[ \t][^\n]*\n|\n)*)", re.MULTILINE)
    bodies = {match[1]: (match[2], match[3]) for match in recipe.finditer(text)}
    assert "check" in bodies, "the justfile no longer has a `check` recipe"
    reached = set()
    for name in bodies["check"][0].split():
        assert name in bodies, name
        reached.update(re.findall(r"tools/[a-z0-9_]+\.py", bodies[name][1]))
    return frozenset(reached)


def test_class_6s_own_remedy_names_the_gates_it_does_not_cover() -> None:
    """ADR-0071 calls the class aspirational; the remedy the refusal prints says so too.

    The enumeration exists so a reader can trust that the omissions are known, which makes an
    omission from the omission list worse here than elsewhere: round 1 named seven tools and
    `just check` runs two more (review round 1 claim 6).
    """
    conflict = next(rule for rule in policy().rules if rule.id == 6)
    assert "uncovered, never cleared" in conflict.remedy
    reached = just_check_tools()
    # The derivation is real rather than a set that happens to be empty.
    assert "tools/check_adr_form.py" in reached
    for path in reached:
        named = path in conflict.landing_path_prefixes
        assert named or path in conflict.remedy, path


def test_the_remedys_just_check_clause_is_true_of_every_tool_it_scopes() -> None:
    """The clause claims a scope, and the scope is checked rather than counted.

    Round 1's remedy said nine tools were "all nine reached by `just check`". Eight are;
    `tools/breaker.py` is reached by `just breaker` and folded into `just watch-report`, and
    ADR-0071's own row 6 made the same slip (review round 2 claim 4). The clause now scopes
    eight and names the ninth separately, so this asserts both halves against the justfile
    rather than against the sentence.
    """
    conflict = next(rule for rule in policy().rules if rule.id == 6)
    reached = just_check_tools()
    scoped, _, rest = conflict.remedy.partition("— the eight `just check` reaches —")
    assert rest, "the remedy no longer scopes its `just check` clause"
    omissions = set(re.findall(r"tools/[a-z0-9_]+\.py", scoped))
    assert omissions <= reached, sorted(omissions - reached)
    assert len(omissions) == 8
    assert "tools/breaker.py" not in reached
    assert "tools/breaker.py" in rest


def test_class_6_keeps_the_label_of_the_refusal_it_actually_issues() -> None:
    """Two rules on one row, and the reader is told which one refused them.

    The invariant — no instance authors the gate that judges it — binds every instance and no
    refusal enforces it. The refusal that fires is still the older keep-on-Claude bar, and it
    is lane-selected. Round 1 relabelled the row "Conflict of interest" while leaving that
    refusal unchanged, so a reader meeting `routing_class=6` would have read a
    conflict-of-interest verdict where a provenance one was issued (review round 1 claim 4).
    Kept rather than retired to `refuses: false`, because retiring it before step 7's
    exemption list exists would leave the gates with neither rule.
    """
    conflict = next(rule for rule in policy().rules if rule.id == 6)
    assert conflict.label == "The gates themselves"
    assert conflict.binds_every_instance is True
    assert conflict.refuses is True
    assert "no refusal enforces it" in conflict.remedy
    assert "still selected by lane" in conflict.remedy
    # The lane selection is the finding, so it is measured rather than read off the prose.
    assert landing("tools/land.py") is not None
    assert routing_policy.enforcing_match(policy(), ("tools/land.py",), "claude-native") is None


def test_class_4s_two_remedies_name_one_seat_rather_than_agreeing_by_accident() -> None:
    """The policy says `planner` and escalate; the condition says transfer to a fable seat.

    They agree only because `SEATS["planner"].escalation` and `SEATS["fable"].preference` are
    both `("fable-high",)`, and nothing asserted it — so reordering the planner's escalation
    list would have silently broken the agreement with both files still reading as if they
    matched (review round 1 claim 8).
    """
    remedy = next(rule for rule in policy().rules if rule.id == 4).remedy
    read = escalation.read_conditions(CONDITIONS)
    assert read.conditions is not None
    condition = next(
        entry
        for entry in read.conditions.conditions
        if entry.name == "plausible_wrong_fix_goes_green"
    )
    assert "`planner` seat" in remedy
    assert "fable" in condition.remedy
    assert dispatch().SEATS["planner"].escalation == dispatch().SEATS["fable"].preference


# --- unchanged behaviour the re-founding must not have broken -------------------------------


@pytest.mark.parametrize(
    ("class_id", "body", "seat"),
    [
        (2, "Routing-class: orchestration", "orchestrator"),
        (3, "Routing-class: adr-authorship", "recon"),
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


def test_the_seams_own_arrangement_refuses_the_same_way_against_this_branchs_policy() -> None:
    """The other half of `test_the_seam_passes_a_refusal_through_without_forking`.

    That test runs the real seam, so it reads the policy from the **main checkout** and can
    only ever exercise the landed copy (#364). This one puts the identical arrangement —
    `zai`, the `orchestrator` seat, #223's body — through `routing_refusal` rooted at `REPO`,
    which is this worktree, so between them both copies of the policy are covered by the
    suite rather than by a clone somebody has to remember to build. If a later edit moves
    class 2, this reds here first and the seam test follows it on landing, instead of the
    landing being the first thing to find out (review round 1 claim 1).
    """
    args = type("Args", (), {"lane": "zai", "profile": "zai-glm52-max", "seat": "orchestrator"})()
    found = dispatch().Readiness(None, body="Dispatch environments, end to end.")
    refusal = dispatch().routing_refusal(args, found, REPO, NOW)
    assert refusal is not None
    assert refusal.kind == "routing_policy_advisory"
    assert "routing_class=2:orchestration" in refusal.found
    assert "seat=orchestrator" in refusal.found


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
