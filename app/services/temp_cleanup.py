from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from app.config import BASE_DIR


PREVIEW_FILE_PATTERNS = (
    "preview_*.json",
    "generate_preview_*.json",
    "hs_upload_preview_*.json",
    "hs_generate_preview_*.json",
)
DEFAULT_PREVIEW_DIR = BASE_DIR / "uploads"


def cleanup_stale_preview_files(max_age_hours: int = 24) -> int:
    return cleanup_stale_preview_files_in_directory(
        DEFAULT_PREVIEW_DIR,
        max_age_hours=max_age_hours,
    )


def cleanup_stale_preview_files_in_directory(
    preview_dir: Path,
    *,
    max_age_hours: int = 24,
    now: datetime | None = None,
) -> int:
    if max_age_hours < 0:
        raise ValueError("max_age_hours must be non-negative")
    if not preview_dir.exists():
        return 0

    cutoff = (now or datetime.now()) - timedelta(hours=max_age_hours)
    deleted_count = 0
    for path in known_preview_files(preview_dir):
        if should_delete_preview_file(path, cutoff):
            path.unlink()
            deleted_count += 1
    return deleted_count


def known_preview_files(preview_dir: Path):
    for pattern in PREVIEW_FILE_PATTERNS:
        yield from preview_dir.glob(pattern)


def should_delete_preview_file(path: Path, cutoff: datetime) -> bool:
    if not path.is_file():
        return False
    modified_at = datetime.fromtimestamp(path.stat().st_mtime)
    return modified_at < cutoff
