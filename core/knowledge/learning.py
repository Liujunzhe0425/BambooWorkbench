"""Deterministic, module-isolated preference evidence and matching."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from core.contracts.result import LearningDescriptor
from core.storage.database import Database


@dataclass(frozen=True, slots=True)
class PreferenceMatch:
    candidate_id: str
    candidate_label: str
    weight: int
    context_fields: tuple[str, ...]
    evidence_count: int


class LearningEvidenceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def stage(
        self,
        *,
        job_id: str,
        module_id: str,
        year: int,
        month: int,
        confirmation_id: str,
        descriptor: LearningDescriptor,
        candidate_id: str,
    ) -> str:
        candidates = {item.candidate_id: item.label for item in descriptor.candidates}
        if candidate_id not in candidates:
            raise ValueError("learning answer is not a declared candidate")
        evidence_id = uuid4().hex
        self.database.execute(
            "INSERT INTO learning_evidence("
            "evidence_id, job_id, module_id, year, month, confirmation_id, "
            "learning_key, field, context_json, context_levels_json, candidate_id, "
            "candidate_label, base_suggestion_id, weight, active, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?)",
            (
                evidence_id,
                job_id,
                module_id,
                year,
                month,
                confirmation_id,
                descriptor.learning_key,
                descriptor.field,
                _canonical_json(descriptor.context),
                _canonical_json(descriptor.context_levels),
                candidate_id,
                candidates[candidate_id],
                descriptor.base_suggestion_id,
                _now(),
            ),
        )
        return evidence_id

    def has_staged_for_job(self, job_id: str) -> bool:
        return bool(
            self.database.scalar(
                "SELECT COUNT(*) FROM learning_evidence WHERE job_id = ?", (job_id,)
            )
        )

    def activate_for_job(self, job_id: str) -> None:
        self.database.execute(
            "UPDATE learning_evidence SET active = 1, activated_at = ?, "
            "revoked_at = NULL, revoked_reason = NULL WHERE job_id = ? AND active = 0",
            (_now(), job_id),
        )

    def revoke_job(self, job_id: str, reason: str) -> None:
        self._revoke("job_id = ?", (job_id,), "task", reason)

    def revoke_evidence(self, evidence_id: str, reason: str) -> None:
        self._revoke("evidence_id = ?", (evidence_id,), "evidence", reason)

    def reset_scenario(self, module_id: str, learning_key: str, reason: str) -> None:
        self._revoke(
            "module_id = ? AND learning_key = ?",
            (module_id, learning_key),
            "scenario",
            reason,
            module_id=module_id,
            learning_key=learning_key,
        )

    def reset_module(self, module_id: str, reason: str) -> None:
        self._revoke(
            "module_id = ?",
            (module_id,),
            "module",
            reason,
            module_id=module_id,
        )

    def preference(
        self,
        module_id: str,
        descriptor: LearningDescriptor,
    ) -> PreferenceMatch | None:
        if not descriptor.preference_adjustable:
            return None
        rows = self.database.connection.execute(
            "SELECT * FROM learning_evidence WHERE module_id = ? AND learning_key = ? "
            "AND active = 1 ORDER BY created_at, evidence_id",
            (module_id, descriptor.learning_key),
        ).fetchall()
        allowed = {candidate.candidate_id: candidate.label for candidate in descriptor.candidates}
        for level in descriptor.context_levels:
            expected = {key: descriptor.context[key] for key in level}
            matching = []
            for row in rows:
                if row["candidate_id"] not in allowed:
                    continue
                context = json.loads(str(row["context_json"]))
                if all(context.get(key) == value for key, value in expected.items()):
                    matching.append(row)
            if not matching:
                continue
            weights = Counter()
            counts = Counter()
            for row in matching:
                weights[str(row["candidate_id"])] += int(row["weight"])
                counts[str(row["candidate_id"])] += 1
            highest = max(weights.values())
            winners = sorted(
                candidate for candidate, weight in weights.items() if weight == highest
            )
            candidate_id = (
                descriptor.base_suggestion_id
                if descriptor.base_suggestion_id in winners
                else winners[0]
            )
            return PreferenceMatch(
                candidate_id=candidate_id,
                candidate_label=allowed[candidate_id],
                weight=weights[candidate_id],
                context_fields=tuple(level),
                evidence_count=counts[candidate_id],
            )
        return None

    def list_module(self, module_id: str) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT * FROM learning_evidence WHERE module_id = ? "
            "ORDER BY learning_key, created_at DESC",
            (module_id,),
        ).fetchall()
        records = [dict(row) for row in rows]
        for record in records:
            record["context"] = json.loads(str(record.pop("context_json")))
            record["context_levels"] = json.loads(str(record.pop("context_levels_json")))
            record["active"] = bool(record["active"])
        return records

    def _revoke(
        self,
        where: str,
        parameters: tuple[object, ...],
        scope: str,
        reason: str,
        *,
        module_id: str | None = None,
        learning_key: str | None = None,
    ) -> None:
        now = _now()
        with self.database.connection:
            query = (
                "SELECT evidence_id, module_id FROM learning_evidence "
                f"WHERE {where} AND active = 1"
            )
            rows = self.database.connection.execute(query, parameters).fetchall()
            self.database.connection.execute(
                f"UPDATE learning_evidence SET active = 0, revoked_at = ?, revoked_reason = ? "
                f"WHERE {where} AND active = 1",
                (now, reason, *parameters),
            )
            if rows or scope in {"scenario", "module"}:
                self.database.connection.execute(
                    "INSERT INTO learning_actions("
                    "action_id, scope, module_id, learning_key, evidence_id, reason, created_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        uuid4().hex,
                        scope,
                        module_id or (str(rows[0]["module_id"]) if rows else "unknown"),
                        learning_key,
                        str(rows[0]["evidence_id"]) if scope == "evidence" and rows else None,
                        reason,
                        now,
                    ),
                )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now().astimezone().isoformat()
