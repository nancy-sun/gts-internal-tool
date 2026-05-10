import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
BACKUP_ROOT = BASE_DIR / "backups"
BACKUP_SOURCES = [
    BASE_DIR / "data" / "gts_catalogue.sqlite3",
    BASE_DIR / "uploads",
    BASE_DIR / "generated",
    BASE_DIR / "config",
]


def create_backup(now: datetime | None = None) -> Path:
    backup_time = now or datetime.now()
    backup_dir = BACKUP_ROOT / backup_time.strftime("%Y-%m-%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)

    for source in BACKUP_SOURCES:
        if not source.exists():
            continue
        destination = backup_dir / source.name
        if source.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
        elif source.suffix == ".sqlite3":
            copy_sqlite_database(source, destination)
        else:
            shutil.copy2(source, destination)

    return backup_dir


def copy_sqlite_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection:
        with sqlite3.connect(destination) as backup_connection:
            source_connection.backup(backup_connection)


if __name__ == "__main__":
    created_path = create_backup()
    print(f"Backup created: {created_path}")
