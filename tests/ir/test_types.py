import pytest

from air.ir import (
    INT,
    JSON,
    ListType,
    MapType,
    PrimitiveType,
    RuntimeKind,
    RuntimeType,
    SemanticKind,
    SemanticType,
    SerializationError,
    TrustLabel,
    parse_type,
)


def test_nested_semantic_type_has_stable_spelling_and_equality() -> None:
    fact = SemanticType(SemanticKind.FACT, INT, TrustLabel.EXTERNAL_UNTRUSTED)
    nested = ListType(fact)

    assert str(nested) == "List<Fact<Int,ExternalUntrusted>>"
    assert parse_type(str(nested)) == nested
    assert hash(parse_type(str(nested))) == hash(nested)


def test_container_and_runtime_types_round_trip() -> None:
    descriptor = MapType(JSON, RuntimeType(RuntimeKind.RESULT, INT, JSON))

    assert parse_type(str(descriptor)) == descriptor
    assert str(parse_type("Goal<Json>")) == "Goal<Json>"


def test_trust_is_required_for_trust_bearing_semantic_types() -> None:
    with pytest.raises(ValueError):
        SemanticType(SemanticKind.CLAIM, INT)


def test_malformed_type_text_is_rejected_without_evaluation() -> None:
    with pytest.raises(SerializationError):
        parse_type("List<__import__('os').system('touch /tmp/nope')>")


def test_primitive_constructor_accepts_canonical_name() -> None:
    assert PrimitiveType("Int") == INT
