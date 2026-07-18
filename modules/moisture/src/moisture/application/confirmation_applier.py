"""Strictly apply rebuilt draft confirmations to a fresh deterministic outcome."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation

from moisture.adapters.rules.builtin_evaluators import evaluate_rules
from moisture.application.run_result import InternalAnomaly, ReviewState
from moisture.application.screening_presentation import (
    screening_bounds,
    screening_suggestion,
)
from moisture.contract.confirmation_reader import ConfirmationBundle
from moisture.domain.enums import DisplayColor, ScreenStatus
from moisture.domain.models import RuleHit, ScreeningDecision
from moisture.domain.statistics import compute_batch_statistics
from moisture.ports.writers import WorkbookBatch


class ConfirmationApplicationError(ValueError):
    """A confirmation answer cannot be safely bound to the rebuilt draft."""


@dataclass(frozen=True, slots=True)
class ConfirmationApplication:
    batches: tuple[WorkbookBatch, ...]
    anomalies: tuple[InternalAnomaly, ...]


def extract_default_year_answer(
    prompts: tuple[Mapping[str, object], ...],
    bundle: ConfirmationBundle,
) -> tuple[int | None, tuple[Mapping[str, object], ...], ConfirmationBundle]:
    """Extract one strict job-level year answer and remove it from normal replay."""

    year_prompts = tuple(prompt for prompt in prompts if prompt.get("field") == "default_year")
    if not year_prompts:
        return None, prompts, bundle
    if len(year_prompts) != 1:
        raise ConfirmationApplicationError("default year confirmation is ambiguous")
    year_id = str(year_prompts[0].get("confirmation_id", ""))
    matches = tuple(answer for answer in bundle.answers if answer.confirmation_id == year_id)
    if len(matches) != 1:
        raise ConfirmationApplicationError("default year answer is missing or duplicated")
    answer = matches[0]
    if answer.remember_mapping:
        raise ConfirmationApplicationError("default year cannot be remembered as a mapping")
    source = year_prompts[0].get("source")
    source_file = source.get("source_file", "") if isinstance(source, Mapping) else ""
    count_match = re.fullmatch(r"批量输入（(\d+) 个文件）", str(source_file))
    if count_match is not None and int(count_match.group(1)) > 1 and not answer.apply_to_batch:
        raise ConfirmationApplicationError("default year must be applied to the whole batch")
    value = answer.value
    if isinstance(value, bool):
        raise ConfirmationApplicationError("default year must be a four digit year")
    if isinstance(value, int):
        year = value
    elif isinstance(value, str) and len(value.strip()) == 4 and value.strip().isdigit():
        year = int(value.strip())
    else:
        raise ConfirmationApplicationError("default year must be a four digit year")
    if not 1900 <= year <= 2100:
        raise ConfirmationApplicationError("default year is outside the supported range")
    remaining_prompts = tuple(prompt for prompt in prompts if prompt.get("field") != "default_year")
    remaining_bundle = ConfirmationBundle(
        schema_version=bundle.schema_version,
        job_id=bundle.job_id,
        answers=tuple(item for item in bundle.answers if item.confirmation_id != year_id),
    )
    return year, remaining_prompts, remaining_bundle


def _source(prompt: Mapping[str, object]) -> str:
    value = prompt.get("source")
    if not isinstance(value, Mapping) or not isinstance(value.get("source_file"), str):
        raise ConfirmationApplicationError("confirmation source is invalid")
    return value["source_file"]


def _validate_answers(
    prompts: tuple[Mapping[str, object], ...], bundle: ConfirmationBundle
) -> dict[str, object]:
    prompt_by_id = {str(prompt["confirmation_id"]): prompt for prompt in prompts}
    explicit: dict[str, object] = {}
    batch_answers: list[tuple[Mapping[str, object], object]] = []
    for answer in bundle.answers:
        prompt = prompt_by_id.get(answer.confirmation_id)
        if prompt is None:
            raise ConfirmationApplicationError("confirmation ID was not rebuilt")
        options = prompt.get("options")
        if not isinstance(options, (list, tuple)) or not any(
            type(answer.value) is type(option) and answer.value == option for option in options
        ):
            raise ConfirmationApplicationError("confirmation value is not an offered candidate")
        if answer.apply_to_batch and prompt.get("batch_applicable") is not True:
            raise ConfirmationApplicationError("confirmation does not allow batch application")
        if answer.remember_mapping and prompt.get("rememberable") is not True:
            raise ConfirmationApplicationError("confirmation does not allow remembered mapping")
        explicit[answer.confirmation_id] = answer.value
        if answer.apply_to_batch:
            batch_answers.append((prompt, answer.value))

    resolved = dict(explicit)
    for confirmation_id, prompt in prompt_by_id.items():
        if confirmation_id in resolved:
            continue
        if prompt.get("batch_applicable") is True:
            for answered_prompt, value in batch_answers:
                if answered_prompt.get("field") != prompt.get("field"):
                    continue
                options = prompt.get("options")
                if isinstance(options, (list, tuple)) and any(
                    type(value) is type(option) and value == option for option in options
                ):
                    resolved[confirmation_id] = value
                    break
        if confirmation_id not in resolved:
            raise ConfirmationApplicationError("confirmation answer is incomplete")
    return resolved


def _is_applicable(value: object) -> bool:
    return isinstance(value, str) and value.strip().casefold() in {
        "适用",
        "applicable",
        "yes",
        "true",
    }


def apply_confirmations(
    outcome: object,
    prompts: tuple[Mapping[str, object], ...],
    bundle: ConfirmationBundle,
) -> ConfirmationApplication:
    """Apply only the formula and rule-scope confirmation types emitted by T15."""

    answers = _validate_answers(prompts, bundle)
    prompt_by_id = {str(prompt["confirmation_id"]): prompt for prompt in prompts}
    non_rule_anomalies = [item for item in outcome.anomalies if item.rule_id is None]
    applied_batches: list[WorkbookBatch] = []

    for original_batch in outcome.batches:
        record = original_batch.record
        source = str(record.source_file) if record.source_file is not None else ""
        samples = list(record.samples)
        for confirmation_id, value in answers.items():
            prompt = prompt_by_id[confirmation_id]
            field = prompt.get("field")
            if (
                _source(prompt) != source
                or not isinstance(field, str)
                or not field.startswith("sample_")
            ):
                continue
            suffix = field.removeprefix("sample_")
            if not suffix.isdigit():
                raise ConfirmationApplicationError("formula confirmation field is invalid")
            try:
                selected = Decimal(str(value))
            except InvalidOperation as error:
                raise ConfirmationApplicationError(
                    "formula confirmation value is invalid"
                ) from error
            sample_index = int(suffix)
            matched = False
            for index, sample in enumerate(samples):
                if sample.sample_index == sample_index:
                    samples[index] = replace(sample, value_used_for_statistics=selected)
                    matched = True
                    break
            if not matched:
                raise ConfirmationApplicationError("formula confirmation sample is unavailable")

        updated_record = replace(record, samples=tuple(samples))
        statistics = compute_batch_statistics(updated_record)
        evaluation = evaluate_rules(updated_record, outcome.rule_package)
        decisions = list(evaluation.decisions)
        for pending in evaluation.pending_matches:
            matching = [
                (confirmation_id, prompt)
                for confirmation_id, prompt in prompt_by_id.items()
                if _source(prompt) == source
                and prompt.get("field") == (pending.target_field or "rule_scope")
            ]
            if not matching:
                continue
            confirmation_id, _ = matching[0]
            if not _is_applicable(answers[confirmation_id]):
                continue
            color = (
                DisplayColor.ORANGE
                if pending.direction == "high"
                else (DisplayColor.GREEN if pending.direction == "low" else DisplayColor.NONE)
            )
            status = (
                ScreenStatus.HIGH
                if color is DisplayColor.ORANGE
                else (
                    ScreenStatus.LOW if color is DisplayColor.GREEN else ScreenStatus.DATA_QUALITY
                )
            )
            hit = RuleHit(
                rule_id=pending.rule_id,
                message=pending.message,
                display_color=color,
                target_field=pending.target_field,
            )
            decisions.append(
                ScreeningDecision(
                    status=status,
                    rule_hits=(hit,),
                    display_color=color,
                    reason=pending.message,
                    target_field=pending.target_field,
                )
            )

        decision = decisions[0] if decisions else ScreeningDecision(status=ScreenStatus.NORMAL)
        lower_threshold, upper_threshold = screening_bounds(evaluation)
        for item in decisions:
            for hit in item.rule_hits:
                identity = hashlib.sha256(
                    f"{record.source_file_hash}:{hit.rule_id}:{hit.target_field}".encode()
                ).hexdigest()[:24]
                non_rule_anomalies.append(
                    InternalAnomaly(
                        anomaly_id=f"msr-anomaly-{identity}",
                        review_state=(
                            ReviewState.SUSPECT_HIGH
                            if hit.display_color is DisplayColor.ORANGE
                            else ReviewState.SUSPECT_LOW
                        ),
                        field=hit.target_field or "workbook",
                        message=hit.message,
                        source_file=record.source_file,
                        sheet=record.source_sheet,
                        rule_id=hit.rule_id,
                    )
                )
        applied_batches.append(
            replace(
                original_batch,
                record=updated_record,
                statistics=statistics,
                screening_decision=decision,
                final_display_color=decision.display_color,
                review_suggestion=screening_suggestion(
                    decision.status,
                    lower_threshold,
                    upper_threshold,
                ),
                lower_threshold=lower_threshold,
                upper_threshold=upper_threshold,
            )
        )

    return ConfirmationApplication(tuple(applied_batches), tuple(non_rule_anomalies))
