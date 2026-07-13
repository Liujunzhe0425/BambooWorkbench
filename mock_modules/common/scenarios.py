from pathlib import Path

ADVERTISED_SCENARIOS = (
    "confirm",
    "partial",
    "fail",
    "invalid",
    "timeout",
    "crash",
    "ai",
    "knowledge",
)


def scenario_for(inputs: list[str]) -> str:
    names = " ".join(Path(path).name.lower() for path in inputs)
    for scenario in ADVERTISED_SCENARIOS:
        if scenario in names:
            return scenario
    return "success"
