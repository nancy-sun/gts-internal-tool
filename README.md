# GTS Internal Tool

Local internal office web tool for storing historical product quotation rows and generating internal quotation Excel sheets.

Version 1 is intentionally small:

- FastAPI web app
- SQLite database for local development/testing fallback
- PostgreSQL production support through `DATABASE_URL`
- Docker deployment files
- Employee username/password login
- Roles: admin, sales, merchandiser
- Local Excel uploads
- Local LAN access
- No CRM, ERP, sales portal, PostgreSQL migration, OSS storage, or public deployment
- No SQLite development data migration; production PostgreSQL starts empty

## Current Status

Implemented:

- FastAPI app
- SQLite database initialization
- PostgreSQL empty-database schema initialization
- Local folder creation
- Username/password login
- One-time first admin setup
- Admin user management
- Password confirmation for sensitive writes
- Operation logs use the logged-in employee identity
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
- Customs / 报关资料 section for HS Code upload/report compatibility and customs master data
- Operation logging for customs uploads, customs reports, and customs master data changes
- Customs Master Data module for maintaining customs item names, HS Code, generic declaration units, and declaration element templates
- Manual local backup script and backup instructions
- `robots.txt` and `X-Robots-Tag` noindex protection for internal-only use
- Dockerfile and Docker Compose for deployable packaging

Phase 1 through Phase 5 MVP work is implemented.

This branch includes cloud-readiness and Docker deployability work. The app has not been deployed, no OSS storage has been added, and existing SQLite development data is not migrated.

HS Code is now part of Customs / 报关资料. Existing `products.hs_code` remains as a legacy fallback for current product HS Code upload/report workflows. The future source-of-truth direction is `product_customs_mapping -> customs_items.hs_code`.

The Customs Master Data module currently manages only customs item master records. Product-to-customs mapping, purchase contracts, declaration batches, declaration detail preview, final declaration workbook export, and customs Excel exports are future phases.

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

## Deployment

Local development can still use SQLite by leaving `DATABASE_URL` empty. Production should use PostgreSQL, normally Alibaba Cloud RDS PostgreSQL, with:

```text
DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
```

Docker is the primary deployment method. The first deployable version keeps uploads, generated files, and backups on persistent mounted directories:

```text
/data/uploads
/data/generated
/data/backups
```

Production starts with a fresh empty PostgreSQL database. Visit `/setup-admin` to create the first admin. See [ALIYUN_DEPLOYMENT.md](ALIYUN_DEPLOYMENT.md) and [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md).

## Test Cases

Automated tests live in `tests/` and include the main upload-search-generate Excel workflow through the FastAPI app. Manual browser layout, LAN, and backup checks are listed in [TEST_CASES.md](TEST_CASES.md).

```bash
python3 -m pytest tests
```

## Local SQLite Development

1. Create `.env` from `.env.example`.
2. Install dependencies.
3. Run the tests.
4. Start the app on port 8080.
5. Open the app and create the first admin account at `/setup-admin` if prompted.

```bash
cp .env.example .env
python -m pip install -r requirements.txt
python3 -m pytest tests
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

## Docker PostgreSQL Smoke Test

Use Docker Compose to test the deployable PostgreSQL path locally:

```bash
docker compose up --build
```

Then check:

```bash
curl http://localhost:8080/healthz
```

The compose environment sets `DATABASE_URL=postgresql+psycopg://...`, so the app initializes and uses PostgreSQL instead of local SQLite. Open `http://localhost:8080`, create the first admin through `/setup-admin`, then test login, user management, upload preview/import, supplier matching, search, and operation logs.
