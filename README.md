# GTS Internal Tool

Local internal office web tool for storing historical product quotation rows and generating internal quotation Excel sheets.

Version 1 is intentionally small:

- FastAPI web app
- SQLite database
- Employee username/password login
- Roles: admin, sales, merchandiser
- Local Excel uploads
- Local LAN access
- No CRM, ERP, sales portal, PostgreSQL migration, OSS storage, or public deployment

## Current Status

Implemented:

- FastAPI app
- SQLite database initialization
- Local folder creation
- Username/password login
- One-time first admin setup
- Admin user management
- Password confirmation for sensitive writes
- Home page
- Template config files for quotation and request Excel layouts
- Database search page
- Operation logs page
- Full quotation upload parsing, preview, confirmation, and import
- Full quotation import detects the header row from `No.` in column A and ignores the Photo column
- Full quotation import reads columns by header name, so extra inserted columns are ignored
- Upload preview requires manual choices for GTS, OEM, factory, and price changes, and warns on unit changes
- Operation logging for full quotation uploads
- Request-list upload, matching preview, manual candidate selection, and immediate Excel download
- Generated quotation Excel includes a blank Photo column
- Operation logging for generated quotations
- HS Code upload by GTS, product search display, and HS Code report Excel download
- Operation logging for HS Code updates and generated HS Code reports
- Manual local backup script and backup instructions
- `robots.txt` and `X-Robots-Tag` noindex protection for internal-only use

Phase 1 through Phase 5 MVP work is implemented.

This branch includes cloud-readiness authentication work only. The app has not been deployed, and no PostgreSQL or OSS migration has been performed.

## Authentication

The app now uses employee username/password login. The first time a new database is opened, visit `/setup-admin` to create the first administrator. Employees do not self-register; an administrator creates employee accounts from `用户管理`.

Roles:

- `admin` / 管理员: manage users and access all internal pages.
- `sales` / 业务员: use office workflows without user administration.
- `merchandiser` / 跟单: use office workflows without user administration.

The old shared access code is disabled by default. `ENABLE_LEGACY_ACCESS_CODE=true` can enable emergency temporary access, but that mode does not grant admin access.

## Staff Instructions

See [STAFF_USAGE.md](STAFF_USAGE.md).

## Backup

See [BACKUP.md](BACKUP.md).

## Test Cases

Automated tests live in `tests/` and include the main upload-search-generate Excel workflow through the FastAPI app. Manual browser layout, LAN, and backup checks are listed in [TEST_CASES.md](TEST_CASES.md).

```bash
python3 -m pytest tests
```

## Run Locally

1. Create `.env` from `.env.example`.
2. Install dependencies.
3. Start the app on port 8080.
4. Open the app and create the first admin account if prompted.

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
