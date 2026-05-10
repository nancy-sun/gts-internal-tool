from pathlib import Path

from app.services.preview_tokens import preview_file_path


def test_preview_file_path_accepts_uuid_hex_tokens():
    token = "a" * 32

    path = preview_file_path(Path("uploads"), "preview", token)

    assert path == Path("uploads") / f"preview_{token}.json"


def test_preview_file_path_rejects_path_like_tokens():
    path = preview_file_path(Path("uploads"), "preview", "../secret")

    assert path == Path("uploads") / "preview_invalid_token.json"
