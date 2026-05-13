from datetime import datetime

from app.services.download_names import attachment_header, dated_download_name


def test_dated_download_name_uses_operator_label_and_mmdd():
    assert (
        dated_download_name("Nancy Sun", "询价", now=datetime(2026, 5, 12))
        == "Nancy_Sun-询价-0512.xlsx"
    )


def test_dated_download_name_falls_back_for_blank_operator():
    assert (
        dated_download_name(" ", "hs", now=datetime(2026, 5, 12))
        == "operator-hs-0512.xlsx"
    )


def test_attachment_header_uses_utf8_filename_parameter_for_chinese_text():
    header = attachment_header("Nancy-询价-0512.xlsx")

    assert header.startswith('attachment; filename="')
    assert "filename*=UTF-8''Nancy-%E8%AF%A2%E4%BB%B7-0512.xlsx" in header
