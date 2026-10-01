# Secure LMS Telegram Bot

Single-app Telegram LMS with a protected Mini App, separate Admin/User command scopes, mandatory phone verification, paid Community + CA Tracker Pro plans, Notion sync, secure referrals, AI Helper, persistent deletion, group broadcasts and Vercel cron support.

## Repository layout

- `main:app`: Vercel Python function entrypoint; imports the FastAPI app from `main.py`.
- `main.py`: FastAPI app, Telegram webhook, health and protected cron routes.
- `*_handlers.py`, `admin_*.py`, `features.py`: Telegram command and feature handlers.
- `ai.py`, `ai_brain.py`: Gemini integration and student conversation memory.
- `database.py`, `services.py`, `security.py`, `privacy.py`: persistence and shared application services.
- `webapp_template.py`, `miniapp_portal.py`: Mini App pages.
- `tools/validate_release.py`: offline release and feature-scope validation.
- `*_SCOPE.md`, `FEATURE_*.md`, `SECURITY_*.md`, `PRODUCTION_*.md`: product and operations documentation.

Python modules stay at the repository root because they share top-level imports and the Vercel entrypoint imports `main` directly.

## Deploy to Vercel

1. Import this repository into Vercel with the Python runtime enabled.
2. Configure the environment variables from `.env.example` in Project Settings, leaving unused optional integrations blank. Use a managed PostgreSQL database for durable production storage; Vercel's local filesystem is not persistent.
3. Set `WEBAPP_BASE_URL` to the deployed HTTPS URL, and set strong values for `CRON_SECRET`, `DATA_ENCRYPTION_KEY` and `REFERRAL_SIGNING_SECRET`.
4. Deploy, then check `/api/health`. Configure the Telegram bot webhook to `https://<your-domain>/webhook` if it was not set during app startup.

See [VERCEL_DEPLOY.md](VERCEL_DEPLOY.md) for setup details and optional integrations.

## Public User commands (maximum 10)
`/start` · `/menu` · `/trending` · `/account` · `/referral` · `/study` · `/support` · `/ask` · `/community` · `/ca`

## Admin commands
`/adminhelp` · `/lms` · `/users` · `/orders` · `/content` · `/subscriptions` · `/promo` · `/broadcast` · `/schedule` · `/inbox` · `/groups` · `/referrals` · `/analytics` · `/ai` · `/presence` · `/security` · `/privacy` · `/health` · `/backup` · `/recovery` · `/moderation` · `/resources` · `/notion` · `/countdown` · `/settings` · `/audit` · `/export` · `/system` · `/lockdown` · `/addcourse` · `/quickadd` · `/listsectionkeys` · `/grant` · `/price` · `/listcourses` · `/listsections` · `/userinfo` · `/activity` · `/contacthistory` · `/pending`

## Important
- Course catalogue/cards are Mini App only; Trending is private-chat only.
- Phone verification requires explicit self-contact share.
- The bot never exposes Admin identity, secret keys or hosting/device details to users.
- The optional outbound proxy is only an egress-routing control, not an anonymity guarantee.
- On Vercel, background work is executed through the protected `/api/cron` route.
- The default UPSC Prelims 2027 countdown date is 23 May 2027; set `EXAM_DATE` only when an explicit override is required.

## Release v2 notes

- Admin surface: 40 commands; no User commands in Admin scope.
- User surface: 10 verified commands; unverified users receive only `/start`.
- LMS unlock: phone verification + global emergency gate.
- CA Tracker: separate Notion-backed datasets and Mini App filters.
- `/api/cron`: protected by `CRON_SECRET`; Hobby deployment is configured for one daily invocation.

## Vercel deployment notes

- The project is pinned to Python 3.13 with `.python-version`.
- Vercel uses the current Services configuration with `main:app` as the FastAPI entrypoint; the legacy `/api/index.py` rewrite shim and `functions` block are not used.
- The FastAPI app remains the single `main:app` backend, so `/webhook`, `/api/*`, `/webapp/*` and `/` continue through the same application.
- The included Vercel configuration is Hobby-safe and invokes `/api/cron` once daily at 19:30 IST. Minute-level background ticks require a Vercel plan that supports minutely Cron Jobs or a separate supported scheduler; the application code and protected `/api/cron` endpoint remain intact.

## v3 production hardening
The release also includes database-backed webhook idempotency, cron race protection, Admin/public command isolation, one-way phone fingerprinting for referral abuse control, membership expiry handling, persisted cron heartbeat, oversized-request protection and expanded Admin backups. See `PRODUCTION_GAP_AUDIT.md`.
