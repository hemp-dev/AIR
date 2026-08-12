import pytest

from air.ir import CapabilitySet, Effect, EffectKind, SerializationError


def test_capability_deny_overrides_allow() -> None:
    capabilities = CapabilitySet.from_strings(
        [
            "read:wm://research/**",
            "deny:read:wm://research/private/**",
        ]
    )

    assert capabilities.allows(Effect(EffectKind.READ, "wm://research/public/item"))
    assert not capabilities.allows(Effect(EffectKind.READ, "wm://research/private/item"))
    assert not capabilities.allows(Effect(EffectKind.READ, "wm://researcher/item"))


def test_unknown_effect_kind_fails_closed_during_decode() -> None:
    with pytest.raises(SerializationError, match="unknown effect kind"):
        Effect.from_json_obj({"kind": "launch", "resource": "anything"})
