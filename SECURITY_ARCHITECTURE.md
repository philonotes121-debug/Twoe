# Security architecture

- Admin authorization is server-side and independent of Telegram command menus.
- User command scope is separate from Admin command scope; verified users receive a maximum of 10 public commands.
- Unverified users receive only `/start` and a phone-contact verification request.
- A user's phone number is stored only after the user explicitly shares their own Telegram contact; it is encrypted at rest and decrypted only in authorized Admin workflows.
- Referral links are signed opaque tokens with expiry. Self-referrals, invalid tokens, duplicate referred users, banned actors and reward-cap abuse are rejected.
- Course catalog data is served only from authenticated LMS Mini App endpoints. System subscription products are excluded from the public course catalog.
- Community and CA Tracker Pro access is enforced at the Mini App/API layer, not just by buttons.
- Telegram webhook uses a secret header derived from the bot token.
- Mini App endpoints verify Telegram `initData` HMAC and freshness before exposing user data.
- Logs redact bot token, AI key, Admin ID/username and IPv4 addresses.
- HTTP security headers include CSP, no-referrer, no-store, frame denial and noindex.
- User-to-Admin support is relayed through the bot; direct Admin identity is not exposed to users.
- Admin online/offline auto mode is based on persistent bot-interaction heartbeat because Telegram does not provide a bot-readable live presence API for arbitrary users.
- Vercel mode uses protected cron ticks instead of assuming persistent background workers.
- Auto-heal covers dispatcher/runtime failures; it is recovery logic, not an absolute security guarantee.
- Optional outbound proxy support can route server egress through a controlled proxy/VPN gateway.
