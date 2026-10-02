# UPSC Course Zone

React/Vite learning portal with an Express Telegram bot backend. The source contains five seed course listings recovered from existing server messages; this is not the full 233-course catalog. No Current Affairs article data or payment provider is included.

## Local development

```sh
npm install
npm run dev
```

The app runs on `http://localhost:3000`. Use `npm run build` for the static frontend and `npm run lint` for TypeScript checks.

## Vercel

Vercel builds the Vite site to `dist` and routes `/api/*`, `/webapp/*`, and `/webhook` to `api/index.ts`. See [VERCEL_DEPLOY.md](VERCEL_DEPLOY.md) for environment configuration and operational limits.

Required Vercel variables: `BOT_TOKEN`, `ADMIN_ID`, `BACKUP_CHANNEL`, and `CRON_SECRET`. `WEBAPP_BASE_URL` can be omitted on Vercel because `VERCEL_URL` is used. `GEMINI_API_KEY` is optional; without it, AI-assisted messages use a short static fallback.

Never commit `.env` or provider credentials. Vercel functions are stateless: user/group registries and Admin reply mappings are in memory and are not durable. Automatic message deletion requires a persistent queue and is disabled in Vercel mode. No PhonePe/Amazon Pay subscription or payment processing is implemented; enrollment requests do not grant access.

## Bot commands

Users: `/start`, `/menu`, `/trending`, `/account`, `/referral`, `/study`, `/support`, `/ask`, `/community`, `/ca`.

Admin-only commands are registered to the configured `ADMIN_ID`. `/broadcast <message>`, `/promo <message>`, `/countdown`, `/gm`, and `/gn` are supported. A group is targeted only after the bot has received an update there; pinning requires bot admin permission.

`/api/cron` is scheduled once daily at 02:00 UTC (07:30 IST) and sends the countdown plus morning message. Night messages remain manually available with `/gn`; daily Vercel night scheduling and durable deletion are not configured.