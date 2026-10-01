"""Unified APScheduler jobs (IST): deletions, digest, GM/GN, countdown, quiz, weekly report."""
import logging
from datetime import datetime, date, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, func

import config
import ai
import services as sv
import os
import features
import extras
from fmt import card
from database import async_session, User, EventLog, Membership

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None

FALLBACK = {
    "morning": ["Uth jao — aaj ka ek chapter kal ki chinta se bada hai.", "Subah ka pehla ghanta sabse keemti hota hai."],
    "night": ["Aaj jitna hua, kaafi hai. Kal phir se.", "Book band karo, neend bhi taiyari ka hissa hai."],
}


def _hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


async def _recent_lines(kind: str) -> list[str]:
    try:
        return [x for x in (await sv.get_setting(f"last_{kind}", "")).split("||") if x]
    except Exception:
        return []


async def _send_all(bot: Bot, flag: str, text: str, *, hours: float, kind: str, pin: bool = False):
    kb = await sv.growth_kb(bot)
    for c in await sv.enabled_chats(flag):
        try:
            m = await bot.send_message(c.id, text, reply_markup=kb)
            await sv.schedule_delete(c.id, m.message_id, hours=hours, kind=kind)
            if pin:
                try:
                    await bot.pin_chat_message(c.id, m.message_id, disable_notification=True)
                except Exception:
                    pass
        except Exception as e:  # noqa: BLE001
            logger.warning("send to %s failed: %s", c.id, e)


async def job_daily(bot: Bot, kind: str):
    if (await sv.get_setting(f"{kind}_on", "1")) != "1":
        return
    avoid = await _recent_lines(kind)
    line = await ai.daily_line(kind, avoid) or FALLBACK[kind][date.today().toordinal() % 2]
    await sv.set_setting(f"last_{kind}", "||".join((avoid + [line])[-6:]))
    title = "Good Morning" if kind == "morning" else "Good Night"
    await _send_all(bot, f"{kind}_on", card("ok" if kind == "morning" else "info", title, [line]), hours=config.DEL_ROUTINE_HOURS, kind=kind)


async def job_countdown(bot: Bot):
    if (await sv.get_setting("countdown_on", "1")) != "1":
        return
    ds = await sv.get_setting("exam_date", config.EXAM_DATE)
    try:
        days = (datetime.strptime(ds, "%Y-%m-%d").date() - date.today()).days
    except Exception:
        return
    if days < 0:
        return
    text = card("warn", config.EXAM_NAME, [f"{days} days remaining ({days // 7} weeks)"], "Complete today's target.")
    await _send_all(bot, "countdown_on", text, hours=12, kind="countdown", pin=True)


async def job_quiz(bot: Bot):
    if (await sv.get_setting("quiz_on", "1")) != "1":
        return
    q = await ai.make_quiz()
    if not q:
        return
    for c in await sv.enabled_chats("quiz_on"):
        try:
            m = await bot.send_poll(c.id, q["q"], q["options"], type="quiz", is_anonymous=True,
                                    correct_option_id=int(q["answer"]), explanation=q.get("why") or None,
                                    reply_markup=await sv.growth_kb(bot))
            await sv.schedule_delete(c.id, m.message_id, hours=config.DEL_QUIZ_HOURS, kind="quiz")
        except Exception as e:  # noqa: BLE001
            logger.warning("quiz to %s failed: %s", c.id, e)


async def job_membership_expiry(bot: Bot):
    """Expire memberships and send at-most-once/day renewal notices."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    import premium
    now = datetime.utcnow()
    async with async_session() as s:
        active = (await s.execute(select(Membership).where(Membership.status == "active"))).scalars().all()
    for m in active:
        remaining = (m.expires_at - now).total_seconds() / 86400
        window = "expired" if remaining <= 0 else "1d" if remaining <= 1 else "3d" if remaining <= 3 else ""
        if not window:
            continue
        marker = f"{m.user_id}:{m.plan}:{window}:{now.strftime('%Y-%m-%d')}"
        if not await sv.claim_fence("membership_notice", marker):
            continue
        title = "CA Tracker Pro" if m.plan == "ca_tracker" else "Join Our Community"
        if remaining <= 0:
            async with async_session() as s:
                row = await s.get(Membership, m.id)
                if row:
                    row.status = "expired"
                    await s.commit()
            text = f"⏰ <b>{title}</b> subscription expired. Renew to restore access."
        else:
            days = max(1, int(remaining + 0.999))
            text = f"⏳ <b>{title}</b> renews in {days} day(s)."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Renew", callback_data=f"plan:{m.plan}")]])
        try:
            await bot.send_message(m.user_id, text, reply_markup=kb)
        except Exception:
            pass


async def job_weekly(bot: Bot):
    since = datetime.utcnow() - timedelta(days=7)
    async with async_session() as s:
        new = (await s.execute(select(func.count(User.id)).where(User.joined_at >= since))).scalar() or 0
        total = (await s.execute(select(func.count(User.id)))).scalar() or 0
        ev = dict((await s.execute(select(EventLog.kind, func.sum(EventLog.n))
                                   .where(EventLog.created_at >= since).group_by(EventLog.kind))).all())
    await sv.notify_admin(bot, "📅 <b>Weekly report</b>\n"
                               f"👥 Users {total} (+{new})\n➕ Joins {ev.get('join', 0)} • ➖ Leaves {ev.get('leave', 0)}\n"
                               f"💬 Group msgs {ev.get('msgs', 0)} • 📩 DMs {ev.get('dm', 0)}\n"
                               "Detail: /analytics 7", urgent=True)


async def job_state_to_db():
    """Mirror the JSON state file (bans/mutes/AI toggle) into the DB."""
    try:
        from security import STATE_BACKUP_PATH
        if os.path.exists(STATE_BACKUP_PATH):
            with open(STATE_BACKUP_PATH, "r", encoding="utf-8") as fh:
                await sv.set_setting("state_backup_json", fh.read())
    except Exception:
        logger.exception("state mirror failed")


async def job_digest(bot: Bot):
    await sv.flush_digest(bot)


async def job_deletions(bot: Bot):
    await sv.run_deletions(bot)


def start(bot: Bot) -> AsyncIOScheduler:
    global _scheduler
    if _scheduler:
        return _scheduler
    sch = AsyncIOScheduler(timezone=config.TIMEZONE)
    sch.add_job(job_deletions, "interval", minutes=1, args=[bot], id="deletions", max_instances=1, coalesce=True)
    sch.add_job(sv.flush_activity, "interval", minutes=5, id="activity", coalesce=True)
    sch.add_job(job_digest, "interval", minutes=30, args=[bot], id="digest", coalesce=True)
    h, m = _hm(config.GOOD_MORNING_TIME)
    sch.add_job(job_daily, "cron", hour=h, minute=m, args=[bot, "morning"], id="gm", misfire_grace_time=600)
    h, m = _hm(config.GOOD_NIGHT_TIME)
    sch.add_job(job_daily, "cron", hour=h, minute=m, args=[bot, "night"], id="gn", misfire_grace_time=600)
    h, m = _hm(config.COUNTDOWN_TIME)
    sch.add_job(job_exam_countdown, "cron", hour=h, minute=m, args=[bot], id="countdown", misfire_grace_time=600)
    h, m = _hm(config.QUIZ_TIME)
    sch.add_job(job_quiz, "cron", hour=h, minute=m, args=[bot], id="quiz", misfire_grace_time=600)
    sch.add_job(job_weekly, "cron", day_of_week="fri", hour=19, minute=0, args=[bot], id="weekly", misfire_grace_time=1800)
    sch.add_job(features.job_reminders, "interval", minutes=1, args=[bot], id="reminders", max_instances=1, coalesce=True)
    sch.add_job(features.verify_referrals, "interval", minutes=5, args=[bot], id="referrals", max_instances=1, coalesce=True)
    sch.add_job(features.job_order_followup, "interval", hours=6, args=[bot], id="orders", coalesce=True)
    sch.add_job(features.job_new_course_alerts, "interval", minutes=30, args=[bot], id="alerts", coalesce=True)
    sch.add_job(job_membership_expiry, "cron", hour=8, minute=5, args=[bot], id="membership_expiry", misfire_grace_time=1800)
    sch.add_job(features.job_cotd, "cron", hour=12, minute=0, args=[bot], id="cotd", misfire_grace_time=900)
    sch.add_job(extras.job_scheduled, "interval", minutes=1, args=[bot], id="sched_bc", max_instances=1, coalesce=True)
    sch.add_job(job_state_to_db, "interval", minutes=5, id="statedb", coalesce=True)
    sch.start()
    _scheduler = sch
    logger.info("Scheduler started (%s jobs)", len(sch.get_jobs()))
    return sch


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None

async def _countdown_kb(bot: Bot, private: bool=False):
    me=await bot.get_me()
    rows=[]
    if private and config.WEBAPP_BASE_URL:
        from aiogram.types import WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
        rows.append([InlineKeyboardButton(text="📚 Open LMS",web_app=WebAppInfo(url=f"{config.WEBAPP_BASE_URL}/webapp/lms"))])
        rows.append([InlineKeyboardButton(text="👥 Community",web_app=WebAppInfo(url=f"{config.WEBAPP_BASE_URL}/webapp/community")),InlineKeyboardButton(text="📰 CA Tracker",web_app=WebAppInfo(url=f"{config.WEBAPP_BASE_URL}/webapp/ca"))])
    else:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        rows.append([InlineKeyboardButton(text="📚 Open LMS",url=f"https://t.me/{me.username}?start=start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def job_exam_countdown(bot: Bot):
    if (await sv.get_setting("countdown_on", "1")) != "1": return {"sent":0,"failed":0}
    ds=await sv.get_setting("exam_date",config.EXAM_DATE)
    try: days=(datetime.strptime(ds,"%Y-%m-%d").date()-date.today()).days
    except Exception: return {"sent":0,"failed":0}
    if days < 0: return {"sent":0,"failed":0}
    line=await ai.countdown_line(days,config.EXAM_DATE) or "Aaj ka target complete karo — consistency matters."
    text=card("warn",config.EXAM_NAME,[f"{days} days remaining"],line)
    sent=failed=0
    async with async_session() as s:
        users=(await s.execute(select(User).where(User.phone_verified==True,User.is_banned==False))).scalars().all()  # noqa: E712
    for u in users:
        try:
            m=await bot.send_message(u.id,text,reply_markup=await _countdown_kb(bot,private=True))
            # Personal countdown must disappear at 23:00 IST; 07:30 -> 930 minutes.
            await sv.schedule_delete(u.id,m.message_id,minutes=15*60+30,kind="countdown_personal")
            sent+=1
        except Exception: failed+=1
    group_text="📅 <b>UPSC Prelims 2027 Countdown</b> · @all\n"+f"{days} days remaining\n{line}"
    for c in await sv.enabled_chats("countdown_on"):
        try:
            m=await bot.send_message(c.id,group_text,reply_markup=await _countdown_kb(bot,private=False))
            await sv.schedule_delete(c.id,m.message_id,hours=12,kind="countdown")
            sent+=1
        except Exception: failed+=1
    return {"sent":sent,"failed":failed,"days":days}


async def serverless_tick(bot: Bot):
    """Idempotent Vercel tick. Mirrors the persistent APScheduler jobs without background loops."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(config.TIMEZONE))
    ran = {}

    async def once(key, marker_value, fn):
        if not await sv.claim_fence(f"cron:{key}", marker_value):
            return False
        try:
            await fn()
            ran[key] = True
            return True
        except Exception:
            logger.exception("cron job failed: %s", key)
            return False

    await job_deletions(bot); ran["deletions"] = True
    await sv.flush_activity(); ran["activity"] = True
    await sv.set_runtime_heartbeat("cron")

    # Per-minute jobs / queues. Each underlying job is itself defensive.
    try:
        await features.job_reminders(bot); ran["reminders"] = True
    except Exception:
        logger.exception("serverless reminders failed")
    try:
        await extras.job_scheduled(bot); ran["scheduled"] = True
    except Exception:
        logger.exception("serverless scheduled broadcast failed")

    if now.minute in (0, 30):
        await once("digest", now.strftime("%Y-%m-%d-%H-%M"), lambda: sv.flush_digest(bot))
        try:
            await features.job_new_course_alerts(bot); ran["course_alerts"] = True
        except Exception:
            logger.exception("serverless course alerts failed")

    if now.minute == 0 and now.hour in (0, 6, 12, 18):
        try:
            await features.job_order_followup(bot); ran["order_followup"] = True
        except Exception:
            logger.exception("serverless order followup failed")

    if now.hour == 0 and now.minute == 1:
        await once("referrals", now.strftime("%Y-%m-%d"), lambda: features.verify_referrals(bot))

    if now.hour == 12 and now.minute == 0:
        await once("cotd", now.strftime("%Y-%m-%d"), lambda: features.job_cotd(bot))

    if now.hour == 5 and now.minute == 0:
        await once("state_mirror", now.strftime("%Y-%m-%d"), job_state_to_db)

    if now.hour == 8 and now.minute == 5:
        await once("membership_expiry", now.strftime("%Y-%m-%d"), lambda: job_membership_expiry(bot))

    # 07:30 exact on plans supporting minute cron; marker prevents duplicates.
    if now.hour == 7 and now.minute == 30:
        await once("countdown", now.strftime("%Y-%m-%d"), lambda: job_exam_countdown(bot))

    # Persistent daily/weekly user-facing routines.
    gm_h, gm_m = _hm(config.GOOD_MORNING_TIME)
    if now.hour == gm_h and now.minute == gm_m:
        await once("morning", now.strftime("%Y-%m-%d"), lambda: job_daily(bot, "morning"))
    gn_h, gn_m = _hm(config.GOOD_NIGHT_TIME)
    if now.hour == gn_h and now.minute == gn_m:
        await once("night", now.strftime("%Y-%m-%d"), lambda: job_daily(bot, "night"))

    q_h, q_m = _hm(config.QUIZ_TIME)
    if now.hour == q_h and now.minute == q_m:
        await once("quiz", now.strftime("%Y-%m-%d"), lambda: job_quiz(bot))

    return ran
