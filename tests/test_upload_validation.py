from types import SimpleNamespace

from app.services.upload_validation import validate_upload_size, validate_xlsx_upload


def test_validate_xlsx_upload_requires_operator_name():
    upload_file = SimpleNamespace(filename="quotation.xlsx")

    assert validate_xlsx_upload(upload_file, " ") == "请填写操作员姓名。"


def test_validate_xlsx_upload_allows_only_xlsx_files():
    upload_file = SimpleNamespace(filename="quotation.xls")

    assert validate_xlsx_upload(upload_file, "Nancy") == "只能上传 .xlsx 文件。"


def test_validate_upload_size_reports_limit():
    message = validate_upload_size(
        b"1234",
        max_upload_size_bytes=3,
        max_upload_size_mb=10,
    )

    assert message == "上传文件超过 10 MB。"
