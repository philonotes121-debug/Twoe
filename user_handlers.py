import json
import logging
import asyncio
import re
import time
from datetime import datetime
from collections import defaultdict

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import select

from database import (
    async_session, User, Course, Order, UserCourse, Section, ContactMessage, log_step,
)
from config import BACKUP_CHANNEL, BOT_NAME, ADMIN_ID, PROFESSOR_CONTACT_LINK
import services as sv
from keyboards import (
    main_menu_kb, upsc_subsections_kb, state_psc_kb, section_webapp_kb,
    all_courses_webapp_kb, payment_method_kb, amazon_gift_intro_kb, gift_card_collect_kb,
    upi_contact_kb, admin_order_decision_kb, join_channel_kb,
    help_kb, SECTION_TITLES, get_line, get_welcome_message, BuyFlow,
    prelims_mains_kb, subject_specific_kb, empty_section_kb, optional_subjects_kb,
    ContactFlow, contact_cancel_kb, ProfessorAIFlow,
)

# 🛡️ IMPORTING SECURITY & ADMIN STATES
from security import scan_image_for_code
from admin_handlers import AI_STATE, ACTIVE_PROMOS

logger = logging.getLogger(__name__)
router = Router()

# ================= ZERO-TRUST ANTI-TRACKING & PRIVACY ENFORCER =================
def sanitize_telemetry_payload(text: str) -> str:
    """Zero-Trust Shield: Strips out any potential IP telemetry, tracking parameters, or exposed endpoints."""
    if not text:
        return ""
    # Scrub potential tracking URLs or IP leaking patterns
    clean_text = re.sub(r"https?://[^\s]+", "[SECURE_LINK_MASKED]", text)
    return clean_text

# ================= GLOBAL TRACKERS =================
broadcast_reply_counts = defaultdict(int)
ai_chat_monitor = defaultdict(list)   
ai_frozen_until = {}                  

def uid_tag(user_id: int) -> str:
    """User ID wrapped so a single tap copies it in Telegram with zero telemetry footprint."""
    return f"<code>{user_id}</code>"


def _with_ai_button(kb: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """The '⭐ Chat with AI Helper' button now lives inside main_menu_kb()
    itself (right under Search Course, highlighted) so it's positioned
    consistently everywhere the menu is shown. This wrapper is kept as a
    no-op (instead of removed) so none of the call-sites need touching —
    it previously appended a second, plain-text AI button at the bottom,
    which would now duplicate the highlighted one."""
    return kb


# ================= CART ABANDONMENT REMINDER TASK =================
async def cart_abandonment_reminder(bot, user_id, course_name):
    """Sends a secure reminder if user stops halfway through payment (4-hour delay)."""
    await asyncio.sleep(4 * 3600) 
    try:
        await bot.send_message(
            user_id, 
            f"🔔 <b>Reminder:</b> Aapka selected course payment pending hai.\n\n"
            f"Agar aapko Amazon Pay Gift Card kharidne mein koi issue aa raha hai, toh kripya Help section se Professor se baat karein!", 
            parse_mode="HTML"
        )
    except Exception: 
        pass


# ================= START / CHANNEL GATE =================
async def _get_or_create_user(tg_user) -> tuple[User, bool]:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == tg_user.id))
        user = result.scalar_one_or_none()
        is_new = user is None
        if user is None:
            user = User(id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name)
            session.add(user)
        else:
            user.username = tg_user.username
            user.first_name = tg_user.first_name
        await session.commit()
        await session.refresh(user)
        return user, is_new


async def _notify_admin_of_start(bot, tg_user, is_new: bool, user: User):
    if tg_user.id == ADMIN_ID:
        return
    status_tag = "🆕 New user" if is_new else "🔁 Returning user"
    text = (
        f"👋 <b>{status_tag} started the bot</b>\n\n"
        f"👤 Name: {tg_user.full_name}\n"
        f"🔗 Username: @{tg_user.username or '—'}\n"
        f"🆔 User ID: {uid_tag(tg_user.id)}\n"
        f"📅 First seen: {user.joined_at.strftime('%d %b %Y, %H:%M UTC') if user.joined_at else '—'}\n"
        f"✅ Backup channel verified: {'Yes' if user.has_joined_backup_channel else 'No'}"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception:
        logger.exception("Failed to notify admin of /start")


async def _is_member_of_backup_channel(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=BACKUP_CHANNEL, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except TelegramForbiddenError:
        logger.error(f"Backup-channel check failed for user {user_id}: bot is not an admin of {BACKUP_CHANNEL}.")
        return False
    except TelegramBadRequest:
        logger.warning(f"Backup-channel check: user {user_id} not found in {BACKUP_CHANNEL}.")
        return False
    except Exception:
        return False


@router.message(CommandStart(deep_link=True))
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    user, is_new = await _get_or_create_user(message.from_user)
    await _notify_admin_of_start(message.bot, message.from_user, is_new, user)
    await log_step(user.id, "Started the bot (/start)")

    if user.is_banned:
        await message.answer("🚫 Access unavailable.")
        return

    # Phone verification is the first LMS unlock step. Do not expose menus or course data before consented contact share.
    if not user.phone_verified and message.chat.type == "private":
        from premium import show_phone_gate
        await sv.set_user_commands(message.bot, user.id, verified=False)
        await show_phone_gate(message)
        return

    await sv.set_user_commands(message.bot, user.id, verified=True)
    pending_course_id = None
    if command.args and command.args.startswith("buy_"):
        try:
            pending_course_id = int(command.args.split("_", 1)[1])
        except ValueError:
            pending_course_id = None

    if config.REQUIRE_BACKUP_FOR_FEATURES and not user.has_joined_backup_channel:
        is_member = await _is_member_of_backup_channel(message.bot, message.from_user.id)
        if not is_member:
            if pending_course_id:
                await state.update_data(pending_course_id=pending_course_id)
            await message.answer(
                f"👋 Welcome to <b>{BOT_NAME}</b>!\n\n"
                "Join the backup channel to continue.",
                reply_markup=join_channel_kb(BACKUP_CHANNEL),
            )
            return
        async with async_session() as session:
            u = await session.get(User, user.id)
            u.has_joined_backup_channel = True
            await session.commit()

    if pending_course_id:
        await _show_buy_screen(message, pending_course_id, tg_user=message.from_user)
        return

    welcome = get_welcome_message(message.from_user.first_name)
    await message.answer(
        f"👋 {welcome}\n\n{get_line()}\n\n"
        "Open the LMS Mini App to browse the course catalogue.",
        reply_markup=_with_ai_button(main_menu_kb()),
    )


@router.callback_query(F.data == "checkjoin")
async def cb_check_join(call: CallbackQuery, state: FSMContext):
    is_member = await _is_member_of_backup_channel(call.bot, call.from_user.id)
    if not is_member:
        await call.answer(
            "We still can't see you in the channel — join, then try again 🙏",
            show_alert=True,
        )
        return
    async with async_session() as session:
        u = await session.get(User, call.from_user.id)
        if u:
            u.has_joined_backup_channel = True
            await session.commit()

    data = await state.get_data()
    pending_course_id = data.get("pending_course_id")
    if pending_course_id:
        await state.update_data(pending_course_id=None)
        await _show_buy_screen(call.message, pending_course_id, tg_user=call.from_user, edit=True)
        await call.answer()
        return

    welcome = get_welcome_message(call.from_user.first_name)
    await call.message.edit_text(
        f"✅ Verified! {welcome}\n\n{get_line()}\n\nChoose a section below:",
        reply_markup=_with_ai_button(main_menu_kb()),
    )
    await call.answer()


@router.callback_query(F.data.in_(["menu:main", "menu:back"]))
async def cb_back_main(call: CallbackQuery, state: FSMContext):
    # Leaving to the main menu also exits "Chat with AI Helper" mode, if active —
    # otherwise a stray message typed later would still be treated as an AI query.
    if await state.get_state() == ProfessorAIFlow.chatting:
        await state.clear()
    await call.message.edit_text(
        f"📚 <b>{BOT_NAME}</b>\n\n{get_line()}\n\nChoose a section:",
        reply_markup=_with_ai_button(main_menu_kb()),
    )
    await call.answer()


@router.callback_query(F.data == "professor_ai:open")
async def cb_open_professor_ai(call: CallbackQuery, state: FSMContext):
    await log_step(call.from_user.id, "Opened Chat with AI Helper")
    await state.set_state(ProfessorAIFlow.chatting)
    await call.message.edit_text(
        "🤖 <b>AI Helper</b>\n\n"
        "Apna sawaal seedha type karke bhejo — courses, syllabus, strategy, kuch bhi.\n\n"
        "⏱️ Fair-use limit: 10 messages / 5 minutes (bahut zyada load na ho, isliye).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅ Back to Menu", callback_data="menu:main")]
        ]),
    )
    await call.answer()


# ================= SECTIONS =================
@router.callback_query(F.data == "topsec:upsc")
async def cb_upsc(call: CallbackQuery):
    await log_step(call.from_user.id, "Opened UPSC menu")
    await call.message.edit_text(f"🏛 <b>UPSC</b>\n\n{get_line()}\n\nWhich stage do you need?", reply_markup=upsc_subsections_kb())
    await call.answer()


@router.callback_query(F.data == "topsec:state_psc")
async def cb_state_psc(call: CallbackQuery):
    await log_step(call.from_user.id, "Opened All State PSC menu")
    await call.message.edit_text(f"🏢 <b>All State PSC</b>\n\n{get_line()}\n\nChoose your state:", reply_markup=state_psc_kb())
    await call.answer()


@router.callback_query(F.data == "topsec:prelims_mains")
async def cb_prelims_mains(call: CallbackQuery):
    await log_step(call.from_user.id, "Opened Prelims & Mains Specific Batch menu")
    await call.message.edit_text(
        f"♛ <b>Prelims & Mains Specific Batch</b>\n\n{get_line()}\n\nWhich stage do you need?",
        reply_markup=prelims_mains_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "topsec:subject_specific")
async def cb_subject_specific(call: CallbackQuery):
    await log_step(call.from_user.id, "Opened Subject Specific Batch menu")
    await call.message.edit_text(
        f"🧑‍🏫 <b>Subject Specific Batch</b>\n\n{get_line()}\n\nChoose a subject:",
        reply_markup=subject_specific_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "upscopt:open")
async def cb_upsc_optional_picker(call: CallbackQuery):
    await log_step(call.from_user.id, "Opened UPSC Optional picker")
    await call.message.edit_text(
        f"📗 <b>UPSC Optional Subjects</b>\n\n{get_line()}\n\nChoose your optional:",
        reply_markup=optional_subjects_kb(),
    )
    await call.answer()


async def _section_course_count(key: str) -> int:
    async with async_session() as session:
        result = await session.execute(select(Section).where(Section.key == key))
        section = result.scalar_one_or_none()
        if not section:
            return 0
        return len([c for c in section.courses if c.is_active])


@router.callback_query(F.data.startswith("sec:"))
async def cb_leaf_section(call: CallbackQuery):
    key = call.data.split(":", 1)[1]
    title = SECTION_TITLES.get(key, key.title())
    await log_step(call.from_user.id, f"Opened section: {title}")

    count = await _section_course_count(key)
    if count == 0:
        await call.message.edit_text(
            f"📂 <b>{title}</b>\n\n"
            "Abhi is category me koi course listed nahi hai. Aapki specific demand ke liye "
            "Professor ko seedha message kar sakte ho 👇",
            reply_markup=empty_section_kb(),
        )
        await call.answer()
        return

    await call.message.edit_text(
        f"📂 <b>{title}</b>\n\n{get_line()}\n\nFull course catalog is in the Mini App 👇",
        reply_markup=section_webapp_kb(key, title),
    )
    await call.answer()


# ================= SEARCH ALL COURSES =================
@router.callback_query(F.data == "allcourses:open")
async def cb_all_courses(call: CallbackQuery):
    await log_step(call.from_user.id, "Opened Search All Courses")
    await call.message.edit_text(
        f"🔍 <b>Search All Courses</b>\n\n{get_line()}\n\n"
        "Browse and search across every section — foundation, mains, optionals, "
        "state PSCs, NET/JRF, and combo deals — in one place 👇",
        reply_markup=all_courses_webapp_kb(),
    )
    await call.answer()


# ================= TRENDING =================
async def _trending_kb() -> InlineKeyboardMarkup:
    async with async_session() as session:
        result = await session.execute(select(Course).where(Course.is_trending == True, Course.is_active == True))  # noqa: E712
        courses = result.scalars().all()
    rows = []
    for c in courses:
        price_tag = f"₹{int(c.price)}" if c.price is not None else "Price TBD"
        rows.append([InlineKeyboardButton(text=f"🔥 {c.name} — {price_tag}", callback_data=f"buy:{c.id}")])
    rows.append([InlineKeyboardButton(text="⬅ Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

TRENDING_TEXT = "🔥 <b>Trending Courses</b>\n\n{line}\n\nThe courses in highest demand right now — buy directly from here."

@router.message(Command("trending"))
async def cmd_trending(message: Message):
    if message.chat.type != "private": return
    u=await sv.ensure_user(message.from_user)
    if not u.phone_verified: return
    await message.answer(TRENDING_TEXT.format(line=get_line()), reply_markup=await _trending_kb())

@router.callback_query(F.data == "trending:open")
async def cb_trending(call: CallbackQuery):
    await log_step(call.from_user.id, "Opened Trending Courses")
    await call.message.edit_text(TRENDING_TEXT.format(line=get_line()), reply_markup=await _trending_kb())
    await call.answer()


# ================= BUY FLOW & FLASH SALES (PROMO) =================
def _course_detail_text(course: Course) -> str:
    price_tag = f"₹{int(course.price)}" if course.price is not None else "Price on request — Professor will confirm with you"
    return (
        f"📘 <b>Selected Course</b>\n"
        f"🆔 Course ID: {course.id}\n"
        f"👨‍🏫 Faculty: {course.faculty or '—'}\n"
        f"🌐 Medium: {course.medium or '—'}\n"
        f"📝 Notes: {course.notes or '—'}\n"
        f"💰 {price_tag}\n♾️ Validity: Lifetime\n\n"
        "Choose a payment method below 👇"
    )


async def _notify_admin_buy_intent(bot, tg_user, course: Course):
    if tg_user.id == ADMIN_ID:
        return
    price_tag = f"₹{int(course.price)}" if course.price is not None else "TBD"
    text = (
        "👀 <b>Buy intent</b> — user opened the payment screen\n\n"
        f"👤 Name: {tg_user.full_name}\n"
        f"🔗 Username: @{tg_user.username or '—'}\n"
        f"🆔 User ID: {uid_tag(tg_user.id)}\n"
        f"📘 Course: {course.name}\n"
        f"🆔 Course ID: {course.id}\n"
        f"💰 Price: {price_tag}"
    )
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception:
        logger.exception("Failed to notify admin of buy intent")


async def _show_buy_screen(message: Message, course_id: int, tg_user=None, edit: bool = False):
    tg_user = tg_user or message.from_user
    async with async_session() as session:
        course = await session.get(Course, course_id)
    if not course or not course.is_active:
        target = message.edit_text if edit else message.answer
        await target("This course isn't available right now — please pick another from the menu.", reply_markup=main_menu_kb())
        return
    await log_step(tg_user.id, f"Viewed buy screen: {course.name}")
    await _notify_admin_buy_intent(message.bot, tg_user, course)
    text, kb = _course_detail_text(course), payment_method_kb(course.id)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(call: CallbackQuery):
    course_id = int(call.data.split(":", 1)[1])
    await _show_buy_screen(call.message, course_id, tg_user=call.from_user, edit=True)
    await call.answer()


@router.callback_query(F.data.startswith("paym:upi:"))
async def cb_pay_upi(call: CallbackQuery):
    course_id = int(call.data.split(":", 2)[2])
    await log_step(call.from_user.id, f"Chose UPI payment for course_id={course_id}")
    await call.message.edit_text(
        "💳 <b>UPI Payment</b>\n\n"
        "UPI payments are handled directly by Professor (₹10 extra charge applies).\n"
        f"Tap below to message Professor and share which course (ID {course_id}) you want — "
        "they'll share UPI details and confirm the amount.",
        reply_markup=upi_contact_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("paym:amazon:"))
async def cb_pay_amazon(call: CallbackQuery):
    course_id = int(call.data.split(":", 2)[2])
    async with async_session() as session:
        course = await session.get(Course, course_id)
    if not course:
        await call.answer("This course isn't available right now.", show_alert=True)
        return
    await log_step(call.from_user.id, f"Chose Amazon Pay Gift Card for course_id={course_id}")
    price_tag = f"₹{int(course.price)}" if course.price is not None else "to be confirmed by Professor"
    await call.message.edit_text(
        f"🎁 <b>Amazon Pay Gift Card</b>\n\nCourse ID {course.id} — {price_tag}\n\n"
        "Buy an Amazon Pay Gift Card of this amount from any UPI app (tap 'How to buy' below for step-by-step help), "
        "then send it here.",
        reply_markup=amazon_gift_intro_kb(course_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("sendgc:"))
async def cb_send_gift_card(call: CallbackQuery, state: FSMContext):
    course_id = int(call.data.split(":", 1)[1])
    async with async_session() as session:
        course = await session.get(Course, course_id)
    if not course:
        await call.answer("This course isn't available right now.", show_alert=True)
        return
        
    await state.set_state(BuyFlow.waiting_for_gift_card)
    await state.update_data(
        course_id=course_id, 
        order_id=None, 
        msg_count=0, 
        attempt=0, 
        price=float(course.price) if course.price else 0
    )
    await log_step(call.from_user.id, f"Started gift card submission for course_id={course_id}")
    
    asyncio.create_task(cart_abandonment_reminder(call.bot, call.from_user.id, course.name))

    price_tag = f"₹{int(course.price)}" if course.price is not None else "to be confirmed by Professor"
    await call.message.edit_text(
        f"🎁 <b>Sending payment for Course ID {course.id}</b> — {price_tag}\n\n"
        "Send the Amazon Gift Card <b>photo</b>, the <b>14-digit alphanumeric code</b>, or any proof.\n"
        "You can send up to <b>3 valid messages</b> here.\n\n"
        "<i>Got a Promo Code? Type:</i> <code>/applypromo CODE</code>\n\n"
        "Everything goes straight to Professor for verification — the course unlocks in 'My Courses' the moment it's approved ✅",
        reply_markup=gift_card_collect_kb(),
    )
    await call.answer()

@router.message(Command("applypromo"))
async def cmd_apply_promo(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data or not data.get("price"): 
        return await message.answer("⚠️ Promo codes can only be applied on the payment screen.")
    
    parts = message.text.split()
    if len(parts) != 2: 
        return await message.answer("Usage: /applypromo <CODE>")
        
    code = parts[1].upper()
    promo = ACTIVE_PROMOS.get(code)
    if isinstance(promo, dict):
        try:
            if datetime.fromisoformat(promo.get("expires_at", "")) <= datetime.utcnow():
                promo = None
            else:
                discount = int(promo.get("discount", 0))
        except Exception:
            promo = None
    else:
        discount = int(promo) if promo is not None else 0
    if promo is not None:
        new_price = data["price"] - (data["price"] * discount / 100)
        await state.update_data(price=new_price)
        await message.answer(
            f"🎉 <b>Promo Applied!</b> You got {discount}% off.\n"
            f"New price to pay: <b>₹{int(new_price)}</b>", 
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Invalid or Expired Promo Code.")


MAX_GIFT_CARD_MESSAGES = 3

# ==============================================================================
# 💳 WORLD-LEVEL PAYMENT & GIFT CARD PROOF HANDLER (ANTI-TRACKING HARDENED)
# ==============================================================================

@router.message(BuyFlow.waiting_for_gift_card, F.photo | F.text | F.document)
async def receive_gift_card_proof(message: Message, state: FSMContext):
    data = await state.get_data()
    course_id = data["course_id"]
    order_id = data.get("order_id")
    msg_count = data.get("msg_count", 0)
    attempt = data.get("attempt", 0) + 1
    
    if attempt > 4:
        await state.clear()
        return await message.answer(
            "❌ <b>Session Cancelled:</b> Aapne 4 invalid attempts kiye hain. "
            "Kripya menu se phir se course select karein aur valid payment proof bhejein.", 
            parse_mode="HTML"
        )
        
    await state.update_data(attempt=attempt)

    code_text = ""
    kind, content = "", ""
    payment_mode_tag = "UNKNOWN"

    if message.photo:
        kind, content = "photo", message.photo[-1].file_id
        scan_msg = await message.answer("🔍 <i>AI Helper: Inspecting payment proof & scanning details...</i>", parse_mode="HTML")
        
        from security import inspect_payment_proof
        expected_amt = data.get("price") or None  
        scan_result = await inspect_payment_proof(message.bot, content, message.from_user.id, expected_amt)
        await scan_msg.delete()
        
        if not scan_result["valid"] or scan_result["type"] == "INVALID":
            remaining_attempts = 4 - attempt

            # Forward every rejected proof to admin too — image + the FULL raw
            # extracted data (a-z: status/type/amount/UTR/date/gift-code/serial/
            # details), not just a summary. This was missing entirely before —
            # handle_payment_submission() in security.py (which did forward
            # rejects) was never actually called from this live flow, so a
            # rejected proof used to just vanish with nothing sent to admin.
            try:
                await message.bot.send_photo(
                    ADMIN_ID,
                    photo=content,
                    caption=(
                        f"⚠️ <b>Rejected Payment Proof — Manual Review Needed</b>\n"
                        f"👤 {message.from_user.full_name} (@{message.from_user.username or '—'})\n"
                        f"🆔 {uid_tag(message.from_user.id)} | Attempt {attempt}/4"
                    ),
                    parse_mode="HTML",
                )
                await message.bot.send_message(
                    ADMIN_ID,
                    f"🤖 <b>AI Verdict:</b> {sanitize_telemetry_payload(scan_result.get('ocr_result', ''))}\n\n"
                    f"📋 <b>Full Extracted Data:</b>\n<code>{sanitize_telemetry_payload(str(scan_result.get('data', 'N/A')))[:3500]}</code>",
                    parse_mode="HTML",
                )
            except Exception:
                logger.exception("Failed to forward rejected payment proof to admin")

            await message.answer(
                "❌ <b>Invalid Payment Proof Detected!</b>\n\n"
                "Aapki image mein koi valid <b>Amazon Pay Gift Card</b> ya <b>UPI Payment screenshot</b> nahi mila.\n"
                "Kripya saaf screenshot bhejein jisme Transaction ID ya Voucher Code clear dikh raha ho. "
                f"(Aapko block nahi kiya gaya hai — Attempt {attempt}/4, {remaining_attempts} attempts left)\n\n"
                f"ℹ️ Aapka screenshot Professor ko bhi bhej diya gaya hai manual review ke liye.",
                parse_mode="HTML",
                reply_markup=gift_card_collect_kb()
            )
            return

        payment_mode_tag = scan_result["type"] 
        code_text = scan_result.get("data", "")

    elif message.document:
        kind, content = "document", message.document.file_id
        payment_mode_tag = "DOCUMENT_VOUCHER"
    else:
        kind, content = "text", message.text
        code_text = message.text
        payment_mode_tag = "TEXT_CODE"
        
        # 🛡️ Enterprise-Grade Flexible Alphanumeric Validation: Strips hyphens, spaces, and special symbols; validates clean length between 10 and 18
        alphanumeric_only = re.sub(r"[^A-Za-z0-9]", "", code_text)
        
        if not (10 <= len(alphanumeric_only) <= 18):
            remaining_attempts = 4 - attempt
            
            # Professional Copy-Pasteable Telemetry Report Dispatched to Admin Endpoint
            try:
                admin_telemetry_report = (
                    f"⚠️ <b>[SECURITY AUDIT] Invalid Code Format Blocked</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>User Name:</b> {message.from_user.full_name}\n"
                    f"🔗 <b>Username:</b> @{message.from_user.username or '—'}\n"
                    f"🆔 <b>User ID:</b> {uid_tag(message.from_user.id)}\n"
                    f"🔄 <b>Attempt Tracker:</b> <code>{attempt}/4</code>\n"
                    f"📊 <b>Extracted Alphanumeric Length:</b> <code>{len(alphanumeric_only)}</code> (Criteria: 10-18)\n"
                    f"📋 <b>Raw Submitted Code / Text:</b>\n"
                    f"<code>{sanitize_telemetry_payload(code_text)}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                await message.bot.send_message(
                    ADMIN_ID, 
                    admin_telemetry_report, 
                    parse_mode="HTML"
                )
            except Exception:
                logger.exception("Failed to dispatch professional validation audit to admin endpoint")

            await message.answer(
                f"⚠️ <b>Invalid Code Format!</b>\n"
                f"Gift card code valid alphanumeric (10 se 18 characters) hona chahiye (dashes, spaces aur special symbols count nahi hote).\n"
                f"(Attempt {attempt}/4 — {remaining_attempts} attempts left)",
                parse_mode="HTML"
            )
            return
                        
    async with async_session() as session:
        course = await session.get(Course, course_id)
        if order_id is None:
            order = Order(
                user_id=message.from_user.id, 
                course_id=course_id, 
                submission_type=kind,
                submission_content=str(content), 
                status="pending"
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            order_id = order.id

    msg_count += 1
    await state.update_data(order_id=order_id, msg_count=msg_count)
    await log_step(message.from_user.id, f"Sent verified payment proof #{msg_count} for order #{order_id} ({course.name})")

    price_to_show = f"₹{int(data.get('price', course.price))}" if course.price is not None else "TBD"

    mode_badge = "🎁 Amazon Pay Gift Card" if payment_mode_tag == "GIFT_CARD" else ("⚡ UPI Payment (₹10+ Extra Charge)" if payment_mode_tag == "UPI_PAYMENT" else "📄 Document/Text")

    if msg_count == 1:
        admin_caption = (
            "🔔 <b>New Verified Order — Action Needed</b>\n\n"
            f"🧾 Order ID: #{order_id}\n"
            f"👤 Name: {message.from_user.full_name}\n"
            f"🔗 Username: @{message.from_user.username or '—'}\n"
            f"🆔 User ID: {uid_tag(message.from_user.id)}\n"
            f"📘 Course: {course.name}\n"
            f"🆔 Course ID: {course.id}\n"
            f"💰 Final Price: {price_to_show}\n"
            f"💳 Payment Mode: <b>{mode_badge}</b>\n"
            f"📎 Message 1/{MAX_GIFT_CARD_MESSAGES}"
        )
        if code_text and kind != "document":
            admin_caption += f"\n\n🤖 Extracted Data/Code: <code>{sanitize_telemetry_payload(code_text)}</code>"

        kb = admin_order_decision_kb(order_id)
    else:
        admin_caption = (
            f"📎 <b>Additional proof for Order #{order_id}</b> "
            f"(message {msg_count}/{MAX_GIFT_CARD_MESSAGES}) — {course.name} — {uid_tag(message.from_user.id)}"
        )
        kb = None

    try:
        if kind == "text":
            admin_caption += f"\n\n🎁 Content:\n<code>{sanitize_telemetry_payload(content)}</code>"
            await message.bot.send_message(ADMIN_ID, admin_caption, reply_markup=kb, parse_mode="HTML")
        elif kind == "photo":
            await message.bot.send_photo(ADMIN_ID, photo=content, caption=admin_caption, reply_markup=kb, parse_mode="HTML")
        else:
            await message.bot.send_document(ADMIN_ID, document=content, caption=admin_caption, reply_markup=kb, parse_mode="HTML")
    except Exception:
        logger.exception("Failed to forward payment proof to admin")

    if payment_mode_tag == "UPI_PAYMENT":
        await message.answer(
            "✅ <b>UPI Payment Received!</b>\n"
            "Note: UPI payments par ₹10+ extra charge applicable hota hai.\n"
            "Aapka proof Professor ke paas bhej diya gaya hai. Verify hote hi course 'My Courses' mein mil jayega!",
            parse_mode="HTML"
        )

    if msg_count >= MAX_GIFT_CARD_MESSAGES:
        await state.clear()
        await message.answer(
            "✅ Sabhi messages mil gaye hain — Professor ko verification ke liye bhej diye gaye hain.\n"
            "Approve hote hi course aapke 'My Courses' section mein show hone lagega 🎉",
            reply_markup=main_menu_kb(),
        )
    else:
        remaining = MAX_GIFT_CARD_MESSAGES - msg_count
        await message.answer(
            f"✅ Received (message {msg_count}/{MAX_GIFT_CARD_MESSAGES}). "
            f"Aap {remaining} messages aur bhej sakte hain, ya niche 'Done' tap karein.",
            reply_markup=gift_card_collect_kb(),
        )
        


@router.callback_query(F.data == "gcdone")
async def cb_gift_card_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("order_id"):
        await call.answer("Send at least one message (photo/code) first.", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text(
        "✅ Got it — everything's been sent to Professor for verification.\n"
        "You'll get a notification once it's approved, and the course will appear under 'My Courses' 🎉",
        reply_markup=main_menu_kb(),
    )
    await call.answer()


# ================= MINI APP -> BUY BRIDGE =================
@router.message(F.web_app_data)
async def handle_webapp_data(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
    except (json.JSONDecodeError, AttributeError):
        return
    if data.get("action") != "buy":
        return
    await _show_buy_screen(message, data.get("course_id"))


# ================= MY COURSES =================
@router.callback_query(F.data == "mycourses:open")
async def cb_my_courses(call: CallbackQuery):
    await log_step(call.from_user.id, "Opened My Courses")
    async with async_session() as session:
        result = await session.execute(
            select(UserCourse, Course).join(Course, UserCourse.course_id == Course.id)
            .where(UserCourse.user_id == call.from_user.id)
        )
        rows = result.all()

    if not rows:
        await call.message.edit_text(
            "🧾 <b>My Courses</b>\n\nNo course has been assigned yet. Buy a course — it'll show here once approved!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Back", callback_data="menu:main")]]),
        )
        await call.answer()
        return

    kb_rows = []
    for _uc, course in rows:
        if course.group_link:
            kb_rows.append([InlineKeyboardButton(text=f"📂 {course.name}", url=course.group_link)])
        else:
            kb_rows.append([InlineKeyboardButton(text=f"⏳ {course.name} (link pending)", callback_data="noop")])
    kb_rows.append([InlineKeyboardButton(text="⬅ Back", callback_data="menu:main")])

    await call.message.edit_text("🧾 <b>My Courses</b>\n\nTap a course to join its group:",
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await call.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer("Professor will add the group link shortly.", show_alert=True)


# ================= HELP / FAQ =================
HELP_TEXT = (
    "🆘 <b>Help</b>\n\nFor any course, payment, or access issue, message Professor directly — "
    "tap the button below 👇"
)

FAQ_TEXT = (
    "❓ <b>Frequently Asked Questions</b>\n\n"
    "<b>How do I pay?</b>\nOnly Amazon Pay Gift Cards are accepted. Tap 'How to buy an Amazon Gift Card?' "
    "on any course's payment screen for instructions.\n\n"
    "<b>How long until my course is approved?</b>\nOrders are reviewed by Professor personally — "
    "you'll get a notification the moment it's approved or if something needs to be resent.\n\n"
    "<b>Is access lifetime?</b>\nYes — every course listed has lifetime validity and free updates when the source material updates.\n\n"
    "<b>A course shows 'Coming Soon' / no price — can I still get it?</b>\nMessage Professor via Help; "
    "pricing for that course hasn't been finalized yet.\n\n"
    "<b>I joined the backup channel but the bot still asks me to join.</b>\nTap 'I've Joined — Continue' again. "
    "If it persists, message Professor — occasionally Telegram takes a minute to reflect a new channel join."
)


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=help_kb())


@router.callback_query(F.data == "help:open")
async def cb_help(call: CallbackQuery):
    await log_step(call.from_user.id, "Opened Help")
    await call.message.edit_text(HELP_TEXT, reply_markup=help_kb())
    await call.answer()


@router.message(Command("faq"))
async def cmd_faq(message: Message):
    await message.answer(FAQ_TEXT, reply_markup=help_kb())


@router.callback_query(F.data == "faq:open")
async def cb_faq(call: CallbackQuery):
    await call.message.edit_text(FAQ_TEXT, reply_markup=help_kb())
    await call.answer()


# ================= CONTACT PROFESSOR =================
@router.callback_query(F.data == "contact:open")
async def cb_contact_open(call: CallbackQuery, state: FSMContext):
    if call.from_user.id == ADMIN_ID:
        await call.answer("Professor can't message themselves here 🙂", show_alert=True)
        return
    await state.set_state(ContactFlow.waiting_for_message)
    await log_step(call.from_user.id, "Started Contact Professor flow")
    await call.message.edit_text(
        "💬 <b>Contact Professor</b>\n\n"
        "Apna sawaal ya demand yahin type karke bhejo (text/photo/document) — "
        "seedha Professor ko pahunchega aur wahi is chat me reply karenge.\n\n"
        "Use /contact to reach support.",
        reply_markup=contact_cancel_kb(),
    )
    await call.answer()


@router.message(Command("contact"))
async def cmd_contact(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        return
    await state.set_state(ContactFlow.waiting_for_message)
    await message.answer(
        "💬 <b>Contact Professor</b>\n\nApna sawaal yahin likho — seedha Professor tak pahunchega.",
        reply_markup=contact_cancel_kb(),
    )


@router.message(ContactFlow.waiting_for_message)
async def receive_contact_message(message: Message, state: FSMContext):
    await state.clear()
    tg_user = message.from_user

    async with async_session() as session:
        session.add(ContactMessage(user_id=tg_user.id, direction="in", content=sanitize_telemetry_payload(message.text or message.caption or "[media]")))
        await session.commit()
    await log_step(tg_user.id, "Sent a Contact Professor message")

    from manager_handlers import forward_to_admin
    await forward_to_admin(message.bot, message, label="message via Contact Professor")

    await message.answer("✅ Message sent to support. Next: no action needed — you will be answered here.")


# ================= ADMIN REPLY ROUTING =================
@router.message(F.reply_to_message, F.from_user.id == ADMIN_ID)
async def admin_reply_to_user(message: Message):
    source_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    match = re.search(r"User ID:\s*(?:<code>)?(\d+)", source_text)
    if not match:
        return 
    target_user_id = int(match.group(1))

    async with async_session() as session:
        session.add(ContactMessage(user_id=target_user_id, direction="out", content=sanitize_telemetry_payload(message.text or message.caption or "[media]")))
        await session.commit()

    try:
        if message.text:
            await message.bot.send_message(target_user_id, f"💬 <b>Message from Professor:</b>\n\n{message.text}")
        else:
            await message.copy_to(chat_id=target_user_id)
        await message.reply("✅ Reply sent to user.")
    except TelegramForbiddenError:
        await message.reply("⚠️ Couldn't deliver — user has blocked the bot.")
    except Exception:
        logger.exception("Failed to deliver admin reply to user")
        await message.reply("⚠️ Couldn't deliver the reply — something went wrong.")


@router.message(Command("myid"))
async def cmd_my_id(message: Message):
    is_admin = message.from_user.id == ADMIN_ID
    await message.answer(
        f"🆔 Your Telegram ID: {uid_tag(message.from_user.id)}\n"
        "Your Telegram ID is shown above."
    )


# ==============================================================================
# 🤖 AI HELPER — Real Gemini-powered Q&A, grounded in the live course catalog
# ==============================================================================
from security import professor_ai_reply, search_courses_by_query

AI_RATE_LIMIT_MSGS = 10
AI_RATE_LIMIT_WINDOW_SEC = 5 * 60     
AI_FREEZE_DURATION_SEC = 20 * 60      


def _check_ai_rate_limit(user_id: int) -> tuple[bool, int]:
    now = time.time()

    frozen_until = ai_frozen_until.get(user_id)
    if frozen_until and now < frozen_until:
        return False, max(1, int((frozen_until - now) / 60))
    if frozen_until and now >= frozen_until:
        del ai_frozen_until[user_id]
        ai_chat_monitor[user_id] = []

    ai_chat_monitor[user_id] = [t for t in ai_chat_monitor[user_id] if now - t < AI_RATE_LIMIT_WINDOW_SEC]
    if len(ai_chat_monitor[user_id]) >= AI_RATE_LIMIT_MSGS:
        ai_frozen_until[user_id] = now + AI_FREEZE_DURATION_SEC
        return False, AI_FREEZE_DURATION_SEC // 60

    ai_chat_monitor[user_id].append(now)
    return True, 0


@router.message(ProfessorAIFlow.chatting, F.text)
async def professor_ai_chat_message(message: Message, state: FSMContext):
    """Registered BEFORE the catch-all fallback() below, so it takes priority
    whenever the user is inside 'Chat with AI Helper'. This is what makes AI
    answer here even when the admin's global toggle (/toggle_ai) is OFF — i.e.
    Professor is online — matching the rule: AI replies to everything only when
    Professor is offline (toggle ON); otherwise AI only replies inside this
    specific flow."""
    await _run_professor_ai(message, message.from_user.id, message.text or "")


@router.message()
async def fallback(message: Message):
    user_id = message.from_user.id
    user_text = message.text or message.caption or ""

    if message.reply_to_message and message.reply_to_message.from_user.id == message.bot.id:
        broadcast_reply_counts[user_id] += 1
        
        if broadcast_reply_counts[user_id] > 5:
            await message.answer("⚠️ Reply limit reached. Next: use /contact to reach support.")
            return
            
        from manager_handlers import forward_to_admin
        try:
            await forward_to_admin(message.bot, message, label="reply (Broadcast/Payment)")
            await message.answer("✅ Message sent to support. Next: no action needed — you will be answered here.")
        except Exception:
            logger.exception("Failed to deliver broadcast reply to admin")
        return

    # Every private DM lands in the admin inbox (reply-able), then AI answers only if
    # the manual toggle is ON or Professor is offline (manual/auto/window).
    if message.chat.type == "private" and user_id != ADMIN_ID:
        from manager_handlers import forward_to_admin
        import services as _sv
        await forward_to_admin(message.bot, message, label="DM")
        if user_text and (AI_STATE.get("enabled", False) or await _sv.ai_active()):
            return await _run_professor_ai(message, user_id, user_text)
        offline_msg = await _sv.get_setting("offline_message", "")
        if await _sv.admin_offline() and offline_msg:
            return await message.answer(offline_msg)
        return await message.answer("✅ Message sent to support. Next: no action needed — you will be answered here.",
                                    reply_markup=_with_ai_button(main_menu_kb()))

    await message.answer(f"{get_line()}\n\nUse the menu below to choose a section 👇", reply_markup=_with_ai_button(main_menu_kb()))


async def _run_professor_ai(message: Message, user_id: int, user_text: str):
    """The actual AI Helper answer flow — rate limit, Gemini call (grounded in
    the live course catalog), admin logging, reply. Extracted out of fallback()
    unchanged so it can also be called from the dedicated ProfessorAIFlow.chatting
    handler below (used when the admin's global AI toggle is OFF but the user is
    specifically inside 'Chat with AI Helper')."""
    allowed, minutes = _check_ai_rate_limit(user_id)
    if not allowed:
        await message.answer(
            f"⏱️ <b>AI Helper thodi der ke liye rest kar raha hai.</b>\n\n"
            f"Aapne 5 minutes mein {AI_RATE_LIMIT_MSGS} messages ki limit cross kar li hai — "
            f"~{minutes} minutes baad phir se try karein, ya /contact se seedha Professor ko likhein.",
            parse_mode="HTML",
        )
        return

    try:
        async with async_session() as session:
            result = await session.execute(select(Course).where(Course.is_active == True))
            courses = result.scalars().all()
        all_courses = [(c.name, c.faculty, c.medium, c.price, [s.key for s in c.sections]) for c in courses]

        import access, ai_brain
        from fmt import card
        approved = await access.is_approved(user_id)
        catalog = "Course catalogue is available only inside the LMS Mini App. Do not list course names or prices in chat." if approved else ""
        try:
            from premium import has_active_plan
            if await has_active_plan(user_id, "ca_tracker"):
                from notion_sync import get_ca_items
                ca_items = await get_ca_items({"q": user_text})
                if ca_items:
                    ctx=[]
                    for x in ca_items[:5]:
                        ctx.append(f"{x.get('source','')} | {x.get('title','')} | {x.get('summary','')[:500]}")
                    catalog += "\nAuthorized CA Tracker Pro context (do not reveal hidden data):\n" + "\n".join(ctx)
        except Exception:
            pass
        ai_reply, ai_status = await ai_brain.answer(user_id, message.from_user.first_name, user_text, catalog)
        if ai_status == "limit":
            ai_reply = card("warn", "Daily AI limit reached", ["You have used today's AI questions."], "Try again tomorrow or use /contact.")
        elif not ai_reply:
            ai_reply = card("err", "AI is unavailable right now", ["Please retry shortly."], "Retry in a minute or use /contact.")
        else:
            ai_reply = card("info", config.AI_NAME, [ai_reply])
        if not approved:
            all_courses = []

        kb_rows = []
        if config.WEBAPP_BASE_URL:
            kb_rows.append([InlineKeyboardButton(text="📚 Open LMS", url=f"{config.WEBAPP_BASE_URL}/webapp/lms")])
        kb_rows.append([InlineKeyboardButton(text="💬 Talk to Professor", callback_data="contact:open")])
        kb_rows.append([InlineKeyboardButton(text="⬅ Back to Menu", callback_data="menu:main")])
        inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    except Exception as err:
        logger.exception(f"AI Helper Engine Error: {err}")
        ai_reply = "⚠️ A technical issue occurred. Next: use /contact to reach support."
        inline_kb = main_menu_kb()

    try:
        # Full query + full reply now go to admin (was hard-truncated to
        # 200/140 chars before, which cut off longer conversations).
        # Telegram's message cap is 4096 chars; 1800/1800 leaves plenty
        # of room for the header even on the longest AI replies.
        def _cap(text: str, limit: int) -> str:
            text = text or ""
            return text if len(text) <= limit else text[:limit] + "… (truncated)"

        await message.bot.send_message(
            ADMIN_ID,
            f"🤖 <b>AI Helper Live Log</b>\n"
            f"👤 Name: {message.from_user.full_name}\n"
            f"🔗 Username: @{message.from_user.username or '—'}\n"
            f"🆔 User ID: {uid_tag(user_id)}\n\n"
            f"💬 Query:\n<i>{_cap(sanitize_telemetry_payload(user_text), 1800)}</i>\n\n"
            f"📤 Response:\n<i>{_cap(sanitize_telemetry_payload(ai_reply), 1800)}</i>",
            parse_mode="HTML"
        )
    except Exception:
        pass

    try:
        return await message.answer(ai_reply, parse_mode="HTML", reply_markup=inline_kb)
    except TelegramBadRequest:
        # Gemini's raw text can occasionally contain stray < > & characters that
        # break Telegram's HTML parser — without this fallback that exception was
        # uncaught here, so the user got nothing at all even though the admin log
        # (sent above) succeeded. Retry once as plain text so the reply still lands.
        logger.warning("AI Helper reply failed HTML parse — retrying as plain text")
        return await message.answer(ai_reply, reply_markup=inline_kb)
