"""features.py — user-facing engagement + growth + privacy features.
All messages: professional English, colour-coded, concise, each with an explicit 'Next:' step."""
import logging
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Router, F, BaseMiddleware
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command, CommandObject
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
                           ChatPermissions)
from sqlalchemy import select, func, delete, update

import ai_brain
import config
import services as sv
from config import ADMIN_ID
from database import (async_session, User, Referral, CoinLedger, Course, Order, UserCourse, Streak, Reminder,
                      Ticket, Interest, InboxItem, ConnectedChat, ContactMessage)
from fmt import card, esc, bar

logger = logging.getLogger(__name__)
router = Router()
IS_ADMIN = F.from_user.id == ADMIN_ID
PRIVATE = F.chat.type == "private"
GROUP = F.chat.type.in_({"group", "supergroup"})

COINS_PER_REFERRAL = int(os.getenv("COINS_PER_REFERRAL", "30"))
COINS_TO_REDEEM = int(os.getenv("COINS_TO_REDEEM", "300"))
IST = ZoneInfo(config.TIMEZONE)


def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows])


def btn(text, data=None, url=None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data) if data else InlineKeyboardButton(text=text, url=url)


async def bot_username(bot) -> str:
    return (await bot.get_me()).username


# =====================================================================================
# REFERRALS + COINS
# =====================================================================================
class RefCapture(BaseMiddleware):
    """Capture only signed, single-use referral tokens. Reward is verified later after phone + channel checks."""
    async def __call__(self, handler, event, data):
        try:
            t = (getattr(event, "text", None) or "").strip()
            u = getattr(event, "from_user", None)
            if u and t.startswith("/start"):
                arg = t.split(maxsplit=1)[1].split()[0] if len(t.split()) > 1 else ""
                if arg.startswith("r_"):
                    from premium import _verify_token
                    payload = _verify_token(arg[2:])
                    ref_id = int(payload.get("uid")) if payload else 0
                    if ref_id and ref_id != u.id:
                        async with async_session() as s:
                            exists = await s.get(User, u.id)
                            referrer = await s.get(User, ref_id)
                            dup = (await s.execute(select(Referral).where(Referral.referred_id == u.id))).scalar_one_or_none()
                            if exists is None and referrer and not referrer.is_banned and not dup and referrer.id != u.id:
                                s.add(Referral(referrer_id=ref_id, referred_id=u.id, status="pending"))
                                await s.commit()
        except Exception:
            logger.exception("ref capture failed")
        return await handler(event, data)


async def credit(user_id: int, delta: int, reason: str, ref: str = "") -> int:
    """Atomic balance change + ledger row. Returns the new balance."""
    async with async_session() as s:
        u = await s.get(User, user_id)
        u.ref_points = (u.ref_points or 0) + delta
        s.add(CoinLedger(user_id=user_id, delta=delta, reason=reason, ref=ref))
        await s.commit()
        return u.ref_points


async def verify_referrals(bot):
    """Scheduler job: a referral is valid once the new user has joined the backup channel."""
    async with async_session() as s:
        pend = (await s.execute(select(Referral).where(Referral.status == "pending"))).scalars().all()
    for r in pend:
        async with async_session() as s:
            referred = await s.get(User, r.referred_id)
        if not referred:
            continue
        if referred.is_banned:
            async with async_session() as s:
                await s.execute(update(Referral).where(Referral.id == r.id).values(status="rejected"))
                await s.commit()
            continue
        if not referred.phone_verified or not referred.has_joined_backup_channel:
            continue
        # One verified phone should not farm multiple referral rewards.
        async with async_session() as s:
            if getattr(referred, "phone_hash", None):
                dup_phone = (await s.execute(select(func.count()).select_from(User).where(
                    User.phone_hash == referred.phone_hash, User.phone_verified == True, User.id != referred.id
                ))).scalar() or 0
                if dup_phone:
                    await s.execute(update(Referral).where(Referral.id == r.id, Referral.status == "pending").values(status="rejected"))
                    await s.commit()
                    continue
            claimed = await s.execute(update(Referral).where(Referral.id == r.id, Referral.status == "pending").values(status="verifying"))
            if claimed.rowcount != 1:
                continue
            await s.commit()
        async with async_session() as s:
            row = await s.get(Referral, r.id)
            if row: row.status, row.verified_at = "verified", datetime.utcnow()
            since = datetime.utcnow() - timedelta(days=1)
            rewarded = (await s.execute(select(func.count()).select_from(CoinLedger).where(
                CoinLedger.user_id == r.referrer_id, CoinLedger.reason == "referral", CoinLedger.created_at >= since
            ))).scalar() or 0
            await s.commit()
        if rewarded >= int(os.getenv("REFERRAL_DAILY_REWARD_CAP", "20")):
            continue
        bal = await credit(r.referrer_id, COINS_PER_REFERRAL, "referral", str(r.referred_id))
        lines = [f"+{COINS_PER_REFERRAL} coins added.", f"Balance: {bal}/{COINS_TO_REDEEM}  {bar(bal, COINS_TO_REDEEM)}"]
        nxt = ("You can redeem a course now. Open /wallet." if bal >= COINS_TO_REDEEM
               else f"Invite {max(1, -(-(COINS_TO_REDEEM - bal) // COINS_PER_REFERRAL))} more to reach {COINS_TO_REDEEM}.")
        try:
            await bot.send_message(r.referrer_id, card("ok", "Referral verified", lines, nxt))
        except Exception:
            pass


async def wallet_view(bot, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    async with async_session() as s:
        u = await s.get(User, user_id)
        verified = (await s.execute(select(func.count()).select_from(Referral).where(
            Referral.referrer_id == user_id, Referral.status == "verified"))).scalar() or 0
        pending = (await s.execute(select(func.count()).select_from(Referral).where(
            Referral.referrer_id == user_id, Referral.status == "pending"))).scalar() or 0
    bal = (u.ref_points if u else 0) or 0
    from premium import referral_link
    link = await referral_link(bot, user_id)
    lines = [f"Balance: {bal}/{COINS_TO_REDEEM}  {bar(bal, COINS_TO_REDEEM)}",
             f"Verified referrals: {verified}  •  Pending: {pending}",
             f"Rule: {COINS_PER_REFERRAL} coins per new user who joins the backup channel.",
             f"Reward: a course priced up to ₹{COINS_TO_REDEEM} at {COINS_TO_REDEEM} coins.",
             f"Your link: {link}"]
    rows = []
    if bal >= COINS_TO_REDEEM:
        rows.append([btn("🎁 Redeem a course", "coin:list")])
        nxt = "Tap Redeem a course."
    else:
        nxt = f"Share your link. {-(-(COINS_TO_REDEEM - bal) // COINS_PER_REFERRAL)} more referral(s) to unlock a course."
    rows.append([btn("📜 History", "coin:hist")])
    return card("info", "Your coins", lines, nxt), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("wallet", "refer", "coins", "my_referral"))
async def wallet_cmd(message: Message):
    await sv.ensure_user(message.from_user)
    text, markup = await wallet_view(message.bot, message.from_user.id)
    await message.answer(text, reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "coin:home")
async def coin_home(call: CallbackQuery):
    await sv.ensure_user(call.from_user)
    text, markup = await wallet_view(call.bot, call.from_user.id)
    await call.message.answer(text, reply_markup=markup, disable_web_page_preview=True)
    await call.answer()


@router.callback_query(F.data == "coin:hist")
async def coin_hist(call: CallbackQuery):
    async with async_session() as s:
        rows = (await s.execute(select(CoinLedger).where(CoinLedger.user_id == call.from_user.id)
                                .order_by(CoinLedger.id.desc()).limit(10))).scalars().all()
    lines = [f"{r.created_at:%d %b}  {r.delta:+d}  {r.reason}" for r in rows] or ["No activity yet."]
    await call.message.answer(card("info", "Coin history", lines, "Share your link to earn coins."))
    await call.answer()


@router.callback_query(F.data == "coin:list")
async def coin_list(call: CallbackQuery):
    async with async_session() as s:
        u = await s.get(User, call.from_user.id)
        if (u.ref_points or 0) < COINS_TO_REDEEM:
            return await call.answer("Not enough coins.", show_alert=True)
        owned = set((await s.execute(select(UserCourse.course_id).where(UserCourse.user_id == u.id))).scalars().all())
        courses = (await s.execute(select(Course).where(
            Course.is_active == True, Course.price.isnot(None), Course.price > 0,  # noqa: E712
            Course.price <= COINS_TO_REDEEM).order_by(Course.name).limit(40))).scalars().all()
    courses = [c for c in courses if c.id not in owned][:12]
    if not courses:
        return await call.answer("No eligible course right now.", show_alert=True)
    rows = [[btn(f"{c.name[:38]} (₹{int(c.price)})", f"coin:pick:{c.id}")] for c in courses]
    await call.message.answer(card("info", "Choose your course", [f"Eligible: priced up to ₹{COINS_TO_REDEEM}."],
                                   "Select one to confirm."), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@router.callback_query(F.data.startswith("coin:pick:"))
async def coin_pick(call: CallbackQuery):
    cid = int(call.data.split(":")[2])
    async with async_session() as s:
        c = await s.get(Course, cid)
    if not c:
        return await call.answer("Course unavailable.", show_alert=True)
    await call.message.answer(
        card("warn", "Confirm redemption", [c.name, f"Cost: {COINS_TO_REDEEM} coins"], "Tap Confirm to unlock instantly."),
        reply_markup=kb([btn("✅ Confirm", f"coin:ok:{cid}"), btn("✖ Cancel", "coin:home")]))
    await call.answer()


@router.callback_query(F.data.startswith("coin:ok:"))
async def coin_redeem(call: CallbackQuery):
    cid, uid = int(call.data.split(":")[2]), call.from_user.id
    async with async_session() as s:
        u = await s.get(User, uid)
        c = await s.get(Course, cid)
        owned = (await s.execute(select(UserCourse).where(UserCourse.user_id == uid, UserCourse.course_id == cid))).first()
        if not c or not c.is_active or not c.price or c.price > COINS_TO_REDEEM:
            return await call.answer("This course is not eligible.", show_alert=True)
        if owned:
            return await call.answer("You already own this course.", show_alert=True)
        if (u.ref_points or 0) < COINS_TO_REDEEM:
            return await call.answer("Not enough coins.", show_alert=True)
        u.ref_points -= COINS_TO_REDEEM
        s.add(CoinLedger(user_id=uid, delta=-COINS_TO_REDEEM, reason="redeem", ref=str(cid)))
        order = Order(user_id=uid, course_id=cid, status="approved", submission_type="coins",
                      submission_content=f"Redeemed {COINS_TO_REDEEM} coins", decided_at=datetime.utcnow())
        s.add(order)
        s.add(UserCourse(user_id=uid, course_id=cid))
        await s.commit()
        link, name, oid, bal = c.group_link, c.name, order.id, u.ref_points
    if link and (link.startswith("-100") or link.startswith("@")):
        try:   # anti-piracy: single-use invite
            link = (await call.bot.create_chat_invite_link(chat_id=link, member_limit=1, name=f"Coins_O{oid}")).invite_link
        except Exception:
            pass
    body = [name, f"Coins left: {bal}"] + ([f"Access link (single use): {link}"] if link else [])
    await call.message.answer(card("ok", "Course unlocked", body,
                                   "Open the link to join." if link else "Your access link will be shared shortly."),
                              disable_web_page_preview=True)
    await call.answer("Unlocked")
    await sv.notify_admin(call.bot, card("info", "Coin redemption", [f"User {uid}", name], raw=False), urgent=True)


# =====================================================================================
# STUDY STREAK
# =====================================================================================
def _today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


async def _streak_row(uid: int) -> Streak:
    async with async_session() as s:
        r = await s.get(Streak, uid)
        if not r:
            r = Streak(user_id=uid)
            s.add(r)
            await s.commit()
            await s.refresh(r)
        return r


@router.message(Command("today"))
async def today_cmd(message: Message):
    r = await _streak_row(message.from_user.id)
    done = r.last_day == _today()
    lines = [f"Target: {esc(r.target) or 'not set'}", f"Streak: {r.current} day(s)  •  Best: {r.best}",
             "Today: ✅ done" if done else "Today: pending"]
    nxt = "Come back tomorrow to extend your streak." if done else ("Complete it, then tap Done." if r.target else "Set one with /target <your goal>.")
    await message.answer(card("ok" if done else "warn", "Daily target", lines, nxt, raw=True),
                         reply_markup=None if done else kb([btn("✅ Mark today done", "ft:done")]))


@router.message(Command("target"))
async def target_cmd(message: Message, command: CommandObject):
    t = (command.args or "").strip()[:200]
    if not t:
        return await message.answer(card("info", "Set your daily target", ["Example: /target 2 hours Polity + 30 MCQs"],
                                         "Send /target followed by your goal."))
    async with async_session() as s:
        r = await s.get(Streak, message.from_user.id) or Streak(user_id=message.from_user.id)
        r.target = t
        s.add(r)
        await s.commit()
    await message.answer(card("ok", "Target saved", [t], "Use /today each evening to mark it done."))


@router.callback_query(F.data == "ft:done")
async def streak_done(call: CallbackQuery):
    today = _today()
    yday = (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
    async with async_session() as s:
        r = await s.get(Streak, call.from_user.id) or Streak(user_id=call.from_user.id, current=0, best=0)
        if r.last_day == today:
            return await call.answer("Already marked today.", show_alert=True)
        r.current = (r.current or 0) + 1 if r.last_day == yday else 1
        r.best = max(r.best or 0, r.current)
        r.last_day = today
        s.add(r)
        await s.commit()
        cur, best = r.current, r.best
    await call.message.answer(card("ok", "Well done", [f"Streak: {cur} day(s)  •  Best: {best}"],
                                   "Repeat tomorrow to keep the streak."))
    await call.answer()


# =====================================================================================
# DOUBT DESK  (live AI answer first, escalate to Professor on demand)
# =====================================================================================
@router.message(Command("doubt"), PRIVATE)
async def doubt_cmd(message: Message, command: CommandObject):
    q = (command.args or "").strip()
    if not q:
        return await message.answer(card("info", "Ask a doubt", ["Example: /doubt Difference between Article 32 and 226"],
                                         "Send /doubt followed by your question."))
    reply, status = await ai_brain.answer(message.from_user.id, message.from_user.first_name, q)
    if status == "limit":
        return await message.answer(card("warn", "Daily AI limit reached", ["Your free AI questions for today are used."],
                                         "Tap below to send this to Professor.")
                                    , reply_markup=await _esc_kb(message.from_user.id, q, ""))
    if not reply:
        return await message.answer(card("err", "AI is unavailable right now", ["Your question was not lost."],
                                         "Tap below to send it to Professor."),
                                    reply_markup=await _esc_kb(message.from_user.id, q, ""))
    await message.answer(card("info", config.AI_NAME, [reply], "Satisfied? No action needed. Otherwise escalate below."),
                         reply_markup=await _esc_kb(message.from_user.id, q, reply))


async def _esc_kb(uid: int, q: str, a: str) -> InlineKeyboardMarkup:
    async with async_session() as s:
        t = Ticket(user_id=uid, question=q[:2000], ai_answer=a[:2000], status="ai_answered")
        s.add(t)
        await s.commit()
        await s.refresh(t)
    return kb([btn("🙋 Ask Professor", f"ft:esc:{t.id}")])


@router.callback_query(F.data.startswith("ft:esc:"))
async def doubt_escalate(call: CallbackQuery):
    tid = int(call.data.split(":")[2])
    async with async_session() as s:
        t = await s.get(Ticket, tid)
        if not t or t.user_id != call.from_user.id:
            return await call.answer("Not found.", show_alert=True)
        if t.status != "ai_answered":
            return await call.answer("Already sent.", show_alert=True)
        t.status = "open"
        await s.commit()
    u = call.from_user
    m = await call.bot.send_message(ADMIN_ID, card(
        "err", f"Doubt #{tid}", [f"Name: {esc(u.full_name)}", f"User ID: <code>{u.id}</code>",
                                  f"Q: {esc(t.question[:900])}"], "Swipe-reply to answer.", raw=True))
    async with async_session() as s:
        s.add(InboxItem(admin_message_id=m.message_id, source_chat_id=u.id, source_message_id=call.message.message_id,
                        user_id=u.id))
        await s.commit()
    await call.message.answer(card("ok", "Sent to Professor", [f"Ticket #{tid}"], "No action needed. You will get the reply here."))
    await call.answer()


@router.message(Command("mydoubts"), PRIVATE)
async def my_doubts(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(Ticket).where(Ticket.user_id == message.from_user.id, Ticket.status != "ai_answered")
                                .order_by(Ticket.id.desc()).limit(8))).scalars().all()
    lines = [f"#{t.id} • {t.status} • {esc(t.question[:40])}" for t in rows] or ["No escalated doubts."]
    await message.answer(card("info", "Your doubts", lines, "Use /doubt to ask a new one.", raw=True))


@router.message(Command("doubts"), IS_ADMIN)
async def admin_doubts(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(Ticket).where(Ticket.status == "open").order_by(Ticket.id))).scalars().all()
    lines = [f"#{t.id} • <code>{t.user_id}</code> • {esc(t.question[:50])}" for t in rows] or ["No open doubts."]
    await message.answer(card("info", "Open doubts", lines, raw=True))


async def mark_answered(user_id: int):
    """Called by the admin-reply flow: closes the user's open tickets."""
    async with async_session() as s:
        await s.execute(update(Ticket).where(Ticket.user_id == user_id, Ticket.status == "open").values(status="answered"))
        await s.commit()


# =====================================================================================
# REMINDERS
# =====================================================================================
def _parse_when(arg: str):
    m = re.match(r"^(\d{1,2}):(\d{2})\s+(.+)$", arg)
    if m:
        now = datetime.now(IST)
        due = now.replace(hour=int(m.group(1)) % 24, minute=int(m.group(2)) % 60, second=0, microsecond=0)
        if due <= now:
            due += timedelta(days=1)
        return due.astimezone(timezone.utc).replace(tzinfo=None), m.group(3)
    m = re.match(r"^(\d{1,4})\s*([mh])\s+(.+)$", arg, re.I)
    if m:
        d = timedelta(minutes=int(m.group(1))) if m.group(2).lower() == "m" else timedelta(hours=int(m.group(1)))
        return datetime.utcnow() + d, m.group(3)
    return None, None


@router.message(Command("remind"), PRIVATE)
async def remind_cmd(message: Message, command: CommandObject):
    due, text = _parse_when((command.args or "").strip())
    if not due:
        return await message.answer(card("info", "Set a reminder", ["/remind 19:30 Revise polity", "/remind 45m Take a break"],
                                         "Send /remind with a time and a note."))
    async with async_session() as s:
        n = (await s.execute(select(func.count(Reminder.id)).where(Reminder.user_id == message.from_user.id,
                                                                    Reminder.sent == False))).scalar() or 0  # noqa: E712
        if n >= 10:
            return await message.answer(card("warn", "Limit reached", ["Maximum 10 active reminders."], "Remove one with /unremind <id>."))
        r = Reminder(user_id=message.from_user.id, text=text[:250], due_at=due)
        s.add(r)
        await s.commit()
        await s.refresh(r)
    local = due.replace(tzinfo=timezone.utc).astimezone(IST)
    await message.answer(card("ok", "Reminder set", [f"#{r.id} • {local:%d %b, %H:%M} IST", text[:250]], "No action needed."))


@router.message(Command("reminders"), PRIVATE)
async def reminders_cmd(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(Reminder).where(Reminder.user_id == message.from_user.id, Reminder.sent == False)  # noqa: E712
                                .order_by(Reminder.due_at))).scalars().all()
    lines = [f"#{r.id} • {r.due_at.replace(tzinfo=timezone.utc).astimezone(IST):%d %b %H:%M} • {esc(r.text[:40])}" for r in rows] or ["None active."]
    await message.answer(card("info", "Your reminders", lines, "Remove with /unremind <id>.", raw=True))


@router.message(Command("unremind"), PRIVATE)
async def unremind_cmd(message: Message, command: CommandObject):
    try:
        rid = int((command.args or "").strip())
    except Exception:
        return await message.answer("Use: /unremind <id>")
    async with async_session() as s:
        await s.execute(delete(Reminder).where(Reminder.id == rid, Reminder.user_id == message.from_user.id))
        await s.commit()
    await message.answer(card("ok", "Reminder removed"))


async def job_reminders(bot):
    async with async_session() as s:
        due = (await s.execute(select(Reminder).where(Reminder.sent == False, Reminder.due_at <= datetime.utcnow()))).scalars().all()  # noqa: E712
    for r in due:
        try:
            m = await bot.send_message(r.user_id, card("warn", "Reminder", [r.text], "Do it now, then /today to log progress."))
            await sv.schedule_delete(r.user_id, m.message_id, hours=24, kind="reminder")
        except Exception:
            pass
        async with async_session() as s:
            await s.execute(update(Reminder).where(Reminder.id == r.id).values(sent=True))
            await s.commit()


# =====================================================================================
# ORDERS + PAYMENT FOLLOW-UP
# =====================================================================================
@router.message(Command("myorders"), PRIVATE)
async def myorders(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(Order, Course.name).join(Course, Course.id == Order.course_id)
                                .where(Order.user_id == message.from_user.id).order_by(Order.id.desc()).limit(8))).all()
    if not rows:
        return await message.answer(card("info", "No orders yet", nxt="Open /start to browse courses."))
    icon = {"pending": "🟡", "approved": "🟢", "rejected": "🔴"}
    lines = [f"{icon.get(o.status, '🔵')} {esc(n[:34])} — {o.status}" for o, n in rows]
    pend = any(o.status == "pending" for o, _ in rows)
    await message.answer(card("info", "Your orders", lines,
                              "Payments are reviewed within 24 hours." if pend else "Open /start for more courses.", raw=True))


async def job_order_followup(bot):
    cutoff = datetime.utcnow() - timedelta(hours=24)
    async with async_session() as s:
        rows = (await s.execute(select(Order).where(Order.status == "pending", Order.created_at <= cutoff))).scalars().all()
    stale = 0
    for o in rows:
        key = f"poke:{o.id}"
        if await sv.get_setting(key, ""):
            continue
        await sv.set_setting(key, "1")
        stale += 1
        try:
            await bot.send_message(o.user_id, card("warn", "Payment under review",
                                                   ["Your order is still being verified."], "No action needed. We will notify you."))
        except Exception:
            pass
    if stale:
        await sv.notify_admin(bot, card("warn", "Pending over 24h", [f"{stale} order(s) need review."], "Open /pending."), urgent=True)


# =====================================================================================
# NEW-COURSE ALERTS  (approved users only)
# =====================================================================================
@router.message(Command("notify_me"), PRIVATE)
async def notify_me(message: Message, command: CommandObject):
    k = (command.args or "").strip().lower()[:40]
    if not k:
        return await message.answer(card("info", "Course alerts", ["Example: /notify_me csat"], "Send /notify_me with a keyword."))
    async with async_session() as s:
        n = (await s.execute(select(func.count(Interest.id)).where(Interest.user_id == message.from_user.id))).scalar() or 0
        if n >= 8:
            return await message.answer(card("warn", "Limit reached", ["Maximum 8 keywords."], "Remove one with /notify_off <keyword>."))
        s.add(Interest(user_id=message.from_user.id, keyword=k))
        await s.commit()
    await message.answer(card("ok", "Alert saved", [f"Keyword: {k}"], "You will be notified when a matching course is added."))


@router.message(Command("notify_off"), PRIVATE)
async def notify_off(message: Message, command: CommandObject):
    k = (command.args or "").strip().lower()
    async with async_session() as s:
        q = delete(Interest).where(Interest.user_id == message.from_user.id)
        if k:
            q = q.where(Interest.keyword == k)
        await s.execute(q)
        await s.commit()
    await message.answer(card("ok", "Alert removed" if k else "All alerts removed"))


async def job_new_course_alerts(bot):
    import access
    async with async_session() as s:
        max_id = (await s.execute(select(func.max(Course.id)))).scalar() or 0
    last = await sv.get_setting("last_alert_course_id", "")
    if last == "":                       # first run: baseline only, no blast
        return await sv.set_setting("last_alert_course_id", str(max_id))
    async with async_session() as s:
        new = (await s.execute(select(Course).where(Course.id > int(last), Course.is_active == True))).scalars().all()  # noqa: E712
        interests = (await s.execute(select(Interest))).scalars().all()
    await sv.set_setting("last_alert_course_id", str(max_id))
    for c in new:
        hay = f"{c.name} {c.faculty or ''}".lower()
        sent = set()
        for i in interests:
            if i.keyword in hay and i.user_id not in sent and await access.is_approved(i.user_id):
                sent.add(i.user_id)
                try:
                    await bot.send_message(i.user_id, card("offer", "New course", [c.name, f"Price: ₹{int(c.price)}" if c.price else "Price on request"],
                                                           "Send /start to view it."))
                except Exception:
                    pass


# =====================================================================================
# COURSE OF THE DAY  (groups)
# =====================================================================================
@router.message(Command("cotd_on", "cotd_off"), IS_ADMIN)
async def cotd_toggle(message: Message):
    on = message.text.startswith("/cotd_on")
    await sv.set_setting("cotd_on", "1" if on else "0")
    await message.answer(card("ok", f"Course of the Day {'ON' if on else 'OFF'}"))


async def job_cotd(bot):
    if (await sv.get_setting("cotd_on", "0")) != "1":
        return
    async with async_session() as s:
        courses = (await s.execute(select(Course).where(Course.is_active == True, Course.price.isnot(None))  # noqa: E712
                                   .order_by(Course.id))).scalars().all()
    if not courses:
        return
    idx = int(await sv.get_setting("cotd_idx", "0") or 0) % len(courses)
    await sv.set_setting("cotd_idx", str(idx + 1))
    c = courses[idx]
    url = f"https://t.me/{await bot_username(bot)}?start=buy_{c.id}"
    text = card("offer", "Course of the Day", [c.name, f"Price: ₹{int(c.price)}"], "Tap below to view details.")
    for ch in await sv.enabled_chats():
        try:
            m = await bot.send_message(ch.id, text, reply_markup=kb([btn("🛒 View course", url=url)]))
            await sv.schedule_delete(ch.id, m.message_id, hours=12, kind="cotd")
        except Exception:
            pass


# =====================================================================================
# GROUP ANTI-SPAM
# =====================================================================================
_recent: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=6))
_admin_cache: dict[tuple, tuple[float, bool]] = {}
LINK_RE = re.compile(r"(https?://|t\.me/|www\.|@[A-Za-z0-9_]{5,})", re.I)


async def _is_group_admin(bot, chat_id: int, uid: int) -> bool:
    k = (chat_id, uid)
    hit = _admin_cache.get(k)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    try:
        m = await bot.get_chat_member(chat_id, uid)
        ok = m.status in ("administrator", "creator")
    except Exception:
        ok = False
    _admin_cache[k] = (time.time(), ok)
    return ok


@router.message(Command("antispam"), IS_ADMIN)
async def antispam_toggle(message: Message, command: CommandObject):
    v = (command.args or "").strip().lower()
    if v not in ("on", "off"):
        return await message.answer(card("info", "Anti-spam", [f"Currently {(await sv.get_setting('antispam_on', '1')) == '1' and 'ON' or 'OFF'}"],
                                         "Use /antispam on or /antispam off"))
    await sv.set_setting("antispam_on", "1" if v == "on" else "0")
    await message.answer(card("ok", f"Anti-spam {v.upper()}"))


@router.message(GROUP)
async def antispam(message: Message):
    if (await sv.get_setting("antispam_on", "1")) != "1" or not message.from_user or message.from_user.is_bot:
        raise SkipHandler
    uid, cid = message.from_user.id, message.chat.id
    if uid == ADMIN_ID or await _is_group_admin(message.bot, cid, uid):
        raise SkipHandler
    text = message.text or message.caption or ""
    backup = (config.backup_username() or "").lower()
    why = None
    if message.forward_date or getattr(message, "forward_origin", None):
        why = "forwarded content"
    elif LINK_RE.search(text) and not (backup and backup in text.lower()):
        why = "external links"
    else:
        dq = _recent[(cid, uid)]
        now = time.time()
        dq.append((now, text.strip().lower()))
        same = [t for t, x in dq if x and x == text.strip().lower() and now - t < 60]
        if len(same) >= 3:
            why = "repeated messages"
    if not why:
        raise SkipHandler
    try:
        await message.delete()
        if why == "repeated messages":
            await message.bot.restrict_chat_member(cid, uid, ChatPermissions(can_send_messages=False),
                                                   until_date=datetime.now(timezone.utc) + timedelta(minutes=10))
        await sv.send_temp(message.bot, cid, card("warn", "Message removed", [f"Reason: {why}."], "Please follow the group rules."),
                           minutes=1, kind="spam")
        await sv.log_event("spam", chat_id=cid, user_id=uid)
    except Exception:
        pass


# =====================================================================================
# PRIVACY  (users + admin)
# =====================================================================================
@router.message(Command("privacy"), PRIVATE)
async def privacy_cmd(message: Message):
    await message.answer(card("info", "Your privacy", [
        "We store only what the service needs: your Telegram ID, name, orders, coins and AI chat memory.",
        "Nothing is sold or shared. Your identity is never shown to other users.",
        "Use /forget_me to erase your AI memory permanently."], "Send /forget_me if you want your AI memory erased."))


@router.message(Command("forget_me"), PRIVATE)
async def forget_me(message: Message):
    await ai_brain.forget(message.from_user.id)
    await message.answer(card("ok", "AI memory erased", ["Your AI chat history and profile were deleted."], "No action needed."))


@router.message(Command("legacy_lockdown"), IS_ADMIN)
async def lockdown(message: Message, command: CommandObject):
    v = (command.args or "").strip().lower()
    if v not in ("on", "off"):
        cur = (await sv.get_setting("lockdown", "0")) == "1"
        return await message.answer(card("info", "Lockdown", [f"Currently {'ON' if cur else 'OFF'}",
                                                              "ON = bot ignores every non-admin update."], "Use /lockdown on or off."))
    await sv.set_setting("lockdown", "1" if v == "on" else "0")
    await message.answer(card("err" if v == "on" else "ok", f"Lockdown {v.upper()}"))


class LockdownMiddleware(BaseMiddleware):
    """Outer middleware: in lockdown, silently drop everything except the admin."""
    async def __call__(self, handler, event, data):
        u = getattr(event, "from_user", None)
        if u and u.id != ADMIN_ID and (await sv.get_setting("lockdown", "0")) == "1":
            return None
        return await handler(event, data)
