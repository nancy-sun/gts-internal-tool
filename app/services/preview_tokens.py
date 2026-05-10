from pathlib import Path
import re


TOKEN_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def preview_file_path(directory: Path, prefix: str, token: str) -> Path:
    if not TOKEN_PATTERN.fullmatch(token):
        return directory / f"{prefix}_invalid_token.json"
    return directory / f"{prefix}_{token}.json"
