# Vercel deployment

1. Import this repository root as a Vercel project. The project uses Vite for static assets and `api/index.ts` as the Node serverless handler.
2. Add required variables in Project Settings: `BOT_TOKEN`, `ADMIN_ID`, `BACKUP_CHANNEL`, `CRON_SECRET`.
3. Optionally add `GEMINI_API_KEY` for AI-assisted `/ask`, evaluation, GM, and GN messages. `WEBAPP_BASE_URL` can be omitted because Vercel provides `VERCEL_URL`; set it explicitly only when using a custom domain. `TELEGRAM_WEBHOOK_SECRET` is optional and otherwise derived from the bot token.
4. Deploy, then request `/api/health` once. The function configures the Telegram webhook at `/webhook`; add the bot as an administrator to the backup channel and grant appropriate group pin permissions.
5. Vercel Cron calls `/api/cron` daily at 02:00 UTC (07:30 IST). `CRON_SECRET` protects this endpoint.

Do not upload `.env`, tokens, or private keys to GitHub. Configure secrets only in Vercel Project Settings.

## Runtime limits

The current user, group, and Admin reply registries are process-memory Maps. They reset across Vercel cold starts and are not shared between function instances. The scheduled countdown can run, but its recipient list is not durable until a database is configured. Vercel mode disables `setTimeout` message deletion because serverless functions cannot guarantee a ten-hour timer. Durable broadcasts, deletion, user activity history, and backup require a persistent database/queue.

PhonePe/Amazon Pay, gift-card verification, paid subscriptions, and course entitlement processing are not integrated. No payment is captured and an enrollment request does not unlock content. The catalog currently contains five metadata seed records and the Current Affairs dataset is empty; replace these with the authoritative catalog before launch.

## Local mode

For a persistent local Node process, use `npm install` followed by `npm run dev`. Local polling and in-process 10-hour deletion timers are enabled outside Vercel.