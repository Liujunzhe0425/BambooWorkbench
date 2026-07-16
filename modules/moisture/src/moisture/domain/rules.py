"""Immutable rule-package models adapted from the verified legacy rule core."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from moisture.domain.enums import DisplayColor
from moisture.domain.models import (
    BatchRecord,
    BatchStatistics,
    DecisionTargetField,
    ScreeningDecision,
)

RuleType = Literal[
    "numeric_threshold",
    "numeric_range",
    "missing_field",
    "formula_mismatch",
    "department_difference",
    "composite",
]
ConfirmationStatus = Literal["confirmed", "pending_confirmation"]

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_OPERATORS = frozenset({">", ">=", "<", "<=", "==", "!="})


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    rule_id: str
    rule_type: str
    message: str | None = None
    field: str | None = None
    operator: str | None = None
    threshold: Decimal | None = None
    lower: Decimal | None = None
    upper: Decimal | None = None
    mode: Literal["inside", "outside"] | None = None
    fields: tuple[str, ...] = ()
    tolerance: Decimal | None = None
    rule_ids: tuple[str, ...] = ()
    combinator: Literal["AND", "OR"] | None = None
    color: DisplayColor = DisplayColor.NONE
    applicable_materials: tuple[str, ...] = ()
    applicable_seasons: tuple[str, ...] = ()
    applicable_suppliers: tuple[str, ...] = ()
    customer_confirmation_status: ConfirmationStatus = "confirmed"

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", tuple(self.fields))
        object.__setattr__(self, "rule_ids", tuple(self.rule_ids))
        object.__setattr__(self, "applicable_materials", tuple(self.applicable_materials))
        object.__setattr__(self, "applicable_seasons", tuple(self.applicable_seasons))
        object.__setattr__(self, "applicable_suppliers", tuple(self.applicable_suppliers))
        if _SAFE_ID.fullmatch(self.rule_id) is None:
            raise ValueError("unsafe rule_id")
        if self.customer_confirmation_status not in {"confirmed", "pending_confirmation"}:
            raise ValueError("invalid customer confirmation status")
        if self.color not in {DisplayColor.NONE, DisplayColor.ORANGE, DisplayColor.GREEN}:
            raise ValueError("unapproved screening color")
        self._validate_parameters()

    def _validate_parameters(self) -> None:
        if self.rule_type == "numeric_threshold":
            self._require("field", "operator", "threshold")
            if self.operator not in _OPERATORS:
                raise ValueError("unsupported numeric threshold operator")
            if self.color == DisplayColor.NONE:
                raise ValueError("numeric threshold requires a screening color")
        elif self.rule_type == "numeric_range":
            self._require("field", "lower", "upper", "mode")
            if self.mode not in {"inside", "outside"}:
                raise ValueError("unsupported numeric range mode")
            if self.lower is not None and self.upper is not None and self.lower > self.upper:
                raise ValueError("lower must not exceed upper")
            if self.color == DisplayColor.NONE:
                raise ValueError("numeric range requires a screening color")
        elif self.rule_type == "missing_field":
            if not self.fields:
                raise ValueError("fields is required for missing_field")
        elif self.rule_type == "formula_mismatch":
            self._require("tolerance")
            if self.tolerance is not None and self.tolerance < 0:
                raise ValueError("tolerance must be non-negative")
        elif self.rule_type == "department_difference":
            self._require("operator", "threshold")
            if self.operator not in _OPERATORS:
                raise ValueError("unsupported department difference operator")
        elif self.rule_type == "composite":
            self._require("combinator")
            if self.combinator not in {"AND", "OR"}:
                raise ValueError("unsupported composite combinator")
            if len(self.rule_ids) < 2:
                raise ValueError("at least two rule_ids are required for composite")
            if len(set(self.rule_ids)) != len(self.rule_ids):
                raise ValueError("duplicate rule_ids are not allowed for composite")
            if self.rule_id in self.rule_ids:
                raise ValueError("composite rule cannot reference itself")
            if any(not rule_id for rule_id in self.rule_ids):
                raise ValueError("empty rule ID is not allowed for composite")

    def _require(self, *names: str) -> None:
        missing = [name for name in names if getattr(self, name) is None]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")


@dataclass(frozen=True, slots=True)
class RulePackageSnapshot:
    schema_version: str
    package_id: str
    rule_version: str
    rules_file: str
    rules_sha256: str
    source: str
    applicable_scope: str
    customer_confirmation_status: ConfirmationStatus
    released_at: str
    module_version: str
    definitions: tuple[RuleDefinition, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "definitions", tuple(self.definitions))
        if self.customer_confirmation_status not in {"confirmed", "pending_confirmation"}:
            raise ValueError("invalid package customer confirmation status")
        if (
            _SAFE_ID.fullmatch(self.package_id) is None
            or _SAFE_ID.fullmatch(self.rule_version) is None
        ):
            raise ValueError("unsafe rule package identifier")
        if self.rules_file != "rules.yaml":
            raise ValueError("rules_file must be rules.yaml")
        if not self.definitions:
            raise ValueError("rule package must contain at least one definition")
        if len({definition.rule_id for definition in self.definitions}) != len(self.definitions):
            raise ValueError("duplicate rule_id in rule package")
        if re.fullmatch(r"[0-9a-f]{64}", self.rules_sha256) is None:
            raise ValueError("rules_sha256 must be a lowercase SHA-256")

    @property
    def content_hash(self) -> str:
        return self.rules_sha256


@dataclass(slots=True)
class RuleContext:
    record: BatchRecord
    statistics: BatchStatistics
    hit_states: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PendingRuleMatch:
    rule_id: str
    message: str
    direction: Literal["high", "low", "data_quality", "unspecified"]
    target_field: DecisionTargetField | None
    threshold: Decimal | None
    rules_sha256: str


@dataclass(frozen=True, slots=True)
class RuleEvaluationResult:
    decisions: tuple[ScreeningDecision, ...] = ()
    pending_matches: tuple[PendingRuleMatch, ...] = ()
