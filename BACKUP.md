# BACKUP

Backup support will be completed in Phase 5.

The intended backup contents are:

- `data/gts_catalogue.sqlite3`
- `uploads/`
- `generated/`, if temporary generated files are kept
- `config/`

The `.env` file contains the shared access code and should be copied only if the manager wants the backup to include local app settings.

Planned backup folder format:

```text
backups/YYYY-MM-DD/
```
