# INSTALL

## Office Computer Setup

1. Install Python 3.10 or newer.
2. Open a terminal in this project folder.
3. Create the local environment file:

```bash
cp .env.example .env
```

4. Edit `.env` and set real values:

```text
SHARED_ACCESS_CODE=your-office-code
SESSION_SECRET_KEY=use-a-long-random-secret
APP_PORT=8080
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

## Change the Shared Access Code

The shared access code is not hard-coded in source code. It is read from `.env`.

1. Stop the running app.
2. Open `.env`.
3. Change this line:

```text
SHARED_ACCESS_CODE=your-new-office-code
```

4. Save `.env`.
5. Start the app again:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Existing browser sessions may remain logged in until the browser session ends. Staff can also click `Log out` and log in with the new code.

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

## Change the Product Edit Password

Manual product edits require a separate confirmation password. The password is not stored in browser local storage or the login session.

1. Stop the running app.
2. Open `.env`.
3. Change:

```text
PRODUCT_EDIT_PASSWORD=55123511
```

4. Save `.env`.
5. Start the app again.

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
