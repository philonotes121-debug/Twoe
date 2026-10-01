# DEPLOYMENT_NOT_FOUND — Final Fix Notes

`404 DEPLOYMENT_NOT_FOUND` is a Vercel deployment/domain-state error, not an application HTTP 404. Vercel documents that it occurs when the referenced deployment does not exist, has been deleted, the URL is wrong, or access to the deployment is unavailable.

This package is intentionally a clean deployment root: `main.py`, `vercel.json`, `requirements.txt`, and `.python-version` are at the repository root. Do not create an extra nested project folder inside GitHub.

## Required deployment setup

1. Create/import a GitHub repository with the CONTENTS of this folder at the repository root.
2. In Vercel, create/import a project from that repository.
3. Root Directory must be the repository root.
4. Deploy to Production.
5. Wait for the deployment to show READY.
6. Open the project domain shown on that READY deployment. Do not reuse an old deployment-specific hostname that now returns `DEPLOYMENT_NOT_FOUND`.
7. Test `/` and `/api/health`.

## Environment

Production needs a PostgreSQL/Neon `DATABASE_URL` (or one of the supported PostgreSQL aliases). MongoDB URLs are not supported by this SQLAlchemy application and are rejected/fallback-protected by `database.py`.

## Expected result

`/api/health` should return a healthy application response. For durable production storage it should report PostgreSQL-backed storage rather than ephemeral SQLite fallback.
