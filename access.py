"""LMS access control.

Flow:
1. /start -> backup channel join is mandatory (handled in user_handlers + security middleware).
2. After joining, the user gets the normal bot (10 commands) without LMS.
3. /lms (or "Unlock LMS") -> user verifies mobile via Telegram contact button.
4. Verification creates a pending LmsAccess request and notifies Admin with Approve/Deny.
5. Admin approves -> user is notified and the LMS Mini App unlocks.

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

# Catalogue-related callbacks and commands that need LMS approval.
GATED_CB = ("menu:", "sec:", "topsec:", "upscopt:", "allcourses:", "mycourses:", "buy", "pay", "gc", "promo", "trending:")
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


async def has_lms(user_id: int) -> bool:
    """Phone verified AND admin approved (or gate off)."""
    if user_id == ADMIN_ID:
        return True
    u = await sv.ensure_user_by_id(user_id)
    if not u or u.is_banned or not u.phone_verified:
        return False
    return await is_approved(user_id)


async def menu_kb_for(user_id: int) -> InlineKeyboardMarkup:
    from keyboards import main_menu_kb, home_kb
    return main_menu_kb() if await has_lms(user_id) else home_kb()


def locked_text(status: str) -> str:
    if status == "pending":
        return card("warn", "LMS request under review", ["Your mobile is verified and the request reached Admin."],
                    "You will get a notification here as soon as Admin approves.")
    if status == "denied":
        return card("err", "LMS access not granted", ["Admin did not approve your last request."],
                    "Tap Request Again or contact Support.")
    return card("info", "LMS locked", ["Verify your mobile number to request LMS access."],
                "Tap the Verify Mobile Number button below.")


def _status_kb(status: str) -> InlineKeyboardMarkup:
    rows = []
    if status == "denied":
        rows.append([InlineKeyboardButton(text="🔁 Request Again", callback_data="lms:req")])
    rows.append([InlineKeyboardButton(text="💬 Contact Support", callback_data="contact:open")])
    rows.append([InlineKeyboardButton(text="⬅ Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def decision_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Approve LMS", callback_data=f"lms:ok:{uid}"),
        InlineKeyboardButton(text="❌ Deny", callback_data=f"lms:no:{uid}")]])


async def submit_request(bot, tg_user, phone_tail: str = "") -> str:
    """Create/refresh a pending request and notify Admin. Returns the resulting status."""
    st = await status_of(tg_user.id)
    if st == "approved":
        return st
    async with async_session() as s:
        row = await s.get(LmsAccess, tg_user.id)
        if not row:
            row = LmsAccess(user_id=tg_user.id)
            s.add(row)
        row.status = "pending"
        row.requested_at = datetime.utcnow()
        row.decided_at = None
        await s.commit()
        refs = (await s.execute(select(func.count()).select_from(User).where(User.referrer_id == tg_user.id))).scalar() or 0
    lines = [f"Name: {esc(tg_user.full_name)}", f"Username: @{esc(tg_user.username or '—')}",
             f"User ID: <code>{tg_user.id}</code>", "Mobile: ✅ verified" + (f" (…{esc(phone_tail)})" if phone_tail else ""),
             f"Referred users: {refs}"]
    try:
        await bot.send_message(ADMIN_ID, card("info", "🔔 New LMS access request", lines, "Approve or deny below.", raw=True),
                               reply_markup=decision_kb(tg_user.id))
    except Exception:
        logger.exception("LMS request admin notify failed")
    return "pending"


async def user_lms_entry(message: Message, tg_user) -> None:
    """Single entry point for /lms, /menu and the Unlock LMS button."""
    from keyboards import main_menu_kb, phone_verification_kb
    u = await sv.ensure_user(tg_user)
    if u.is_banned:
        await message.answer("🚫 Access unavailable.")
        return
    if await sv.get_setting("lockdown", "0") == "1":
        await message.answer(card("warn", "LMS unavailable", ["Access is temporarily restricted."], "Try again later."))
        return
    if not u.phone_verified:
        await message.answer(locked_text("none"), reply_markup=phone_verification_kb())
        return
    st = await status_of(u.id)
    if st == "approved":
        await message.answer(card("ok", "LMS unlocked", ["Open the LMS Mini App below."]), reply_markup=main_menu_kb())
        return
    if st == "none":
        st = await submit_request(message.bot, tg_user)
    await message.answer(locked_text(st), reply_markup=_status_kb(st))


class LmsGateMiddleware(BaseMiddleware):
    """Inner middleware: only LMS/catalogue actions require phone verification + Admin approval."""
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user or user.id == ADMIN_ID:
            return await handler(event, data)
        is_cb = isinstance(event, CallbackQuery)
        if is_cb:
            d = event.data or ""
            # Paid community/CA plans are their own access grant and can be bought before LMS approval.
            if d.startswith("buy:"):
                try:
                    from database import Course
                    cid = int(d.split(":", 1)[1])
                    async with async_session() as s:
                        product = await s.get(Course, cid)
                    if product and product.system_product in ("community", "ca_tracker"):
                        return await handler(event, data)
                except Exception:
                    pass
            if not d.startswith(GATED_CB):
                return await handler(event, data)
            if d in ("menu:main", "menu:back") and not await has_lms(user.id):
                # Non-LMS users go back to the normal home menu instead of a lock screen.
                state = data.get("state")
                if state is not None:
                    await state.clear()
                from keyboards import home_kb
                try:
                    await event.message.edit_text(f"📚 <b>{config.BOT_NAME}</b>\n\nChoose an option:", reply_markup=home_kb())
                except Exception:
                    await event.message.answer(f"📚 <b>{config.BOT_NAME}</b>\n\nChoose an option:", reply_markup=home_kb())
                await event.answer()
                return None
        elif isinstance(event, Message):
            t = (event.text or "").strip()
            if not t.startswith(GATED_CMDS):
                return await handler(event, data)
        else:
            return await handler(event, data)

        if await has_lms(user.id) and await sv.get_setting("lockdown", "0") != "1":
            return await handler(event, data)
        if is_cb:
            await event.answer("🔒 LMS locked — verify & get Admin approval first.", show_alert=False)
            await user_lms_entry(event.message, user)
        else:
            await user_lms_entry(event, user)
        return None


@router.message(Command("lms"), ~IS_ADMIN)
async def lms_user_cmd(message: Message):
    if message.chat.type != "private":
        return
    await user_lms_entry(message, message.from_user)


@router.callback_query(F.data == "lms:open")
async def lms_open_cb(call: CallbackQuery):
    await call.answer()
    await user_lms_entry(call.message, call.from_user)


@router.callback_query(F.data == "lms:req")
async def request_access(call: CallbackQuery):
    u = await sv.ensure_user(call.from_user)
    await call.answer()
    if not u.phone_verified:
        return await user_lms_entry(call.message, call.from_user)
    st = await status_of(u.id)
    if st == "approved":
        from keyboards import main_menu_kb
        return await call.message.answer(card("ok", "Already approved"), reply_markup=main_menu_kb())
    if st == "pending":
        return await call.message.answer(locked_text(st), reply_markup=_status_kb(st))
    st = await submit_request(call.bot, call.from_user)
    await call.message.answer(locked_text(st), reply_markup=_status_kb(st))


@router.callback_query(IS_ADMIN, F.data.startswith(("lms:ok:", "lms:no:")))
async def decide(call: CallbackQuery):
    _, act, uid = call.data.split(":")
    uid = int(uid)
    approve = act == "ok"
    await _set(uid, "approved" if approve else "denied")
    try:
        await call.message.edit_text(call.message.html_text + ("\n\n✅ APPROVED" if approve else "\n\n❌ DENIED"))
    except Exception:
        pass
    await call.answer("Done")
    await notify_user(call.bot, uid, approve)


async def notify_user(bot, uid: int, approve: bool):
    from keyboards import main_menu_kb, home_kb
    try:
        if approve:
            await bot.send_message(uid, card("ok", "🎉 LMS unlocked", ["Admin approved your request.", "The LMS Mini App is now open for you."],
                                             "Tap Open LMS below."), reply_markup=main_menu_kb())
        else:
            await bot.send_message(uid, card("err", "LMS access not granted", ["Admin did not approve your request."],
                                             "You can request again or contact Support."), reply_markup=_status_kb("denied"))
            await bot.send_message(uid, "Menu:", reply_markup=home_kb())
    except Exception:
        logger.warning("LMS decision notify failed for %s", uid)


# Backwards-compatible alias.
_notify_user = notify_user


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
    await notify_user(message.bot, uid, True)
    await message.answer(card("ok", "Approved", [f"User {uid}"]))


@router.message(Command("lms_deny"), IS_ADMIN)
async def lms_deny(message: Message, command: CommandObject):
    uid = _uid(command)
    if not uid:
        return await message.answer("Use: /lms_deny USER_ID")
    await _set(uid, "denied")
    await notify_user(message.bot, uid, False)
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


# ---------------- Home-menu buttons (previously had no handlers) ----------------
@router.callback_query(F.data == "account:open")
async def account_cb(call: CallbackQuery):
    await call.answer()
    await call.message.answer(await account_text(call.from_user.id), reply_markup=await menu_kb_for(call.from_user.id))


async def account_text(uid: int) -> str:
    from premium import active_membership
    u = await sv.ensure_user_by_id(uid)
    comm = await active_membership(uid, "community")
    ca = await active_membership(uid, "ca_tracker")
    st = await status_of(uid)
    lms = "✅ unlocked" if (u and u.phone_verified and st == "approved") else (
        "⏳ pending Admin approval" if st == "pending" else "🔒 locked (use /lms)")
    return (f"👤 <b>Account</b>\n"
            f"Backup channel: {'✅ joined' if u and u.has_joined_backup_channel else '❌ not joined'}\n"
            f"Mobile: {'✅ verified' if u and u.phone_verified else '❌ not verified'}\n"
            f"LMS: {lms}\n"
            f"Community: {'✅ active till ' + comm.expires_at.strftime('%d %b %Y') if comm else 'inactive'}\n"
            f"CA Tracker: {'✅ active till ' + ca.expires_at.strftime('%d %b %Y') if ca else 'inactive'}")


@router.callback_query(F.data == "referral:open")
async def referral_cb(call: CallbackQuery):
    await call.answer()
    from premium import send_referral
    await send_referral(call.message, call.from_user.id)


@router.callback_query(F.data == "countdown:open")
async def countdown_cb(call: CallbackQuery):
    await call.answer()
    try:
        exam = datetime.strptime(config.EXAM_DATE, "%Y-%m-%d").date()
        days = (exam - datetime.utcnow().date()).days
        text = f"📅 <b>{esc(config.EXAM_NAME)}</b>\n\n⏳ <b>{max(days, 0)} days</b> left ({exam:%d %b %Y})."
    except Exception:
        text = "📅 Countdown date is not configured."
    await call.message.answer(text, reply_markup=await menu_kb_for(call.from_user.id))
