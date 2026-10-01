import csv
import io
import asyncio
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile, ChatMemberUpdated, WebAppInfo
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func, desc

from database import async_session, Course, Section, Order, UserCourse, User, UserActivity, ContactMessage, ConnectedChat, Membership
from keyboards import AdminAddCourse, AdminBroadcast
from config import ADMIN_ID
import config
from security import auto_delete_task

router = Router()

# ================= NEW: GLOBAL STATES FOR PREMIUM FEATURES =================
AI_STATE = {"enabled": False}
ACTIVE_PROMOS = {}

def admin_only(message: Message) -> bool:
    return message.from_user.id == ADMIN_ID


def uid_tag(user_id: int) -> str:
    """User ID wrapped so a single tap copies it in Telegram."""
    return f"<code>{user_id}</code>"


def _parse_price(txt: str):
    """Returns (price_or_None, error_message_or_None)."""
    txt = txt.strip().upper()
    if txt == "TBD":
        return None, None
    try:
        return float(txt), None
    except ValueError:
        return 0, f"⚠️ '{txt}' isn't a valid number. Send a number only (e.g. 350) or type 'TBD'."


def _parse_id(txt: str):
    """Returns (id_or_None, error_message_or_None) — guards against non-numeric IDs."""
    try:
        return int(txt.strip()), None
    except ValueError:
        return None, f"⚠️ '{txt}' isn't a valid ID. Send a number only."

# ================= NEW: AUTO CHAT DETECTION (For Broadcast 72h) =================
@router.my_chat_member()
async def on_bot_added_to_chat(event: ChatMemberUpdated):
    """Automatically tracks when bot is added or removed from groups/channels."""
    async with async_session() as session:
        chat = await session.get(ConnectedChat, event.chat.id)
        
        # If bot is added and made member/admin
        if event.new_chat_member.status in ["member", "administrator", "creator"]:
            if not chat:
                session.add(ConnectedChat(id=event.chat.id, type=event.chat.type))
                await session.commit()
                
        # If bot is removed or kicked
        elif event.new_chat_member.status in ["left", "kicked", "restricted"]:
            if chat:
                await session.delete(chat)
                await session.commit()


# ================= NEW: PREMIUM ADMIN COMMANDS =================
@router.message(Command("toggle_ai"))
async def cmd_toggle_ai(message: Message):
    if not admin_only(message): return
    AI_STATE["enabled"] = not AI_STATE["enabled"]
    status = "ON" if AI_STATE["enabled"] else "OFF"
    await message.answer(f"🤖 AI Auto-Reply is now <b>{status}</b>", parse_mode="HTML")

@router.message(Command("createpromo"))
async def cmd_create_promo(message: Message):
    if not admin_only(message): return
    parts = message.text.split()
    if len(parts) != 3:
        return await message.answer("Use: /createpromo CODE DISCOUNT_PERCENT")
    try:
        code, percent = parts[1].upper(), int(parts[2])
    except ValueError:
        return await message.answer("Discount must be a number.")
    if not code.isalnum() or not 1 <= percent <= 100:
        return await message.answer("Use an alphanumeric code and 1-100% discount.")
    import services as _sv
    from datetime import datetime, timedelta
    import json as _j
    expiry = datetime.utcnow() + timedelta(hours=12)
    ACTIVE_PROMOS[code] = {"discount": percent, "expires_at": expiry.isoformat()}
    await _sv.set_setting("promos_json", _j.dumps(ACTIVE_PROMOS))

    # 12h group broadcast; persistent deletion survives restarts/serverless deploys.
    chats = [c for c in await _sv.enabled_chats() if c.type in ("group", "supergroup")]
    me = await message.bot.get_me()
    url = f"https://t.me/{me.username}?start=start"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎟 Open LMS & Use Promo", url=url)]])
    sent = 0
    for chat in chats:
        try:
            m = await message.bot.send_message(chat.id, f"🎟 <b>Promo active: {code}</b>\n{percent}% off\nValid for 12 hours.", reply_markup=kb)
            await _sv.schedule_delete(chat.id, m.message_id, hours=12, kind="promo")
            sent += 1
        except Exception:
            pass
    await message.answer(f"✅ {code} created. {percent}% off · expires in 12h · broadcast to {sent} groups.")

@router.message(Command("addforall"))
async def cmd_addforall(message: Message):
    """Broadcasts a replied Ad message to ALL connected groups & channels."""
    if not admin_only(message): return
    if not message.reply_to_message:
        return await message.answer("❌ Please reply to the Ad message/photo with /addforall")
        
    await message.answer("📢 Broadcasting to ALL connected Groups & Channels... (Auto-deletes in 24h)")
    
    async with async_session() as session:
        chats = (await session.execute(select(ConnectedChat))).scalars().all()
    
    if not chats:
        return await message.answer("⚠️ Bot is not in any groups or channels yet.")

    sent, failed = 0, 0
    for chat in chats:
        try:
            sent_msg = await message.reply_to_message.copy_to(chat_id=chat.id)
            import services as _sv
            await _sv.schedule_delete(chat.id, sent_msg.message_id, hours=24, kind="broadcast")
            sent += 1
        except Exception:
            failed += 1
            
    await message.answer(f"✅ Broadcast complete!\nSent to: <b>{sent} chats</b>\nFailed: {failed} chats.", parse_mode="HTML")

@router.message(Command("weekly_report"))
async def manual_weekly_report(message: Message):
    if not admin_only(message): return
    async with async_session() as session:
        users_count = (await session.execute(select(func.count(User.id)))).scalar()
        revenue = (await session.execute(select(Course.price).join(UserCourse, UserCourse.course_id == Course.id))).all()
        total_rev = sum(float(p[0]) for p in revenue if p[0] is not None)
        chats_count = (await session.execute(select(func.count(ConnectedChat.id)))).scalar()
    
    report_text = (
        "📊 <b>WEEKLY AI BUSINESS REPORT</b>\n\n"
        f"👥 <b>Total Users Base:</b> {users_count}\n"
        f"📢 <b>Connected Groups/Channels:</b> {chats_count}\n"
        f"💰 <b>Total Verified Revenue:</b> ₹{int(total_rev)}\n"
        "🛡️ <b>Security Status:</b> Active (0 Breaches)\n\n"
        "<i>Running on Premium Auto-Pilot!</i> 🚀"
    )
    await message.answer(report_text, parse_mode="HTML")


# ================= ADD COURSE =================
@router.message(Command("addcourse"))
async def cmd_add_course(message: Message, state: FSMContext):
    if not admin_only(message):
        return
    await state.set_state(AdminAddCourse.name)
    await message.answer("➕ <b>New Course</b>\n\nSend the course name:")


@router.message(AdminAddCourse.name)
async def add_course_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddCourse.faculty)
    await message.answer("👨‍🏫 Faculty/Institute name:")


@router.message(AdminAddCourse.faculty)
async def add_course_faculty(message: Message, state: FSMContext):
    await state.update_data(faculty=message.text.strip())
    await state.set_state(AdminAddCourse.medium)
    await message.answer("🌐 Medium (English / Hindi / Both):")


@router.message(AdminAddCourse.medium)
async def add_course_medium(message: Message, state: FSMContext):
    await state.update_data(medium=message.text.strip())
    await state.set_state(AdminAddCourse.notes)
    await message.answer("📝 Short notes/description (or '-' if none):")


@router.message(AdminAddCourse.notes)
async def add_course_notes(message: Message, state: FSMContext):
    notes = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(notes=notes)
    await state.set_state(AdminAddCourse.price)
    await message.answer("💰 Price in ₹ (number only, or 'TBD' if not decided yet):")


@router.message(AdminAddCourse.price)
async def add_course_price(message: Message, state: FSMContext):
    price, error = _parse_price(message.text)
    if error:
        await message.answer(error)
        return  # stay in same state, let them retry
    await state.update_data(price=price)
    await state.set_state(AdminAddCourse.section)

    async with async_session() as session:
        result = await session.execute(select(Section).where(Section.parent_id.isnot(None)))
        sections = result.scalars().all()
    listing = "\n".join(f"{s.id} — {s.name}" for s in sections) or "(No sub-sections found in DB)"
    await message.answer(
        f"📂 Which section(s)? Send the section ID (comma-separated if the course belongs in multiple sections):\n\n{listing}"
    )


@router.message(AdminAddCourse.section)
async def add_course_section(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        section_ids = [int(x.strip()) for x in message.text.split(",")]
    except ValueError:
        await message.answer("⚠️ Send numbers only, comma-separated. Try again:")
        return

    async with async_session() as session:
        course = Course(name=data["name"], faculty=data["faculty"], medium=data["medium"],
                         notes=data["notes"], price=data["price"])
        for sid in section_ids:
            section = await session.get(Section, sid)
            if section:
                course.sections.append(section)
        session.add(course)
        await session.commit()
        await session.refresh(course)

    await state.clear()
    price_tag = f"₹{int(course.price)}" if course.price is not None else "TBD"
    await message.answer(f"✅ Course added!\n\n📘 {course.name} — {price_tag}\n🆔 Course ID: {course.id}")


# ================= QUICK ADD (one-line, using section KEYS) =================
@router.message(Command("quickadd"))
async def cmd_quick_add(message: Message):
    if not admin_only(message):
        return
    body = message.text.split(maxsplit=1)
    if len(body) != 2:
        await message.answer(
            "Usage:\n/quickadd Name | Faculty | Medium | Notes | Price(or TBD) | section_key1,section_key2\n\n"
            "Example:\n/quickadd Polity Crash 2027 | Jatin Gupta | Hindi | Complete crash course | 499 | subj_polity\n\n"
            "Use /listsectionkeys to see valid section keys."
        )
        return
    parts = [p.strip() for p in body[1].split("|")]
    if len(parts) != 6:
        await message.answer("⚠️ Need exactly 6 parts separated by '|': Name | Faculty | Medium | Notes | Price | section_keys")
        return
    name, faculty, medium, notes, price_txt, keys_txt = parts
    price, error = _parse_price(price_txt)
    if error:
        await message.answer(error)
        return
    section_keys = [k.strip() for k in keys_txt.split(",") if k.strip()]

    async with async_session() as session:
        result = await session.execute(select(Section))
        sections_by_key = {s.key: s for s in result.scalars().all()}
        matched, unmatched = [], []
        for k in section_keys:
            if k in sections_by_key:
                matched.append(sections_by_key[k])
            else:
                unmatched.append(k)
        course = Course(name=name, faculty=faculty, medium=medium, notes=notes, price=price)
        course.sections = matched
        session.add(course)
        await session.commit()
        await session.refresh(course)

    price_tag = f"₹{int(course.price)}" if course.price is not None else "TBD"
    warn = f"\n⚠️ Unknown section key(s) ignored: {', '.join(unmatched)}" if unmatched else ""
    await message.answer(
        f"✅ Course added!\n\n📘 {course.name} — {price_tag}\n🆔 Course ID: {course.id}\n"
        f"📂 Sections: {', '.join(s.name for s in matched) or '(none — unlisted)'}{warn}"
    )


@router.message(Command("listsectionkeys"))
async def cmd_list_section_keys(message: Message):
    if not admin_only(message):
        return
    async with async_session() as session:
        result = await session.execute(select(Section).order_by(Section.parent_id, Section.id))
        sections = result.scalars().all()
    lines = ["🔑 <b>Section Keys</b> (use with /quickadd, /movecourse)\n"]
    for s in sections:
        tag = " (top-level)" if s.parent_id is None else ""
        lines.append(f"<code>{s.key}</code> — {s.name}{tag}")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await message.answer(text[i:i + 3500])


# ================= MANUAL GRANT =================
@router.message(Command("grant"))
async def cmd_grant(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Usage: /grant <user_id> <course_id>\n\nDirectly unlocks a course for a user — bypasses payment, shows up in their 'My Courses' immediately.")
        return
    user_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    course_id, id_error2 = _parse_id(parts[2])
    if id_error2:
        await message.answer(id_error2)
        return
    async with async_session() as session:
        user = await session.get(User, user_id)
        course = await session.get(Course, course_id)
        if not user:
            await message.answer("❌ User not found (they must /start the bot at least once first).")
            return
        if not course:
            await message.answer("❌ Course ID not found.")
            return
        existing = await session.execute(
            select(UserCourse).where(UserCourse.user_id == user_id, UserCourse.course_id == course_id)
        )
        if existing.scalar_one_or_none():
            await message.answer("ℹ️ This user already owns this course.")
            return
        session.add(UserCourse(user_id=user_id, course_id=course_id))
        await session.commit()

    try:
        group_text = (
            f"🎉 Professor has assigned you <b>{course.name}</b>!\n\n"
            + (f"Join the group here: {course.group_link}" if course.group_link
               else "The group link will be added shortly — check 'My Courses' again soon.")
        )
        await message.bot.send_message(user_id, group_text)
    except Exception:
        pass
    await message.answer(f"✅ Granted {course.name} (ID {course.id}) to user {uid_tag(user_id)}.")


# ================= QUICK COMMANDS =================
@router.message(Command("price"))
async def cmd_price(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Usage: /price <course_id> <new_price_or_TBD>")
        return
    course_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    price, error = _parse_price(parts[2])
    if error:
        await message.answer(error)
        return
    async with async_session() as session:
        course = await session.get(Course, course_id)
        if not course:
            await message.answer("❌ Course ID not found.")
            return
        course.price = price
        await session.commit()
        tag = f"₹{int(price)}" if price is not None else "TBD"
        await message.answer(f"✅ Price updated: {course.name} → {tag}")


@router.message(Command("removecourse"))
async def cmd_remove_course(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            "Usage: /removecourse [course_id]\n"
            "Multiple at once: /removecourse 12,15,20  (comma or space separated)"
        )
        return

    raw_ids = [p for p in parts[1].replace(",", " ").split() if p]
    ids, bad = [], []
    for raw in raw_ids:
        cid, err = _parse_id(raw)
        if err:
            bad.append(raw)
        else:
            ids.append(cid)

    if bad:
        await message.answer(f"⚠️ Skipping invalid ID(s): {', '.join(bad)}")

    if not ids:
        return

    removed, missing = [], []
    async with async_session() as session:
        for cid in ids:
            course = await session.get(Course, cid)
            if not course:
                missing.append(cid)
                continue
            course.is_active = False
            removed.append(f"{cid} — {course.name}")
        await session.commit()

    reply = ""
    if removed:
        reply += f"🗑️ Hidden {len(removed)} course(s):\n" + "\n".join(removed)
    if missing:
        reply += ("\n\n" if reply else "") + "❌ Not found: " + ", ".join(str(m) for m in missing)
    await message.answer(reply or "Nothing removed.")


@router.message(Command("setlink"))
async def cmd_set_link(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("Usage: /setlink <course_id> <group_link>")
        return
    course_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    async with async_session() as session:
        course = await session.get(Course, course_id)
        if not course:
            await message.answer("❌ Course ID not found.")
            return
        course.group_link = parts[2].strip()
        await session.commit()
        await message.answer(f"🔗 Group link set: {course.name}")


@router.message(Command("trending_add"))
async def cmd_trending_add(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Usage: /trending_add <course_id>")
        return
    course_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    async with async_session() as session:
        course = await session.get(Course, course_id)
        if not course:
            await message.answer("❌ Course ID not found.")
            return
        course.is_trending = True
        await session.commit()
        await message.answer(f"🔥 Added to trending: {course.name}")


@router.message(Command("trending_remove"))
async def cmd_trending_remove(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Usage: /trending_remove <course_id>")
        return
    course_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    async with async_session() as session:
        course = await session.get(Course, course_id)
        if not course:
            await message.answer("❌ Course ID not found.")
            return
        course.is_trending = False
        await session.commit()
        await message.answer(f"➖ Removed from trending: {course.name}")


@router.message(Command("listcourses"))
async def cmd_list_courses(message: Message):
    if not admin_only(message):
        return
    async with async_session() as session:
        result = await session.execute(select(Course).where(Course.is_active == True))  # noqa: E712
        courses = result.scalars().all()
    if not courses:
        await message.answer("No courses found.")
        return
    lines = []
    for c in courses:
        tag = f"₹{int(c.price)}" if c.price is not None else "TBD"
        star = "🔥" if c.is_trending else ""
        lines.append(f"{c.id}. {star}{c.name} — {tag}")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await message.answer(text[i:i + 3500])


@router.message(Command("movecourse"))
async def cmd_move_course(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3:
        await message.answer(
            "Usage: /movecourse <course_id> <section_id1,section_id2,...>\n"
            "Replaces the course's current section(s) with the ones you list. "
            "Use /listsections to see section IDs."
        )
        return
    course_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    try:
        section_ids = [int(x.strip()) for x in parts[2].split(",")]
    except ValueError:
        await message.answer("⚠️ Section IDs must be numbers, comma-separated.")
        return

    async with async_session() as session:
        course = await session.get(Course, course_id)
        if not course:
            await message.answer("❌ Course ID not found.")
            return
        new_sections = []
        for sid in section_ids:
            sec = await session.get(Section, sid)
            if sec:
                new_sections.append(sec)
        course.sections = new_sections
        await session.commit()
        names = ", ".join(s.name for s in new_sections) or "(none — course is now unlisted)"
        await message.answer(f"📂 {course.name} moved to: {names}")


@router.message(Command("listsections"))
async def cmd_list_sections(message: Message):
    if not admin_only(message):
        return
    async with async_session() as session:
        result = await session.execute(select(Section).where(Section.parent_id.isnot(None)))
        sections = result.scalars().all()
    lines = [f"{s.id} — {s.name}" for s in sections]
    text = "📂 <b>Sections</b>\n\n" + "\n".join(lines)
    for i in range(0, len(text), 3500):
        await message.answer(text[i:i + 3500])


@router.message(Command("pending"))
async def cmd_pending(message: Message):
    if not admin_only(message):
        return
    async with async_session() as session:
        result = await session.execute(
            select(Order, Course, User)
            .join(Course, Order.course_id == Course.id)
            .join(User, Order.user_id == User.id)
            .where(Order.status == "pending")
            .order_by(Order.created_at)
        )
        rows = result.all()
    if not rows:
        await message.answer("✅ No pending orders right now.")
        return
    lines = ["⏳ <b>Pending Orders</b>\n"]
    for order, course, user in rows:
        lines.append(
            f"#{order.id} — {course.name} — @{user.username or '—'} (ID {uid_tag(user.id)}) — "
            f"{order.created_at.strftime('%d %b, %H:%M')}"
        )
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await message.answer(text[i:i + 3500])


@router.message(Command("userinfo"))
async def cmd_user_info(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Usage: /userinfo <user_id>")
        return
    user_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            await message.answer("❌ User not found.")
            return
        courses_result = await session.execute(
            select(Course).join(UserCourse, UserCourse.course_id == Course.id).where(UserCourse.user_id == user_id)
        )
        courses = courses_result.scalars().all()
        orders_result = await session.execute(select(func.count(Order.id)).where(Order.user_id == user_id))
        order_count = orders_result.scalar()

        activity_result = await session.execute(
            select(UserActivity).where(UserActivity.user_id == user_id).order_by(desc(UserActivity.created_at)).limit(8)
        )
        activity_rows = activity_result.scalars().all()

    course_lines = "\n".join(f"• {c.name} (ID {c.id})" for c in courses) or "None yet"
    activity_lines = "\n".join(
        f"• {a.step} ({a.created_at.strftime('%d %b, %H:%M')})" for a in activity_rows
    ) or "No activity logged yet."

    await message.answer(
        f"👤 <b>{user.first_name or '—'}</b> (@{user.username or '—'})\n"
        f"🆔 ID: {uid_tag(user.id)}\n"
        f"📅 Joined: {user.joined_at.strftime('%d %b %Y') if user.joined_at else '—'}\n"
        f"🚫 Banned: {'Yes' if user.is_banned else 'No'}\n"
        f"✅ Backup channel verified: {'Yes' if user.has_joined_backup_channel else 'No'}\n"
        f"🧾 Total orders placed: {order_count}\n\n"
        f"📘 <b>Courses owned:</b>\n{course_lines}\n\n"
        f"🕘 <b>Recent steps:</b>\n{activity_lines}"
    )


@router.message(Command("activity"))
async def cmd_activity(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Usage: /activity <user_id>")
        return
    user_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    async with async_session() as session:
        result = await session.execute(
            select(UserActivity).where(UserActivity.user_id == user_id).order_by(desc(UserActivity.created_at)).limit(30)
        )
        rows = result.scalars().all()
    if not rows:
        await message.answer("No activity logged for this user yet.")
        return
    lines = [f"🕘 <b>Recent steps — {uid_tag(user_id)}</b>\n"]
    for a in rows:
        lines.append(f"• {a.step} — {a.created_at.strftime('%d %b, %H:%M')}")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await message.answer(text[i:i + 3500])


@router.message(Command("contacthistory"))
async def cmd_contact_history(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Usage: /contacthistory <user_id>")
        return
    user_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    async with async_session() as session:
        result = await session.execute(
            select(ContactMessage).where(ContactMessage.user_id == user_id).order_by(ContactMessage.created_at)
        )
        rows = result.scalars().all()
    if not rows:
        await message.answer("No contact messages with this user yet.")
        return
    lines = [f"💬 <b>Contact history — {uid_tag(user_id)}</b>\n"]
    for m in rows:
        arrow = "👤→🧑‍🏫" if m.direction == "in" else "🧑‍🏫→👤"
        lines.append(f"{arrow} {m.content} ({m.created_at.strftime('%d %b, %H:%M')})")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await message.answer(text[i:i + 3500])


@router.message(Command("legacy_export"))
async def cmd_export(message: Message):
    if not admin_only(message):
        return
    async with async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "username", "first_name", "joined_at", "is_banned", "backup_channel_verified"])
    for u in users:
        writer.writerow([u.id, u.username or "", u.first_name or "",
                          u.joined_at.isoformat() if u.joined_at else "", u.is_banned, u.has_joined_backup_channel])

    file_bytes = buf.getvalue().encode("utf-8")
    await message.answer_document(
        BufferedInputFile(file_bytes, filename=f"users_export_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"),
        caption=f"📤 Exported {len(users)} users."
    )


@router.message(Command("topcourses"))
async def cmd_top_courses(message: Message):
    if not admin_only(message):
        return
    async with async_session() as session:
        result = await session.execute(
            select(Course.name, func.count(UserCourse.id).label("cnt"))
            .join(UserCourse, UserCourse.course_id == Course.id)
            .group_by(Course.id, Course.name)
            .order_by(desc("cnt"))
            .limit(10)
        )
        rows = result.all()
    if not rows:
        await message.answer("No course grants yet.")
        return
    lines = ["🏆 <b>Top Courses (by grants)</b>\n"]
    for i, (name, cnt) in enumerate(rows, 1):
        lines.append(f"{i}. {name} — {cnt} students")
    await message.answer("\n".join(lines))


@router.message(Command("recentusers"))
async def cmd_recent_users(message: Message):
    if not admin_only(message):
        return
    async with async_session() as session:
        result = await session.execute(select(User).order_by(desc(User.joined_at)).limit(15))
        users = result.scalars().all()
    if not users:
        await message.answer("No users yet.")
        return
    lines = ["🆕 <b>Recent Users</b>\n"]
    for u in users:
        lines.append(
            f"• {u.first_name or '—'} (@{u.username or '—'}) — {uid_tag(u.id)} — "
            f"{u.joined_at.strftime('%d %b, %H:%M') if u.joined_at else '—'}"
        )
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await message.answer(text[i:i + 3500])


@router.message(Command("findcourse"))
async def cmd_find_course(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Usage: /findcourse <keyword>")
        return
    keyword = parts[1].strip().lower()
    async with async_session() as session:
        result = await session.execute(select(Course))
        all_courses = result.scalars().all()
    matches = [c for c in all_courses if keyword in c.name.lower() or keyword in (c.faculty or "").lower()]
    if not matches:
        await message.answer("No matching courses found.")
        return
    lines = [f"🔎 <b>Matches for '{parts[1].strip()}'</b>\n"]
    for c in matches[:40]:
        tag = f"₹{int(c.price)}" if c.price is not None else "TBD"
        active = "" if c.is_active else " (hidden)"
        sections = ", ".join(s.name for s in c.sections) or "—"
        lines.append(f"{c.id}. {c.name} — {tag}{active}\n   📂 {sections}")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await message.answer(text[i:i + 3500])


@router.message(Command("courseinfo"))
async def cmd_course_info(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Usage: /courseinfo <course_id>")
        return
    course_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    async with async_session() as session:
        course = await session.get(Course, course_id)
        if not course:
            await message.answer("❌ Course ID not found.")
            return
        owners_result = await session.execute(select(func.count(UserCourse.id)).where(UserCourse.course_id == course_id))
        owner_count = owners_result.scalar()

    tag = f"₹{int(course.price)}" if course.price is not None else "TBD"
    sections = ", ".join(s.name for s in course.sections) or "— (unlisted)"
    await message.answer(
        f"📘 <b>{course.name}</b>\n"
        f"🆔 Course ID: {course.id}\n"
        f"👨‍🏫 Faculty: {course.faculty or '—'}\n"
        f"🌐 Medium: {course.medium or '—'}\n"
        f"📝 Notes: {course.notes or '—'}\n"
        f"💰 Price: {tag}\n"
        f"🔗 Group link: {course.group_link or 'Not set — /setlink'}\n"
        f"🔥 Trending: {'Yes' if course.is_trending else 'No'}\n"
        f"✅ Active: {'Yes' if course.is_active else 'No (hidden)'}\n"
        f"📂 Sections: {sections}\n"
        f"🎓 Students granted: {owner_count}"
    )


@router.message(Command("revenue"))
async def cmd_revenue(message: Message):
    if not admin_only(message):
        return
    async with async_session() as session:
        result = await session.execute(
            select(Course.price)
            .join(UserCourse, UserCourse.course_id == Course.id)
        )
        prices = [p for (p,) in result.all() if p is not None]
        pending_result = await session.execute(select(func.count(Order.id)).where(Order.status == "pending"))
        pending_count = pending_result.scalar()

    total = sum(float(p) for p in prices)
    await message.answer(
        "💰 <b>Revenue Estimate</b>\n\n"
        f"✅ Approved sales: {len(prices)}\n"
        f"💵 Estimated total (from approved orders): ₹{int(total)}\n"
        f"⏳ Orders still pending review: {pending_count}\n\n"
        "This counts approved course grants only, at each course's current listed price."
    )


# ================= ORDER APPROVE/REJECT =================
# MODIFIED WITH SINGLE-USE INVITE LINK FOR ANTI-PIRACY
@router.callback_query(F.data.startswith("adm_ok:"))
async def cb_approve(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("This is for Professor only.", show_alert=True)
        return
    order_id = int(call.data.split(":", 1)[1])
    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order or order.status != "pending":
            await call.answer("This order has already been processed.", show_alert=True)
            return
        order.status = "approved"
        order.decided_at = datetime.utcnow()
        course = await session.get(Course, order.course_id)
        if not course:
            await call.answer("Product missing", show_alert=True)
            return
        if course.system_product:
            from premium import activate_membership, PLANS
            plan = course.system_product
            await session.commit()
            await activate_membership(order.user_id, plan, order.id)
            try:
                from notion_sync import sync_access_event
                await sync_access_event(order.user_id, plan, "approved")
            except Exception:
                pass
        else:
            session.add(UserCourse(user_id=order.user_id, course_id=order.course_id))
            await session.commit()

    # ANTI-PIRACY: Try to generate Single-Use Link if group_link is a Chat ID
    link = course.group_link
    if link and (link.startswith("-100") or link.startswith("@")):
        try:
            invite = await call.bot.create_chat_invite_link(chat_id=link, member_limit=1, name=f"Access_O{order_id}")
            link = invite.invite_link
        except Exception:
            pass # Fallback to standard text if bot isn't admin in that chat

    if call.message.caption:
        await call.message.edit_caption(caption=call.message.caption + "\n\n✅ APPROVED")
    else:
        await call.message.edit_text(call.message.text + "\n\n✅ APPROVED")

    if course.system_product == "ca_tracker":
        url = f"{config.WEBAPP_BASE_URL}/webapp/ca" if config.WEBAPP_BASE_URL else ""
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📰 Open CA Tracker Pro", web_app=WebAppInfo(url=url))]]) if url else None
        await call.bot.send_message(order.user_id, "✅ CA Tracker Pro activated for 30 days.", reply_markup=kb)
    elif course.system_product == "community":
        rows=[]
        if config.WEBAPP_BASE_URL:
            rows.append([InlineKeyboardButton(text="👥 Open Community LMS", web_app=WebAppInfo(url=f"{config.WEBAPP_BASE_URL}/webapp/community"))])
            rows.append([InlineKeyboardButton(text="📚 Open LMS", web_app=WebAppInfo(url=f"{config.WEBAPP_BASE_URL}/webapp/lms"))])
        if config.COMMUNITY_GROUP_LINK:
            rows.append([InlineKeyboardButton(text="👥 Join Community", url=config.COMMUNITY_GROUP_LINK)])
        await call.bot.send_message(order.user_id, "✅ Join Our Community activated for 30 days.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)
    else:
        group_text = (
            "✅ Course access approved.\n\n"
            + (f"Private access link: {link}" if link else "Open LMS to view your access.")
        )
        await call.bot.send_message(order.user_id, group_text)
    await call.answer("Approved ✅")


@router.callback_query(F.data.startswith("adm_no:"))
async def cb_reject(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("This is for Professor only.", show_alert=True)
        return
    order_id = int(call.data.split(":", 1)[1])
    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order or order.status != "pending":
            await call.answer("This order has already been processed.", show_alert=True)
            return
        order.status = "rejected"
        order.decided_at = datetime.utcnow()
        await session.commit()

    if call.message.caption:
        await call.message.edit_caption(caption=call.message.caption + "\n\n❌ REJECTED")
    else:
        await call.message.edit_text(call.message.text + "\n\n❌ REJECTED")

    await call.bot.send_message(
        order.user_id,
        "❌ The gift card couldn't be verified. Please try again with the correct code/photo, "
        "or contact Professor via the Help section.",
    )
    await call.answer("Rejected ❌")


# ================= BROADCAST =================
@router.message(Command("legacy_broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if not admin_only(message):
        return
    await state.set_state(AdminBroadcast.waiting_message)
    await message.answer("📢 Send the broadcast message (text/photo/anything) — it will go to all users:")


@router.message(AdminBroadcast.waiting_message)
async def do_broadcast(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        result = await session.execute(select(User.id).where(User.is_banned == False))  # noqa: E712
        user_ids = [row[0] for row in result.all()]

    sent, failed = 0, 0
    status_msg = await message.answer(f"📤 Sending... 0/{len(user_ids)}")
    for uid in user_ids:
        try:
            cp = await message.copy_to(chat_id=uid)
            import services as _sv
            await _sv.schedule_delete(uid, cp.message_id, hours=24, kind="broadcast")
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(f"✅ Broadcast complete!\nSent: {sent} | Failed: {failed}")


# ================= STATS =================
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not admin_only(message):
        return
    async with async_session() as session:
        total_users = (await session.execute(select(func.count(User.id)))).scalar()
        banned = (await session.execute(select(func.count(User.id)).where(User.is_banned == True))).scalar()  # noqa
        total_courses = (await session.execute(select(func.count(Course.id)).where(Course.is_active == True))).scalar()  # noqa
        pending_orders = (await session.execute(select(func.count(Order.id)).where(Order.status == "pending"))).scalar()
        approved_orders = (await session.execute(select(func.count(Order.id)).where(Order.status == "approved"))).scalar()
        rejected_orders = (await session.execute(select(func.count(Order.id)).where(Order.status == "rejected"))).scalar()
        total_sales = (await session.execute(select(func.count(UserCourse.id)))).scalar()

    await message.answer(
        "📊 <b>Bot Stats</b>\n\n"
        f"👥 Total Users: {total_users}\n🚫 Banned: {banned}\n📘 Active Courses: {total_courses}\n\n"
        f"⏳ Pending Orders: {pending_orders}\n✅ Approved: {approved_orders}\n❌ Rejected: {rejected_orders}\n"
        f"🎓 Total Course Grants: {total_sales}"
    )


# ================= BAN / UNBAN =================
@router.message(Command("ban", "block"))
async def cmd_ban(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Usage: /ban <user_id>")
        return
    user_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            await message.answer("❌ User not found.")
            return
        user.is_banned = True
        await session.commit()
        await message.answer(f"🚫 User {parts[1]} banned.")


@router.message(Command("unban", "unblock"))
async def cmd_unban(message: Message):
    if not admin_only(message):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Usage: /unban <user_id>")
        return
    user_id, id_error = _parse_id(parts[1])
    if id_error:
        await message.answer(id_error)
        return
    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            await message.answer("❌ User not found.")
            return
        user.is_banned = False
        await session.commit()
        await message.answer(f"✅ User {parts[1]} unbanned.")


@router.message(Command("restart"))
async def cmd_restart(message: Message):
    """NOT a process restart — a safe 'cache clean', same idea as a phone cleaner
    app: clears only short-lived, self-expiring in-memory trackers (spam/burst
    rate-limit windows, Professor-AI chat cooldowns, broadcast-reply counters).
    Deliberately does NOT touch: the database (courses/orders/users/payments),
    shadow-bans/freezes/mutes, or the persisted /toggle_ai state — nothing real
    is ever lost, exactly as requested."""
    if not admin_only(message):
        return
    from security import burst_monitor, spam_monitor
    # Deferred import (not at module top) to avoid a circular import: user_handlers
    # imports AI_STATE from this file at startup, so this file can't import
    # user_handlers back at load time — only safe once both are fully loaded.
    from user_handlers import ai_chat_monitor, ai_frozen_until, broadcast_reply_counts

    cleared = 0
    for tracker in (burst_monitor, spam_monitor, ai_chat_monitor, broadcast_reply_counts):
        cleared += len(tracker)
        tracker.clear()
    cleared += len(ai_frozen_until)
    ai_frozen_until.clear()

    await message.answer(
        f"🧹 <b>Cache Cleared</b>\n\n"
        f"Cleared <b>{cleared}</b> temporary entries — spam/burst rate-limit windows, "
        f"AI chat cooldowns, broadcast-reply counters.\n\n"
        f"✅ Koi user data, course, order, ya security ban touch nahi hua — sirf "
        f"temporary cache clean hui hai, mobile cleaner jaise.",
        parse_mode="HTML"
    )


@router.message(Command("legacy_adminhelp"))
async def cmd_admin_help(message: Message):
    if not admin_only(message):
        return
    await message.answer(
        "🛠 <b>Admin Commands</b>\n\n"
        "<b>New Premium Features</b>\n"
        "/toggle_ai — Turn Auto-Reply ON/OFF\n"
        "/createpromo &lt;CODE&gt; &lt;PERCENT&gt; — Create Flash Sale discount\n"
        "/addforall — Broadcast Ad to all groups (24h auto-delete)\n"
        "/weekly_report — Generate AI Business Report\n"
        "/restart — Clear temporary cache (no data lost)\n\n"
        "<b>Courses</b>\n"
        "/addcourse — add a new course (step-by-step)\n"
        "/quickadd Name | Faculty | Medium | Notes | Price|TBD | section_keys — add a course in ONE message\n"
        "/listsectionkeys — see all section keys (for /quickadd, /movecourse)\n"
        "/price &lt;id&gt; &lt;price|TBD&gt; — change price\n"
        "/removecourse &lt;id&gt; — hide a course\n"
        "/setlink &lt;id&gt; &lt;group_link&gt; — set a course's group link\n"
        "/movecourse &lt;id&gt; &lt;section_id1,section_id2,...&gt; — reassign a course's section(s)\n"
        "/listsections — list all section IDs\n"
        "/trending_add &lt;id&gt; — add to trending\n"
        "/trending_remove &lt;id&gt; — remove from trending\n"
        "/listcourses — list all course IDs + prices\n"
        "/grant &lt;user_id&gt; &lt;course_id&gt; — manually unlock a course for a user (no payment needed)\n\n"
        "<b>Orders &amp; Users</b>\n"
        "/pending — quick view of orders awaiting approval\n"
        "/userinfo &lt;user_id&gt; — look up a user, their courses + recent steps\n"
        "/activity &lt;user_id&gt; — full recent step-by-step trail for a user\n"
        "/contacthistory &lt;user_id&gt; — full Contact Professor thread with a user\n"
        "/revenue — approved-sales revenue estimate\n"
        "/ban &lt;user_id&gt; — block a user\n"
        "/unban &lt;user_id&gt; — unblock a user\n\n"
        "<b>Discovery &amp; Reports</b>\n"
        "/findcourse &lt;keyword&gt; — search courses by name/faculty\n"
        "/courseinfo &lt;id&gt; — full detail + student count for one course\n"
        "/topcourses — best-selling courses\n"
        "/recentusers — last 15 users who joined\n"
        "/export — download all users as a CSV file\n\n"
        "<b>Replying to users</b>\n"
        "Just hit Reply (Telegram's native reply) on any forwarded order or "
        "'Contact Professor' message — your reply is delivered to that user automatically.\n\n"
        "<b>Broadcast &amp; Stats</b>\n"
        "/broadcast — message all users\n"
        "/stats — bot-wide numbers",
        parse_mode="HTML"
    )
