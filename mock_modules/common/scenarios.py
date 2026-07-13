from pathlib import Path


def scenario_for(inputs: list[str]) -> str:
    names = " ".join(Path(path).name.lower() for path in inputs)
    for scenario in [
        "confirm",
        "partial",
        "fail",
        "invalid",
        "timeout",
        "crash",
        "ai",
        "knowledge",
    ]:
        if scenario in names:
            return scenario
    return "success"
