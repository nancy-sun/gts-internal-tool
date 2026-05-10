# TEMPLATE_CONFIG

Excel parsing uses JSON files in `config/`.

The MVP assumes:

- First worksheet
- Header row is detected by finding `No.` in column A
- Data starts on the row immediately after the detected header
- Upload parsing detects known columns by header name, so extra inserted columns are ignored
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

If staff insert extra columns, the import can still work as long as the important headers keep recognizable names such as `GTS No.`, `OEM`, `Factory`, `Quantity`, and `Unit Price`.

## Request Template

File:

```text
config/request_template.json
```

The request parser detects known columns by header name. A request sheet can contain only `GTS No.`, or `GTS No.` plus `Description`, or the fuller request layout.

The fallback request columns are:

```text
B GTS No.
C Description
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

## HS Code Files

HS Code upload and HS Code report generation use the first worksheet and detect columns by header name.

HS Code upload requires:

```text
GTS column
HS Code column
```

HS Code generation requires:

```text
GTS column
```

The GTS column uses the same GTS aliases as quotation upload. The HS Code column supports these aliases:

```text
HS
hscode
海关编码
hs code
```

Extra columns are ignored. Parsed row order is kept when generating the HS Code report.
