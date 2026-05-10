from pathlib import Path

from app.services.preview_tokens import preview_file_path, remove_preview_file


def test_preview_file_path_accepts_uuid_hex_tokens():
    token = "a" * 32

    path = preview_file_path(Path("uploads"), "preview", token)

    assert path == Path("uploads") / f"preview_{token}.json"


def test_preview_file_path_rejects_path_like_tokens():
    path = preview_file_path(Path("uploads"), "preview", "../secret")

    assert path == Path("uploads") / "preview_invalid_token.json"


def test_remove_preview_file_is_idempotent(tmp_path: Path):
    path = tmp_path / "preview.json"
    path.write_text("{}", encoding="utf-8")

    remove_preview_file(path)
    remove_preview_file(path)

    assert not path.exists()
