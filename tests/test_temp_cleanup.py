from datetime import datetime
import os
from pathlib import Path

from app.services.temp_cleanup import cleanup_stale_preview_files_in_directory


def test_cleanup_stale_preview_files_deletes_only_old_known_preview_files(
    tmp_path: Path,
) -> None:
    old_preview = tmp_path / "preview_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json"
    old_generate_preview = tmp_path / "generate_preview_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.json"
    recent_preview = tmp_path / "hs_upload_preview_cccccccccccccccccccccccccccccccc.json"
    unrelated_json = tmp_path / "notes.json"
    uploaded_excel = tmp_path / "dddddddddddddddddddddddddddddddd_upload.xlsx"
    generated_excel = tmp_path / "quotation.xlsx"

    for path in [
        old_preview,
        old_generate_preview,
        recent_preview,
        unrelated_json,
        uploaded_excel,
        generated_excel,
    ]:
        path.write_text("temporary", encoding="utf-8")

    old_time = datetime(2026, 5, 15, 8, 0, 0)
    recent_time = datetime(2026, 5, 16, 10, 0, 0)
    for path in [old_preview, old_generate_preview, unrelated_json, uploaded_excel, generated_excel]:
        set_mtime(path, old_time)
    set_mtime(recent_preview, recent_time)

    deleted_count = cleanup_stale_preview_files_in_directory(
        tmp_path,
        max_age_hours=24,
        now=datetime(2026, 5, 16, 12, 0, 0),
    )

    assert deleted_count == 2
    assert not old_preview.exists()
    assert not old_generate_preview.exists()
    assert recent_preview.exists()
    assert unrelated_json.exists()
    assert uploaded_excel.exists()
    assert generated_excel.exists()


def test_cleanup_stale_preview_files_keeps_backup_files(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    backup_dir = tmp_path / "backups" / "auto"
    upload_dir.mkdir()
    backup_dir.mkdir(parents=True)
    stale_preview = upload_dir / "hs_generate_preview_dddddddddddddddddddddddddddddddd.json"
    backup_file = backup_dir / "preview_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee.json"
    stale_preview.write_text("preview", encoding="utf-8")
    backup_file.write_text("backup", encoding="utf-8")
    set_mtime(stale_preview, datetime(2026, 5, 15, 8, 0, 0))
    set_mtime(backup_file, datetime(2026, 5, 15, 8, 0, 0))

    deleted_count = cleanup_stale_preview_files_in_directory(
        upload_dir,
        max_age_hours=24,
        now=datetime(2026, 5, 16, 12, 0, 0),
    )

    assert deleted_count == 1
    assert not stale_preview.exists()
    assert backup_file.exists()


def test_cleanup_stale_preview_files_ignores_missing_directory(tmp_path: Path) -> None:
    deleted_count = cleanup_stale_preview_files_in_directory(tmp_path / "missing")

    assert deleted_count == 0


def set_mtime(path: Path, modified_at: datetime) -> None:
    timestamp = modified_at.timestamp()
    os.utime(path, (timestamp, timestamp))
