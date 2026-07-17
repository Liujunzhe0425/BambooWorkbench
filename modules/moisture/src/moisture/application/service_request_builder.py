"""Declare bounded framework service requests; never invoke a service."""

from __future__ import annotations

import hashlib
import json


def _identity(root_job_id: str, service: str, rule_hash: str, candidate_digest: str) -> str:
    encoded = json.dumps(
        {
            "root_job_id": root_job_id,
            "module": "moisture",
            "service": service,
            "rule_hash": rule_hash,
            "candidate_digest": candidate_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def build_knowledge_request(
    *,
    root_job_id: str,
    allowed_scopes: tuple[str, ...],
    needed: bool,
    rule_hash: str,
    candidate_digest: str,
) -> dict[str, object] | None:
    """Build at most one privacy-minimal knowledge guidance request."""

    if not needed:
        return None
    normalized = {scope.strip().casefold() for scope in allowed_scopes}
    scope = "moisture" if "moisture" in normalized else "shared" if "shared" in normalized else None
    if scope is None:
        return None
    query = "竹丝水分规则适用范围复核指导"
    if len(query.encode("utf-8")) > 200:  # defensive contract guard
        raise ValueError("knowledge query exceeds 200 UTF-8 bytes")
    return {
        "request_id": (
            "msr-knowledge-"
            f"{_identity(root_job_id, 'knowledge', rule_hash, candidate_digest)}"
        ),
        "service": "knowledge",
        "scope": scope,
        "purpose": "获取水分规则适用范围指导",
        "payload": {"query": query},
        "requires_user_consent": False,
    }
