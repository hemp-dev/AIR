import pytest

from air.ir import ActorRef, Provenance, StateRef, TrustLabel
from air.state import (
    InvalidPatchError,
    Patch,
    PatchIntegrityError,
    StaleVersionError,
    StateNotFoundError,
    StateStore,
    WriteScopeError,
)


def test_state_refs_and_projection_are_normalized_and_minimal() -> None:
    store = StateStore()
    first = store.put(
        "wm://case/input",
        {"public": {"answer": 713}, "secret": "do-not-forward"},
        trust=TrustLabel.EXTERNAL_UNTRUSTED,
        provenance=Provenance(produced_by=ActorRef("agent://source")),
    )

    projection = store.project("wm://case/input", ["public.answer"])

    assert str(first.ref) == "wm://case/input#v1"
    assert projection.json_value() == {"public": {"answer": 713}}
    assert "secret" not in str(projection.json_value())
    assert projection.materialized_bytes > 0
    assert store.read("wm://case/input#v1").json_value() == {
        "public": {"answer": 713},
        "secret": "do-not-forward",
    }


def test_state_ref_rejects_traversal_and_missing_objects() -> None:
    with pytest.raises(ValueError):
        StateRef.parse("wm://case/../payments")

    store = StateStore()
    with pytest.raises(StateNotFoundError):
        store.read("wm://case/missing")


def test_commit_creates_new_immutable_version_and_preserves_history() -> None:
    store = StateStore()
    first = store.put("wm://case/result", {"answer": 0, "audit": {"source": "fixture"}})
    patch = Patch(
        "patch.answer",
        "wm://case/result",
        first.version,
        {"answer": 713},
        ("answer",),
        provenance=Provenance(source_refs=("wm://case/input#v1",)),
    )

    second = store.commit(patch)

    assert second.ref == StateRef.parse("wm://case/result#v2")
    assert first.json_value() == {"answer": 0, "audit": {"source": "fixture"}}
    assert second.json_value() == {"answer": 713, "audit": {"source": "fixture"}}
    assert store.history[0].changed_paths == ("answer",)


def test_stale_and_out_of_scope_patches_never_overwrite_state() -> None:
    store = StateStore()
    first = store.put("wm://case/result", {"answer": 0, "private": "unchanged"})
    store.commit(
        Patch("patch.first", "wm://case/result", first.version, {"answer": 1}, ("answer",))
    )

    stale = Patch("patch.stale", "wm://case/result", first.version, {"answer": 2}, ("answer",))
    with pytest.raises(StaleVersionError):
        store.commit(stale)

    escaped = Patch(
        "patch.escape",
        "wm://case/result",
        2,
        {"private": "attacker"},
        ("answer",),
    )
    with pytest.raises(WriteScopeError):
        store.commit(escaped)
    assert store.read("wm://case/result").json_value() == {
        "answer": 1,
        "private": "unchanged",
    }


def test_identical_patch_replay_is_idempotent_but_changed_replay_is_rejected() -> None:
    store = StateStore()
    first = store.put("wm://case/result", {"answer": 0})
    patch = Patch("patch.replay", "wm://case/result", first.version, {"answer": 1}, ("answer",))

    committed = store.commit(patch)
    assert store.commit(patch) == committed
    with pytest.raises(PatchIntegrityError):
        store.commit(
            Patch("patch.replay", "wm://case/result", first.version, {"answer": 9}, ("answer",))
        )


def test_invalid_patch_is_rejected_before_commit() -> None:
    with pytest.raises(InvalidPatchError):
        Patch("patch.invalid", "wm://case/result", 1, {}, ("answer",))


def test_wildcard_write_scope_covers_children_but_not_siblings() -> None:
    store = StateStore()
    first = store.put("wm://case/result", {"audit": {"source": "fixture"}, "other": 0})

    second = store.commit(
        Patch(
            "patch.wildcard",
            "wm://case/result",
            first.version,
            {"audit.score": 1},
            ("audit.*",),
        )
    )

    assert second.json_value() == {"audit": {"source": "fixture", "score": 1}, "other": 0}
    with pytest.raises(WriteScopeError):
        store.commit(
            Patch(
                "patch.sibling",
                "wm://case/result",
                second.version,
                {"other": 2},
                ("audit.*",),
            )
        )
