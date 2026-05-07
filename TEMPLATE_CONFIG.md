# TEMPLATE_CONFIG

Excel parsing uses JSON files in `config/`.

The MVP assumes:

- First worksheet
- Header row: row 3
- Data starts: row 4
- Maximum parsed data rows: 300

## Full Quotation Template

File:

```text
config/quotation_template.json
```

Default column order:

```text
A No.
B GTS No.
C Description
D OEM
E Factory
F Chinese Description
G Quantity
H Unit
I Unit Price
J Total Price
K Item/Package
L Packages
M Weight / Package
N G.W.
O Length
P Width
Q Height
R Measurements / Volume
S Packaging
T Expected Delivery
U Comment
```

## Request Template

File:

```text
config/request_template.json
```

The default request parser reads GTS/OEM/quantity/comment from the same columns as the full quotation sheet:

```text
B GTS No.
D OEM
G Quantity
U Comment
```

If the office later uses a simpler request sheet, edit `config/request_template.json`.

Example:

```json
{
  "sheet_name": null,
  "header_row": 1,
  "start_row": 2,
  "max_rows": 300,
  "columns": {
    "gts_no": "A",
    "oem": "B",
    "quantity": "C",
    "comment": "D"
  }
}
```

`sheet_name: null` means the first worksheet is used.
