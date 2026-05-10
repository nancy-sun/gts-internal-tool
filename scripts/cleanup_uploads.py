from datetime import datetime, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
DEFAULT_RETENTION_DAYS = 3
UPLOAD_CLEANUP_PATTERNS = (
    "*.xlsx",
    "preview_*.json",
    "generate_preview_*.json",
    "hs_upload_preview_*.json",
    "hs_generate_preview_*.json",
)


def cleanup_uploads(
    upload_dir: Path = UPLOAD_DIR,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now: datetime | None = None,
) -> list[Path]:
    if not upload_dir.exists():
        return []

    cutoff = (now or datetime.now()) - timedelta(days=retention_days)
    deleted_paths: list[Path] = []
    for pattern in UPLOAD_CLEANUP_PATTERNS:
        for path in upload_dir.glob(pattern):
            if should_delete(path, cutoff):
                path.unlink()
                deleted_paths.append(path)
    return deleted_paths


def should_delete(path: Path, cutoff: datetime) -> bool:
    if not path.is_file():
        return False
    modified_at = datetime.fromtimestamp(path.stat().st_mtime)
    return modified_at < cutoff


if __name__ == "__main__":
    deleted = cleanup_uploads()
    print(f"Deleted {len(deleted)} expired upload file(s).")
