# INSTALL

## Office Computer Setup

1. Install Python 3.11 or newer.
2. Open a terminal in this project folder.
3. Create the local environment file:

```bash
cp .env.example .env
```

4. Edit `.env` and set real values:

```text
SHARED_ACCESS_CODE=your-office-code
SESSION_SECRET_KEY=use-a-long-random-secret
APP_PORT=3000
```

5. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

6. Start the app:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 3000
```

7. Open the app from the office computer:

```text
http://localhost:3000
```

8. Open the app from another LAN computer:

```text
http://192.168.x.x:3000
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
uvicorn app.main:app --host 0.0.0.0 --port 3000
```

Existing browser sessions may remain logged in until the browser session ends. Staff can also click `Log out` and log in with the new code.

## Change the Port

The app currently uses port `3000`.

To change it:

1. Stop the running app.
2. Open `.env`.
3. Change:

```text
APP_PORT=3000
```

4. Start the app with the same port value:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 3000
```

If you change `APP_PORT` to `8000`, start with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
