from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import get_settings


AUTO_BACKUP_DIR = get_settings().backup_dir / "auto"


class BackupError(RuntimeError):
    pass


def create_auto_backup(reason: str) -> Path:
    settings = get_settings()
    if settings.database_backend != "sqlite":
        return Path("rds-postgresql-managed-backup")
    database_file = settings.database_file
    if not database_file.exists():
        raise BackupError(f"数据库文件不存在：{database_file}")

    try:
        AUTO_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(f"数据库自动备份失败：{exc}") from exc
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = AUTO_BACKUP_DIR / f"{timestamp}_{safe_backup_reason(reason)}.sqlite3"
    copy_sqlite_database(database_file, backup_file)
    return backup_file


def safe_backup_reason(reason: str) -> str:
    safe_reason = re.sub(r"[^A-Za-z0-9_-]+", "-", reason.strip()).strip("-_")
    return safe_reason or "backup"


def copy_sqlite_database(source: Path, destination: Path) -> None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(source) as source_connection:
            with sqlite3.connect(destination) as backup_connection:
                source_connection.backup(backup_connection)
    except sqlite3.Error as exc:
        raise BackupError(f"数据库自动备份失败：{exc}") from exc
    except OSError as exc:
        raise BackupError(f"数据库自动备份失败：{exc}") from exc
