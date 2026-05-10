from fastapi import UploadFile


def validate_xlsx_upload(upload_file: UploadFile, operator_name: str) -> str | None:
    if not operator_name.strip():
        return "请填写操作员姓名。"
    filename = upload_file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        return "只能上传 .xlsx 文件。"
    return None


def validate_upload_size(
    contents: bytes,
    *,
    max_upload_size_bytes: int,
    max_upload_size_mb: int,
) -> str | None:
    if len(contents) <= max_upload_size_bytes:
        return None
    return f"上传文件超过 {max_upload_size_mb} MB。"
