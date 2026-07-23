from moisture.application.decision_aggregation import ordered_decisions, primary_decision
from moisture.domain.enums import DisplayColor, ScreenStatus
from moisture.domain.models import RuleHit, ScreeningDecision


def _decision(rule_id: str, target: str) -> ScreeningDecision:
    hit = RuleHit(rule_id, rule_id, DisplayColor.ORANGE, target)
    return ScreeningDecision(
        status=ScreenStatus.HIGH,
        rule_hits=(hit,),
        display_color=DisplayColor.ORANGE,
        reason=rule_id,
        target_field=target,
    )


def test_mean_remains_primary_while_range_hit_is_preserved() -> None:
    range_decision = _decision("RANGE_VALUE_HIGH", "range_value")
    mean_decision = _decision("HIGH_DEFAULT", "mean")

    ordered = ordered_decisions((range_decision, mean_decision))

    assert ordered == (mean_decision, range_decision)
    assert primary_decision(ordered) is mean_decision
