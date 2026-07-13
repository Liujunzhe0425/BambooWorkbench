from pathlib import Path

import pytest

from core.platform.path_safety import (
    resolve_contained_file,
    resolve_contained_target,
    resolve_path,
)


def test_resolve_path_normalizes_runtime_error(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "loop"
    original_resolve = Path.resolve

    def simulated_loop(path: Path, *args, **kwargs):
        if path == target:
            raise RuntimeError("simulated link loop")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", simulated_loop)

    with pytest.raises(ValueError, match="target path resolution failed.*link loop"):
        resolve_path(target, "target", strict=False)


def test_resolve_contained_file_rejects_protocol_link_without_os_privilege(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    protocol = root / "job.json"
    protocol.write_text("{}", encoding="utf-8")
    original_is_symlink = Path.is_symlink

    def simulated_link(path: Path) -> bool:
        return path == protocol or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", simulated_link)

    with pytest.raises(ValueError, match="protocol file must not be a link"):
        resolve_contained_file(protocol, root, "protocol file", reject_link=True)


def test_resolve_contained_target_rejects_simulated_external_resolution(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "output-final"
    outside = tmp_path / "outside"
    original_resolve = Path.resolve

    def simulated_escape(path: Path, *args, **kwargs):
        if path == target:
            return outside
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", simulated_escape)

    with pytest.raises(ValueError, match="final output is outside root"):
        resolve_contained_target(target, root, "final output", reject_link=True)


def test_resolve_contained_target_rejects_real_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "output-final"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Windows symlink privilege unavailable: {exc}")

    with pytest.raises(ValueError, match="link|outside root"):
        resolve_contained_target(link, root, "final output", reject_link=True)
