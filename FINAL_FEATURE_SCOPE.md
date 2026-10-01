# Final Feature Scope

Source: `FEATURE_CHECKLIST_SOURCE.xlsx` (uploaded checklist).

## Inclusion policy
- USER: all 90 capabilities retained; only 10 user-facing commands are exposed, with overlapping capabilities consolidated behind them and/or Mini App flows.
- ADMIN: all 88 capabilities retained; exactly 29 Admin-only commands are exposed. No User command is included in the Admin command scope.
- SECURITY: all 88 capabilities included, including every row that was previously unselected in the workbook.
- AI: all 21 capabilities included, including every row that was previously unselected in the workbook.

## User command scope (10)
`/start` `/menu` `/trending` `/account` `/referral` `/study` `/support` `/ask` `/community` `/ca`

## Admin command scope (29)
`/adminhelp` `/lms` `/users` `/orders` `/content` `/subscriptions` `/promo` `/broadcast` `/schedule` `/inbox` `/groups` `/referrals` `/analytics` `/ai` `/presence` `/security` `/privacy` `/health` `/backup` `/recovery` `/moderation` `/resources` `/notion` `/countdown` `/settings` `/audit` `/export` `/system` `/lockdown`

## Access rules
- User LMS Mini App unlock: mobile-number verification.
- Admin LMS approval state is retained for audit/workflow and does not replace phone verification.
- Course catalogue is rendered inside the LMS Mini App; public chat does not expose a course list.
- Trending is allowed only in private user chat.
- Admin command handlers fail closed for non-admin users and the Admin command scope is chat-specific.

## Paid plans
- Join Our Community: INR 800 / 30 days; all courses, personal AI tracking, answer evaluation.
- CA TRACKER PRO by Professor 🥼: INR 200 / 30 days; Notion-synced Daily CA, Editorial, Place in News, International Organisations, independent filters/search/zoom.

## Automation
- Promo creation broadcasts to enabled groups and schedules deletion after 12 hours.
- UPSC Prelims 2027 countdown defaults to the official calendar date in config.
- Vercel tick mirrors scheduled/deletion/reminder/alert/referral/order/COTD/countdown tasks without infinite background loops.

## Security acceptance criteria
- No hard-coded production secrets.
- Telegram webhook secret verification.
- Mini App initData HMAC verification.
- Encrypted phone-number storage.
- Log/message secret scrubbing.
- Rate limiting/threat detection/auto-heal/state recovery retained.
- AI is portal-grounded and isolated from Admin/other-user secrets.
