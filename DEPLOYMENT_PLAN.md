# DEPLOYMENT_PLAN

This project is currently a local office LAN tool. Do not deploy it publicly until the deployment strategy, access control, and storage plan are decided.

## Option A: Local office only

Architecture:
- One office computer runs FastAPI, SQLite, uploads, generated files, and backups.
- Staff access it through the office LAN, for example `http://192.168.x.x:8080`.

Pros:
- Simplest and lowest cost.
- Current app already supports this model.
- Data stays inside the office network.

Cons:
- No remote access unless staff use VPN/remote desktop.
- Availability depends on one office computer.
- Manual backup discipline is important.

Security risks:
- Shared access code is acceptable only for LAN use.
- Anyone on the LAN who knows the code can access the app.

Backup strategy:
- Keep daily local backups from `BACKUP.md`.
- Periodically copy backups to an external drive or another office computer.

Estimated code changes:
- None required.

Recommended use case:
- Current MVP and office-only quotation workflow.

## Option B: Cloudflare Tunnel + local office server

Architecture:
- Office computer still runs the app and stores SQLite/uploads/backups locally.
- Cloudflare Tunnel exposes the local app through a protected URL.
- Use Cloudflare Access in front of the app for remote staff.

Pros:
- Remote access without moving the app/database to the cloud.
- Avoids opening router ports.
- Keeps current local storage model.

Cons:
- Office computer must stay on.
- Internet/tunnel outage affects remote access.
- Requires careful Cloudflare Access setup.

Security risks:
- Do not rely only on the shared access code over the public internet.
- Use Cloudflare Access or another identity layer before exposing the app.

Backup strategy:
- Same as local office only.
- Confirm backups still run when the app is accessed remotely.

Estimated code changes:
- Low. Review session cookie settings for HTTPS and proxy headers before pilot use.

Recommended use case:
- Leadership wants limited remote access while keeping office-local data.

## Option C: True cloud deployment with SQLite persistent disk

Architecture:
- App runs on a cloud VM or platform with a persistent disk.
- SQLite database, uploads, generated files, and backups live on that disk.

Pros:
- Remote access is easier.
- App availability is no longer tied to one office computer.
- Smaller change than PostgreSQL/object storage.

Cons:
- Persistent disk must be configured correctly.
- SQLite is still single-file storage and needs careful backup.
- File uploads/backups must not be on ephemeral storage.

Security risks:
- Shared access code is not enough for long-term internet exposure.
- HTTPS and secret management become mandatory.

Backup strategy:
- Disk snapshots plus app-level SQLite backups.
- Test restore into a separate environment.

Estimated code changes:
- Low to medium. Add production cookie/proxy settings, document persistent volume paths, and harden secrets.

Recommended use case:
- Small team remote usage where SQLite is still acceptable and persistent disk is guaranteed.

## Option D: True cloud deployment with PostgreSQL + object storage

Architecture:
- App runs on cloud compute.
- PostgreSQL stores relational data.
- Object storage stores uploads/generated/backups.
- Secrets are managed by the cloud platform.

Pros:
- Most scalable and cloud-standard.
- Better durability and backup options.
- Easier to add user accounts, roles, and future sales portal features.

Cons:
- Largest code and migration effort.
- Requires database migration, object storage integration, and deployment operations.
- More moving parts to monitor.

Security risks:
- Requires real authentication/authorization before handling sales quotation data.
- Public repo or leaked environment variables would be high risk.

Backup strategy:
- Managed PostgreSQL backups with restore tests.
- Object storage versioning/lifecycle policy.
- Separate export/restore procedure for business continuity.

Estimated code changes:
- High. Introduce database abstraction/migrations, PostgreSQL compatibility, object storage service, and stronger auth model.

Recommended use case:
- Future stage with remote teams, sales quotation data, and role-based access needs.

## Cloud-readiness checklist

- Decide deployment strategy before building a sales portal.
- Use HTTPS for any remote/public access.
- Review session cookie settings for HTTPS, proxy headers, and SameSite behavior.
- Do not expose the shared access code directly to the public internet.
- Use Cloudflare Access or future user accounts before remote production use.
- Keep SQLite on persistent storage if SQLite remains in use.
- Keep uploads, generated files, and backups on persistent storage.
- Define and test backup/restore before remote access.
- Store secrets in `.env` locally or managed secret storage in cloud.
- Never commit `.env`, database files, uploaded Excel files, generated files, or backups to a public repo.
