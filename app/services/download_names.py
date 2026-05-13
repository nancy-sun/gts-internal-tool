from datetime import datetime
import re
from urllib.parse import quote


UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\s]+')


def dated_download_name(
    operator_name: str,
    label: str,
    now: datetime | None = None,
) -> str:
    date_text = (now or datetime.now()).strftime("%m%d")
    safe_operator = safe_filename_part(operator_name) or "operator"
    return f"{safe_operator}-{label}-{date_text}.xlsx"


def attachment_header(filename: str) -> str:
    ascii_fallback = quote(filename, safe="").replace("%", "")
    return (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )


def safe_filename_part(value: str) -> str:
    return UNSAFE_FILENAME_CHARS.sub("_", value.strip()).strip("._")
