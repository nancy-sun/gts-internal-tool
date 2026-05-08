from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    def __init__(self) -> None:
        self.app_name = os.getenv(
            "APP_NAME",
            "GTS Internal Tool",
        )
        self.app_port = int(os.getenv("APP_PORT", "8080"))
        self.shared_access_code = os.getenv("SHARED_ACCESS_CODE", "")
        self.session_secret_key = os.getenv("SESSION_SECRET_KEY", "")
        self.database_path = os.getenv("DATABASE_PATH", "data/gts_catalogue.sqlite3")
        self.max_upload_size_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))

        if not self.shared_access_code:
            raise RuntimeError("SHARED_ACCESS_CODE must be set in .env")
        if len(self.session_secret_key) < 16:
            raise RuntimeError("SESSION_SECRET_KEY must be at least 16 characters")

    @property
    def database_file(self) -> Path:
        return BASE_DIR / self.database_path

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_local_directories() -> None:
    for folder in ["data", "uploads", "generated", "backups", "config"]:
        (BASE_DIR / folder).mkdir(parents=True, exist_ok=True)
