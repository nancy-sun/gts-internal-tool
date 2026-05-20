# Deployment Checklist

Use this checklist before the first Alibaba Cloud staging deployment.

## Before Deployment

- [ ] `python3 -m pytest tests` passes.
- [ ] Docker image builds successfully.
- [ ] Docker Compose PostgreSQL smoke test passes.
- [ ] `.env.production` is created on the server outside git.
- [ ] `.env.production` uses `SESSION_SECRET_KEY`, not a placeholder.
- [ ] `.env.production` uses `DATABASE_URL=postgresql+psycopg://...`.
- [ ] `ENABLE_LEGACY_ACCESS_CODE=false`.
- [ ] RDS PostgreSQL instance is created.
- [ ] Production database is empty and ready for `/setup-admin`.
- [ ] ECS security group is configured.
- [ ] RDS whitelist/security group allows only ECS private IP or ECS security group.
- [ ] Persistent host directories exist:
  - [ ] `/data/uploads`
  - [ ] `/data/generated`
  - [ ] `/data/backups`
- [ ] Docker run or compose mounts persistent directories:
  - [ ] `/data/uploads:/data/uploads`
  - [ ] `/data/generated:/data/generated`
  - [ ] `/data/backups:/data/backups`
- [ ] Nginx is configured as HTTPS reverse proxy.
- [ ] Nginx passes `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto`.
- [ ] HTTPS certificate is installed.
- [ ] `FORCE_HTTPS=true`.
- [ ] `SECURE_COOKIES=true`.

## Startup Verification

- [ ] Container starts successfully.
- [ ] `curl -i http://127.0.0.1:8080/healthz` returns database ok from ECS.
- [ ] Public/staging `/healthz` returns `{"status":"ok","database":"ok"}`.
- [ ] `/healthz` does not expose secrets, paths, or `DATABASE_URL`.
- [ ] `/robots.txt` returns `Disallow: /`.
- [ ] Business pages redirect to `/login` before login.
- [ ] `/setup-admin` creates the first admin on the empty PostgreSQL database.
- [ ] After admin exists, `/setup-admin` no longer allows bootstrap admin creation.
- [ ] Admin can log in.
- [ ] Non-admin cannot access `/admin/users`.

## Workflow Smoke Test

- [ ] Create at least one non-admin employee account.
- [ ] Upload quotation preview opens.
- [ ] Supplier matching in upload preview works.
- [ ] Confirm quotation import works after supplier matching is resolved.
- [ ] Search database works.
- [ ] Generate quotation Excel works.
- [ ] Supplier list and supplier edit work.
- [ ] Product edit requires password confirmation.
- [ ] HS Code upload/report works if needed for staging.
- [ ] Operation logs show the logged-in user.

## Backup And Rollback

- [ ] RDS automatic backup is enabled.
- [ ] RDS restore process is documented/tested for staging.
- [ ] ECS `/data/uploads`, `/data/generated`, and `/data/backups` backup method is defined.
- [ ] Previous Docker image tag is retained.
- [ ] Rollback command/process is documented for the server.
