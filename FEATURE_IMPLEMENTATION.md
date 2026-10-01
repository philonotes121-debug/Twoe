# Feature implementation / consolidation map

Source of truth: `LMS_AZ_Feature_Checklist_TABLET_WORKING (1).xlsx`.

- USER: all 90 capabilities retained; only 10 public user commands exposed.
- ADMIN: all 88 capabilities retained; consolidated into 29 Admin-only commands.
- SECURITY: all 88 rows are treated as included, including previously unselected rows.
- AI: all 21 rows are treated as included, including previously unselected rows.

## Admin command surface (29)

`/adminhelp` `/lms` `/users` `/orders` `/content` `/subscriptions` `/promo` `/broadcast` `/schedule` `/inbox` `/groups` `/referrals` `/analytics` `/ai` `/presence` `/security` `/privacy` `/health` `/backup` `/recovery` `/moderation` `/resources` `/notion` `/countdown` `/settings` `/audit` `/export` `/system` `/lockdown`

Legacy Admin commands remain internally gated for compatibility/callback flows but are not published in the Admin command menu.

## User command policy

Exactly 10 verified-user commands are published. Before phone verification only `/start` is published. Course catalog routes stay inside the LMS Mini App; only Trending is intentionally exposed in the user's personal chat.

## Paid plans

- Join Our Community — ₹800 / 30 days: all LMS courses, personal AI tracking, answer evaluation.
- CA TRACKER PRO by Professor 🥼 — ₹200 / 30 days: Notion-synced Daily CA, Editorial, Place in News and International Organisations datasets with separate dataset tabs, filters and zoom.

## Security notes

The AI may sound natural and concise, but it must not falsely claim to be the real human Administrator. Admin identity, host/device details and secrets are never intentionally exposed to users.
