from datetime import datetime
import os
from pathlib import Path

from scripts.cleanup_uploads import cleanup_uploads


def test_cleanup_uploads_deletes_excel_and_stale_preview_files_older_than_retention(
    tmp_path: Path,
) -> None:
    old_excel = tmp_path / "old.xlsx"
    old_preview = tmp_path / "preview_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json"
    recent_excel = tmp_path / "recent.xlsx"
    unrelated_file = tmp_path / "notes.txt"
    for path in [old_excel, old_preview, recent_excel, unrelated_file]:
        path.write_text("temporary", encoding="utf-8")

    set_mtime(old_excel, datetime(2026, 5, 1, 9, 0, 0))
    set_mtime(old_preview, datetime(2026, 5, 1, 9, 0, 0))
    set_mtime(recent_excel, datetime(2026, 5, 9, 9, 0, 0))
    set_mtime(unrelated_file, datetime(2026, 5, 1, 9, 0, 0))

    deleted = cleanup_uploads(
        upload_dir=tmp_path,
        retention_days=3,
        now=datetime(2026, 5, 10, 9, 0, 0),
    )

    assert deleted == [old_excel, old_preview]
    assert not old_excel.exists()
    assert not old_preview.exists()
    assert recent_excel.exists()
    assert unrelated_file.exists()


def test_cleanup_uploads_ignores_missing_upload_directory(tmp_path: Path) -> None:
    deleted = cleanup_uploads(upload_dir=tmp_path / "missing")

    assert deleted == []


def set_mtime(path: Path, modified_at: datetime) -> None:
    timestamp = modified_at.timestamp()
    os.utime(path, (timestamp, timestamp))
