# TEST_CASES

This file tracks manual checks that are not covered well by unit tests.

## Browser UI

- Open every page and confirm visible labels are Chinese, except product/technical terms such as `GTS Internal Tool`, `GTS`, `OEM`, `Excel`, and `.xlsx`.
- Confirm dashboard shows only the navigation brand and the four action buttons.
- Confirm breadcrumb and return button appear on non-dashboard pages.
- Confirm upload preview status uses icons, not text.
- Confirm generation preview status uses icons, not text.
- Confirm long OEM values wrap to more than one line.
- Confirm GTS values stay on one line.
- Confirm preview tables scroll vertically inside the table area instead of making the full page scroll.
- Confirm desktop preview tables do not require horizontal scrolling for normal office files.
- Confirm unit prices display with `¥` in upload preview, generation candidate choices, and search results.
- Confirm displayed timestamps in tables show date only.
- Confirm operator name is remembered by the browser after first entry.

## End-to-End Office Workflow

- Upload a dummy quotation file with at least 10 rows.
- Search one uploaded GTS number by full value and partial value.
- Generate a quotation from a request list using the uploaded GTS numbers.
- Choose a non-latest quotation candidate and confirm generated Excel uses the selected row.
- Uncheck one generation preview row and confirm generated Excel excludes it.
- Restart the app and confirm uploaded data still exists.

## Local Deployment

- Start the app on port 8080.
- Open `http://localhost:8080` on the office computer.
- Open the LAN URL from another computer on the same network.
- Confirm invalid shared access code is rejected.
- Confirm correct shared access code logs in.

## Backup / Restore

- Run the manual backup command from `BACKUP.md`.
- Confirm the backup folder contains database, uploads, generated, and config.
- Restore backup files into a test copy of the app.
- Start the app and confirm historical quotation data is available.
