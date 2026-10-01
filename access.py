"""LMS access control — the course library is opened ONLY for users the admin approves.

Flow: user taps Request Access -> admin gets Approve/Deny card -> user is notified with next step.
Enforced in the bot (middleware) AND on the Mini App API (signed initData + approved check).
"""
import logging
from datetime import datetime

from aiogram import Router, F, BaseMiddleware
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func

import config
import services as sv
from config import ADMIN_ID
from database import async_session, LmsAccess, User, UserCourse
from fmt import card, esc

logger = logging.getLogger(__name__)
router = Router()
IS_ADMIN = F.from_user.id == ADMIN_ID

# Catalogue-related callbacks and commands that need approval.
GATED_CB = ("menu:", "sec:", "topsec:", "upscopt:", "allcourses:", "mycourses:", "buy", "pay", "gc", "promo")
GATED_CMDS = ("/courses", "/trending", "/applypromo", "/mycourses")


async def gate_on() -> bool:
    return (await sv.get_setting("lms_gate", "1")) == "1"


async def status_of(user_id: int) -> str:
    """approved / pending / denied / none"""
    if user_id == ADMIN_ID:
        return "approved"
    if not await gate_on():
        return "approved"
    async with async_session() as s:
        row = await s.get(LmsAccess, user_id)
    return row.status if row else "none"


async def is_approved(user_id: int) -> bool:
    return (await status_of(user_id)) == "approved"


def request_kb(status: str) -> InlineKeyboardMarkup:
    rows = []
    if status == "none":
        rows.append([InlineKeyboardButton(text="🔓 Request Access", callback_data="lms:req")])
    rows.append([InlineKeyboardButton(text="🪙 Coins & Referrals", callback_data="coin:home"),
                 InlineKeyboardButton(text="💬 Contact Support", callback_data="contact:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def locked_text(status: str) -> str:
    if status == "pending":
        return card("warn", "Request received", ["Your access request is under review."],
                    "No action needed. You will be notified once it is approved.")
    if status == "denied":
        return card("err", "Access not granted", ["Your request was not approved."],
                    "Use Contact Support if you believe this is a mistake.")
    return card("info", "Access required", ["The course library opens by approval only."],
                "Tap Request Access. You will be notified here.")


async def _joined_or_prompt(bot, user, reply) -> bool:
    """Backup-channel join comes first (also required for referral credit). True = joined."""
    from keyboards import join_channel_kb
    st = await sv.backup_status(bot, user.id)
    if st is False:
        await reply(card("warn", "Join required", ["Join the backup channel to continue."],
                         "Tap Join, then press Continue."), reply_markup=join_channel_kb(config.BACKUP_CHANNEL))
        return False
    if st is True:
        async with async_session() as s:
            u = await s.get(User, user.id)
            if u and not u.has_joined_backup_channel:
                u.has_joined_backup_channel = True
                await s.commit()
    return True


class LmsGateMiddleware(BaseMiddleware):
    """Inner middleware (runs only for updates that matched a handler)."""
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user or user.id == ADMIN_ID:
            return await handler(event, data)
        is_cb = isinstance(event, CallbackQuery)
        if is_cb:
            d = event.data or ""
            # System subscription products may be purchased before LMS approval; the paid plan is the access grant.
            if d.startswith("buy:"):
                try:
                    from database import Course
                    cid=int(d.split(":",1)[1])
                    async with async_session() as s:
                        product=await s.get(Course,cid)
                    if product and product.system_product in ("community","ca_tracker"):
                        return await handler(event,data)
                except Exception:
                    pass
            if d != "checkjoin" and not d.startswith(GATED_CB):
                return await handler(event, data)
        elif isinstance(event, Message):
            t = (event.text or "").strip()
            if not (t.startswith("/start") or t.startswith(GATED_CMDS)):
                return await handler(event, data)
        else:
            return await handler(event, data)

        # User-facing LMS access is unlocked by phone verification only.
        # LmsAccess remains an administrative audit/request record and no longer
        # blocks the verified user's Mini App.
        u = await sv.ensure_user(user)
        if u.phone_verified and await sv.get_setting("lockdown", "0") != "1":
            return await handler(event, data)
        if is_cb:
            await event.answer()
            reply = event.message.answer
        else:
            reply = event.answer
        if not u.phone_verified:
            from premium import show_phone_gate
            await show_phone_gate(event.message if is_cb else event)
            return None
        await reply(card("warn", "LMS unavailable", ["Access is temporarily restricted."], "Try again later."), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Contact Support", callback_data="contact:open")]]))
        return None


def decision_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Approve", callback_data=f"lms:ok:{uid}"),
        InlineKeyboardButton(text="❌ Deny", callback_data=f"lms:no:{uid}")]])


@router.callback_query(F.data == "lms:req")
async def request_access(call: CallbackQuery):
    u = call.from_user
    st = await status_of(u.id)
    if st in ("pending", "approved", "denied"):
        await call.message.answer(locked_text(st) if st != "approved" else
                                  card("ok", "Already approved", nxt="Send /start to open the library."))
        return await call.answer()
    await sv.ensure_user(u)
    async with async_session() as s:
        s.add(LmsAccess(user_id=u.id, status="pending"))
        await s.commit()
        refs = (await s.execute(select(func.count()).select_from(User).where(User.referrer_id == u.id))).scalar() or 0
    await call.message.answer(locked_text("pending"))
    await call.answer()
    await call.bot.send_message(ADMIN_ID, card(
        "info", "LMS access request",
        [f"Name: {esc(u.full_name)}", f"Username: @{esc(u.username or '—')}", f"User ID: <code>{u.id}</code>",
         f"Referred users: {refs}"], "Approve or deny below.", raw=True), reply_markup=decision_kb(u.id))


@router.callback_query(IS_ADMIN, F.data.startswith(("lms:ok:", "lms:no:")))
async def decide(call: CallbackQuery):
    _, act, uid = call.data.split(":")
    uid = int(uid)
    approve = act == "ok"
    async with async_session() as s:
        row = await s.get(LmsAccess, uid)
        if not row:
            row = LmsAccess(user_id=uid)
            s.add(row)
        row.status = "approved" if approve else "denied"
        row.decided_at = datetime.utcnow()
        await s.commit()
    try:
        await call.message.edit_text(call.message.html_text + ("\n\n✅ APPROVED" if approve else "\n\n❌ DENIED"))
    except Exception:
        pass
    await call.answer("Done")
    await _notify_user(call.bot, uid, approve)


async def _notify_user(bot, uid: int, approve: bool):
    try:
        if approve:
            await bot.send_message(uid, card("ok", "Access approved", ["The course library is now open."],
                                             "Send /start to browse courses."))
        else:
            await bot.send_message(uid, card("err", "Access not granted", ["Your request was not approved."],
                                             "Use /contact if you need help."))
    except Exception:
        pass


def _uid(command: CommandObject):
    try:
        return int((command.args or "").split()[0])
    except Exception:
        return None


@router.message(Command("lms_requests"), IS_ADMIN)
async def lms_requests(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(LmsAccess).where(LmsAccess.status == "pending")
                                .order_by(LmsAccess.requested_at).limit(20))).scalars().all()
    if not rows:
        return await message.answer(card("ok", "No pending requests"))
    for r in rows:
        await message.answer(card("info", "Pending request", [f"User ID: <code>{r.user_id}</code>",
                                                              f"Requested: {r.requested_at:%d %b %H:%M}"], raw=True),
                             reply_markup=decision_kb(r.user_id))


async def _set(uid: int, status: str):
    async with async_session() as s:
        row = await s.get(LmsAccess, uid)
        if not row:
            row = LmsAccess(user_id=uid)
            s.add(row)
        row.status, row.decided_at = status, datetime.utcnow()
        await s.commit()


@router.message(Command("lms_approve"), IS_ADMIN)
async def lms_approve(message: Message, command: CommandObject):
    uid = _uid(command)
    if not uid:
        return await message.answer("Use: /lms_approve USER_ID")
    await _set(uid, "approved")
    await _notify_user(message.bot, uid, True)
    await message.answer(card("ok", "Approved", [f"User {uid}"]))


@router.message(Command("lms_deny"), IS_ADMIN)
async def lms_deny(message: Message, command: CommandObject):
    uid = _uid(command)
    if not uid:
        return await message.answer("Use: /lms_deny USER_ID")
    await _set(uid, "denied")
    await message.answer(card("err", "Denied", [f"User {uid}"]))


@router.message(Command("lms_revoke"), IS_ADMIN)
async def lms_revoke(message: Message, command: CommandObject):
    uid = _uid(command)
    if not uid:
        return await message.answer("Use: /lms_revoke USER_ID")
    await _set(uid, "denied")
    await message.answer(card("warn", "Access revoked", [f"User {uid}"]))


@router.message(Command("lms_grandfather"), IS_ADMIN)
async def lms_grandfather(message: Message):
    """Approve everyone who already owns a course, so existing customers are not locked out."""
    async with async_session() as s:
        ids = (await s.execute(select(UserCourse.user_id).distinct())).scalars().all()
    for uid in ids:
        await _set(uid, "approved")
    await message.answer(card("ok", "Existing customers approved", [f"{len(ids)} users"]))


@router.message(Command("lms_gate"), IS_ADMIN)
async def lms_gate(message: Message, command: CommandObject):
    v = (command.args or "").strip().lower()
    if v not in ("on", "off"):
        return await message.answer(card("info", "LMS gate", [f"Currently {'ON' if await gate_on() else 'OFF'}"],
                                         "Use /lms_gate on or /lms_gate off"))
    await sv.set_setting("lms_gate", "1" if v == "on" else "0")
    await message.answer(card("ok", f"LMS gate {v.upper()}"))
