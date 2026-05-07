import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.config import BASE_DIR
from app.services.excel_parser import _clean_cell_value, _parse_number
from app.services.normalization import normalize_gts_no, normalize_oem


REQUEST_FIELDS = ["gts_no", "oem", "quantity", "comment"]


@dataclass
class ParsedRequestRow:
    row_number: int
    values: dict[str, Any]
    warnings: list[str]
    errors: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def load_request_template_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or BASE_DIR / "config" / "request_template.json"
    with path.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


def parse_request_workbook(
    workbook_path: Path,
    config: dict[str, Any] | None = None,
) -> list[ParsedRequestRow]:
    template = config or load_request_template_config()
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        sheet_name = template.get("sheet_name")
        worksheet = workbook[sheet_name] if sheet_name else workbook.worksheets[0]
        start_row = int(template["start_row"])
        max_rows = int(template.get("max_rows", 300))
        columns = template["columns"]

        parsed_rows: list[ParsedRequestRow] = []
        for row_number in range(start_row, start_row + max_rows):
            values = {
                field: _clean_cell_value(worksheet[f"{columns[field]}{row_number}"].value)
                for field in REQUEST_FIELDS
            }
            if all(value in ("", None) for value in values.values()):
                continue

            warnings: list[str] = []
            errors: list[str] = []
            gts_no_normalized, gts_warnings = normalize_gts_no(values["gts_no"])
            oem_normalized, oem_warnings = normalize_oem(values["oem"])
            values["gts_no_normalized"] = gts_no_normalized
            values["oem_normalized"] = oem_normalized
            values["quantity"] = _parse_number(values["quantity"], "quantity", warnings)
            warnings.extend([f"GTS No. {warning}" for warning in gts_warnings])
            warnings.extend([f"OEM {warning}" for warning in oem_warnings])

            if not gts_no_normalized and not oem_normalized:
                errors.append("Row must contain GTS No. or OEM.")

            parsed_rows.append(
                ParsedRequestRow(
                    row_number=row_number,
                    values=values,
                    warnings=warnings,
                    errors=errors,
                )
            )
        return parsed_rows
    finally:
        workbook.close()
