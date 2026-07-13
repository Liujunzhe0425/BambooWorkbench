import json
import os
import tempfile
from pathlib import Path

from core.ai.gateway import AIGateway, ConsentDenied, GatewayRequest
from core.contracts.service_request import ServiceRequest
from core.knowledge.models import KnowledgeRecord
from core.knowledge.repository import KnowledgeRepository
from core.platform.path_safety import (
    resolve_contained_directory,
    resolve_contained_target,
    resolve_path,
)
from core.security.redaction import RedactionPreview


class KnowledgeScopeDenied(RuntimeError):
    pass


class InvalidServiceRequest(RuntimeError):
    pass


def _knowledge_payload(record: KnowledgeRecord) -> dict[str, object]:
    return {
        "record_id": record.record_id,
        "namespace": record.namespace,
        "title": record.title,
        "content": record.content,
        "source_kind": record.source_kind.value,
        "source_path": record.source_path,
    }


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


class ServiceOrchestrator:
    def __init__(
        self,
        knowledge_repository: KnowledgeRepository,
        ai_gateway: AIGateway,
        provider_id: str = "mock",
        model: str = "mock-model",
    ) -> None:
        self.knowledge_repository = knowledge_repository
        self.ai_gateway = ai_gateway
        self.provider_id = provider_id
        self.model = model

    def preview_ai(
        self,
        task_id: str,
        module_id: str,
        request: ServiceRequest,
    ) -> RedactionPreview:
        if request.service != "ai":
            raise InvalidServiceRequest("only AI requests have outbound previews")
        return self.ai_gateway.preview(
            GatewayRequest(
                task_id=task_id,
                module_id=module_id,
                provider_id=self.provider_id,
                model=self.model,
                payload=request.payload,
            )
        )

    def resolve(
        self,
        task_id: str,
        module_id: str,
        allowed_namespaces: set[str],
        requests: list[ServiceRequest | dict[str, object]],
        ai_consent: dict[str, bool],
        task_dir: Path,
    ) -> Path:
        validated = [ServiceRequest.model_validate(item) for item in requests]
        request_ids = [item.request_id for item in validated]
        if len(request_ids) != len(set(request_ids)):
            raise InvalidServiceRequest("service request IDs must be unique")

        responses: list[dict[str, object]] = []
        for item in validated:
            if item.service == "knowledge":
                responses.append(
                    self._resolve_knowledge(item, allowed_namespaces=allowed_namespaces)
                )
                continue
            responses.append(
                self._resolve_ai(
                    task_id,
                    module_id,
                    item,
                    allowed=ai_consent.get(item.request_id),
                )
            )

        root = resolve_path(task_dir, "service task directory", strict=True)
        if not root.is_dir() or task_dir.is_symlink():
            raise ValueError("service task directory must be a real directory")
        protocol_target = resolve_contained_target(
            root / "protocol",
            root,
            "service protocol directory",
            reject_link=True,
        )
        if protocol_target.exists() and not protocol_target.is_dir():
            raise ValueError("service protocol path must be a directory")
        protocol_target.mkdir(exist_ok=True)
        protocol = resolve_contained_directory(
            protocol_target,
            root,
            "service protocol directory",
            reject_link=True,
        )
        target = resolve_contained_target(
            protocol / "service-response.json",
            protocol,
            "service response",
            reject_link=True,
        )
        _atomic_json(
            target,
            {
                "schema_version": "1.0",
                "task_id": task_id,
                "module_id": module_id,
                "responses": responses,
            },
        )
        return target

    def _resolve_knowledge(
        self,
        request: ServiceRequest,
        *,
        allowed_namespaces: set[str],
    ) -> dict[str, object]:
        namespace = request.scope
        if namespace is None or namespace not in allowed_namespaces:
            raise KnowledgeScopeDenied(namespace or "<missing>")
        query = request.payload.get("query")
        if not isinstance(query, str) or not query.strip():
            raise InvalidServiceRequest("knowledge request requires a non-empty query")
        hits = self.knowledge_repository.search(namespace, query)
        return {
            "request_id": request.request_id,
            "service": "knowledge",
            "status": "ok",
            "items": [_knowledge_payload(hit) for hit in hits],
        }

    def _resolve_ai(
        self,
        task_id: str,
        module_id: str,
        request: ServiceRequest,
        *,
        allowed: bool | None,
    ) -> dict[str, object]:
        try:
            response = self.ai_gateway.complete(
                GatewayRequest(
                    task_id=task_id,
                    module_id=module_id,
                    provider_id=self.provider_id,
                    model=self.model,
                    payload=request.payload,
                ),
                allowed,
            )
        except ConsentDenied:
            return {
                "request_id": request.request_id,
                "service": "ai",
                "status": "denied",
                "text": None,
            }
        return {
            "request_id": request.request_id,
            "service": "ai",
            "status": "ok",
            "text": response.text,
        }
