from datetime import datetime
from pathlib import Path
import sqlite3

import app.services.backup as auto_backup
import scripts.backup as backup
from app.config import get_settings


def test_create_backup_copies_database_uploads_generated_and_config(tmp_path: Path, monkeypatch):
    source_root = tmp_path / "source"
    backup_root = tmp_path / "backups"
    data_dir = source_root / "data"
    uploads_dir = source_root / "uploads"
    generated_dir = source_root / "generated"
    config_dir = source_root / "config"
    data_dir.mkdir(parents=True)
    uploads_dir.mkdir()
    generated_dir.mkdir()
    config_dir.mkdir()
    database_file = data_dir / "gts_catalogue.sqlite3"
    with sqlite3.connect(database_file) as connection:
        connection.execute("CREATE TABLE backup_test (value TEXT)")
        connection.execute("INSERT INTO backup_test (value) VALUES ('db')")
    (uploads_dir / "upload.xlsx").write_text("upload", encoding="utf-8")
    (generated_dir / "quote.xlsx").write_text("generated", encoding="utf-8")
    (config_dir / "quotation_template.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(backup, "BACKUP_ROOT", backup_root)
    monkeypatch.setattr(
        backup,
        "BACKUP_SOURCES",
        [database_file, uploads_dir, generated_dir, config_dir],
    )

    backup_dir = backup.create_backup(now=datetime(2026, 5, 10, 18, 30, 45))

    assert backup_dir.parent == backup_root
    assert backup_dir.name == "2026-05-10_183045"
    with sqlite3.connect(backup_dir / "gts_catalogue.sqlite3") as connection:
        value = connection.execute("SELECT value FROM backup_test").fetchone()[0]
    assert value == "db"
    assert (backup_dir / "uploads" / "upload.xlsx").read_text(encoding="utf-8") == "upload"
    assert (backup_dir / "generated" / "quote.xlsx").read_text(encoding="utf-8") == "generated"
    assert (backup_dir / "config" / "quotation_template.json").read_text(encoding="utf-8") == "{}"


def test_create_auto_backup_uses_timestamp_and_safe_reason(
    tmp_path: Path,
    monkeypatch,
):
    database_file = tmp_path / "gts.sqlite3"
    backup_dir = tmp_path / "auto-backups"
    with sqlite3.connect(database_file) as connection:
        connection.execute("CREATE TABLE backup_test (value TEXT)")
        connection.execute("INSERT INTO backup_test (value) VALUES ('auto')")

    class FixedDatetime:
        @classmethod
        def now(cls):
            return datetime(2026, 5, 16, 14, 25, 30)

    monkeypatch.setenv("SHARED_ACCESS_CODE", "test-access-code")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-key")
    monkeypatch.setenv("PRODUCT_EDIT_PASSWORD", "55123511")
    monkeypatch.setenv("DATABASE_PATH", str(database_file))
    get_settings.cache_clear()
    monkeypatch.setattr(auto_backup, "AUTO_BACKUP_DIR", backup_dir)
    monkeypatch.setattr(auto_backup, "datetime", FixedDatetime)

    backup_file = auto_backup.create_auto_backup("full quotation import!")

    assert backup_file.parent == backup_dir
    assert backup_file.name == "20260516_142530_full-quotation-import.sqlite3"
    with sqlite3.connect(backup_file) as connection:
        value = connection.execute("SELECT value FROM backup_test").fetchone()[0]
    assert value == "auto"
    get_settings.cache_clear()
