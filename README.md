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
- Operation logging for full quotation uploads
- Request-list upload, matching preview, manual candidate selection, and immediate Excel download
- Operation logging for generated quotations

The remaining work is Phase 5 polish and backup documentation/scripts.

## Run Locally

1. Create `.env` from `.env.example`.
2. Install dependencies.
3. Start the app on port 3000.

```bash
cp .env.example .env
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 3000
```

Open:

```text
http://localhost:3000
```

Other office computers can use the office computer LAN address:

```text
http://192.168.x.x:3000
```
