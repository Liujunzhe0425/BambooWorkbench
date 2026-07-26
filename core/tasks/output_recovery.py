"""Incremental output-manifest scan and conservative database recovery."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from core.contracts.result import OutputArtifact
from core.platform.installation import inspect_installation
from core.platform.paths import AppPaths
from core.storage.repositories.monthly import MonthlyRepository
from core.storage.repositories.output_roots import OutputRootRepository
from core.storage.repositories.tasks import TaskRepository
from core.tasks.output_manifest import scan_output_manifests, validate_output_manifest


class OutputRecoveryService:
    def __init__(
        self,
        paths: AppPaths,
        tasks: TaskRepository,
        monthly: MonthlyRepository,
        output_roots: OutputRootRepository,
    ) -> None:
        self.paths = paths
        self.tasks = tasks
        self.monthly = monthly
        self.output_roots = output_roots

    def scan(self) -> dict[str, int]:
        self._mark_registered_integrity()
        installation = inspect_installation(self.paths)
        if installation is None:
            return {"valid": 0, "recovered": 0, "conflicts": 0}
        manifests = [
            (path, payload)
            for path, payload in scan_output_manifests(self.output_roots.read_registry())
            if payload.get("installation_id") == installation.instance_id
        ]
        manifests.sort(key=lambda item: str(item[1]["committed_at"]))
        for path, payload in manifests:
            self._recover_task_outputs(path, payload)
        official_manifests = [item for item in manifests if bool(item[1]["official"])]
        groups: defaultdict[tuple[str, int, int], list[tuple[Path, dict[str, object]]]] = (
            defaultdict(list)
        )
        for item in official_manifests:
            payload = item[1]
            groups[
                (str(payload["module_id"]), int(payload["year"]), int(payload["month"]))
            ].append(item)
        recovered = 0
        conflicts = 0
        for (_module_id, _year, _month), candidates in groups.items():
            selected = self._select_candidate(candidates)
            if selected is None:
                conflicts += 1
                for _path, payload in candidates:
                    if self.tasks.exists(str(payload["job_id"])):
                        self.tasks.set_result_integrity(str(payload["job_id"]), "conflict")
                continue
            if self._recover_manifest(*selected):
                recovered += 1
        return {"valid": len(manifests), "recovered": recovered, "conflicts": conflicts}

    def _mark_registered_integrity(self) -> None:
        known_roots = self.output_roots.read_registry()
        for task in self.tasks.list_recent(limit=100_000):
            job_id = str(task["job_id"])
            outputs = self.tasks.list_outputs(job_id)
            if not outputs:
                continue
            paths = [Path(str(record["path"])) for record in outputs]
            if any(not path.is_file() for path in paths):
                self.tasks.set_result_integrity(job_id, "missing")
                continue
            try:
                manifests = {
                    _manifest_for_output(path, known_roots)
                    for path in paths
                }
                if len(manifests) != 1:
                    raise ValueError("outputs do not share one result folder")
                validate_output_manifest(next(iter(manifests)))
            except (OSError, ValueError):
                self.tasks.set_result_integrity(job_id, "invalid")
            else:
                self.tasks.set_result_integrity(job_id, "ok")

    @staticmethod
    def _select_candidate(
        candidates: list[tuple[Path, dict[str, object]]],
    ) -> tuple[Path, dict[str, object]] | None:
        if len(candidates) == 1:
            return candidates[0]
        by_job = {str(payload["job_id"]): (path, payload) for path, payload in candidates}
        replaced = {
            str(payload["replacement_for_job_id"])
            for _path, payload in candidates
            if payload.get("replacement_for_job_id")
        }
        heads = [item for job_id, item in by_job.items() if job_id not in replaced]
        if len(heads) != 1:
            return None
        seen: set[str] = set()
        current = heads[0]
        while True:
            job_id = str(current[1]["job_id"])
            if job_id in seen:
                return None
            seen.add(job_id)
            predecessor = current[1].get("replacement_for_job_id")
            if predecessor is None:
                break
            if str(predecessor) not in by_job:
                return None
            current = by_job[str(predecessor)]
        return heads[0] if len(seen) == len(by_job) else None

    def _recover_manifest(self, path: Path, payload: dict[str, object]) -> bool:
        created = self._recover_task_outputs(path, payload)
        job_id = str(payload["job_id"])
        snapshot_path = self.paths.tasks / job_id / "monthly-snapshot.json"
        snapshot_payload = payload["snapshot"]
        if not snapshot_path.is_file() or _sha256(snapshot_path) != snapshot_payload["sha256"]:
            self.tasks.set_result_integrity(job_id, "invalid")
            return created
        snapshot = self.monthly.get_snapshot_for_job(job_id)
        if snapshot is None:
            snapshot_id = self.monthly.register_snapshot(
                module_id=str(payload["module_id"]),
                year=int(payload["year"]),
                month=int(payload["month"]),
                job_id=job_id,
                contract_version="1.0",
                snapshot_format=str(snapshot_payload["format"]),
                path=snapshot_path,
                size=snapshot_path.stat().st_size,
                sha256=str(snapshot_payload["sha256"]),
            )
        else:
            snapshot_id = str(snapshot["snapshot_id"])
        self.monthly.recover_official_slot(
            module_id=str(payload["module_id"]),
            year=int(payload["year"]),
            month=int(payload["month"]),
            job_id=job_id,
            snapshot_id=snapshot_id,
            committed_at=str(payload["committed_at"]),
            transaction_id=str(payload.get("transaction_id") or uuid4().hex),
        )
        return True

    def _recover_task_outputs(self, path: Path, payload: dict[str, object]) -> bool:
        job_id = str(payload["job_id"])
        created = False
        if not self.tasks.exists(job_id):
            self.tasks.create(
                job_id,
                str(payload["module_id"]),
                "success",
                str(payload["created_at"]),
                task_name=str(payload["task_name"]),
                period_year=int(payload["year"]),
                period_month=int(payload["month"]),
            )
            created = True
        internal_result = self.paths.tasks / job_id / "output-final" / "result.json"
        self.tasks.update_status(
            job_id,
            "success",
            result_path=str(internal_result) if internal_result.is_file() else None,
        )
        artifacts = [
            OutputArtifact(
                type=str(record["type"]),
                path=str(path.parent / str(record["path"])),
                label=str(record["label"]),
                mime_type=str(record["mime_type"]),
            )
            for record in payload["outputs"]
        ]
        self.tasks.replace_outputs(job_id, artifacts)
        self.tasks.set_result_integrity(job_id, "ok")
        return created


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_for_output(path: Path, roots: tuple[Path, ...]) -> Path:
    resolved = path.resolve(strict=True)
    for raw_root in roots:
        try:
            root = raw_root.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_relative_to(root):
            relative = resolved.relative_to(root)
            if len(relative.parts) >= 2:
                return root / relative.parts[0] / ".bamboo-task.json"
    raise ValueError("output is not inside a known output root")
