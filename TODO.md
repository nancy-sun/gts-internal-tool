# TODO

## HS Code Data

Add a simple HS code workflow after the current quotation MVP is stable.

### Upload HS Code Data

- Add an `上传 HS Code` page similar to quotation upload.
- Accept `.xlsx` files containing only:
  - GTS No.
  - HS Code
- Normalize GTS No. using the existing GTS normalization rule.
- Each GTS product should have one active HS code value.
- During preview, match uploaded GTS No. against existing product data.
- If the uploaded HS code is different from the existing HS code for that GTS:
  - show a warning in preview
  - ask the user to choose whether to keep the old HS code or use the new HS code
- Confirm before saving.
- Record upload action in operation logs.

### Get HS Codes

- Add a `获取 HS Code` section/page.
- Accept a request Excel containing a list of items with GTS No.
- Normalize GTS No. and match against the database.
- Show a preview table with:
  - uploaded GTS No.
  - matched product
  - HS Code
  - match status
- Allow the user to generate/export an Excel file with the matched HS codes.
- Show unmatched GTS rows clearly.

### Before Implementation

- Decide where HS code should be stored:
  - add `hs_code` to `products`, or
  - create a new simple HS code table.
- Keep the feature small. Do not add customs, tariff, supplier, or compliance workflows in this phase.
