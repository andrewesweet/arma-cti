"""Lint and execute one key-addressed behavioural obligation (#592).

Each obligation lives at ``tests/specs/<key>.json``. The key is the only identity: a behavioural
record's companion ``<key>.feature`` is parsed with Cucumber's official Gherkin parser/compiler,
while a ``non-behavioural`` record has no feature and is reported as ``held_to_review``.

The JSON envelope carries the Python runner name, binding level, shared step-library path, and
any provisional terms. A provisional declaration is accepted by lint, but ``check`` refuses it
until the term is present in the runtime-read CONTEXT.md glossary. Step text is the only prose
linted, and only text inside backticks is a domain-term claim; Gherkin feature/scenario prose and
Examples' angle-bracket parameters remain ordinary Gherkin data.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple, NoReturn, cast

from gherkin import Compiler, Parser
from gherkin.errors import CompositeParserException

# ``tools/`` contains standalone scripts, so sibling imports use this script's directory.
sys.path.insert(0, str(Path(__file__).parent))

import gate

if TYPE_CHECKING:
    from collections.abc import Sequence

REPO: Final = Path(__file__).resolve().parents[1]
SPEC_DIR: Final = Path("tests/specs")
BEHAVIOURAL: Final = "behavioural"
NON_BEHAVIOURAL: Final = "non-behavioural"
PYTHON_RUNNER: Final = "python"
PASSED: Final = "passed"
FAILURE: Final = "failure"
NON_RESULT: Final = "non_result"
HELD_TO_REVIEW: Final = "held_to_review"
UNKNOWN_TERM: Final = "unknown_term"
MARKED_TERM: Final = re.compile(r"`([^`\r\n]+)`")
OBLIGATION_KEY: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
RECORD_FIELDS: Final = frozenset(
    {"binding", "feature", "kind", "provisional_terms", "runner", "step_library"}
)


class SpecificationError(RuntimeError):
    """A specification record or its execution input could not be read."""

    def __init__(self, code: str, detail: str) -> None:
        """Keep a machine-readable refusal code beside its human remedy."""
        super().__init__(detail)
        self.code = code
        self.detail = detail


class Finding(NamedTuple):
    """One authoring-time or repository-scan finding."""

    code: str
    detail: str
    line: int | None = None


class ProvisionalTerm(NamedTuple):
    """A term the specification declares temporarily, with its required definition."""

    term: str
    definition: str


class Step(NamedTuple):
    """One step returned by the standard Gherkin AST."""

    text: str
    line: int


class Obligation(NamedTuple):
    """One key-addressed obligation envelope."""

    key: str
    record: Path
    kind: str
    runner: str
    binding: str
    feature: Path
    step_library: str
    provisional: tuple[ProvisionalTerm, ...]


class LintReport(NamedTuple):
    """The complete static read of one obligation."""

    obligation: Obligation | None
    document: dict[str, object] | None
    steps: tuple[Step, ...]
    errors: tuple[Finding, ...]
    provisional: tuple[ProvisionalTerm, ...]
    unratified: tuple[str, ...]


class RepositoryLint(NamedTuple):
    """All per-obligation reports plus repository-level findings."""

    reports: tuple[LintReport, ...]
    errors: tuple[Finding, ...]


class CheckReport(NamedTuple):
    """Rendered static-gate output and its process exit."""

    lines: tuple[str, ...]
    exit_code: int
    lint: RepositoryLint


class RunResult(NamedTuple):
    """A typed execution result; absence never becomes ``passed``."""

    obligation_key: str
    result: str
    scenarios: int
    detail: str | None


@dataclass
class ExecutionContext:
    """Mutable state shared by the steps in one scenario."""

    values: dict[str, object]

    def __init__(self) -> None:
        """Start each scenario with isolated mutable state."""
        self.values = {}


def _finding(code: str, detail: str, line: int | None = None) -> Finding:
    """Build a finding while keeping line information out of its human remedy."""
    return Finding(code, detail, line)


def _raise_specification(code: str, detail: str, cause: BaseException | None = None) -> NoReturn:
    """Raise a typed specification refusal, optionally preserving its cause."""
    error = SpecificationError(code, detail)
    if cause is None:
        raise error
    raise error from cause


def _key_path(root: Path, key: str, suffix: str) -> Path:
    """Resolve one key without allowing a command argument to escape the spec directory."""
    if OBLIGATION_KEY.fullmatch(key) is None:
        _raise_specification("invalid_obligation_key", f"obligation={key!r} is not a stable key")
    return root / SPEC_DIR / f"{key}{suffix}"


def _text_field(document: Mapping[str, object], name: str, default: str = "") -> str:
    """Read a string field or refuse the record rather than coercing absent data."""
    value = document.get(name, default)
    if not isinstance(value, str):
        _raise_specification("record_invalid", f"field={name} must be a string")
    return value


def _provisional_terms(document: Mapping[str, object]) -> tuple[ProvisionalTerm, ...]:
    """Read provisional declarations and require a non-empty definition for each."""
    raw = document.get("provisional_terms", [])
    if not isinstance(raw, list):
        _raise_specification("record_invalid", "field=provisional_terms must be a list")
    terms: list[ProvisionalTerm] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            _raise_specification(
                "provisional_invalid",
                f"provisional_terms[{index}] must contain a term and definition",
            )
        term = _text_field(item, "term").strip()
        definition = _text_field(item, "definition").strip()
        if not term or not definition:
            _raise_specification(
                "provisional_invalid",
                (
                    f"provisional term {term or '<empty>'!r} needs a non-empty definition; "
                    "add its definition before declaring it provisional"
                ),
            )
        terms.append(ProvisionalTerm(term, definition))
    seen: set[str] = set()
    duplicates: list[str] = []
    for term in terms:
        if term.term in seen:
            duplicates.append(term.term)
        seen.add(term.term)
    if duplicates:
        _raise_specification(
            "provisional_invalid",
            f"duplicate provisional term={duplicates[0]!r}; declare it once",
        )
    return tuple(terms)


def _read_record(root: Path, key: str) -> tuple[Path, dict[str, object]]:
    """Read and structurally validate one key-addressed JSON record."""
    record = _key_path(root, key, ".json")
    try:
        source = record.read_text(encoding="utf-8")
        raw = json.loads(source)
    except FileNotFoundError as error:
        _raise_specification(
            "obligation_missing",
            f"obligation={key!r} has no record at {record}; add the obligation record",
            error,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _raise_specification(
            "record_unreadable",
            f"obligation={key!r} record={record} could not be read: {error}",
            error,
        )
    if not isinstance(raw, dict):
        _raise_specification("record_invalid", f"obligation={key!r} record must be an object")
    unknown = sorted(set(raw) - RECORD_FIELDS)
    if unknown:
        _raise_specification(
            "record_invalid",
            f"obligation={key!r} unknown field={unknown[0]!r}; remove it from the record",
        )
    return record, raw


def _obligation_from_document(
    root: Path,
    key: str,
    record: Path,
    raw: Mapping[str, object],
) -> Obligation:
    """Build one obligation from a validated record document."""
    kind = _text_field(raw, "kind").strip()
    if kind == "non_behavioral":
        kind = NON_BEHAVIOURAL
    if kind not in {BEHAVIOURAL, NON_BEHAVIOURAL}:
        _raise_specification(
            "record_invalid",
            f"obligation={key!r} kind={kind!r} must be behavioural or non-behavioural",
        )
    provisional = _provisional_terms(raw)
    if kind == NON_BEHAVIOURAL:
        return Obligation(
            key, record, kind, "", "", _key_path(root, key, ".feature"), "", provisional
        )
    runner = _text_field(raw, "runner").strip()
    binding = _text_field(raw, "binding").strip()
    if not runner:
        _raise_specification(
            "record_invalid",
            f"obligation={key!r} runner must be declared; set runner='python'",
        )
    if not binding:
        _raise_specification(
            "record_invalid",
            f"obligation={key!r} binding must be declared; set its execution level",
        )
    step_library = _text_field(raw, "step_library").strip()
    feature_name = _text_field(raw, "feature", f"{key}.feature").strip()
    expected_feature = f"{key}.feature"
    if feature_name != expected_feature:
        _raise_specification(
            "obligation_identity_mismatch",
            (
                f"obligation={key!r} feature={feature_name!r} does not match its key; "
                f"use {expected_feature!r}"
            ),
        )
    return Obligation(
        key,
        record,
        kind,
        runner,
        binding,
        record.with_name(feature_name),
        step_library,
        provisional,
    )


def read_obligation(root: Path, key: str) -> Obligation:
    """Read one obligation envelope addressed only by its stable key."""
    record, raw = _read_record(root, key)
    return _obligation_from_document(root, key, record, raw)


def _step_nodes(node: object) -> tuple[Step, ...]:
    """Traverse the parser's AST and read only actual Gherkin step nodes."""
    found: list[Step] = []
    if isinstance(node, dict):
        if "keywordType" in node and "text" in node and isinstance(node["text"], str):
            location = cast("Mapping[str, object]", node["location"])
            found.append(Step(node["text"], int(location["line"])))
            return tuple(found)
        for value in node.values():
            found.extend(_step_nodes(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_step_nodes(value))
    return tuple(found)


def _has_scenario(node: object) -> bool:
    """Whether the standard AST contains at least one executable Scenario node."""
    if isinstance(node, dict):
        if "scenario" in node:
            return True
        return any(_has_scenario(value) for value in node.values())
    if isinstance(node, list):
        return any(_has_scenario(value) for value in node)
    return False


def _parse_feature_source(
    path: Path, source: str
) -> tuple[dict[str, object] | None, tuple[Finding, ...]]:
    """Parse one feature source with the standard parser and keep errors typed."""
    try:
        parsed = Parser().parse(source)
    except CompositeParserException as error:
        return None, (
            _finding("gherkin_parse_error", f"feature={path} is not valid Gherkin: {error}"),
        )
    feature = parsed.get("feature")
    if not isinstance(feature, dict):
        return None, (_finding("gherkin_parse_error", f"feature={path} has no Feature node"),)
    document = cast("dict[str, object]", parsed)
    if not _has_scenario(feature):
        return document, (_finding("no_scenarios", f"feature={path} has no executable Scenario"),)
    return document, ()


def _parse_feature(path: Path) -> tuple[dict[str, object] | None, tuple[Finding, ...]]:
    """Read and parse one repository feature with the standard parser."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return None, (
            _finding("specification_unreadable", f"feature={path} could not be read: {error}"),
        )
    return _parse_feature_source(path, source)


def _marked_term_findings(
    steps: tuple[Step, ...],
    language: gate.Language,
    provisional_names: set[str],
) -> tuple[Finding, ...]:
    """Check only backtick-marked claims and return their authoring remedies."""
    findings: list[Finding] = []
    avoided = dict(language.avoids)
    for step in steps:
        for match in MARKED_TERM.finditer(step.text):
            term = match.group(1).strip()
            if term in avoided:
                findings.append(
                    _finding(
                        "avoided_term",
                        (
                            f"marked term {term!r} is on CONTEXT.md's _Avoid_ list; "
                            f"Use the ratified term {avoided[term]!r} instead"
                        ),
                        step.line,
                    )
                )
            elif term not in language.terms and term not in provisional_names:
                findings.append(
                    _finding(
                        UNKNOWN_TERM,
                        (
                            f"marked term {term!r} does not resolve in CONTEXT.md; "
                            "add it to the Language section, declare it provisional with a "
                            "definition, or remove the backticks"
                        ),
                        step.line,
                    )
                )
    return tuple(findings)


def _lint_obligation(
    root: Path,
    obligation: Obligation,
    *,
    feature_source: str | None = None,
) -> LintReport:
    """Lint one already-read obligation against the live glossary."""
    errors: list[Finding] = []
    if obligation.kind != NON_BEHAVIOURAL and obligation.runner != PYTHON_RUNNER:
        errors.append(
            _finding(
                "runner_unsupported",
                (
                    f"obligation={obligation.key!r} runner={obligation.runner!r} is unsupported; "
                    "use runner='python'"
                ),
            )
        )
    language = gate.read_language(root)
    if language is None:
        if obligation.kind == NON_BEHAVIOURAL and not obligation.provisional:
            return LintReport(obligation, None, (), tuple(errors), obligation.provisional, ())
        errors.append(
            _finding(
                "context_unreadable",
                "CONTEXT.md could not be read; restore the Language section before linting",
            )
        )
        return LintReport(obligation, None, (), tuple(errors), obligation.provisional, ())
    provisional_names = {term.term for term in obligation.provisional}
    unratified = tuple(sorted(term for term in provisional_names if term not in language.terms))
    if obligation.kind == NON_BEHAVIOURAL:
        return LintReport(obligation, None, (), tuple(errors), obligation.provisional, unratified)
    if feature_source is None:
        document, parse_errors = _parse_feature(obligation.feature)
    else:
        document, parse_errors = _parse_feature_source(obligation.feature, feature_source)
    errors.extend(parse_errors)
    if document is None:
        return LintReport(obligation, None, (), tuple(errors), obligation.provisional, unratified)
    steps = _step_nodes(document)
    errors.extend(_marked_term_findings(steps, language, provisional_names))
    return LintReport(
        obligation,
        document,
        steps,
        tuple(errors),
        obligation.provisional,
        tuple(sorted(unratified)),
    )


def lint_obligation(root: Path, key: str) -> LintReport:
    """Lint one obligation, reading the current glossary at invocation time."""
    try:
        obligation = read_obligation(root, key)
    except SpecificationError as error:
        return LintReport(None, None, (), (_finding(error.code, error.detail),), (), ())
    return _lint_obligation(root, obligation)


def lint_embedded_obligation(
    root: Path,
    key: str,
    record: Mapping[str, object],
    feature_source: str | None,
) -> LintReport:
    """Lint an embedded plan obligation through this runner's normal lint path."""
    virtual_record = root / SPEC_DIR / f"{key}.json"
    try:
        obligation = _obligation_from_document(root, key, virtual_record, record)
    except SpecificationError as error:
        return LintReport(None, None, (), (_finding(error.code, error.detail),), (), ())
    return _lint_obligation(root, obligation, feature_source=feature_source)


def lint_repository(root: Path) -> RepositoryLint:
    """Lint every record and reject orphaned Gherkin files."""
    spec_dir = root / SPEC_DIR
    if not spec_dir.exists():
        return RepositoryLint((), ())
    try:
        entries = tuple(sorted(spec_dir.iterdir()))
    except OSError as error:
        return RepositoryLint(
            (),
            (
                _finding(
                    "specifications_unreadable", f"directory={spec_dir} could not be read: {error}"
                ),
            ),
        )
    records = {path.stem: path for path in entries if path.is_file() and path.suffix == ".json"}
    features = {path.stem for path in entries if path.is_file() and path.suffix == ".feature"}
    errors = [
        _finding(
            "orphan_feature",
            f"feature={spec_dir / f'{key}.feature'} has no {key}.json obligation record",
        )
        for key in sorted(features - records.keys())
    ]
    reports = tuple(lint_obligation(root, key) for key in sorted(records))
    return RepositoryLint(reports, tuple(errors))


def _execution_failure(key: str, scenarios: int, detail: str) -> RunResult:
    """Build the one status used when a parsed step ran and did not satisfy."""
    return RunResult(key, FAILURE, scenarios, detail)


def _execute_pickle(
    key: str,
    pickle: Mapping[str, object],
    definitions: Mapping[str, object],
    scenario_count: int,
) -> RunResult | None:
    """Execute one compiled scenario, returning a result only when it stops the run."""
    scenario = str(pickle.get("name", "<unnamed scenario>"))
    steps = pickle.get("steps", [])
    if not isinstance(steps, list):
        return RunResult(key, NON_RESULT, scenario_count, f"scenario={scenario} has no step list")
    context = ExecutionContext()
    for raw_step in steps:
        if not isinstance(raw_step, dict) or not isinstance(raw_step.get("text"), str):
            return RunResult(
                key, NON_RESULT, scenario_count, f"scenario={scenario} has an unreadable step"
            )
        text = raw_step["text"]
        function = definitions.get(text)
        if not callable(function):
            return RunResult(
                key,
                NON_RESULT,
                scenario_count,
                f"scenario={scenario!r} has no step definition for {text!r}",
            )
        try:
            outcome = function(context, text)
        except Exception as error:  # noqa: BLE001 — a bound driver exception is a failure
            return _execution_failure(
                key, scenario_count, f"scenario={scenario!r} step={text!r} raised: {error}"
            )
        if outcome is False:
            return _execution_failure(
                key, scenario_count, f"scenario={scenario!r} step={text!r} was not satisfied"
            )
    return None


def execute_document(
    key: str,
    document: Mapping[str, object],
    definitions: Mapping[str, object],
    *,
    uri: str = "obligation.feature",
) -> RunResult:
    """Execute compiled scenarios against one shared step-definition interface."""
    compiled_document = dict(document)
    compiled_document["uri"] = uri
    try:
        pickles = Compiler().compile(compiled_document)
    except Exception as error:  # noqa: BLE001 — a compiler failure is a typed non-result
        return RunResult(key, NON_RESULT, 0, f"Gherkin scenarios could not be compiled: {error}")
    if not pickles:
        return RunResult(key, NON_RESULT, 0, "specification produced no executable scenarios")
    for pickle in pickles:
        if not isinstance(pickle, dict):
            return RunResult(key, NON_RESULT, len(pickles), "compiled scenario is unreadable")
        result = _execute_pickle(key, pickle, definitions, len(pickles))
        if result is not None:
            return result
    return RunResult(key, PASSED, len(pickles), None)


def _step_library(root: Path, relative: str) -> Mapping[str, object]:
    """Load a repository-local shared step library for the one Python runner."""
    if not relative:
        _raise_specification(
            "step_library_missing",
            "no step_library was declared; add the shared Python driver path to the obligation",
        )
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        _raise_specification(
            "step_library_outside_repository",
            f"step_library={relative!r} must stay inside the repository",
            error,
        )
    if not path.is_file():
        _raise_specification(
            "step_library_missing",
            f"step_library={relative!r} does not exist; add the shared Python driver",
        )
    module_spec = importlib.util.spec_from_file_location("cti_acceptance_steps", path)
    if module_spec is None or module_spec.loader is None:
        _raise_specification("step_library_unreadable", f"step_library={path} could not be loaded")
    module = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 — an unavailable driver is a typed non-result
        _raise_specification(
            "step_library_unreadable",
            f"step_library={path} could not be executed: {error}",
            error,
        )
    definitions = getattr(module, "STEPS", None)
    if not isinstance(definitions, Mapping):
        _raise_specification(
            "step_library_invalid",
            f"step_library={path} must export a mapping named STEPS",
        )
    return definitions


def run_obligation(
    root: Path,
    key: str,
    *,
    definitions: Mapping[str, object] | None = None,
) -> RunResult:
    """Lint and execute one obligation, preserving failure/non-result/held distinctions."""
    report = lint_obligation(root, key)
    return _run_lint_report(root, key, report, definitions)


def _run_lint_report(
    root: Path,
    key: str,
    report: LintReport,
    definitions: Mapping[str, object] | None,
) -> RunResult:
    """Execute one lint report while keeping all typed outcome branches shared."""
    if report.errors:
        detail = "; ".join(finding.detail for finding in report.errors)
        return RunResult(key, NON_RESULT, 0, f"specification could not execute: {detail}")
    if report.obligation is None:
        return RunResult(key, NON_RESULT, 0, "obligation could not be read")
    if report.obligation.kind == NON_BEHAVIOURAL:
        return RunResult(
            key,
            HELD_TO_REVIEW,
            0,
            "obligation is non-behavioural and is held to review",
        )
    step_definitions = definitions
    if step_definitions is None:
        try:
            step_definitions = _step_library(root, report.obligation.step_library)
        except SpecificationError as error:
            return RunResult(key, NON_RESULT, 0, error.detail)
    if report.document is None:
        return RunResult(key, NON_RESULT, 0, "parsed Gherkin document is absent")
    return execute_document(
        key,
        report.document,
        step_definitions,
        uri=report.obligation.feature.as_posix(),
    )


def run_embedded_obligation(
    root: Path,
    key: str,
    record: Mapping[str, object],
    feature_source: str | None,
    *,
    definitions: Mapping[str, object] | None = None,
) -> RunResult:
    """Execute a plan package's embedded specification through the keyed runner."""
    report = lint_embedded_obligation(root, key, record, feature_source)
    return _run_lint_report(root, key, report, definitions)


def check(root: Path) -> CheckReport:
    """Return the static gate's complete read; provisional debt is not silently green."""
    result = lint_repository(root)
    lines, exit_code = _check_lines(result)
    return CheckReport(lines, exit_code, result)


def _check_lines(result: RepositoryLint) -> tuple[tuple[str, ...], int]:
    """Render the static gate and its refusing branches."""
    reports = result.reports
    errors = [*result.errors, *(finding for report in reports for finding in report.errors)]
    if errors:
        return (
            (
                "acceptance_specs=refused",
                "refusal=specification_invalid",
                *(f"error={finding.code} {finding.detail}" for finding in errors),
                "action=Repair the specification and rerun `just accept <obligation-key>`.",
            ),
            1,
        )
    provisional = [
        (report.obligation.key, term)
        for report in reports
        for term in report.unratified
        if report.obligation is not None
    ]
    if provisional:
        key, term = provisional[0]
        return (
            (
                "acceptance_specs=refused",
                "refusal=provisional_unratified",
                f"obligation={key} term={term}",
                (
                    f"action=ratify {term!r} in CONTEXT.md's Language section or remove its "
                    "provisional declaration before landing."
                ),
            ),
            1,
        )
    return ((f"acceptance_specs=ok count={len(reports)} provisional=none",), 0)


def _result_document(result: RunResult) -> str:
    """Render a result without collapsing its typed status into an exit code."""
    document: dict[str, object] = {
        "obligation_key": result.obligation_key,
        "result": result.result,
        "scenarios": result.scenarios,
    }
    if result.detail is not None:
        document["detail"] = result.detail
    return json.dumps(document, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    """Build the three command surfaces: lint, static check, and one-key execution."""
    parser = argparse.ArgumentParser(prog="acceptance", description=__doc__)
    verbs = parser.add_subparsers(dest="verb", required=True)
    run = verbs.add_parser("run", help="execute one obligation")
    run.add_argument("key")
    run.add_argument("--root", type=Path, default=REPO)
    lint = verbs.add_parser("lint", help="lint one key or every obligation")
    lint.add_argument("key", nargs="?")
    lint.add_argument("--root", type=Path, default=REPO)
    static = verbs.add_parser("check", help="run the landing-time acceptance gate")
    static.add_argument("--root", type=Path, default=REPO)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested acceptance surface."""
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    if args.verb == "run":
        result = run_obligation(root, args.key)
        print(_result_document(result))  # noqa: T201 — JSON is this CLI's public result
        return {PASSED: 0, HELD_TO_REVIEW: 0, FAILURE: 1, NON_RESULT: 2}[result.result]
    if args.verb == "check":
        report = check(root)
        print(
            "\n".join(report.lines),
            file=sys.stdout if report.exit_code == 0 else sys.stderr,
        )
        return report.exit_code
    if args.key:
        report = lint_obligation(root, args.key)
        if report.errors:
            print("acceptance_lint=refused", file=sys.stderr)  # noqa: T201
            for finding in report.errors:
                print(f"error={finding.code} {finding.detail}", file=sys.stderr)  # noqa: T201
            return 1
        provisional = ",".join(term.term for term in report.provisional) or "none"
        status = ",".join(report.unratified) or "none"
        print(  # noqa: T201 — the lint result is this CLI's public output
            f"acceptance_lint=ok obligation={args.key} provisional={provisional} "
            f"unratified={status}"
        )
        return 0
    report = check(root)
    print(
        "\n".join(report.lines),
        file=sys.stdout if report.exit_code == 0 else sys.stderr,
    )
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
