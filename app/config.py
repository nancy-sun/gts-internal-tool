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
        self.app_env = os.getenv("APP_ENV", "local")
        self.app_port = int(os.getenv("APP_PORT", "8080"))
        self.base_url = os.getenv("BASE_URL", "")
        self.force_https = _env_bool("FORCE_HTTPS", False)
        self.secure_cookies = _env_bool("SECURE_COOKIES", False)
        self.shared_access_code = os.getenv("SHARED_ACCESS_CODE", "")
        self.session_secret_key = os.getenv("SESSION_SECRET_KEY", os.getenv("SESSION_SECRET", ""))
        self.database_url = os.getenv("DATABASE_URL", "").strip()
        self.database_path = os.getenv("DATABASE_PATH", "data/gts_catalogue.sqlite3")
        self.max_upload_size_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
        production_paths = self.app_env.strip().lower() == "production"
        self.upload_dir = Path(os.getenv("UPLOAD_DIR", "/data/uploads" if production_paths else "uploads"))
        self.generated_dir = Path(os.getenv("GENERATED_DIR", "/data/generated" if production_paths else "generated"))
        self.backup_dir = Path(os.getenv("BACKUP_DIR", "/data/backups" if production_paths else "backups"))
        self.product_edit_password = os.getenv("PRODUCT_EDIT_PASSWORD", "")
        self.supplier_edit_password = os.getenv(
            "SUPPLIER_EDIT_PASSWORD",
            self.product_edit_password,
        )
        self.enable_legacy_access_code = (
            os.getenv("ENABLE_LEGACY_ACCESS_CODE", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )

        if len(self.session_secret_key) < 16:
            raise RuntimeError("SESSION_SECRET_KEY must be at least 16 characters")
        if self.enable_legacy_access_code and not self.shared_access_code:
            raise RuntimeError(
                "SHARED_ACCESS_CODE must be set when ENABLE_LEGACY_ACCESS_CODE=true"
            )

    @property
    def database_file(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            sqlite_path = self.database_url.removeprefix("sqlite:///")
            return Path(sqlite_path) if Path(sqlite_path).is_absolute() else BASE_DIR / sqlite_path
        return BASE_DIR / self.database_path

    @property
    def database_backend(self) -> str:
        if self.database_url.startswith("postgresql"):
            return "postgresql"
        return "sqlite"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_local_directories() -> None:
    settings = get_settings()
    paths = [
        BASE_DIR / "data",
        BASE_DIR / "config",
        settings.upload_dir,
        settings.generated_dir,
        settings.backup_dir,
    ]
    if settings.database_backend == "sqlite":
        paths.append(settings.database_file.parent)
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
