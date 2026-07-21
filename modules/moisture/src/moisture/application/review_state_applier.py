"""Apply only strictly validated auxiliary evidence to deterministic batches."""

from __future__ import annotations

from dataclasses import dataclass, replace

from moisture.application.ai_request_builder import (
    AIRequestBuildResult,
    candidates_from_batches,
    opaque_candidate_id,
)
from moisture.application.run_result import InternalAnomaly, ReviewState
from moisture.application.service_response_validator import ValidatedReviewDecision
from moisture.domain.enums import ConfirmationState, DisplayColor, ReviewStatus
from moisture.domain.models import AIReviewDecision
from moisture.ports.writers import WorkbookBatch


@dataclass(frozen=True, slots=True)
class AppliedReviewEvidence:
    batches: tuple[WorkbookBatch, ...]
    anomalies: tuple[InternalAnomaly, ...]


def degrade_batches(batches: tuple[WorkbookBatch, ...], reason: str) -> tuple[WorkbookBatch, ...]:
    return tuple(
        replace(
            batch,
            ai_review=AIReviewDecision(
                status=ReviewStatus.NOT_COMPLETED,
                display_color=batch.screening_decision.display_color,
                confirmation_state=ConfirmationState.PENDING_HUMAN_REVIEW,
                rationale=reason,
                target_field=batch.screening_decision.target_field,
            ),
            final_display_color=batch.screening_decision.display_color,
            ai_degradation_reason=reason,
            review_suggestion="辅助服务不可用或响应无效，保留确定性橙绿初筛",
        )
        if batch.screening_decision.display_color in {DisplayColor.ORANGE, DisplayColor.GREEN}
        else batch
        for batch in batches
    )


def apply_validated_review(
    batches: tuple[WorkbookBatch, ...],
    anomalies: tuple[InternalAnomaly, ...],
    request: AIRequestBuildResult,
    decisions: tuple[ValidatedReviewDecision, ...],
    rule_package: object,
) -> AppliedReviewEvidence:
    candidates = candidates_from_batches(batches, rule_package)
    by_public_id = {opaque_candidate_id(item): item for item in candidates}
    decision_by_id = {item.candidate_id: item for item in decisions}
    promoted_records: dict[str, ValidatedReviewDecision] = {}
    for public_id, candidate in by_public_id.items():
        decision = decision_by_id[public_id]
        if candidate.record_id is not None:
            promoted_records[candidate.record_id] = decision

    updated_batches: list[WorkbookBatch] = []
    for batch in batches:
        decision = promoted_records.get(batch.record.record_id)
        if decision is None:
            updated_batches.append(batch)
            continue
        color = DisplayColor.RED if decision.direction == "high" else DisplayColor.BLUE
        status = (
            ReviewStatus.REVIEW_HIGH if decision.direction == "high" else ReviewStatus.REVIEW_LOW
        )
        updated_batches.append(
            replace(
                batch,
                ai_review=AIReviewDecision(
                    status=status,
                    display_color=color,
                    confirmation_state=ConfirmationState.PENDING_HUMAN_REVIEW,
                    rationale="结构化辅助证据已通过严格校验",
                    target_field=decision.field,
                    confidence=decision.confidence,
                ),
                final_display_color=color,
                confirmation_state=ConfirmationState.PENDING_HUMAN_REVIEW,
                ai_degradation_reason=None,
                review_suggestion="有效辅助证据支持的高度疑似，非正式错误或责任结论",
            )
        )

    updated_anomalies = tuple(
        replace(
            anomaly,
            review_state=(
                ReviewState.HIGH_SUSPICION_HIGH
                if promoted_records.get(
                    next(
                        (
                            batch.record.record_id
                            for batch in batches
                            if batch.record.source_file == anomaly.source_file
                        ),
                        "",
                    )
                ).direction
                == "high"
                else ReviewState.HIGH_SUSPICION_LOW
            ),
            message="有效辅助证据支持的高度疑似，非正式错误或责任结论",
        )
        if any(
            batch.record.record_id in promoted_records
            and batch.record.source_file == anomaly.source_file
            for batch in batches
        )
        and anomaly.rule_id is not None
        else anomaly
        for anomaly in anomalies
    )
    return AppliedReviewEvidence(tuple(updated_batches), updated_anomalies)
