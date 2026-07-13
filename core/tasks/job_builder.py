from pathlib import Path

from core.contracts.enums import JobPhase, ModuleId, RunMode
from core.contracts.job import JobRequest


def build_draft_job(
    job_id: str, module_id: ModuleId, snapshots: list[Path], task_dir: Path
) -> JobRequest:
    return JobRequest(
        schema_version="1.0",
        job_id=job_id,
        module_id=module_id,
        phase=JobPhase.DRAFT,
        run_mode=RunMode.SINGLE if len(snapshots) == 1 else RunMode.BATCH,
        input_files=[str(path.resolve()) for path in snapshots],
        output_dir=str((task_dir / "output-draft").resolve()),
        module_config_file=None,
        ai_enabled=False,
        allowed_knowledge_scopes=["shared", module_id.value],
    )
