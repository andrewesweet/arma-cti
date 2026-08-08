"""The probe↔harness contract is derived from the runner, not restated (#215).

`tools/probe_contract.py` prints what a probe owes the harness by reading it off
`spike/regress.sh` and `spike/run.sh`. The drift assertion is the deliverable as
much as the recipe is: a header key added to `regress.sh` has to appear in the
contract, or the output is a doc wearing derivation's clothes — and the recorded
cost of a contract read wrong is #150/#191, a probe that tested the wrong thing.

These tests pin the derivation against the live runner and plant the mutation
that proves it is live, then hold the #209 line that verdict semantics are
pointed at rather than paraphrased.
"""

from __future__ import annotations

import pytest

from conftest import REPO, load_tool

probe_contract = load_tool("probe_contract")

REGRESS_SH = REPO / "spike" / "regress.sh"
RUN_SH = REPO / "spike" / "run.sh"
REGRESS = REGRESS_SH.read_text(encoding="utf-8")
RUN = RUN_SH.read_text(encoding="utf-8")

# The keys the runner reads today. Pinned so a derivation change is a conscious
# act, and so the drift test below has a known before-state to mutate from.
CURRENT_KEYS = ["probe", "issues", "window", "env", "expect", "quarantined"]


def test_every_key_the_runner_reads_is_derived() -> None:
    """`header_of` call sites are the contract; this is the set they yield.

    Compared as a set: first-seen order in the file is not meaningful, and the
    display order (the runner's documented `// key:` block) is its own concern.
    """
    assert set(probe_contract.derive_header_keys(REGRESS)) == set(CURRENT_KEYS)


def test_the_contract_renders_every_derived_key() -> None:
    """No key the runner reads may be absent from the printed contract."""
    rendered = probe_contract.render_contract(REGRESS, RUN)
    for key in probe_contract.derive_header_keys(REGRESS):
        assert key in rendered, f"header key {key!r} missing from the contract"


def test_required_is_what_the_validation_block_enforces() -> None:
    """Required is code-derived: the three the bring-up loop dies without."""
    assert probe_contract.derive_required_keys(REGRESS) == {"probe", "window", "issues"}


def test_optional_keys_are_not_gated_at_bring_up() -> None:
    """env, expect and quarantined are read but never demanded."""
    optional = set(
        probe_contract.derive_header_keys(REGRESS)
    ) - probe_contract.derive_required_keys(REGRESS)
    assert optional == {"env", "expect", "quarantined"}


def test_every_key_carries_the_runner_s_own_purpose() -> None:
    """The purpose prose is read off regress.sh, not maintained here."""
    docs = probe_contract.derive_doc_block(REGRESS)
    for key in CURRENT_KEYS:
        assert key in docs, f"{key!r} has no `// key:` line in regress.sh"
        assert docs[key][1], f"{key!r} has no purpose text"


def test_the_completion_sentinel_is_read_off_the_runner() -> None:
    assert probe_contract.derive_completion_sentinel(REGRESS) == "probe_done"


def test_the_window_binds_the_probe_s_own_header() -> None:
    assert probe_contract.derive_window_source(REGRESS) == "window"


def test_a_fail_line_short_circuits_the_completion_wait() -> None:
    """A probe that fails must not time out waiting on its own window."""
    assert probe_contract.derive_fail_short_circuits(RUN) is True


def test_the_runner_s_own_classes_are_derived() -> None:
    """The classes come from the runner's emit sites, non-empty and code-read."""
    classes = set(probe_contract.derive_runner_classes(REGRESS, RUN))
    # The classes run.sh fails with directly; the table owns the rest.
    assert {"timeout", "node_crashed", "infra_unavailable", "assertion_failed"} <= classes


# The drift test: criterion 2. A header key added to regress.sh has to surface in
# the contract, or the derivation is decorative and a second copy has come back.
_SYNTHETIC_KEY = "synopsis"


def _regress_with_an_undocumented_key() -> str:
    """regress.sh with a new `header_of` read added, as a future key would land.

    Inserted inside the validation loop, where a real new key would be enforced;
    no doc line, so the contract's undocumented-key fallback is the path taken.
    """
    anchor = '[[ -n "$(header_of "$file" issues)" ]] || die'
    assert anchor in REGRESS, "regress.sh changed shape; update the drift anchor"
    call = f' synopsis="$(header_of "$file" {_SYNTHETIC_KEY})"'
    return REGRESS.replace(anchor, anchor + "\n    " + call, 1)


def test_a_key_added_to_the_runner_appears_in_the_contract() -> None:
    """The mutation that makes derivation worth more than a doc."""
    mutated = _regress_with_an_undocumented_key()
    assert _SYNTHETIC_KEY in probe_contract.derive_header_keys(mutated)
    assert _SYNTHETIC_KEY in probe_contract.render_contract(mutated, RUN)


def test_a_key_removed_from_the_runner_leaves_the_contract() -> None:
    """The other direction of the same drift: a dropped key must drop out."""
    mutated = REGRESS.replace(f'header_of "$file" expect', f'header_of "$file" zzgone')
    keys = probe_contract.derive_header_keys(mutated)
    assert "expect" not in keys
    assert "zzgone" in keys


def test_the_contract_points_at_the_failure_class_table() -> None:
    """Criterion 3: verdict semantics are pointed at, never restated."""
    rendered = probe_contract.render_contract(REGRESS, RUN)
    assert "CLAUDE.md" in rendered
    assert "Failure classes" in rendered


def test_the_contract_does_not_paraphrase_the_table() -> None:
    """Distinctive table prose must not leak into the contract (#209)."""
    rendered = probe_contract.render_contract(REGRESS, RUN)
    # Phrases unique to CLAUDE.md's "Required response" column, verbatim.
    forbidden = [
        "Fix the code under test",
        "Investigate synchronisation",
        "Collect dump, escalate to human",
        "Regenerate; never hand-edit",
        "Re-dispatch to another lane",
    ]
    for phrase in forbidden:
        assert phrase not in rendered, f"contract restates table prose: {phrase!r}"


def test_main_prints_the_contract_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """Criterion 1: it prints and exits 0, no Arma, no lock."""
    assert probe_contract.main([]) == 0
    out = capsys.readouterr().out
    assert "Header keys" in out
    assert "probe_done" in out
