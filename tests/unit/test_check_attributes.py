"""The `check-attributes` leg's own assertions (#484).

Named for the module it executes, so the mutation tier plants its mutants here:
`tools/check_attributes.py` is this landing's new gate, and a gate whose own
logic no test notices changing is the #41 shape.

The registry-half tests — vocabulary, emission, journal — live in
`tests/unit/test_attribute_registry.py`, the module named for
`tools/attribute_registry.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    from types import ModuleType

check_attributes: ModuleType = load_tool("check_attributes")


def test_the_leg_covers_every_name_the_trees_python_carries() -> None:
    """The leg's own assertion, run against the real tree rather than a sample.

    This is the test that makes the registry an authority rather than a fourth
    copy: the checker derives its subject set from `git ls-files` plus the
    uncommitted, so a name hand-typed into any module reddens here before it
    reddens the leg.
    """
    root = Path(__file__).resolve().parent.parent.parent
    sources = check_attributes.tracked_sources(root)
    assert "tools/attribute_registry.py" in sources, "the derivation reads the real tree"
    assert not check_attributes.check(sources), "every emitted name is a registered one"


def test_an_attribute_emitted_but_absent_from_the_registry_reds() -> None:
    """The negative criterion: the leg catches a hand-typed name, all three forms.

    The unregistered names are assembled from fragments rather than spelled,
    because this module is itself a tracked source the leg scans — a literal
    fake name here would redden the very coverage test above, which is the leg
    working, just on its own fixture.
    """
    unregistered = f"cti.{'unregistered'}.attribute"
    nowhere = f"cti.{'nowhere'}."

    exact = check_attributes.check({"tools/example.py": f'X = "{unregistered}"\n'})
    assert [(f.name, f.form) for f in exact] == [(unregistered, "exact")]

    rendered = check_attributes.check({"tools/example.py": 'X = f"cti.issue={n}"\n'})
    assert rendered == [], "a name the registry carries, in the key=value form, stays green"

    prefix = check_attributes.check({"tools/example.py": f'X = f"{nowhere}{{k}}"\n'})
    assert [(f.name, f.form) for f in prefix] == [(nowhere.rstrip("."), "prefix")]


def test_a_source_that_does_not_tokenise_is_a_finding_not_a_silence() -> None:
    """#496's rule at this leg's boundary: unreadable is reported, never green."""
    broken = "def f(:\n    pass\n"
    _exact, _prefixes, findings = check_attributes.names_in(broken, "tools/broken.py")
    assert [finding.form for finding in findings] == ["source"]
    assert "unparseable" in findings[0].name
    assert check_attributes.check({"tools/broken.py": broken}), "and the leg reds on it"
