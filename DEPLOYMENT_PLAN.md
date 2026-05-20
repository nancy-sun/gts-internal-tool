# DEPLOYMENT_PLAN

This project is Docker/PostgreSQL deployable for a first Alibaba Cloud staging environment. Do not expose it publicly until HTTPS, RDS access rules, backups, and staff account setup are verified.

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
- Employee username/password login is now primary.
- Keep the old shared access code disabled unless emergency access is needed.

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
- Employee username/password login is required for cloud access.
- HTTPS and secret management become mandatory.

Backup strategy:
- Disk snapshots plus app-level SQLite backups.
- Test restore into a separate environment.

Estimated code changes:
- Low to medium. Add production cookie/proxy settings, document persistent volume paths, and harden secrets.

Recommended use case:
- Small team remote usage where SQLite is still acceptable and persistent disk is guaranteed.

## Option D: True cloud deployment with PostgreSQL + future object storage

Architecture:
- App runs on cloud compute.
- PostgreSQL stores relational data.
- First deployable version stores uploads/generated/backups on ECS persistent mounted directories.
- Object storage is a future step.
- Secrets are managed by the cloud platform.

Pros:
- Most scalable and cloud-standard.
- Better durability and backup options.
- Easier to add user accounts, roles, and future sales portal features.

Cons:
- Largest code and migration effort.
- Requires deployment operations and PostgreSQL schema verification.
- Object storage integration remains future work.
- More moving parts to monitor.

Security risks:
- Requires real authentication/authorization before handling sales quotation data.
- Public repo or leaked environment variables would be high risk.

Backup strategy:
- Managed PostgreSQL backups with restore tests.
- ECS persistent directory backups for `/data/uploads`, `/data/generated`, and `/data/backups`.
- Future object storage versioning/lifecycle policy.
- Separate export/restore procedure for business continuity.

Estimated code changes:
- Low for first staging deployment. PostgreSQL compatibility and Docker packaging are implemented; OSS remains future work.

Recommended use case:
- Recommended production direction: Docker app on ECS plus Alibaba Cloud RDS PostgreSQL. Production starts empty and first admin is created through `/setup-admin`.

## Cloud-readiness checklist

- Decide deployment strategy before building a sales portal.
- Complete `DEPLOYMENT_CHECKLIST.md` before Alibaba Cloud staging.
- Use HTTPS for any remote/public access.
- Review session cookie settings for HTTPS, proxy headers, and SameSite behavior.
- Keep legacy shared access code disabled by default.
- Use employee username/password accounts and refine role permissions before storing sales quotation data.
- Keep SQLite on persistent storage if SQLite remains in use.
- For Docker deployment, mount `/data/uploads`, `/data/generated`, and `/data/backups` as persistent directories.
- Use PostgreSQL `DATABASE_URL` for production and leave `DATABASE_URL` empty for local SQLite development.
- Do not migrate local SQLite development data into production PostgreSQL.
- Define and test backup/restore before remote access.
- Store secrets in `.env` locally or managed secret storage in cloud.
- Never commit `.env`, database files, uploaded Excel files, generated files, or backups to a public repo.
