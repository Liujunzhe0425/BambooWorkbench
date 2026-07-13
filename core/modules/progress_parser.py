from core.contracts.progress import ProgressEvent


def parse_progress(line: bytes) -> ProgressEvent:
    return ProgressEvent.model_validate_json(line.decode("utf-8").strip())
