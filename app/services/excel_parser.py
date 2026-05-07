import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.config import BASE_DIR
from app.services.normalization import normalize_gts_no, normalize_oem


QUOTATION_FIELDS = [
    "no",
    "gts_no",
    "description",
    "oem",
    "factory",
    "chinese_description",
    "quantity",
    "unit",
    "unit_price",
    "total_price",
    "item_per_package",
    "packages",
    "weight_per_package",
    "gross_weight",
    "length",
    "width",
    "height",
    "measurements_volume",
    "packaging",
    "expected_delivery",
    "comment",
]

NUMERIC_FIELDS = {"quantity", "unit_price", "total_price"}


@dataclass
class ParsedQuotationRow:
    row_number: int
    values: dict[str, Any]
    warnings: list[str]
    errors: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def load_template_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or BASE_DIR / "config" / "quotation_template.json"
    with path.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


def parse_full_quotation_workbook(
    workbook_path: Path,
    config: dict[str, Any] | None = None,
) -> list[ParsedQuotationRow]:
    template = config or load_template_config()
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        sheet_name = template.get("sheet_name")
        worksheet = workbook[sheet_name] if sheet_name else workbook.worksheets[0]
        start_row = int(template["start_row"])
        max_rows = int(template.get("max_rows", 300))
        columns = template["columns"]

        parsed_rows: list[ParsedQuotationRow] = []
        for row_number in range(start_row, start_row + max_rows):
            values = {
                field: _clean_cell_value(worksheet[f"{columns[field]}{row_number}"].value)
                for field in QUOTATION_FIELDS
            }
            if all(value in ("", None) for value in values.values()):
                continue

            warnings: list[str] = []
            errors: list[str] = []
            gts_no_normalized, gts_warnings = normalize_gts_no(values["gts_no"])
            oem_normalized, oem_warnings = normalize_oem(values["oem"])
            values["gts_no_normalized"] = gts_no_normalized
            values["oem_normalized"] = oem_normalized
            warnings.extend([f"GTS No. {warning}" for warning in gts_warnings])
            warnings.extend([f"OEM {warning}" for warning in oem_warnings])

            for field in NUMERIC_FIELDS:
                values[field] = _parse_number(values[field], field, warnings)

            if not gts_no_normalized and not oem_normalized:
                errors.append("Row must contain GTS No. or OEM.")

            parsed_rows.append(
                ParsedQuotationRow(
                    row_number=row_number,
                    values=values,
                    warnings=warnings,
                    errors=errors,
                )
            )
        return parsed_rows
    finally:
        workbook.close()


def _clean_cell_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return value


def _parse_number(value: Any, field: str, warnings: list[str]) -> float | None:
    if value in ("", None):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        warnings.append(f"{field} is not a number and will be left blank.")
        return None
