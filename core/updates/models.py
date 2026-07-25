from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReleaseUpdate:
    version: str
    tag_name: str
    title: str
    notes_url: str
    asset_name: str
    asset_url: str
    asset_size: int
    sha256: str


def semantic_version(value: str) -> tuple[int, int, int]:
    parts = value.removeprefix("v").split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError("版本号必须使用 x.y.z 格式")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]
