# Alibaba Cloud Deployment Guide

This guide describes the first Docker deployable version. Do not migrate local SQLite development data. Production starts with a fresh PostgreSQL database, and the first admin is created through `/setup-admin`.

## A. Alibaba Resources

- ECS instance for the Docker app container.
- RDS PostgreSQL instance for production data.
- ECS security group allowing only required inbound ports, normally 80/443 from office/VPN or approved networks.
- RDS whitelist or security group rule allowing the ECS private IP/security group only.
- Domain after ICP filing, for example `internal.gtsmotor.cn`.

## B. RDS Connection

- Put ECS and RDS in the same Alibaba Cloud region and VPC when possible.
- Use the RDS internal endpoint from ECS.
- Do not whitelist `0.0.0.0/0`.
- Store the RDS URL only in `.env.production` on the server:

```text
DATABASE_URL=postgresql+psycopg://user:password@rds-internal-host:5432/dbname
```

## C. Docker Deployment

1. Clone the repo on ECS.
2. Checkout the deployment branch.
3. Create `.env.production` from `.env.production.example`.
4. Set real secrets and RDS `DATABASE_URL`.
5. Create persistent local directories:

```bash
mkdir -p /data/uploads /data/generated /data/backups
```

6. Build and run the app:

```bash
docker build -t gts-internal-tool .
docker run -d \
  --name gts-internal-tool \
  --env-file .env.production \
  -p 8080:8080 \
  -v /data/uploads:/data/uploads \
  -v /data/generated:/data/generated \
  -v /data/backups:/data/backups \
  gts-internal-tool
```

7. Verify:

```bash
curl http://127.0.0.1:8080/healthz
```

For local PostgreSQL smoke testing, use `docker-compose.yml`; it starts both the app and a local PostgreSQL container.

## D. Nginx Reverse Proxy

- Point `internal.gtsmotor.cn` to ECS.
- Terminate HTTPS in Nginx.
- Proxy to `http://127.0.0.1:8080`.
- Pass proxy headers:

```nginx
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

Set in `.env.production`:

```text
BASE_URL=https://internal.gtsmotor.cn
FORCE_HTTPS=true
SECURE_COOKIES=true
```

## E. First Admin Setup

1. Open the production URL.
2. The empty PostgreSQL database redirects to `/setup-admin`.
3. Create the first admin.
4. Use `用户管理` to create employee accounts.

## F. Data Policy

- Current SQLite development data is not migrated.
- SQLite IDs are not preserved.
- Production starts empty.
- Future production data lives in RDS PostgreSQL.

## G. File Storage Policy

- This version does not implement OSS.
- Uploads, generated files, and local backup artifacts are stored on ECS persistent mounted directories:
  - `/data/uploads`
  - `/data/generated`
  - `/data/backups`
- These directories must be included in ECS backup procedures.
- OSS is a future task for product images, contracts, large generated files, and long-term file durability.

## H. Backup

- Enable RDS automatic backups and set retention according to company policy.
- Test RDS restore into a separate environment before production use.
- Back up `/data/uploads`, `/data/generated`, and `/data/backups`.
- PostgreSQL database backup is managed by RDS; the SQLite auto-backup command is for local SQLite mode only.

## I. Rollback

- Keep the previous Docker image tag before upgrading.
- Keep `.env.production` outside git.
- If application rollback is needed, stop the new container and start the previous image.
- If data rollback is needed, restore RDS from an Alibaba Cloud backup.
