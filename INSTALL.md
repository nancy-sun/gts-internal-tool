# INSTALL

## Office Computer Setup

This setup uses local SQLite and does not require Docker.

1. Install Python 3.10 or newer.
2. Open a terminal in this project folder.
3. Create the local environment file:

```bash
cp .env.example .env
```

4. Edit `.env` and set real values:

```text
SESSION_SECRET_KEY=use-a-long-random-secret
APP_PORT=8080
ENABLE_LEGACY_ACCESS_CODE=false
```

5. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

6. Start the app:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

7. Open the app from the office computer:

```text
http://localhost:8080
```

8. Open the app from another LAN computer:

```text
http://192.168.x.x:8080
```

Replace `192.168.x.x` with the office computer's LAN IP address.

## First Admin Setup

The app uses employee username/password login. No email is required.

On first run with an empty database:

1. Open the app in the browser.
2. The app will redirect to `/setup-admin`.
3. Create the first administrator account.
4. Log in as admin.
5. Open `用户管理` to create staff accounts.

Deactivated users cannot log in. For resigned employees, normally disable the account instead of reusing it for another person. Admin can delete users if needed; old operation logs remain and keep the historical `operator_name`, while their `user_id` is detached.

## Emergency Legacy Access Code

The old shared access code is disabled by default and is only an emergency fallback.

To enable it temporarily:

1. Stop the running app.
2. Open `.env`.
3. Set:

```text
ENABLE_LEGACY_ACCESS_CODE=true
SHARED_ACCESS_CODE=your-emergency-code
```

4. Save `.env`.
5. Start the app again:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Legacy access mode cannot enter user management. Return `ENABLE_LEGACY_ACCESS_CODE=false` after emergency use.

## Change the Port

The app currently uses port `8080`.

To change it:

1. Stop the running app.
2. Open `.env`.
3. Change:

```text
APP_PORT=8080
```

4. Start the app with the same port value:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

If you change `APP_PORT` to `8000`, start with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Sensitive Write Confirmation

Product edits, supplier edits, user management, and full quotation import require the logged-in user to re-enter their own login password.

`PRODUCT_EDIT_PASSWORD` and `SUPPLIER_EDIT_PASSWORD` are legacy fallback settings only. They are not required for normal username/password login.

## Backup Setup

Manual backup:

```bash
python3 scripts/backup.py
```

Daily scheduled backup instructions are in `BACKUP.md`.

## Temporary Upload Cleanup

After data is imported or exported, the database is the real saved record. Uploaded Excel files are only kept temporarily.

Manual cleanup:

```bash
python3 scripts/cleanup_uploads.py
```

Daily scheduled cleanup instructions are in `BACKUP.md`.

## Docker Local PostgreSQL Smoke Test

Docker is the primary production packaging method. For a local PostgreSQL smoke test:

1. Review `docker-compose.yml`. It includes a local test PostgreSQL `DATABASE_URL`.
2. Start:

```bash
docker compose up --build
```

3. Open:

```text
http://localhost:8080
```

4. Create the first admin through `/setup-admin`.

The compose setup mounts persistent local directories under `docker-data/` for uploads, generated files, and backups. OSS is not implemented yet.

For Alibaba Cloud staging deployment, follow `ALIYUN_DEPLOYMENT.md` and complete `DEPLOYMENT_CHECKLIST.md` before staff testing.

## Troubleshooting

Docker not installed:
- Use the local SQLite setup above, or install Docker Desktop before running `docker compose up --build`.

Wrong `DATABASE_URL`:
- Local SQLite mode can leave `DATABASE_URL` empty.
- PostgreSQL mode must use the `postgresql+psycopg://user:password@host:5432/dbname` format.
- If PostgreSQL is unavailable, `/healthz` returns a database error.

Session secret missing or too short:
- Set `SESSION_SECRET_KEY` to a random value with at least 16 characters.
- Do not use the example value in production.

Database not initialized:
- The app initializes an empty SQLite or PostgreSQL schema at startup.
- If startup fails, check database connectivity and the `DATABASE_URL` value.
- On a fresh database, open `/setup-admin` to create the first administrator.
