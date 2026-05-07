# BACKUP

Backups are created by `scripts/backup.py`.

Backup contents:

- `data/gts_catalogue.sqlite3`
- `uploads/`
- `generated/`
- `config/`

The `.env` file is not included because it contains the shared access code and session secret.

Backup folder format:

```text
backups/YYYY-MM-DD/
```

## Manual Backup

Run this command from the project folder:

```bash
python3 scripts/backup.py
```

The command prints the created backup folder path.

## Daily Backup on macOS

Use `cron` for a simple daily local backup.

1. Open the crontab editor:

```bash
crontab -e
```

2. Add this line to run the backup every day at 18:30:

```cron
30 18 * * * cd /Users/nancy/Documents/gts-internal-tool && /usr/bin/python3 scripts/backup.py >> backups/backup.log 2>&1
```

3. Save and exit.

## Daily Backup on Windows

Use Task Scheduler.

1. Open Task Scheduler.
2. Create a Basic Task named `GTS Internal Tool Backup`.
3. Trigger: daily.
4. Action: start a program.
5. Program: path to `python.exe`.
6. Arguments:

```text
scripts\backup.py
```

7. Start in:

```text
C:\path\to\gts-internal-tool
```

## Restore Reminder

To restore, stop the app first, then copy the backed-up `gts_catalogue.sqlite3`, `uploads`, `generated`, and `config` contents back into the project folder.
