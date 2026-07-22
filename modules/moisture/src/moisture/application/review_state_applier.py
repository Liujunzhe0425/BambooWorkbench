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
from moisture.domain.review import AIReviewCandidate
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
    promoted_records: dict[str, tuple[AIReviewCandidate, ValidatedReviewDecision]] = {}
    for public_id, candidate in by_public_id.items():
        decision = decision_by_id[public_id]
        if candidate.record_id is not None:
            # Candidate order is strongest deviation first; keep that stable
            # record-level presentation when more than one metric is flagged.
            promoted_records.setdefault(candidate.record_id, (candidate, decision))

    updated_batches: list[WorkbookBatch] = []
    for batch in batches:
        promoted = promoted_records.get(batch.record.record_id)
        if promoted is None:
            updated_batches.append(batch)
            continue
        _, decision = promoted
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

    promoted_by_source = {
        batch.record.source_file: promoted_records[batch.record.record_id]
        for batch in batches
        if batch.record.record_id in promoted_records
    }
    updated_anomalies = tuple(
        replace(
            anomaly,
            review_state=(
                ReviewState.HIGH_SUSPICION_HIGH
                if promoted_by_source[anomaly.source_file][1].direction == "high"
                else ReviewState.HIGH_SUSPICION_LOW
            ),
            message="有效辅助证据支持的高度疑似，非正式错误或责任结论",
        )
        if anomaly.source_file in promoted_by_source
        and anomaly.rule_id == promoted_by_source[anomaly.source_file][0].rule_id
        and anomaly.field == promoted_by_source[anomaly.source_file][0].target_field
        else anomaly
        for anomaly in anomalies
    )
    return AppliedReviewEvidence(tuple(updated_batches), updated_anomalies)
