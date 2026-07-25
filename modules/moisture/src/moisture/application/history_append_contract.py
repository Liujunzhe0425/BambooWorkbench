"""Frozen identities and choices for the standard-summary append workflow."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from moisture.ports.writers import WorkbookBatch

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class HistoryConflictChoice(StrEnum):
    KEEP_EXISTING = "keep_existing"
    USE_NEW = "use_new"


@dataclass(frozen=True, slots=True)
class HistoryAppendConflict:
    """One stable record ID whose historical and new business content differ."""

    record_id: str
    existing_fingerprint: str
    new_fingerprint: str
    existing_display_name: str
    new_display_name: str

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ValueError("record_id must not be empty")
        for value in (self.existing_fingerprint, self.new_fingerprint):
            if not _SHA256.fullmatch(value):
                raise ValueError("conflict fingerprints must be lowercase SHA-256")
        if self.existing_fingerprint == self.new_fingerprint:
            raise ValueError("equal business content is not a conflict")
        for value in (self.existing_display_name, self.new_display_name):
            if (
                not value
                or "/" in value
                or "\\" in value
                or any(ord(character) < 32 for character in value)
            ):
                raise ValueError("conflict display names must be safe file names")


def provisional_batch_key(batch: WorkbookBatch) -> str:
    """Use the existing stable record ID until a business batch key is approved."""

    return batch.record.record_id


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _material_type(value: str | None) -> str | None:
    normalized = value.strip() if isinstance(value, str) else value
    return "原竹丝" if normalized in {"竹丝", "原竹丝"} else normalized


def batch_business_fingerprint(batch: WorkbookBatch) -> str:
    """Hash values recoverable from a standard summary, excluding derived rule state."""

    record = batch.record
    payload = {
        "record_id": record.record_id,
        "supplier": record.supplier,
        "material_type": _material_type(record.material_type),
        "arrival_date": record.arrival_date.isoformat() if record.arrival_date else None,
        "test_date": record.test_date.isoformat() if record.test_date else None,
        "total_weight_kg": _decimal(record.total_weight_kg),
        "samples": [
            {
                "sample_index": sample.sample_index,
                "value_used_for_statistics": _decimal(sample.value_used_for_statistics),
            }
            for sample in record.samples
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def history_conflict_confirmation_id(
    root_job_id: str,
    conflict: HistoryAppendConflict,
) -> str:
    identity = json.dumps(
        {
            "root_job_id": root_job_id,
            "field": "history_record_conflict",
            "record_id": conflict.record_id,
            "existing_fingerprint": conflict.existing_fingerprint,
            "new_fingerprint": conflict.new_fingerprint,
            "options": tuple(choice.value for choice in HistoryConflictChoice),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"msr-confirm-{hashlib.sha256(identity).hexdigest()[:24]}"


def build_history_conflict_prompt(
    root_job_id: str,
    conflict: HistoryAppendConflict,
) -> dict[str, object]:
    """Build the strict confirmation prompt consumed later by H-C2."""

    return {
        "confirmation_id": history_conflict_confirmation_id(root_job_id, conflict),
        "field": "history_record_conflict",
        "reason": "历史汇总与新输入包含相同批次但业务内容不同，请确认新汇总采用哪一份",
        "suggested_value": HistoryConflictChoice.KEEP_EXISTING.value,
        "options": [choice.value for choice in HistoryConflictChoice],
        "confidence": 0.5,
        "blocking": True,
        "batch_applicable": False,
        "rememberable": False,
        "source": {
            "source_file": (f"{conflict.existing_display_name} ↔ {conflict.new_display_name}"),
            "sheet": "竹丝含水率统计",
            "cell_or_range": conflict.record_id,
        },
    }
