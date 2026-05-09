# STAFF_USAGE

## Login

Open the office LAN address in a browser and enter the shared access code.

Staff do not have individual accounts. For uploads and generated quotations, enter your name on the page so the manager can see who performed the action.

## Upload Full Quotation List

1. Click `Upload Full Quotation List`.
2. Enter your name.
3. Upload a `.xlsx` quotation file.
4. Review the preview page.
5. If the preview shows warnings such as `old factory => new factory` or `old price => new price`, double-check the row before importing.
6. If a matched product has different non-empty product fields, tick the fields that should be updated.
7. Confirm import.

The system keeps old quotation rows and inserts new quotation rows. It does not delete old rows.

## Generate Quotation

1. Click `Generate Quotation from GTS/OEM List`.
2. Enter your name.
3. Upload a `.xlsx` request list.
4. The request list may contain only `GTS No.`, or `GTS No.` with `Description`, or GTS/OEM/quantity/comment columns.
5. Review matched, unmatched, conflict, and multiple-candidate rows.
6. For rows with multiple quotation candidates, select the quotation row to use.
7. Click `Generate Excel`.

The generated file is created for immediate download. It is not permanently stored in `generated/` in the MVP.
If the request list includes `Description`, the generated sheet keeps that uploaded description and fills Chinese Description from the selected historical quotation row.

## Search Database

Use `Search Database` to search by:

- GTS No.
- OEM
- Description
- Chinese Description
- Factory

Search actions are not logged.

## Operation Logs

Managers can open `Operation Logs` to see uploads and generated quotations.
