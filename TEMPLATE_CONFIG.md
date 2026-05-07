# TEMPLATE_CONFIG

Excel parsing uses JSON files in `config/`.

The MVP assumes:

- First worksheet
- Header row is detected by finding `No.` in column A
- Data starts on the row immediately after the detected header
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
E Photo
F Factory
G Chinese Description
H Quantity
I Unit
J Unit Price
K Total Price
L Item/Package
M Packages
N Weight / Package
O G.W.
P Length
Q Width
R Height
S Measurements / Volume
T Packaging
U Expected Delivery
V Comment
```

The Photo column is ignored during import. It is present only so the workbook layout matches real office quotation sheets.

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
