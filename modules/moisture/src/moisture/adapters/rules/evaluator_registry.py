"""Explicit registry: the only extension point for rule evaluators."""

from typing import Protocol

from moisture.domain.models import RuleHit
from moisture.domain.rules import RuleContext, RuleDefinition


class RuleEvaluator(Protocol):
    def evaluate(self, context: RuleContext, definition: RuleDefinition) -> tuple[RuleHit, ...]: ...


class RuleEvaluatorRegistry:
    def __init__(self) -> None:
        self._evaluators: dict[str, RuleEvaluator] = {}

    @property
    def registered_types(self) -> frozenset[str]:
        return frozenset(self._evaluators)

    def register(self, rule_type: str, evaluator: RuleEvaluator) -> None:
        if rule_type in self._evaluators:
            raise ValueError(f"duplicate rule type: {rule_type}")
        self._evaluators[rule_type] = evaluator

    def get(self, rule_type: str) -> RuleEvaluator:
        try:
            return self._evaluators[rule_type]
        except KeyError as error:
            raise ValueError(f"unknown rule type: {rule_type}") from error
