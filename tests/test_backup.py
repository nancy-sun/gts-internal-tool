from pathlib import Path

import scripts.backup as backup


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
    database_file.write_text("db", encoding="utf-8")
    (uploads_dir / "upload.xlsx").write_text("upload", encoding="utf-8")
    (generated_dir / "quote.xlsx").write_text("generated", encoding="utf-8")
    (config_dir / "quotation_template.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(backup, "BACKUP_ROOT", backup_root)
    monkeypatch.setattr(
        backup,
        "BACKUP_SOURCES",
        [database_file, uploads_dir, generated_dir, config_dir],
    )

    backup_dir = backup.create_backup()

    assert backup_dir.parent == backup_root
    assert (backup_dir / "gts_catalogue.sqlite3").read_text(encoding="utf-8") == "db"
    assert (backup_dir / "uploads" / "upload.xlsx").read_text(encoding="utf-8") == "upload"
    assert (backup_dir / "generated" / "quote.xlsx").read_text(encoding="utf-8") == "generated"
    assert (backup_dir / "config" / "quotation_template.json").read_text(encoding="utf-8") == "{}"
