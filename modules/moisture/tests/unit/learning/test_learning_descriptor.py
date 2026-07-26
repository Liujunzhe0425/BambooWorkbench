"""Unit tests for private learning descriptor model (L-S1)."""

from __future__ import annotations

# ruff: noqa: E402, I001

import json
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.contract.learning_descriptor import (
    LearningCandidate,
    LearningContextLevel,
    LearningDescriptor,
    LearningDescriptorError,
)

FIXTURES = MODULE_ROOT / "tests" / "fixtures" / "learning"


def _fixture() -> dict:
    return json.loads(
        (FIXTURES / "learning-descriptor-example.json").read_text(encoding="utf-8")
    )


def test_fixture_round_trips() -> None:
    payload = _fixture()
    descriptor = LearningDescriptor.from_payload(payload)
    assert descriptor.to_payload() == payload


def test_canonical_form_is_stable() -> None:
    payload = _fixture()
    first = LearningDescriptor.from_payload(payload).to_payload()
    second = LearningDescriptor.from_payload(payload).to_payload()
    assert first == second


def test_candidate_rejects_empty_display() -> None:
    with pytest.raises(LearningDescriptorError):
        LearningCandidate("msr-candidate-" + "1" * 24, "  ")


def test_candidate_rejects_overlong_display() -> None:
    with pytest.raises(LearningDescriptorError):
        LearningCandidate("msr-candidate-" + "1" * 24, "x" * 301)


def test_candidate_rejects_control_chars() -> None:
    with pytest.raises(LearningDescriptorError):
        LearningCandidate("msr-candidate-" + "1" * 24, "test\x00")


def test_context_rejects_unknown_field() -> None:
    with pytest.raises(LearningDescriptorError):
        LearningContextLevel(
            "msr-learning-" + "a" * 24, "moisture", "formula_conflict", None, None,
        )


def test_context_rejects_invalid_material_category() -> None:
    with pytest.raises(LearningDescriptorError):
        LearningContextLevel(
            "msr-learning-" + "a" * 24, "moisture", "supplier",
            "unknown_material", None,
        )


def test_descriptor_rejects_non_adjustable() -> None:
    payload = _fixture()
    payload["preference_adjustable"] = False
    with pytest.raises(LearningDescriptorError):
        LearningDescriptor.from_payload(payload)


def test_descriptor_rejects_duplicate_candidates() -> None:
    payload = _fixture()
    payload["candidates"] = [payload["candidates"][0], payload["candidates"][0]]
    with pytest.raises(LearningDescriptorError):
        LearningDescriptor.from_payload(payload)


def test_descriptor_rejects_base_suggestion_not_in_candidates() -> None:
    payload = _fixture()
    payload["base_suggestion"] = "msr-candidate-" + "9" * 24
    with pytest.raises(LearningDescriptorError):
        LearningDescriptor.from_payload(payload)


def test_descriptor_rejects_context_key_mismatch() -> None:
    payload = _fixture()
    payload["learning_key"] = "msr-learning-" + "f" * 24
    with pytest.raises(LearningDescriptorError):
        LearningDescriptor.from_payload(payload)


def test_from_payload_rejects_bad_type() -> None:
    with pytest.raises(LearningDescriptorError):
        LearningDescriptor.from_payload({"not": "valid"})
