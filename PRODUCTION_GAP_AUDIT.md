# Production Gap Audit — v3

Existing v2 functionality was retained. The following relevant production gaps were added/refined without removing the 287 source features.

## Added hardening
1. Cross-instance Telegram webhook idempotency using a database-backed `processed_updates` table.
2. Failed webhook processing releases the update claim so Telegram can retry safely.
3. Database-backed cron fences prevent duplicate execution when Vercel invokes the cron endpoint concurrently.
4. Admin public-command isolation: the Admin account cannot enter the 10 public User command handlers by mistake.
5. Admin command audit records only the command name, never raw arguments or secrets.
6. Personal phone HMAC fingerprint for duplicate-account/referral-farming detection; the fingerprint is one-way.
7. Subscription expiry lifecycle: active memberships expire automatically and renewal notices are sent at most once per day.
8. Subscription renewal uses inline actions and does not expose internal implementation details.
9. Runtime cron heartbeat is persisted in the database for health monitoring after cold starts.
10. Web request body-size limit is configurable to reduce oversized webhook/API abuse.
11. Expanded Admin backup includes course grants, memberships, referrals, coin ledger, support contacts, tickets and interests in addition to core Users/Orders/Courses.
12. Reprovider-specific traces remain excluded from source/runtime configuration.
13. Existing secret scrubbing, encrypted phone storage, Mini App `initData` verification, webhook secret validation, rate limits, threat detection, freeze/ban controls and AI data boundaries remain active.

## Product-flow refinements
14. Course catalogue remains Mini App-only; user chat does not enumerate the catalogue.
15. Trending remains private-chat only.
16. Paid Community and CA Tracker Pro remain Mini App-gated.
17. Notion datasets remain separated as Daily CA, Editorial, Place in News and International Organisations with independent filters.
18. Admin remains a dedicated 29-command surface; public User commands are not published to the Admin scope.
19. Inline action buttons remain the primary navigation mechanism for user-facing automated messages.
20. UPSC countdown, scheduled deletion and serverless cron flow remain compatible with persistent and Vercel modes.

## Honest limitations
- No software can be guaranteed literally unhackable.
- A VPN/proxy can route outbound traffic but does not make the hosting provider or platform invisible.
- Telegram does not expose a user's true online/offline presence to bots; Admin auto-offline is therefore inferred from recent bot activity/quiet-hours settings.
- Full live Telegram/Gemini/Notion network testing depends on deployment credentials and network availability.
