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
backups/YYYY-MM-DD_HHMMSS/
```

## Manual Backup

Run this command from the project folder:

```bash
python3 scripts/backup.py
```

The command prints the created backup folder path.

## Automatic Database Backup

Before confirming a full quotation import or HS Code bulk update, the app creates a database-only backup in:

```text
backups/auto/
```

File name format:

```text
YYYYMMDD_HHMMSS_reason.sqlite3
```

If this automatic backup fails, the import or HS Code update stops and no database rows are written. Manual backups are still recommended because they also copy uploads, generated files, and config.

## Temporary Upload Cleanup

Uploaded Excel files are temporary. The database is the saved business record after an upload is confirmed or a quotation is generated.

Preview JSON files are removed automatically after a successful import or download. If a staff member starts a preview and then leaves it unfinished, the cleanup command also removes stale preview JSON files after 3 days.

Run this command from the project folder to delete uploaded `.xlsx` files and stale preview files older than 3 days:

```bash
python3 scripts/cleanup_uploads.py
```

## Daily Backup on macOS

Use `cron` for a simple daily local backup.

1. Open the crontab editor:

```bash
crontab -e
```

2. Add these lines to cleanup temporary uploads every day at 18:25 and run the backup every day at 18:30:

```cron
25 18 * * * cd /Users/nancy/Documents/gts-internal-tool && /usr/bin/python3 scripts/cleanup_uploads.py >> backups/cleanup.log 2>&1
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
