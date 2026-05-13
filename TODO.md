# TODO

This file tracks known follow-up work after the current implementation.

## Manual Verification

- Test the HS Code upload flow with a real office workbook.
- Test the HS Code report flow with a real GTS list workbook.
- Confirm product search shows HS Code and quotation upload / quotation generation do not show HS Code.

## Later Improvements

- Decide whether browser sessions should expire automatically after a workday.
- Add browser automation for the main UI flows if manual visual checks become repetitive.
- Revisit backup/restore testing after the first office test cycle.
- Add a post-upload audit summary for changed price, changed factory, changed OEM, confirmed duplicates, and failed rows.
- Group product search results by product, with quotation history expandable below each product.
- Add a data quality page for missing HS Code, missing OEM, missing description, and products with no quotation history.
- Add a maintenance/status page for database path, backup folder, last backup, and temporary upload cleanup status.
- Add a recent activity panel on the dashboard for latest uploads, generated quotation files, HS Code updates, and product edits.
