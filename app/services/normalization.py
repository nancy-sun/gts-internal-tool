import re


SUSPICIOUS_CHARACTER_PATTERN = re.compile(r"[^A-Za-z0-9\s\-_/.,;:()\\]+")


def normalize_part_number(value: object | None) -> tuple[str, list[str]]:
    if value is None:
        return "", []

    raw_value = str(value).strip()
    warnings: list[str] = []
    if not raw_value:
        return "", warnings

    suspicious_characters = sorted(set(SUSPICIOUS_CHARACTER_PATTERN.findall(raw_value)))
    if suspicious_characters:
        warnings.append(
            "Suspicious characters found: " + ", ".join(suspicious_characters)
        )

    normalized = re.sub(r"[^A-Za-z0-9]", "", raw_value).upper()
    return normalized, warnings


def normalize_gts_no(value: object | None) -> tuple[str, list[str]]:
    return normalize_part_number(value)


def normalize_oem(value: object | None) -> tuple[str, list[str]]:
    return normalize_part_number(value)
