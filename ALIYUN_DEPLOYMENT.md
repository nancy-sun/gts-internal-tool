# Alibaba Cloud Deployment Guide

This guide is for the first Alibaba Cloud staging deployment of GTS Internal Tool.

Do not migrate local SQLite development data. Production starts with a fresh PostgreSQL database, and the first admin is created through `/setup-admin`.

## A. Alibaba Resources

Create these resources first:

- ECS instance for the Docker app container.
- Alibaba Cloud RDS PostgreSQL instance for production data.
- ECS security group allowing only required inbound ports, normally `80` and `443`.
- RDS whitelist or security group rule allowing only the ECS private IP or ECS security group.
- Domain after ICP filing, for example `internal.gtsmotor.cn`.

Recommended placement:

- ECS and RDS should be in the same Alibaba Cloud region.
- ECS and RDS should be in the same VPC when possible.
- The app should connect to RDS through the RDS internal endpoint.
- Do not whitelist `0.0.0.0/0` on RDS.

## B. Production Environment File

Create `.env.production` on the ECS server. Do not commit it to git.

Use `.env.production.example` as the template:

```text
APP_NAME="GTS Internal Tool"
APP_ENV=production
APP_PORT=8080
DATABASE_URL=postgresql+psycopg://user:password@rds-internal-host:5432/dbname
SESSION_SECRET_KEY=replace-with-a-long-random-secret
ENABLE_LEGACY_ACCESS_CODE=false
BASE_URL=https://internal.gtsmotor.cn
FORCE_HTTPS=true
SECURE_COOKIES=true
MAX_UPLOAD_SIZE_MB=10
UPLOAD_DIR=/data/uploads
GENERATED_DIR=/data/generated
BACKUP_DIR=/data/backups
```

Do not put real passwords or session secrets in documentation, screenshots, or tickets.

## C. Persistent File Directories

The first deployable version does not use OSS. Uploaded files, generated files, and local backup artifacts are stored in ECS host directories mounted into Docker.

Create these exact host paths:

```bash
sudo mkdir -p /data/uploads /data/generated /data/backups
sudo chown -R $USER:$USER /data/uploads /data/generated /data/backups
```

Docker must mount:

- `/data/uploads:/data/uploads`
- `/data/generated:/data/generated`
- `/data/backups:/data/backups`

Important files must not live only inside the container filesystem. If the container is recreated without these mounts, uploaded/generated files can be lost.

## D. Docker Deployment

Clone and build on ECS:

```bash
git clone <repo-url> gts-internal-tool
cd gts-internal-tool
git checkout feature/auth-cloud-readiness
docker build -t gts-internal-tool:staging .
```

Run the container:

```bash
docker run -d \
  --name gts-internal-tool \
  --env-file .env.production \
  -p 127.0.0.1:8080:8080 \
  -v /data/uploads:/data/uploads \
  -v /data/generated:/data/generated \
  -v /data/backups:/data/backups \
  gts-internal-tool:staging
```

Verify local health from ECS:

```bash
curl -i http://127.0.0.1:8080/healthz
```

Expected response:

```json
{"status":"ok","database":"ok"}
```

For local PostgreSQL smoke testing before ECS deployment, use `docker-compose.yml`. It starts the app and a local PostgreSQL container with persistent compose volumes.

## E. Nginx Reverse Proxy

Terminate HTTPS in Nginx and proxy to the app on localhost.

Example:

```nginx
server {
    listen 80;
    server_name internal.gtsmotor.cn;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name internal.gtsmotor.cn;

    ssl_certificate /etc/nginx/ssl/internal.gtsmotor.cn.crt;
    ssl_certificate_key /etc/nginx/ssl/internal.gtsmotor.cn.key;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Required app settings behind HTTPS proxy:

```text
BASE_URL=https://internal.gtsmotor.cn
FORCE_HTTPS=true
SECURE_COOKIES=true
```

The Docker command runs Uvicorn with proxy header support. Nginx must pass `X-Forwarded-Proto` so the app can recognize HTTPS correctly.

## F. First Admin Setup

1. Open `https://internal.gtsmotor.cn`.
2. A fresh PostgreSQL database redirects to `/setup-admin`.
3. Create the first admin user.
4. Use `用户管理` to create employee accounts.

After the first user exists, `/setup-admin` redirects to `/login` and cannot create another bootstrap admin.

## G. Security Checks

Before staff use staging:

- Confirm `/healthz` works without login and does not expose secrets or paths.
- Confirm business pages redirect to `/login`.
- Confirm non-admin users cannot access `/admin/users`.
- Confirm `robots.txt` disallows all crawlers.
- Confirm responses include `X-Robots-Tag: noindex, nofollow, noarchive`.
- Confirm `ENABLE_LEGACY_ACCESS_CODE=false`.
- Confirm sensitive writes require logged-in user password confirmation.

## H. Data Policy

- Current SQLite development data is not migrated.
- SQLite IDs are not preserved.
- Production starts empty.
- Future production business data lives in RDS PostgreSQL.
- Uploaded/generated files live in mounted ECS directories until OSS is implemented later.

## I. Backup

- Enable RDS automatic backups and set retention according to company policy.
- Test RDS restore into a separate staging environment before production use.
- Back up ECS host directories:
  - `/data/uploads`
  - `/data/generated`
  - `/data/backups`
- SQLite manual/auto backup behavior remains for local SQLite mode. PostgreSQL database backups should be handled by RDS.

## J. Rollback

- Keep the previous Docker image tag before upgrading.
- Keep `.env.production` outside git.
- If app rollback is needed, stop the new container and start the previous image.
- If database rollback is needed, restore RDS from an Alibaba Cloud backup into a controlled environment.
- Verify `/healthz` and login after rollback.
