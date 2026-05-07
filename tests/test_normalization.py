from app.services.normalization import normalize_gts_no, normalize_oem


def test_normalize_removes_spaces_and_hyphens():
    assert normalize_gts_no("5010 064 551")[0] == "5010064551"
    assert normalize_oem("5010-064-551")[0] == "5010064551"


def test_normalize_keeps_letters_and_numbers_uppercase():
    assert normalize_gts_no(" GTS-00123 ")[0] == "GTS00123"
    assert normalize_oem(" A 500 008 3949 ")[0] == "A5000083949"


def test_normalize_does_not_convert_similar_characters():
    assert normalize_oem("OI-I0")[0] == "OII0"


def test_normalize_reports_suspicious_characters():
    normalized, warnings = normalize_oem("ABC#123")
    assert normalized == "ABC123"
    assert warnings
