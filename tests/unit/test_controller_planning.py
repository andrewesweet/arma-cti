"""Initiative Planning package, stage, and publication seams (#379)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import TYPE_CHECKING, cast

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

planning = load_tool("controller_planning")
controller = load_tool("controller")
policy = load_tool("controller_policy")
ports = load_tool("controller_ports")
store_module = load_tool("controller_store")


CONTEXT = """## Language

**Commander**: the decision-maker.
**Campaign**: the persistent playthrough.
"""


def repository(tmp_path: Path) -> Path:
    """Create the smallest checkout the planning validator reads."""
    root = tmp_path / "repo"
    (root / "tests" / "specs").mkdir(parents=True)
    (root / "CONTEXT.md").write_text(CONTEXT, encoding="utf-8")
    return root


def package() -> dict[str, object]:
    """Build one complete plan package with both obligation outcomes."""
    content = "Commander can see Campaign."
    return {
        "schema": planning.PLAN_SCHEMA,
        "schema_version": planning.PLAN_SCHEMA_VERSION,
        "initiative_key": "initiative-1",
        "desired_outcome": {
            "key": "outcome-1",
            "revision": 1,
            "content": content,
            "content_digest": hashlib.sha256(content.encode()).hexdigest(),
        },
        "product_specification": {
            "obligations": [
                {
                    "key": "O1",
                    "kind": "behavioural",
                    "statement": "Commander can see Campaign.",
                    "specification": {
                        "binding": "unit",
                        "feature": (
                            "Feature: visibility\n"
                            "  Scenario: visible\n"
                            "    Given a `Commander` exists\n"
                            "    Then the `Campaign` is visible\n"
                        ),
                        "runner": "python",
                        "step_library": "tests/steps.py",
                        "provisional_terms": [],
                    },
                },
                {
                    "key": "O2",
                    "kind": "non-behavioural",
                    "statement": "Campaign feel is reviewed by a person.",
                    "specification": None,
                },
            ]
        },
        "design_disposition": {
            "kind": "not_required",
            "reference": None,
            "reasons": ["Work Items share no cross-cutting design decision."],
        },
        "implementation_design": None,
        "work_items": [
            {
                "key": "W1",
                "title": "Expose Campaign visibility",
                "body": "Implement the visible Campaign behaviour.",
                "obligation_keys": ["O1"],
                "exclusive_resources": [],
            },
            {
                "key": "W2",
                "title": "Review Campaign feel",
                "body": "Review the non-behavioural product choice.",
                "obligation_keys": ["O2"],
                "exclusive_resources": [],
            },
        ],
        "dependencies": [
            {
                "blocked_key": "W2",
                "blocked_by": "W1",
                "reason": "data",
            }
        ],
        "obligation_coverage": [
            {"obligation_key": "O1", "work_item_keys": ["W1"]},
            {"obligation_key": "O2", "work_item_keys": ["W2"]},
        ],
        "obligation_summary": {"mechanised": 1, "held_to_review": 1},
    }


def test_valid_package_is_closed_and_counts_both_obligation_outcomes(tmp_path: Path) -> None:
    validated = planning.validate_plan_package(package(), repository_root=repository(tmp_path))

    assert validated.initiative_key == "initiative-1"
    assert validated.revision_id.startswith("initiative-1-r1-")
    assert validated.obligation_counts == {"mechanised": 1, "held_to_review": 1}
    assert validated.unratified_terms == ()
    assert validated.document["desired_outcome"] == package()["desired_outcome"]
    assert planning.work_item_marker(validated, "W1") == (
        "<!-- arma-cti:work-item=initiative-1:work-item:W1 -->"
    )
    assert planning.plan_revision_marker(validated).startswith(
        "<!-- arma-cti:plan-revision=initiative-1-r1-"
    )


def test_validation_digest_binds_exact_input_bytes(tmp_path: Path) -> None:
    raw = json.dumps(package(), indent=2, ensure_ascii=False).encode("utf-8")

    validated = planning.validate_plan_bytes(raw, repository_root=repository(tmp_path))

    assert validated.raw_bytes == raw
    assert validated.content_digest == hashlib.sha256(raw).hexdigest()


def test_validation_rejects_raw_bytes_for_a_different_mapping(tmp_path: Path) -> None:
    candidate = package()
    raw_candidate = package()
    raw_work_items = cast("list[dict[str, object]]", raw_candidate["work_items"])
    raw_work_items[0]["title"] = "Different package"
    raw = json.dumps(raw_candidate, separators=(",", ":")).encode("utf-8")

    with pytest.raises(planning.PlanValidationError, match="package_bytes_mismatch"):
        planning.validate_plan_package(
            candidate, repository_root=repository(tmp_path), raw_bytes=raw
        )


def test_validation_checks_raw_json_types_before_mapping_equality(tmp_path: Path) -> None:
    candidate = package()
    raw_candidate = package()
    raw_outcome = cast("dict[str, object]", raw_candidate["desired_outcome"])
    raw_outcome["revision"] = 1.0
    raw = json.dumps(raw_candidate, separators=(",", ":")).encode("utf-8")

    with pytest.raises(planning.PlanValidationError, match="invalid_positive_integer"):
        planning.validate_plan_package(
            candidate, repository_root=repository(tmp_path), raw_bytes=raw
        )


@pytest.mark.parametrize(
    ("name", "change", "code"),
    [
        (
            "unknown schema",
            lambda value: value.update(schema="initiative-plan/v999"),
            "unknown_schema",
        ),
        (
            "unexpected field",
            lambda value: value["work_items"][0].update(extra=True),
            "unexpected_field",
        ),
        (
            "duplicate obligation",
            lambda value: value["product_specification"]["obligations"].append(
                value["product_specification"]["obligations"][0]
            ),
            "duplicate_obligation_key",
        ),
        (
            "dangling reference",
            lambda value: value["dependencies"].append(
                {"blocked_key": "W2", "blocked_by": "missing", "reason": "data"}
            ),
            "dangling_dependency",
        ),
        (
            "dependency cycle",
            lambda value: value["dependencies"].append(
                {"blocked_key": "W1", "blocked_by": "W2", "reason": "data"}
            ),
            "dependency_cycle",
        ),
        ("missing disposition", lambda value: value.pop("design_disposition"), "missing_field"),
        (
            "uncovered obligation",
            lambda value: value["obligation_coverage"].pop(),
            "uncovered_obligation",
        ),
    ],
)
def test_unexpected_plan_shapes_refuse_before_publication(
    tmp_path: Path,
    name: str,
    change: Callable[[dict[str, object]], None],
    code: str,
) -> None:
    candidate = package()
    change(candidate)

    with pytest.raises(planning.PlanValidationError) as error:
        planning.validate_plan_package(candidate, repository_root=repository(tmp_path))

    assert error.value.code == code, name


def test_submission_stores_exact_validated_package_without_tracker_mutation(tmp_path: Path) -> None:
    root = repository(tmp_path)
    raw = json.dumps(package(), separators=(",", ":")).encode("utf-8")
    tracker = planning.RecordingTracker()
    submission = planning.PlanningSubmission(
        planning.ValidatedPlanStore(tmp_path / "controller"),
        tracker,
        repository_root=root,
    )

    stored = submission.submit(raw)

    assert stored.raw_bytes == raw
    assert stored.package_path.read_bytes() == raw
    assert stored.digest_path.read_text(encoding="utf-8").strip() == stored.content_digest
    assert tracker.calls == []


def test_provisional_spec_is_validated_but_exposes_unratified_debt(tmp_path: Path) -> None:
    candidate = package()
    specification = cast("dict[str, object]", candidate["product_specification"])
    obligations = cast("list[dict[str, object]]", specification["obligations"])
    spec = cast("dict[str, object]", obligations[0]["specification"])
    spec["provisional_terms"] = [{"term": "New Term", "definition": "a temporary planning term"}]
    feature = spec["feature"]
    assert isinstance(feature, str)
    spec["feature"] = feature.replace("`Campaign`", "`New Term`")

    validated = planning.validate_plan_package(candidate, repository_root=repository(tmp_path))

    assert validated.unratified_terms == ("New Term",)


def test_ratified_provisional_term_no_longer_blocks_publication(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "CONTEXT.md").write_text(
        CONTEXT + "\n**New Term**: a ratified domain term.\n", encoding="utf-8"
    )
    candidate = package()
    specification = cast("dict[str, object]", candidate["product_specification"])
    obligations = cast("list[dict[str, object]]", specification["obligations"])
    spec = cast("dict[str, object]", obligations[0]["specification"])
    spec["provisional_terms"] = [{"term": "New Term", "definition": "a temporary domain term"}]
    feature = spec["feature"]
    assert isinstance(feature, str)
    spec["feature"] = feature.replace("`Campaign`", "`New Term`")

    validated = planning.validate_plan_package(candidate, repository_root=root)

    assert validated.unratified_terms == ()
    assert planning.publication_actions(validated, "377")


def test_non_behavioural_obligation_is_held_to_review_not_failure(tmp_path: Path) -> None:
    validated = planning.validate_plan_package(package(), repository_root=repository(tmp_path))

    assert validated.held_to_review == ("O2",)
    assert validated.behavioural == ("O1",)


def test_zero_obligation_category_still_requires_a_numeric_summary_count(tmp_path: Path) -> None:
    candidate = package()
    specification = cast("dict[str, object]", candidate["product_specification"])
    obligations = cast("list[dict[str, object]]", specification["obligations"])
    obligations.pop(0)
    work_items = cast("list[dict[str, object]]", candidate["work_items"])
    work_items.pop(0)
    candidate["dependencies"] = []
    coverage = cast("list[dict[str, object]]", candidate["obligation_coverage"])
    coverage.pop(0)
    summary = cast("dict[str, object]", candidate["obligation_summary"])
    summary["mechanised"] = "zero"

    with pytest.raises(planning.PlanValidationError, match="invalid_nonnegative_integer"):
        planning.validate_plan_package(candidate, repository_root=repository(tmp_path))


def test_zero_obligation_category_is_valid_when_its_count_is_zero(tmp_path: Path) -> None:
    candidate = package()
    specification = cast("dict[str, object]", candidate["product_specification"])
    obligations = cast("list[dict[str, object]]", specification["obligations"])
    obligations.pop(0)
    work_items = cast("list[dict[str, object]]", candidate["work_items"])
    work_items.pop(0)
    candidate["dependencies"] = []
    coverage = cast("list[dict[str, object]]", candidate["obligation_coverage"])
    coverage.pop(0)
    summary = cast("dict[str, object]", candidate["obligation_summary"])
    summary["mechanised"] = 0

    validated = planning.validate_plan_package(candidate, repository_root=repository(tmp_path))

    assert validated.obligation_counts == {"mechanised": 0, "held_to_review": 1}


def test_plan_store_rejects_same_revision_bound_to_different_bytes(tmp_path: Path) -> None:
    root = repository(tmp_path)
    store = planning.ValidatedPlanStore(tmp_path / "controller")
    first = planning.validate_plan_package(package(), repository_root=root)
    store.store(first)
    raw = first.raw_bytes + b"\n"
    second = replace(first, raw_bytes=raw, content_digest=hashlib.sha256(raw).hexdigest())

    with pytest.raises(planning.PlanStorageError, match="plan_revision_conflict"):
        store.store(second)


def test_plan_store_rejects_a_digest_file_that_does_not_match_the_package(tmp_path: Path) -> None:
    root = repository(tmp_path)
    store = planning.ValidatedPlanStore(tmp_path / "controller")
    first = planning.validate_plan_package(package(), repository_root=root)
    stored = store.store(first)
    stored.digest_path.write_text("0" * 64 + "\n", encoding="utf-8")

    with pytest.raises(planning.PlanStorageError, match="plan_revision_conflict"):
        store.store(first)


def test_plan_store_rejects_package_bytes_changed_under_the_same_digest(tmp_path: Path) -> None:
    root = repository(tmp_path)
    store = planning.ValidatedPlanStore(tmp_path / "controller")
    first = planning.validate_plan_package(package(), repository_root=root)
    stored = store.store(first)
    stored.package_path.write_bytes(stored.raw_bytes + b"\n")

    with pytest.raises(planning.PlanStorageError, match="plan_revision_conflict"):
        store.store(first)


def test_plan_store_rejects_a_package_under_the_wrong_revision_id(tmp_path: Path) -> None:
    root = repository(tmp_path)
    store = planning.ValidatedPlanStore(tmp_path / "controller")
    first = planning.validate_plan_package(package(), repository_root=root)
    revision_directory = store.root / "validated-plans" / "wrong-revision"
    package_path = revision_directory / "package.json"
    digest_path = revision_directory / "content.sha256"
    package_path.parent.mkdir(parents=True)
    package_path.write_bytes(first.raw_bytes)
    digest_path.write_text(first.content_digest + "\n", encoding="utf-8")

    with pytest.raises(planning.PlanStorageError, match="plan_revision_mismatch"):
        store.load("wrong-revision")


def test_publication_uses_the_validated_bytes_after_mapping_mutation(tmp_path: Path) -> None:
    validated = planning.validate_plan_package(package(), repository_root=repository(tmp_path))
    document = validated.document
    work_items = document["work_items"]
    assert isinstance(work_items, list)
    work_items[0]["title"] = "Mutated after validation"

    actions = planning.publication_actions(validated, "377")

    work_item_action = actions[1]
    payload = dict(work_item_action.payload)
    assert payload["title"] == "Expose Campaign visibility"


def test_product_question_has_no_publication_action() -> None:
    question = planning.StageVerdict(
        status=planning.PRODUCT_QUESTION,
        input_revision="outcome-1@1",
        plan=None,
        question={
            "question": "Which Campaign value matters?",
            "choices": ["speed", "safety"],
        },
        reason="product intent is ambiguous",
    )

    assert question.publication_allowed is False
    assert question.question == {
        "question": "Which Campaign value matters?",
        "choices": ["speed", "safety"],
    }


def test_resource_collision_requires_a_resource_dependency() -> None:
    candidate = package()
    work_items = candidate["work_items"]
    assert isinstance(work_items, list)
    for item in work_items:
        assert isinstance(item, dict)
        item = cast("dict[str, object]", item)
        item["exclusive_resources"] = ["shared-file"]
    candidate["dependencies"] = []

    with pytest.raises(planning.PlanValidationError, match="missing_resource_dependency"):
        planning.validate_plan_package(candidate)


def test_resource_dependency_may_be_declared_in_either_direction(tmp_path: Path) -> None:
    candidate = package()
    work_items = candidate["work_items"]
    assert isinstance(work_items, list)
    for item in work_items:
        assert isinstance(item, dict)
        item = cast("dict[str, object]", item)
        item["exclusive_resources"] = ["shared-file"]
    candidate["dependencies"] = [{"blocked_key": "W2", "blocked_by": "W1", "reason": "resource"}]

    validated = planning.validate_plan_package(candidate, repository_root=repository(tmp_path))

    assert validated.revision_id.startswith("initiative-1-r1-")


def test_publisher_replays_every_action_boundary_without_duplicate_artifacts(
    tmp_path: Path,
) -> None:
    validated = planning.validate_plan_package(package(), repository_root=repository(tmp_path))
    actions = planning.publication_actions(validated, "377")

    for boundary in range(1, len(actions) + 1):
        tracker = planning.RecordingTracker(fail_after=boundary)
        publisher = planning.PlanPublisher(tracker)
        with pytest.raises(planning.TrackerError, match="injected_failure"):
            publish_all(publisher, actions)
        assert tracker.mutation_count == boundary
        tracker.fail_after = None

        for action in actions:
            publisher.apply(action)

        assert len(tracker.parent_markers) == 1
        assert set(tracker.issues) == {
            planning.work_item_intent(validated, "W1"),
            planning.work_item_intent(validated, "W2"),
        }
        assert {ref.identifier for ref in tracker.issues.values()} == {"1000", "1001"}
        assert len(tracker.sub_issues) == 2
        assert len(tracker.dependencies) == 1
        mutations = tracker.mutation_count
        for action in actions:
            publisher.apply(action)
        assert tracker.mutation_count == mutations


def test_recording_tracker_fails_at_the_configured_mutation_boundary() -> None:
    tracker = planning.RecordingTracker(fail_after=1)

    with pytest.raises(planning.TrackerError, match="injected_failure"):
        tracker.create_work_item("initiative-1:work-item:W1", "title", "body")


def test_dependency_publication_refuses_when_only_one_issue_is_missing() -> None:
    tracker = planning.RecordingTracker()
    tracker.issues["initiative-1:work-item:W1"] = planning.TrackerRef("1001", 1001, 1001)
    action = planning.ControlAction(
        "tracker.add_dependency",
        "initiative-1:dependency:W2:W1",
        (
            ("blocked_intent", "initiative-1:work-item:W2"),
            ("blocker_intent", "initiative-1:work-item:W1"),
            ("marker", "dependency-marker"),
        ),
    )

    with pytest.raises(planning.TrackerError, match="publication_dependency_missing"):
        planning.PlanPublisher(tracker).apply(action)


def test_stage_verdict_rejects_a_plan_for_another_frozen_input() -> None:
    request = planning.StageRequest(
        planning.INITIATIVE_PLANNING,
        "outcome-1@1",
        planning.DesiredOutcomeSnapshot("outcome-1", 1, "content", "digest"),
        "repository snapshot",
    )
    verdict = {
        "schema": planning.STAGE_VERDICT_SCHEMA,
        "schema_version": planning.STAGE_VERDICT_VERSION,
        "stage": planning.INITIATIVE_PLANNING,
        "status": planning.INCONCLUSIVE,
        "input_revision": "outcome-1@2",
        "plan": None,
        "question": None,
        "reason": "stage could not decide",
    }

    with pytest.raises(planning.StageValidationError, match="input_revision_mismatch"):
        planning.validate_stage_verdict(verdict, request)


def publish_all(publisher: planning.PlanPublisher, actions: tuple[object, ...]) -> None:
    """Apply every action through one publisher call for failure-boundary tests."""
    for action in actions:
        publisher.apply(cast("planning.ControlAction", action))


def planning_facts() -> policy.ControlFacts:
    """Build one exact Product Curator fact for controller integration tests."""
    content = cast("dict[str, object]", package()["desired_outcome"])
    return policy.ControlFacts(
        configured_curator="curator-1",
        desired_outcomes=(
            policy.DesiredOutcomeFact(
                cast("str", content["key"]),
                cast("int", content["revision"]),
                cast("str", content["content_digest"]),
                cast("str", content["content"]),
                377,
            ),
        ),
        initiatives=(),
        work_items=(),
        work_runs=(),
    )


def valid_verdict() -> dict[str, object]:
    """Return one stage envelope carrying the package above."""
    return {
        "schema": planning.STAGE_VERDICT_SCHEMA,
        "schema_version": planning.STAGE_VERDICT_VERSION,
        "stage": planning.INITIATIVE_PLANNING,
        "status": planning.VALID,
        "input_revision": "outcome-1@1",
        "plan": package(),
        "question": None,
        "reason": "plan validated by stage",
    }


def controller_instance(
    root: Path,
    *,
    gateway: planning.RecordingStageGateway,
    tracker: planning.RecordingTracker,
) -> controller.Controller:
    """Assemble controller with real publisher adapter and deterministic test seams."""
    repository_root = root / "repository"
    (repository_root / "tests" / "specs").mkdir(parents=True)
    (repository_root / "CONTEXT.md").write_text(CONTEXT, encoding="utf-8")
    collector = ports.FakeFactCollector(planning_facts())
    mutation_ports = ports.ActionPorts(
        planning.PlanPublisher(tracker),
        ports.RecordingActionPort(),
        ports.RecordingActionPort(),
        ports.RecordingActionPort(),
    )
    return controller.Controller(
        fact_collector=collector,
        clock=ports.FakeClock("2026-08-27T12:00:00+00:00"),
        identity=ports.FakeIdentity("test-controller"),
        store=store_module.ControllerStore(root / "controller"),
        action_ports=mutation_ports,
        stage_gateway=gateway,
        repository_context=planning.StaticRepositoryContext("frozen repository context"),
        repository_root=repository_root,
    )


def test_controller_stores_then_publishes_one_operative_plan_without_approval(
    tmp_path: Path,
) -> None:
    gateway = planning.RecordingStageGateway(valid_verdict())
    tracker = planning.RecordingTracker()
    instance = controller_instance(tmp_path, gateway=gateway, tracker=tracker)

    first = instance.run_cycle(dry_run=False)
    second = instance.run_cycle(dry_run=False)

    assert first.lifecycle.state == "operative"
    assert first.planning_status == planning.VALID
    assert first.plan_revision is not None
    assert first.product_question is None
    assert first.to_document()["planning"] == {
        "status": planning.VALID,
        "plan_revision": first.plan_revision,
    }
    assert second.actions == ()
    assert len(gateway.requests) == 1
    assert gateway.requests[0].desired_outcome.content == "Commander can see Campaign."
    assert gateway.requests[0].repository_context == "frozen repository context"
    assert len(tracker.parent_markers) == 1
    assert len(tracker.issues) == 2
    assert len(tracker.sub_issues) == 2
    assert len(tracker.dependencies) == 1
    assert (
        len(list((tmp_path / "controller" / "plans" / "validated-plans").glob("*/package.json")))
        == 1
    )


@pytest.mark.parametrize("boundary", range(1, 7))
def test_interrupted_publication_resumes_from_stable_markers_without_rerunning_stage(
    tmp_path: Path,
    boundary: int,
) -> None:
    gateway = planning.RecordingStageGateway(valid_verdict())
    tracker = planning.RecordingTracker(fail_after=boundary)
    instance = controller_instance(tmp_path, gateway=gateway, tracker=tracker)

    with pytest.raises(planning.TrackerError, match="injected_failure"):
        instance.run_cycle(dry_run=False)

    tracker.fail_after = None
    resumed = instance.run_cycle(dry_run=False)

    assert resumed.state_source == "resumed"
    assert len(gateway.requests) == 1
    assert len(tracker.parent_markers) == 1
    assert len(tracker.issues) == 2
    assert len(tracker.sub_issues) == 2
    assert len(tracker.dependencies) == 1
    rows = [
        json.loads(line)
        for line in instance.store.journal_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["phase"] for row in rows] == ["planned", "applied", "confirmed"]


@pytest.mark.parametrize(
    "status",
    [planning.INVALID, planning.INCONCLUSIVE, planning.INFRA_UNAVAILABLE],
)
def test_non_publishable_planning_status_creates_no_plan_or_tracker_mutation(
    tmp_path: Path,
    status: str,
) -> None:
    verdict = valid_verdict()
    verdict["status"] = status
    verdict["plan"] = None
    verdict["reason"] = f"{status} result"
    gateway = planning.RecordingStageGateway(verdict)
    tracker = planning.RecordingTracker()
    instance = controller_instance(tmp_path, gateway=gateway, tracker=tracker)

    report = instance.run_cycle(dry_run=False)

    assert report.planning_status == status
    assert report.actions == ()
    assert tracker.calls == []
    assert not (tmp_path / "controller" / "plans" / "validated-plans").exists()


def test_product_question_pauses_only_initiative_and_exposes_exact_choices(tmp_path: Path) -> None:
    verdict = valid_verdict()
    verdict.update(
        status=planning.PRODUCT_QUESTION,
        plan=None,
        question={"question": "Which Campaign value matters?", "choices": ["speed", "safety"]},
        reason="product intent is ambiguous",
    )
    gateway = planning.RecordingStageGateway(verdict)
    tracker = planning.RecordingTracker()
    instance = controller_instance(tmp_path, gateway=gateway, tracker=tracker)

    report = instance.run_cycle(dry_run=False)

    assert report.lifecycle.state == "needs_product_input"
    assert report.product_question == {
        "question": "Which Campaign value matters?",
        "choices": ["speed", "safety"],
    }
    assert report.actions == ()
    assert tracker.calls == []


def test_unratified_plan_is_stored_but_cannot_publish_work_items(tmp_path: Path) -> None:
    candidate = package()
    specification = cast("dict[str, object]", candidate["product_specification"])
    obligations = cast("list[dict[str, object]]", specification["obligations"])
    spec = cast("dict[str, object]", obligations[0]["specification"])
    spec["provisional_terms"] = [{"term": "New Term", "definition": "a temporary planning term"}]
    feature_source = cast("str", spec["feature"])
    spec["feature"] = feature_source.replace("`Campaign`", "`New Term`")
    gateway = planning.RecordingStageGateway({**valid_verdict(), "plan": candidate})
    tracker = planning.RecordingTracker()
    instance = controller_instance(tmp_path, gateway=gateway, tracker=tracker)

    report = instance.run_cycle(dry_run=False)

    assert report.planning_status == planning.INVALID
    assert report.actions == ()
    assert tracker.calls == []
    assert list((tmp_path / "controller" / "plans" / "validated-plans").glob("*/package.json"))


def test_absent_stage_verdict_is_a_typed_non_publishable_result(tmp_path: Path) -> None:
    gateway = planning.RecordingStageGateway(None)
    tracker = planning.RecordingTracker()
    instance = controller_instance(tmp_path, gateway=gateway, tracker=tracker)

    report = instance.run_cycle(dry_run=False)

    assert report.planning_status == planning.INVALID
    assert report.actions == ()
    assert tracker.calls == []
    assert not (tmp_path / "controller" / "plans" / "validated-plans").exists()
