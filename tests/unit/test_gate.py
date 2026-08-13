"""Tests for `tools/gate.py` — the gate-derivation functions (#323 review round 2 finding 5).

`gate` was lifted out of `brief` so neither `brief` nor `dispatch` imports the other to reach
the body-reading functions (#323 review finding 3). The extraction kept `test_brief.py` as the
measured subject, so the gate ladder sat where no test module's stem pointed and the mutation
gate could not see it. This module gives `tools/gate.py` a subject of its own, and the tests are
written to discriminate — each branch of the ladder and each reader is pinned by an assertion a
mutant survives only by changing nothing the test notices.
"""

from __future__ import annotations

from pathlib import Path

from conftest import REPO, load_tool

gate = load_tool("gate")
admission = load_tool("admission")


# ---------------------------------------------------------------------- the readers


def test_named_paths_extracts_deduplicates_and_sorts_path_tokens() -> None:
    # A path token needs a slash with a non-empty segment either side: that is what tells a
    # surface (`addons/main/fn_foo.sqf`) from the rule being quoted (`addons/`). A bare word is
    # not a path, and a trailing-slash directory is not either. The result is deduped and sorted.
    body = "edit b/z.py and a/m.py and b/z.py under addons/ and tools/worker.py"
    assert gate.named_paths(body) == ("a/m.py", "b/z.py", "tools/worker.py")


def test_named_paths_keeps_multi_segment_paths_whole() -> None:
    # A deeper path is one token, not split at every slash.
    assert gate.named_paths("see addons/main/functions/fn_effectApply.sqf") == (
        "addons/main/functions/fn_effectApply.sqf",
    )


def test_in_world_keeps_only_surfaces_the_policy_names() -> None:
    # `in_world` defers entirely to admission's list — the one authority — so the test builds a
    # known in-world path from that list rather than naming a prefix of its own.
    prefixes = admission.IN_WORLD_PREFIXES
    assert prefixes, "the policy must name at least one in-world prefix"
    first = prefixes[0]
    in_world_path = (first + "sub/file.sqf") if first.endswith("/") else (first + "/file.sqf")
    assert gate.in_world((in_world_path, "tools/dispatch.py", "README.md")) == (in_world_path,)
    assert gate.in_world(("tools/dispatch.py", "README.md")) == ()


def test_domain_vocabulary_reads_terms_longest_first_with_the_engine_words() -> None:
    # CONTEXT.md spells a term it is defining as a bold label opening a line. The longer term is
    # returned first so `Command Port` is matched before `Command`, and the two engine words that
    # name the world without being CONTEXT.md nouns are always present.
    context = "**Command Port**: a thing.\n\n**Command**: another thing.\n"
    vocab = gate.domain_vocabulary(context)
    assert "Command Port" in vocab
    assert "Command" in vocab
    assert "SQF" in vocab
    assert "in-world" in vocab
    assert vocab.index("Command Port") < vocab.index("Command")


def test_domain_mentions_is_case_sensitive_and_bounded() -> None:
    # Case matters: a lower-case "base" is ordinary English, not a claim about the world. Word
    # boundaries matter: "FireBase" does not contain the term "Base" for these purposes. Empty
    # vocabulary is the unreadable-CONTEXT.md case and mentions nothing.
    assert gate.domain_mentions("the Base and a Command Port", ("Base", "Command Port")) == (
        "Base",
        "Command Port",
    )
    assert gate.domain_mentions("lowercase base here", ("Base",)) == ()
    assert gate.domain_mentions("FireBase and Base", ("Base",)) == ("Base",)
    assert gate.domain_mentions("anything", ()) == ()


def test_read_vocabulary_reads_the_checkout_and_is_silent_when_it_cannot() -> None:
    # The real checkout carries CONTEXT.md and so a non-empty vocabulary; a directory without one
    # is the unreadable case, which leaves the vocabulary signal silent rather than crashing.
    assert gate.read_vocabulary(REPO)
    assert gate.read_vocabulary(Path("/no/such/checkout")) == ()


# ---------------------------------------------------------------------- the gate ladder


def test_derive_gate_owes_regress_to_an_in_world_path_even_without_a_vocabulary() -> None:
    # An in-world path decides `regress` without needing CONTEXT.md, and that beats the
    # vocabulary check — the order of the ladder is the assertion. A regress gate produces a
    # verdict, which is what the paste rule attaches to.
    gate_result = gate.derive_gate("implement addons/main/fn_foo.sqf", ())
    assert gate_result.kind == gate.GATE_REGRESS
    assert gate_result.reads_a_verdict is True
    assert any(part.startswith("in_world=") for part in gate_result.because)


def test_derive_gate_is_undetermined_when_the_vocabulary_could_not_be_read() -> None:
    # No in-world path and an unreadable vocabulary: undetermined because the check could not
    # run, which is not a check that cleared.
    gate_result = gate.derive_gate("edit tools/dispatch.py", ())
    assert gate_result.kind == gate.GATE_UNDETERMINED
    assert gate_result.reads_a_verdict is False
    assert any(part.startswith("vocabulary=unreadable") for part in gate_result.because)


def test_derive_gate_is_undetermined_when_no_path_is_named() -> None:
    # A readable vocabulary but no path at all in the body: undetermined, because the surface
    # cannot be read off the body and undetermined never resolves to the cheaper gate.
    gate_result = gate.derive_gate("refactor the dispatcher", ("Base", "Squad"))
    assert gate_result.kind == gate.GATE_UNDETERMINED
    assert any(part.startswith("named_paths=none") for part in gate_result.because)


def test_derive_gate_is_undetermined_when_the_body_speaks_the_domain_language() -> None:
    # No in-world path, but a domain term the body uses: still undetermined, because measured
    # in-world issues named only evidence paths. The domain-language branch is distinct from the
    # no-path branch above.
    gate_result = gate.derive_gate("adjust the Base in tools/dispatch.py", ("Base",))
    assert gate_result.kind == gate.GATE_UNDETERMINED
    assert any("domain_terms=" in part for part in gate_result.because)


def test_derive_gate_is_fast_when_no_surface_and_no_domain_term_is_reached() -> None:
    # A non-world path and no domain term: the corpus is not owed.
    gate_result = gate.derive_gate("edit tools/dispatch.py quickly", ("Base",))
    assert gate_result.kind == gate.GATE_FAST
    assert gate_result.reads_a_verdict is False
    assert any(part.startswith("named_paths=") for part in gate_result.because)
