from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_settings


def build_system_status() -> dict[str, Any]:
    settings = get_settings()
    database_file = settings.database_file
    uploads_dir = settings.upload_dir
    generated_dir = settings.generated_dir
    auto_backup_dir = settings.backup_dir / "auto"
    latest_backup = latest_file_mtime(auto_backup_dir)
    database_path = str(database_file) if settings.database_backend == "sqlite" else "PostgreSQL DATABASE_URL"

    return {
        "app_mode": settings.app_env,
        "database": {
            "path": database_path,
            "exists": database_file.exists() if settings.database_backend == "sqlite" else True,
            "size": format_bytes(file_size(database_file)) if settings.database_backend == "sqlite" else "由 RDS 管理",
        },
        "uploads": folder_status(uploads_dir),
        "generated": folder_status(generated_dir),
        "auto_backups": {
            **folder_status(auto_backup_dir),
            "latest_backup_time": format_datetime(latest_backup),
        },
    }


def folder_status(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size": format_bytes(folder_size(path)),
    }


def file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() and path.is_file() else 0


def folder_size(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def latest_file_mtime(path: Path) -> datetime | None:
    if not path.exists() or not path.is_dir():
        return None
    latest_timestamp = None
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        mtime = child.stat().st_mtime
        if latest_timestamp is None or mtime > latest_timestamp:
            latest_timestamp = mtime
    return datetime.fromtimestamp(latest_timestamp) if latest_timestamp is not None else None


def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def format_datetime(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else "暂无"
