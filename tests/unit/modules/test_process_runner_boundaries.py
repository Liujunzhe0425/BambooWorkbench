from pathlib import Path

import pytest

from core.modules.process_runner import resolve_contained_file


def test_resolve_contained_file_accepts_regular_file(tmp_path: Path) -> None:
    root = tmp_path / "output"
    root.mkdir()
    result = root / "result.json"
    result.write_text("{}", encoding="utf-8")

    assert resolve_contained_file(result, root, "result.json") == result.resolve()


def test_resolve_contained_file_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "output"
    root.mkdir()
    outside = tmp_path / "result.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="outside output_dir"):
        resolve_contained_file(outside, root, "result.json")


def test_resolve_contained_file_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "output"
    root.mkdir()
    outside = tmp_path / "result.json"
    outside.write_text("{}", encoding="utf-8")
    link = root / "result.json"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Windows symlink privilege unavailable: {exc}")

    with pytest.raises(ValueError, match="outside output_dir"):
        resolve_contained_file(link, root, "result.json")


@pytest.mark.parametrize("loop_target", ["root", "file"])
def test_resolve_contained_file_normalizes_symlink_loop_runtime_error(
    tmp_path: Path, monkeypatch, loop_target: str
) -> None:
    root = tmp_path / "output"
    root.mkdir()
    result = root / "result.json"
    result.write_text("{}", encoding="utf-8")
    original_resolve = Path.resolve

    def simulated_loop(path: Path, *args, **kwargs):
        target = root if loop_target == "root" else result
        if path == target:
            raise RuntimeError("Symlink loop from simulated test")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", simulated_loop)

    with pytest.raises(ValueError, match="path resolution failed.*Symlink loop"):
        resolve_contained_file(result, root, "result.json")
