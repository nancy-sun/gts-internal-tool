# GTS Internal Tool

Local internal office web tool for storing historical product quotation rows and generating internal quotation Excel sheets.

Version 1 is intentionally small:

- FastAPI web app
- SQLite database
- Shared access code
- Local Excel uploads
- Local LAN access
- No CRM, ERP, individual accounts, roles, delete function, or public deployment

## Phase 1 Status

Implemented foundation:

- FastAPI app
- SQLite database initialization
- Local folder creation
- Shared access code login
- Home page
- Template config files for quotation and request Excel layouts

Feature pages for upload, generate, search, and logs are placeholders until later phases.

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
