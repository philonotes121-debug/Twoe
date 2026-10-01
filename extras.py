"""extras.py — remaining features from the original Aisha bot + admin order queue + command aliases."""
import io
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, BufferedInputFile
from sqlalchemy import select, func

import config
import services as sv
from config import ADMIN_ID
from database import async_session, User, Course, Order, UserCourse, EventLog, ConnectedChat
from fmt import card, esc

logger = logging.getLogger(__name__)
router = Router()
IS_ADMIN = F.from_user.id == ADMIN_ID
PRIVATE = F.chat.type == "private"
IST = ZoneInfo(config.TIMEZONE)


# ---------------------------------------------------------------- pending orders (admin queue)
@router.message(Command("pending_payments"), IS_ADMIN)
async def pending_orders(message: Message):
    from keyboards import admin_order_decision_kb
    async with async_session() as s:
        rows = (await s.execute(select(Order, Course.name, User.first_name).join(Course, Course.id == Order.course_id)
                                .join(User, User.id == Order.user_id).where(Order.status == "pending")
                                .order_by(Order.id).limit(15))).all()
    if not rows:
        return await message.answer(card("ok", "No pending orders"))
    for o, cname, uname in rows:
        await message.answer(card("warn", f"Order #{o.id}", [f"User: {esc(uname)} (<code>{o.user_id}</code>)", f"Course: {esc(cname)}",
                                                            f"Proof: {esc(o.submission_type)}", f"Age: {o.created_at:%d %b %H:%M}"],
                                  "Approve or reject.", raw=True), reply_markup=admin_order_decision_kb(o.id))


# ---------------------------------------------------------------- scheduled broadcasts (persistent)
async def _sched() -> list:
    try:
        return json.loads(await sv.get_setting("sched_bc", "[]"))
    except Exception:
        return []


@router.message(Command("legacy_schedule"), IS_ADMIN)
async def schedule_bc(message: Message, command: CommandObject):
    src = message.reply_to_message
    try:
        when = datetime.strptime((command.args or "").strip(), "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    except Exception:
        when = None
    if not src or not when:
        return await message.answer(card("info", "Schedule a broadcast", ["Reply to the message, then send:", "/schedule 2026-10-05 07:30  (IST)"],
                                         "Reply to your message and send the command."))
    items = await _sched()
    nid = max([i["id"] for i in items], default=0) + 1
    items.append({"id": nid, "at": when.astimezone(ZoneInfo("UTC")).replace(tzinfo=None).isoformat(),
                  "chat": src.chat.id, "msg": src.message_id})
    await sv.set_setting("sched_bc", json.dumps(items))
    await message.answer(card("ok", "Scheduled", [f"#{nid} • {when:%d %b %Y, %H:%M} IST", "Target: all enabled chats"],
                              "See /scheduled. Cancel with /unschedule <id>."))


@router.message(Command("scheduled"), IS_ADMIN)
async def scheduled_list(message: Message):
    items = await _sched()
    lines = [f"#{i['id']} • {datetime.fromisoformat(i['at']).replace(tzinfo=ZoneInfo('UTC')).astimezone(IST):%d %b %H:%M} IST" for i in items] or ["None."]
    await message.answer(card("info", "Scheduled broadcasts", lines))


@router.message(Command("unschedule"), IS_ADMIN)
async def unschedule(message: Message, command: CommandObject):
    try:
        rid = int((command.args or "").strip())
    except Exception:
        return await message.answer("Use: /unschedule <id>")
    await sv.set_setting("sched_bc", json.dumps([i for i in await _sched() if i["id"] != rid]))
    await message.answer(card("ok", "Removed"))


async def job_scheduled(bot):
    items = await _sched()
    if not items:
        return
    now, keep = datetime.utcnow(), []
    for i in items:
        if datetime.fromisoformat(i["at"]) > now:
            keep.append(i)
            continue
        kb = await sv.growth_kb(bot)
        ok = 0
        for c in await sv.enabled_chats():
            try:
                m = await bot.copy_message(c.id, i["chat"], i["msg"], reply_markup=kb)
                await sv.schedule_delete(c.id, m.message_id, hours=config.DEL_BROADCAST_HOURS, kind="broadcast")
                ok += 1
            except Exception:
                pass
        await sv.notify_admin(bot, card("ok", f"Scheduled broadcast #{i['id']} sent", [f"Delivered to {ok} chats"]), urgent=True)
    await sv.set_setting("sched_bc", json.dumps(keep))


# ---------------------------------------------------------------- user tags / logs
@router.message(Command("tag_user"), IS_ADMIN)
async def tag_user(message: Message, command: CommandObject):
    a = (command.args or "").split(maxsplit=1)
    tags = json.loads(await sv.get_setting("user_tags", "{}"))
    if not a:
        lines = [f"<code>{k}</code> → {esc(v)}" for k, v in list(tags.items())[-20:]] or ["No tags."]
        return await message.answer(card("info", "User tags", lines, "Use /tag_user ID label.", raw=True))
    if len(a) < 2:
        tags.pop(a[0], None)
    else:
        tags[a[0]] = a[1][:40]
    await sv.set_setting("user_tags", json.dumps(tags))
    await message.answer(card("ok", "Tag updated"))


@router.message(Command("logs"), IS_ADMIN)
async def logs_cmd(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(EventLog).order_by(EventLog.id.desc()).limit(20))).scalars().all()
    lines = [f"{r.created_at:%d %b %H:%M} • {r.kind} • {r.user_id or '-'}" for r in rows] or ["No events."]
    await message.answer(card("info", "Recent events", lines))


# ---------------------------------------------------------------- user-facing extras
@router.message(Command("feedback"), PRIVATE)
async def feedback(message: Message, command: CommandObject):
    t = (command.args or "").strip()
    if not t:
        return await message.answer(card("info", "Send feedback", ["Example: /feedback The notes were very helpful"], "Send /feedback with your message."))
    await sv.notify_admin(message.bot, card("info", "Feedback", [f"From <code>{message.from_user.id}</code>", esc(t[:800])], raw=True), urgent=True)
    await message.answer(card("ok", "Thank you", ["Your feedback was received."], "No action needed."))


@router.message(Command("set_resources"), IS_ADMIN)
async def set_resources(message: Message, command: CommandObject):
    v = (command.args or "").strip() or (message.reply_to_message.text if message.reply_to_message else "")
    if not v:
        return await message.answer("Use: /set_resources <text or reply>")
    await sv.set_setting("resources", v)
    await message.answer(card("ok", "Resources saved"))


@router.message(Command("legacy_resources"), PRIVATE)
async def resources(message: Message):
    v = await sv.get_setting("resources", "")
    await message.answer(card("info", "Free resources", [esc(v)] if v else ["Nothing published yet."],
                              "Join the backup channel for updates." if not v else None, raw=True), disable_web_page_preview=True)


@router.message(Command("leaderboard"), PRIVATE)
async def leaderboard(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(User.first_name, User.ref_points, User.id).where(User.ref_points > 0)
                                .order_by(User.ref_points.desc()).limit(10))).all()
    medals = ["🥇", "🥈", "🥉"] + ["▫️"] * 7
    lines = [f"{medals[i]} {esc((n or 'User')[:14])} — {p} coins" for i, (n, p, _) in enumerate(rows)] or ["No entries yet."]
    await message.answer(card("info", "Top referrers", lines, "Share your link from /wallet to enter.", raw=True))


@router.message(Command("my_courses"), PRIVATE)
async def my_courses(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(Course.name).join(UserCourse, UserCourse.course_id == Course.id)
                                .where(UserCourse.user_id == message.from_user.id))).scalars().all()
    await message.answer(card("info", "Your courses", [esc(n[:50]) for n in rows] or ["None yet."],
                              "Open /start to browse." if not rows else "Open /myorders for details.", raw=True))


@router.message(Command("courses"), PRIVATE)
async def courses_cmd(message: Message):
    from keyboards import main_menu_kb
    await message.answer(card("info", "Course library", nxt="Choose a section below."), reply_markup=main_menu_kb())


@router.message(Command("certificate"), PRIVATE)
async def certificate(message: Message):
    async with async_session() as s:
        row = (await s.execute(select(Course.name).join(UserCourse, UserCourse.course_id == Course.id)
                               .where(UserCourse.user_id == message.from_user.id).order_by(UserCourse.id.desc()).limit(1))).scalar()
    if not row:
        return await message.answer(card("warn", "No enrolment found", nxt="Enrol in a course first, then send /certificate."))
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1200, 800), "#fdfaf3")
    d = ImageDraw.Draw(img)
    d.rectangle([30, 30, 1170, 770], outline="#1e3a8a", width=8)

    def font(sz):
        for f in ("DejaVuSans-Bold.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(f, sz)
            except Exception:
                pass
        return ImageFont.load_default()
    d.text((600, 150), "CERTIFICATE OF ENROLMENT", fill="#1e3a8a", font=font(50), anchor="mm")
    d.text((600, 290), "This is to certify that", fill="#444", font=font(30), anchor="mm")
    d.text((600, 380), message.from_user.full_name[:34], fill="#111", font=font(60), anchor="mm")
    d.text((600, 490), "is enrolled in", fill="#444", font=font(30), anchor="mm")
    d.text((600, 570), row[:48], fill="#1e3a8a", font=font(42), anchor="mm")
    d.text((600, 700), f"{config.BOT_NAME}  •  {datetime.now(IST):%d %B %Y}", fill="#666", font=font(26), anchor="mm")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    await message.answer_photo(BufferedInputFile(buf.getvalue(), "certificate.png"),
                               caption=card("ok", "Certificate ready", nxt="Save or share it."))


@router.message(Command("admincommands"), IS_ADMIN)
async def admincommands(message: Message):
    await message.answer(card("info", "Admin quick reference", [
        "Access: /lms_requests /lms_approve /lms_deny /lms_revoke /lms_gate /lms_grandfather",
        "Orders: /pending /grant /revenue /createpromo",
        "Inbox: swipe-reply • /pending_inbox /doubts",
        "Chats: /chats /register_chat /addchat /watch /chatflag",
        "Broadcast: /broadcast_all /broadcast_selected /schedule /scheduled /delete_broadcast",
        "Control: /offline /lockdown /antispam /notify /toggle_ai",
        "Insight: /dashboard /analytics /analytics3d /logs /health /export_users",
        "Users: /userinfo /tag_user /ban /unban"], "Use /adminhelp for the full list."))
