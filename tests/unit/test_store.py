"""The persistence seam: operational facts only, typed refusals, the contract #290 fills (#291).

`store.Store` is the Protocol the daemon's save/load handlers delegate durability
to; `FakeStore` is the in-memory stand-in until #290's atomic store lands. What
these pin is the seam's contract rather than any one store's internals: a save
returns the version, checksum and generation and nothing of the document, a load
hands the document back with where it came from, and a store with nothing to
load refuses by a type the handler can tell apart from a document the schema
refused.
"""

from __future__ import annotations

import inspect

import pytest

from cti_daemon.store import (
    FakeStore,
    Loaded,
    NoValidGenerationError,
    SaveOutcome,
    Store,
    StoreError,
    checksum,
)


def test_the_fake_store_satisfies_the_protocol() -> None:
    assert isinstance(FakeStore(), Store)


def test_a_save_returns_operational_facts_and_never_the_document() -> None:
    document = {"version": 1, "clock": 10.0, "secret": "both sides' Funds"}
    outcome = FakeStore().save(document)

    assert set(inspect.signature(SaveOutcome).parameters) == {"version", "checksum", "generation"}
    assert outcome.version == 1
    assert outcome.checksum == checksum(document)
    assert outcome.generation == 1
    # The ack's fields carry no snapshot: no clock, no secret, no document.
    assert "secret" not in (outcome.version, outcome.checksum, outcome.generation)


def test_each_save_advances_the_generation() -> None:
    keeper = FakeStore()
    first = keeper.save({"version": 1})
    second = keeper.save({"version": 1})
    assert (first.generation, second.generation) == (1, 2)


def test_a_load_hands_back_what_was_saved_at_its_generation() -> None:
    keeper = FakeStore()
    saved = keeper.save({"version": 1, "clock": 30.0})
    loaded = keeper.load()

    assert isinstance(loaded, Loaded)
    assert loaded.document == {"version": 1, "clock": 30.0}
    assert loaded.generation == saved.generation
    assert loaded.checksum == saved.checksum


def test_a_load_off_an_empty_store_is_a_typed_no_valid_generation() -> None:
    with pytest.raises(NoValidGenerationError, match="no saved generation"):
        FakeStore().load()


def test_no_valid_generation_is_a_store_refusal() -> None:
    assert issubclass(NoValidGenerationError, StoreError)
