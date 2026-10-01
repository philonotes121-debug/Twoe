# Vercel deployment

1. Import the extracted project root as one Vercel project. `vercel.json` uses the Services model and points the backend to `main:app`; do not select an outer nested ZIP directory as the project root.
2. Set the environment variables from `.env.example` in Vercel Project Settings.
3. Never upload `.env`, database files, runtime state or provider tokens.
4. `WEBAPP_BASE_URL` must be the public HTTPS URL of this same Vercel project.
5. Set `CRON_SECRET` to a long random secret; `/api/cron` rejects missing/incorrect Authorization.
6. Set `DATA_ENCRYPTION_KEY` to a valid Fernet key. Generate one locally with:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
7. Set `REFERRAL_SIGNING_SECRET` to a long random value.
8. Add the Notion integration to the databases/data sources used by CA Tracker Pro and copy their IDs.
9. Add the bot to the backup channel as required for membership checks.
10. The included Hobby-safe Vercel Cron route runs `/api/cron` once daily at 19:30 IST (14:00 UTC). The protected endpoint and idempotent serverless tick remain intact. Minute-level scheduling requires a Vercel plan that supports minutely Cron Jobs or another supported scheduler.

Use managed PostgreSQL in production. SQLite is provided only as a local fallback because serverless instance files are temporary and are not shared between invocations.

## First deploy without environment variables

The FastAPI service is intentionally safe to boot before secrets are configured. The `/` and `/api/health` endpoints can load in this state; Telegram bot routes return `503` until a valid `BOT_TOKEN` is configured. This avoids a deployment-wide `500 FUNCTION_INVOCATION_FAILED` caused by aiogram validating an empty token during module import.

For the bot to become functional, configure `BOT_TOKEN` and `ADMIN_ID`. For secure production operation also configure `CRON_SECRET`, `DATA_ENCRYPTION_KEY`, and `REFERRAL_SIGNING_SECRET`. `GEMINI_API_KEY` enables AI features; it is optional for the base web service. `WEBAPP_BASE_URL` may be omitted because the application falls back to Vercel's `VERCEL_URL` system variable when available. Vercel documents `VERCEL_URL` as the generated deployment domain and supports FastAPI Services with a `main:app` entrypoint.

## Import existing Livegram users

Use the same Telegram bot token to preserve the existing bot identity. Save the Livegram JSON export (or `ID | @username` text list) under the ignored `data/` directory. Point `DATABASE_URL` at the production PostgreSQL database, preview the import, then apply it:

```sh
python tools/import_livegram_users.py data/livegram_users.txt
python tools/import_livegram_users.py data/livegram_users.txt --apply
```

The importer stores Telegram IDs and usernames, preserves existing user fields and bans, and is safe to rerun. Imported users count in `/stats` and `/analytics`; `/broadcast users` targets all non-banned users. Never commit the export to GitHub. Telegram does not provide old conversation history through the Bot API, and users who blocked the bot cannot receive broadcasts.

The application does not use provider-specific host environment fallbacks. The optional `OUTBOUND_PROXY` is only for outbound traffic routing; it does not make the application or hosting platform anonymous or unhackable. Cron secrets are accepted through headers only, never through a URL query parameter.


## Runtime compatibility

- Python is pinned to 3.13 via `requirements.txt + .python-version`. Vercel supports Python 3.12, 3.13 and 3.14, and this project intentionally pins 3.13 for dependency stability.
- Gemini uses the current Google Gen AI SDK `2.23.0`; the code uses the stable `genai.Client().models.generate_content(...)` API.
- Current default AI model: `gemini-3.8-flash`; fallback: `gemini-3.5-flash-lite`.


## Environment variables
