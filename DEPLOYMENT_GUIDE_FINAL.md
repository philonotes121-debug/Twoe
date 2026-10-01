# 🚀 FINAL DEPLOYMENT GUIDE - Bot Telegram Vercel

## ⚠️ CRITICAL FIX APPLIED
**Issue**: `sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:mongodb.srv`
**Root Cause**: Old MongoDB connection string in DATABASE_URL
**Solution**: Use PostgreSQL (Neon/Vercel Postgres) instead

---

## 📋 PRE-DEPLOYMENT CHECKLIST

### 1. **Remove Old MongoDB Environment Variables**
Go to Vercel Dashboard → Project Settings → Environment Variables
- ❌ DELETE any variable named:
  - `DATABASE_URL` (if it starts with `mongodb+srv://`)
  - `MONGO_URI`
  - `MONGODB_CONNECTION_STRING`

### 2. **Add PostgreSQL Connection (Choose ONE)**

#### Option A: **Vercel Postgres** (Recommended)
1. Go to Vercel Dashboard → Your Project
2. Click "Storage" tab → Create Database → "Postgres"
3. Copy the connection string ending in `?sslmode=require`
4. Create new env var: `POSTGRES_URL` = (paste the string)

#### Option B: **Neon** (Free Alternative)
1. Visit [neon.tech](https://console.neon.tech/)
2. Create new project
3. Copy connection string
4. Create new env var: `NEON_DATABASE_URL` = (paste the string)

#### Option C: **Railway/Other Postgres**
1. Get your PostgreSQL async connection string
2. Format: `postgresql+asyncpg://user:password@host:port/dbname`
3. Create env var: `DATABASE_URL` = (paste formatted string)

---

## 🔧 STEP-BY-STEP DEPLOYMENT

### Step 1: Verify Environment Variables in Vercel
Ensure these are set in Vercel Dashboard (Settings → Environment Variables):
```
BOT_TOKEN=<your_telegram_bot_token>
ADMIN_ID=<your_telegram_user_id>
BOT_NAME=UPSC Course Zone by Professor
GEMINI_API_KEY=<your_gemini_api_key>
POSTGRES_URL=<your_postgres_connection_string>  # OR NEON_DATABASE_URL
ADMIN_USERNAME=your_username
BACKUP_CHANNEL=https://t.me/your_backup_channel
CRON_SECRET=any_random_secret_key
PERSONAL_DATA_HMAC_KEY=any_random_secret_key
DATA_ENCRYPTION_KEY=any_random_secret_key
REFERRAL_SIGNING_SECRET=any_random_secret_key
```

### Step 2: Download All Project Files
Copy ALL files from this folder to your local machine:
```bash
# Everything in Bot-telegram-vercel-final-deploy-ready-v3/
- main.py
- database.py
- requirements.txt
- vercel.json
- config.py
- all handler files (.py files)
- all other supporting files
```

### Step 3: Push to Vercel via Git
```bash
# Initialize git (if not already done)
git init
git add .
git commit -m "Fix: MongoDB → PostgreSQL migration, command fixes"

# Connect to Vercel (if not already connected)
vercel link

# Deploy
vercel --prod
```

OR **Drag & Drop in Vercel Dashboard**:
1. Go to Vercel Dashboard → Your Project
2. Drop the files folder
3. Vercel will auto-deploy

### Step 4: Verify Deployment
```bash
# Check logs in Vercel Dashboard
# URL: https://vercel.com/<team>/<project>/functions

# Should see:
✅ "Database initialized successfully"
✅ "User commands registered: 10 commands"
✅ "Admin commands registered: 29+ commands"
✅ "Bot is running on Vercel"
```

### Step 5: Test the Bot
1. Open Telegram
2. Search for your bot (by BOT_NAME or username)
3. Press `/start`
4. Should show: "Verify & open LMS"

**For Admin** (ADMIN_ID user only):
- Type `/adminhelp` → Should show full admin menu
- Should see 29+ admin commands

**For Regular User**:
- Type `/menu` → Open LMS
- Type `/trending` → Trending courses
- Type `/account` → Account info
- Type `/referral` → Referral system
- Type `/study` → Study tracker
- Type `/support` → Support
- Type `/ask` → AI Helper
- Type `/community` → Community channel
- Type `/ca` → CA Tracker

---

## ✅ COMMAND VERIFICATION

### User Commands (10 total)
```
/start        - Verify & open LMS
/menu         - Open LMS
/trending     - Trending (private chat)
/account      - Account, access & orders
/referral     - Referral & rewards
/study        - Target, streak & reminders
/support      - Support & doubt
/ask          - AI Helper
/community    - Join Our Community ₹800/month
/ca           - CA Tracker Pro ₹200/month
```

### Admin Commands (29+ total)
```
/adminhelp    - Admin control centre
/lms          - LMS access & gate
/users        - Users & profiles
/orders       - Payments & grants
/content      - Courses & sections
/subscriptions- Community & CA plans
/promo        - Promo + 12h group broadcast
/broadcast    - Broadcast messages
/schedule     - Scheduled campaigns
/inbox        - Support inbox
/groups       - Connected groups/chats
/referrals    - Referral audit
/analytics    - Analytics
/ai           - AI controls
/presence     - Admin online/offline
/security     - Security posture
/privacy      - Privacy audit
/health       - Runtime health
/backup       - Data backup
/recovery     - State recovery
/moderation   - Ban/block/antispam
/resources    - Resources
/notion       - Notion / CA sync
/countdown    - UPSC countdown
/settings     - Runtime settings
/audit        - Audit trail
/export       - Controlled export
/system       - System status
/lockdown     - Emergency lockdown
```

---

## 🐛 TROUBLESHOOTING

### Issue 1: "Can't load plugin: sqlalchemy.dialects:mongodb.srv"
**Solution**: 
- Clear ALL `DATABASE_URL` variables with `mongodb://` or `mongodb+srv://`
- Set `POSTGRES_URL` or `NEON_DATABASE_URL` instead
- Redeploy

### Issue 2: "User only sees /lms command"
**Solution**:
- Command registration happens on first `/start`
- User needs to type `/start` first
- Check Vercel logs for: "Admin commands registered" or "User commands registered"
- If still broken, add to Vercel env: `FORCE_COMMAND_RESET=1`, deploy, then remove and redeploy

### Issue 3: "Database connection refused"
**Solution**:
- Verify `POSTGRES_URL` format: `postgresql+asyncpg://user:pass@host/db?sslmode=require`
- Check Postgres is accessible from Vercel's IP range (should be automatic)
- Restart Vercel deployment: Click "Redeploy" in dashboard

### Issue 4: "Admin commands not showing"
**Solution**:
- Verify `ADMIN_ID` in environment is YOUR Telegram user ID (not bot ID)
- Ensure you're the only person with that ID
- After setting ADMIN_ID, send `/start` to bot
- Check Vercel logs for "Admin commands registered for user: {ADMIN_ID}"

### Issue 5: "Timeout during deployment"
**Solution**:
- Database initialization can take time on first run
- Click "Redeploy" in Vercel dashboard
- Wait up to 2 minutes
- Check logs: URL ends with `/logs`

---

## 📊 DATABASE INITIALIZATION

On **first deployment**, the bot automatically:
1. Creates all tables (users, courses, sections, etc.)
2. Seeds 50+ courses
3. Seeds section hierarchy (UPSC, Subject-Specific, etc.)
4. Registers user commands
5. Registers admin commands

**Time**: Usually 30-60 seconds for first init.

---

## 🔐 SECURITY NOTES

1. **Never commit `.env`** - Keep secrets in Vercel only
2. **Never commit `app.env`** - Local testing file only
3. **Verify PostgreSQL is Private** - No public IP exposure
4. **Rotate HMAC Keys** - Change `PERSONAL_DATA_HMAC_KEY`, `DATA_ENCRYPTION_KEY` periodically
5. **Admin ID must be unique** - Only one person should have this ID

---

## 📈 SCALING TIPS

- **Vercel limits**: Free tier handles up to ~10k users
- **Database**: Neon/Vercel Postgres handles 10k+ rows easily
- **Commands**: Registered once per bot startup, no scaling issues
- **Broadcasts**: Use `/broadcast` with progressive delays to avoid Telegram rate limits

---

## 🎯 FINAL CHECKLIST

- [ ] Removed all MongoDB env vars
- [ ] Set PostgreSQL connection URL (POSTGRES_URL or NEON_DATABASE_URL)
- [ ] Set BOT_TOKEN, ADMIN_ID, GEMINI_API_KEY
- [ ] Pushed to Vercel (git push or drag & drop)
- [ ] Deployment shows no errors in Vercel logs
- [ ] Sent `/start` to bot
- [ ] Verified /menu works for regular user
- [ ] Verified /adminhelp works with ADMIN_ID user
- [ ] Verified at least 3 user commands appear
- [ ] Verified at least 10 admin commands appear

---

## ✨ YOU'RE READY!

Your bot is now deployment-ready with:
- ✅ PostgreSQL backend (no MongoDB)
- ✅ 10 user commands
- ✅ 29+ admin commands
- ✅ Full LMS functionality
- ✅ Vercel-optimized FastAPI
- ✅ Production security hardening

**Questions?** Check Vercel logs at: `https://vercel.com/<team>/<project>/functions`

