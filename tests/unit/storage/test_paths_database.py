import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from core.platform.installation import (
    complete_fresh_installation,
    inspect_installation,
    prepare_installation,
)
from core.platform.paths import AppPaths
from core.security.credentials import InMemoryCredentialStore
from core.storage import database as database_module
from core.storage.database import Database, Migration
from core.storage.settings import SettingsStore


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    opened = Database.open(AppPaths.for_root(tmp_path))
    try:
        yield opened
    finally:
        opened.close()


def test_paths_create_required_directories(tmp_path: Path) -> None:
    paths = AppPaths.for_root(tmp_path / "BambooWorkbench")

    paths.ensure()

    assert paths.database.parent.is_dir()
    assert paths.output.is_dir()
    assert paths.source.is_dir()
    assert paths.source_for_module("moisture").is_dir()
    assert paths.source_for_module("boiling").is_dir()
    assert paths.source_for_module("after_sales").is_dir()
    assert paths.modules.is_dir()
    assert paths.knowledge.is_dir()
    assert paths.tasks.is_dir()
    assert paths.logs.is_dir()
    assert paths.cache.is_dir()


def test_fresh_install_initializes_marker_defaults_and_clears_known_credentials(
    tmp_path: Path,
) -> None:
    paths = AppPaths.for_root(tmp_path / "fresh-install")
    existing_source = paths.source / "竹丝水分" / "用户文件.xlsx"
    existing_output = paths.output / "既有成果.txt"
    existing_source.parent.mkdir(parents=True)
    existing_source.write_text("source", encoding="utf-8")
    existing_output.parent.mkdir(parents=True)
    existing_output.write_text("output", encoding="utf-8")
    state = prepare_installation(paths)
    database = Database.open(paths)
    database.migrate()
    settings = SettingsStore(database)
    credentials = InMemoryCredentialStore()
    for credential_id in ("deepseek", "openai-compatible", "github-updates"):
        credentials.set_secret(credential_id, "secret")

    complete_fresh_installation(paths, state, settings, credentials)

    assert state.fresh is True
    assert inspect_installation(paths) is not None
    assert settings.get("ai_network_enabled") == "false"
    assert settings.get("output_dir") == str(paths.output)
    assert existing_source.read_text(encoding="utf-8") == "source"
    assert existing_output.read_text(encoding="utf-8") == "output"
    assert not any(
        credentials.has_secret(credential_id)
        for credential_id in ("deepseek", "openai-compatible", "github-updates")
    )
    database.close()


def test_existing_install_preserves_settings_credentials_and_instance_id(
    tmp_path: Path,
) -> None:
    paths = AppPaths.for_root(tmp_path / "existing-install")
    first = prepare_installation(paths)
    database = Database.open(paths)
    database.migrate()
    settings = SettingsStore(database)
    credentials = InMemoryCredentialStore()
    complete_fresh_installation(paths, first, settings, credentials)
    credentials.set_secret("deepseek", "secret")
    settings.set("ai_network_enabled", "true")
    settings.set("output_dir", "D:/custom-output")

    second = prepare_installation(paths)
    complete_fresh_installation(paths, second, settings, credentials)

    assert second.fresh is False
    assert second.instance_id == first.instance_id
    assert credentials.get_secret("deepseek") == "secret"
    assert settings.get("ai_network_enabled") == "true"
    assert settings.get("output_dir") == "D:/custom-output"
    database.close()


def test_database_migrates_once_and_settings_round_trip(database: Database) -> None:
    database.migrate()
    database.migrate()
    settings = SettingsStore(database)

    settings.set("output_dir", "D:/exports")
    settings.set("output_dir", "D:/revised-exports")

    assert settings.get("output_dir") == "D:/revised-exports"
    assert settings.get("missing", "fallback") == "fallback"
    assert (
        database.scalar("SELECT version FROM schema_version")
        == database_module.MIGRATIONS[-1].version
    )


def test_database_upgrades_v1_and_preserves_settings(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_migrations = database_module.MIGRATIONS
    monkeypatch.setattr(database_module, "MIGRATIONS", all_migrations[:1])
    database.migrate()
    SettingsStore(database).set("output_dir", "D:/保留/export")

    monkeypatch.setattr(database_module, "MIGRATIONS", all_migrations)
    database.migrate()

    assert (
        database.scalar("SELECT version FROM schema_version")
        == database_module.MIGRATIONS[-1].version
    )
    assert SettingsStore(database).get("output_dir") == "D:/保留/export"
    assert database.scalar(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("tasks",),
    ) == 1


def test_failed_migration_does_not_advance_version(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    database.migrate()
    current_version = database_module.MIGRATIONS[-1].version
    failing_migration = Migration(
        version=current_version + 1,
        statements=(
            "CREATE TABLE should_be_rolled_back (value TEXT)",
            "INSERT INTO missing_table(value) VALUES ('failure')",
        ),
    )
    monkeypatch.setattr(
        database_module,
        "MIGRATIONS",
        (*database_module.MIGRATIONS, failing_migration),
    )

    with pytest.raises(sqlite3.OperationalError):
        database.migrate()

    assert database.scalar("SELECT version FROM schema_version") == current_version
    assert (
        database.scalar(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("should_be_rolled_back",),
        )
        == 0
    )


def test_close_releases_database_file(tmp_path: Path) -> None:
    paths = AppPaths.for_root(tmp_path)
    database = Database.open(paths)
    database.migrate()

    database.close()

    paths.database.unlink()
    assert not paths.database.exists()
