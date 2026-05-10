# GTS Internal Tool

Local internal office web tool for storing historical product quotation rows and generating internal quotation Excel sheets.

Version 1 is intentionally small:

- FastAPI web app
- SQLite database
- Shared access code
- Local Excel uploads
- Local LAN access
- No CRM, ERP, individual accounts, roles, delete function, or public deployment

## Current Status

Implemented:

- FastAPI app
- SQLite database initialization
- Local folder creation
- Shared access code login
- Home page
- Template config files for quotation and request Excel layouts
- Database search page
- Operation logs page
- Full quotation upload parsing, preview, confirmation, and import
- Full quotation import detects the header row from `No.` in column A and ignores the Photo column
- Full quotation import reads columns by header name, so extra inserted columns are ignored
- Upload preview flags factory, unit, and price changes against the latest historical quotation row
- Operation logging for full quotation uploads
- Request-list upload, matching preview, manual candidate selection, and immediate Excel download
- Generated quotation Excel includes a blank Photo column
- Operation logging for generated quotations
- Manual local backup script and backup instructions

Phase 1 through Phase 5 MVP work is implemented.

## Staff Instructions

See [STAFF_USAGE.md](STAFF_USAGE.md).

## Backup

See [BACKUP.md](BACKUP.md).

## Test Cases

Automated tests live in `tests/`. Manual browser, LAN, and backup checks are listed in [TEST_CASES.md](TEST_CASES.md).

## Run Locally

1. Create `.env` from `.env.example`.
2. Install dependencies.
3. Start the app on port 8080.

```bash
cp .env.example .env
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open:

```text
http://localhost:8080
```

Other office computers can use the office computer LAN address:

```text
http://192.168.x.x:8080
```
