# TEST_CASES

This file tracks what is automated and what still needs manual checking.

## Automated Coverage

Run all automated checks with:

```bash
python3 -m pytest tests
```

The automated tests cover:

- Shared access code rejects wrong values and protects authenticated pages.
- Upload preview reads a real `.xlsx`, streams preview rows, blocks rows missing factory, unit, or price, and refuses confirm when preview has errors.
- Confirmed upload inserts products and quotation items, then writes upload logs.
- Search finds uploaded GTS values by partial input and shows `¥` unit prices.
- Generate preview matches uploaded GTS data, shows database Chinese description, unit, candidate price, and operator.
- Generate download creates a real Excel file, keeps uploaded request description, fills missing OEM/unit from system data, recalculates total price, and writes generation logs.
- Core service behavior: normalization, Excel parsing, matching, conflicts, duplicate skip, latest candidate selection, generated columns, backup copying, and operation log creation.

## Browser UI

These are visual/browser checks that are still better reviewed manually unless we add a browser automation dependency such as Playwright.

- Open every page and confirm visible labels are Chinese, except product/technical terms such as `GTS Internal Tool`, `GTS`, `OEM`, `Excel`, and `.xlsx`.
- Confirm dashboard shows only the navigation brand and the four action buttons.
- Confirm breadcrumb and return button appear on non-dashboard pages.
- Confirm upload preview status uses icons, not text.
- Confirm generation preview status uses icons, not text.
- Confirm long OEM values wrap to more than one line.
- Confirm GTS values stay on one line.
- Confirm preview tables scroll vertically inside the table area instead of making the full page scroll.
- Confirm preview tables have stable width during loading and allow horizontal scrolling when the window is narrow.
- Confirm unit prices display with `¥` in upload preview, generation candidate choices, and search results.
- Confirm displayed timestamps in tables show date only.
- Confirm operator name is remembered by the browser after first entry.

## End-to-End Office Workflow

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
