import shutil
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


def create_backup() -> Path:
    date_folder = datetime.now().strftime("%Y-%m-%d")
    backup_dir = BACKUP_ROOT / date_folder
    backup_dir.mkdir(parents=True, exist_ok=True)

    for source in BACKUP_SOURCES:
        if not source.exists():
            continue
        destination = backup_dir / source.name
        if source.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)

    return backup_dir


if __name__ == "__main__":
    created_path = create_backup()
    print(f"Backup created: {created_path}")
