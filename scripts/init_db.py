import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config import ensure_local_directories
from app.database import initialize_database


if __name__ == "__main__":
    ensure_local_directories()
    initialize_database()
    print("Database initialized.")
