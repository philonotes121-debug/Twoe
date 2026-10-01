"""
manager_handlers.py — everything from upsc_manager.py, ported to the shared DB.

Inbox (info-card + forwarded copy, BOTH mapped -> fixes "Inbox item नहीं मिला"),
chat registry, campaign broadcasts with delete, offline/AI controls, feature toggles,
products, analytics (2D/3D), exports, group service-message cleanup + welcome.
Admin-only commands are gated by ADMIN_ID.
"""
import asyncio
import csv
import io
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Message, CallbackQuery, ChatMemberUpdated, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from sqlalchemy import select, func, delete

import config
from config import ADMIN_ID
from fmt import card
from database import (
    async_session, User, ContactMessage, ConnectedChat, InboxItem,
    BroadcastCampaign, BroadcastMessage, ScheduledDeletion, EventLog,
)
import ai
import services as sv

logger = logging.getLogger(__name__)
router = Router()

IS_ADMIN = F.from_user.id == ADMIN_ID
PRIVATE = F.chat.type == "private"
GROUP = F.chat.type.in_({"group", "supergroup"})


def esc(t: str) -> str:
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ============================================================================
# INBOX  (user -> admin).  Both admin-side messages are mapped to the user.
# ============================================================================
def inbox_kb(item_id: int, user_id: int, blocked: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Reply", callback_data=f"ib:reply:{item_id}"),
         InlineKeyboardButton(text="✅ Done", callback_data=f"ib:done:{item_id}")],
        [InlineKeyboardButton(text="🔓 Unblock" if blocked else "🚫 Block",
                              callback_data=f"ib:{'unblock' if blocked else 'block'}:{user_id}"),
         InlineKeyboardButton(text="🗑 Delete Source", callback_data=f"ib:del:{item_id}")],
    ])


async def forward_to_admin(bot: Bot, message: Message, *, label: str = "DM") -> None:
    """Send admin an info card AND a copy of the original. Admin can reply to either."""
    u = message.from_user
    async with async_session() as s:
        row = await s.get(User, u.id)
        blocked = bool(row and row.is_banned)
    body = esc(message.text or message.caption or "")
    card = (
        f"📩 <b>New {label}</b>\n\n"
        f"👤 Name: {esc(u.full_name)}\n🔗 Username: @{u.username or '—'}\n"
        f"🆔 User ID: <code>{u.id}</code>\n"
        + (f"\n💬 {body[:1500]}" if body else "")
        + "\n\n↩️ <i>Is message (ya neeche wali copy) par Reply karo — user tak pahunch jayega.</i>"
    )
    ids = []
    try:
        card_msg = await bot.send_message(ADMIN_ID, card)
        ids.append(card_msg.message_id)
        if not message.text:  # media: also copy the original
            cp = await message.copy_to(ADMIN_ID)
            ids.append(cp.message_id)
    except Exception:
        logger.exception("forward_to_admin failed")
        return
    async with async_session() as s:
        first_item = None
        for mid in ids:
            it = InboxItem(admin_message_id=mid, source_chat_id=message.chat.id,
                           source_message_id=message.message_id, user_id=u.id)
            s.add(it)
            if first_item is None:
                first_item = it
        await s.commit()
        await s.refresh(first_item)
        item_id = first_item.id
    try:
        await bot.edit_message_reply_markup(ADMIN_ID, ids[0], reply_markup=inbox_kb(item_id, u.id, blocked))
    except Exception:
        pass
    await sv.log_event("dm", user_id=u.id)


@router.message(IS_ADMIN, PRIVATE, F.reply_to_message)
async def admin_reply(message: Message):
    sv.touch_admin()
    rid = message.reply_to_message.message_id
    async with async_session() as s:
        it = (await s.execute(select(InboxItem).where(InboxItem.admin_message_id == rid)
                              .order_by(InboxItem.id.desc()))).scalars().first()
    user_id = it.user_id if it else None
    if not user_id:  # fallback: parse "User ID" from the replied text (older cards)
        src = message.reply_to_message.text or message.reply_to_message.caption or ""
        m = re.search(r"User ID:\s*(?:<code>)?(\d+)", src)
        user_id = int(m.group(1)) if m else None
    if not user_id:
        raise SkipHandler  # not an inbox reply — let other handlers see it
    try:
        if message.text:
            sent = await message.bot.send_message(user_id, card("info", "Support reply", [esc(message.text)], "Reply here if you need more help.", raw=True),
                                                  reply_markup=await sv.growth_kb(message.bot))
        else:
            sent = await message.copy_to(user_id, reply_markup=await sv.growth_kb(message.bot))
        await sv.schedule_delete(user_id, sent.message_id, hours=config.DEL_PERSONAL_HOURS, kind="dm")
        async with async_session() as s:
            s.add(ContactMessage(user_id=user_id, direction="out", content=(message.text or "[media]")[:1000]))
            await s.commit()
        import features
        await features.mark_answered(user_id)
        await message.reply("🟢 Delivered.")
    except Exception as e:  # noqa: BLE001
        await message.reply(f"🔴 Not delivered: {str(e)[:120]}")


@router.callback_query(IS_ADMIN, F.data.startswith("ib:"))
async def inbox_actions(call: CallbackQuery):
    _, action, arg = call.data.split(":", 2)
    arg = int(arg)
    if action == "reply":
        await call.answer("Is message par swipe-Reply karke jawab likho.", show_alert=True)
        return
    if action in ("block", "unblock"):
        async with async_session() as s:
            u = await s.get(User, arg)
            if u:
                u.is_banned = action == "block"
                await s.commit()
        await call.answer("Blocked" if action == "block" else "Unblocked")
        try:
            async with async_session() as s:
                it = (await s.execute(select(InboxItem).where(InboxItem.user_id == arg)
                                      .order_by(InboxItem.id.desc()))).scalars().first()
            await call.message.edit_reply_markup(reply_markup=inbox_kb(it.id if it else 0, arg, action == "block"))
        except Exception:
            pass
        return
    async with async_session() as s:
        it = await s.get(InboxItem, arg)
        if not it:
            await call.answer("Item nahi mila (purana ho sakta hai).", show_alert=True)
            return
        if action == "done":
            it.resolved = True
            await s.commit()
            await call.answer("Marked done")
            try:
                await call.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        elif action == "del":
            try:
                await call.bot.delete_message(it.source_chat_id, it.source_message_id)
                await call.answer("Source message delete ho gaya")
            except Exception:
                await call.answer("Delete nahi ho paya (48h se purana / permission nahi).", show_alert=True)


# ============================================================================
# GROUPS: activity count, watch, service-message cleanup, welcome, join/leave
# ============================================================================
@router.message(GROUP, F.new_chat_members)
async def on_new_members(message: Message):
    bot = message.bot
    try:
        await message.delete()
    except Exception:
        pass
    for m in message.new_chat_members:
        if m.is_bot:
            continue
        await sv.log_event("join", chat_id=message.chat.id, user_id=m.id)
        line = (await ai.welcome_line(m.first_name)) or "Swagat hai — roz thoda, par roz padhna."
        custom = await sv.get_setting("welcome_text", "")
        text = (custom.replace("{name}", esc(m.first_name)) if custom
                else f"👋 <b>{esc(m.first_name)}</b>, welcome!\n<i>{esc(line)}</i>")
        try:
            await sv.send_temp(bot, message.chat.id, text, minutes=config.DEL_WELCOME_MIN,
                               kb=await sv.growth_kb(bot), kind="welcome")
        except Exception:
            pass
        await sv.notify_admin(bot, f"➕ {esc(m.full_name)} joined {esc(message.chat.title or '')}", kind="join")


@router.message(GROUP, F.left_chat_member)
async def on_left_member(message: Message):
    try:
        await message.delete()
    except Exception:
        pass
    m = message.left_chat_member
    await sv.log_event("leave", chat_id=message.chat.id, user_id=m.id)
    await sv.notify_admin(message.bot, f"➖ {esc(m.full_name)} left {esc(message.chat.title or '')}", kind="leave")


@router.chat_member()
async def on_chat_member(ev: ChatMemberUpdated):
    """Channels (no service messages): join/leave via chat_member updates."""
    if ev.chat.type != "channel":
        return
    old, new = ev.old_chat_member.status, ev.new_chat_member.status
    u = ev.new_chat_member.user
    if old in ("left", "kicked") and new == "member":
        await sv.log_event("join", chat_id=ev.chat.id, user_id=u.id)
        await sv.notify_admin(ev.bot, f"➕ {esc(u.full_name)} joined channel {esc(ev.chat.title or '')}", kind="join")
    elif old in ("member", "restricted") and new in ("left", "kicked"):
        await sv.log_event("leave", chat_id=ev.chat.id, user_id=u.id)
        await sv.notify_admin(ev.bot, f"➖ {esc(u.full_name)} left channel {esc(ev.chat.title or '')}", kind="leave")


@router.message(GROUP)
async def group_watch(message: Message):
    sv.bump_activity(message.chat.id)
    async with async_session() as s:
        ch = await s.get(ConnectedChat, message.chat.id)
    if ch and ch.watch and message.from_user and message.from_user.id != ADMIN_ID:
        try:
            await sv.notify_admin(message.bot, f"👁 <b>{esc(message.chat.title or '')}</b> — {esc(message.from_user.full_name)}: "
                                               f"{esc((message.text or message.caption or '[media]')[:300])}", kind="watch")
        except Exception:
            pass
    raise SkipHandler  # never swallow group messages


# ============================================================================
# CHAT REGISTRY
# ============================================================================
async def _upsert_chat(chat) -> ConnectedChat:
    async with async_session() as s:
        row = await s.get(ConnectedChat, chat.id)
        if not row:
            row = ConnectedChat(id=chat.id, type=chat.type)
            s.add(row)
        row.title = chat.title or row.title
        row.username = chat.username or row.username
        await s.commit()
        await s.refresh(row)
        return row


@router.message(Command("register_chat"), IS_ADMIN, GROUP)
async def register_chat(message: Message):
    await _upsert_chat(message.chat)
    await message.reply(f"✅ Registered: {esc(message.chat.title or '')} (<code>{message.chat.id}</code>)")


@router.message(Command("addchat", "add_channel"), IS_ADMIN)
async def addchat(message: Message, command: CommandObject):
    ref = (command.args or "").strip()
    if not ref:
        return await message.answer("Use: /addchat -100123… ya @channelusername")
    try:
        chat = await message.bot.get_chat(int(ref) if re.fullmatch(r"-?\d+", ref) else ref)
    except Exception as e:  # noqa: BLE001
        return await message.answer(f"❌ Chat nahi mili (bot ko pehle add karo): {esc(str(e))[:120]}")
    await _upsert_chat(chat)
    await message.answer(f"✅ Added: {esc(chat.title or '')} (<code>{chat.id}</code>)")


@router.message(Command("chats", "channel_list"), IS_ADMIN)
async def chats_cmd(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(ConnectedChat).order_by(ConnectedChat.added_at))).scalars().all()
    if not rows:
        return await message.answer("Koi chat connected nahi.")
    out = ["📋 <b>Connected chats</b>"]
    for c in rows:
        t = c.title
        if not t:
            try:
                t = (await message.bot.get_chat(c.id)).title
                async with async_session() as s:
                    r = await s.get(ConnectedChat, c.id)
                    r.title = t
                    await s.commit()
            except Exception:
                t = "?"
        flags = "".join(k for k, v in (("🌅", c.morning_on), ("🌙", c.night_on), ("⏳", c.countdown_on),
                                       ("🧠", c.quiz_on), ("👁", c.watch)) if v)
        out.append(f"{'🟢' if c.enabled else '🔴'} {esc(t)} — <code>{c.id}</code> {flags}")
    await message.answer("\n".join(out)[:4000])


async def _chat_set(message: Message, command: CommandObject, **vals):
    try:
        cid = int((command.args or "").split()[0])
    except Exception:
        return await message.answer("Chat ID do: /" + command.command + " -100123…")
    async with async_session() as s:
        row = await s.get(ConnectedChat, cid)
        if not row:
            return await message.answer("Ye chat registered nahi hai.")
        for k, v in vals.items():
            setattr(row, k, v)
        await s.commit()
    await message.answer("✅ Done.")


@router.message(Command("disablechat", "remove_channel"), IS_ADMIN)
async def disablechat(message: Message, command: CommandObject):
    await _chat_set(message, command, enabled=False)


@router.message(Command("enablechat"), IS_ADMIN)
async def enablechat(message: Message, command: CommandObject):
    await _chat_set(message, command, enabled=True)


@router.message(Command("watch"), IS_ADMIN)
async def watch_cmd(message: Message, command: CommandObject):
    await _chat_set(message, command, watch=True)


@router.message(Command("unwatch"), IS_ADMIN)
async def unwatch_cmd(message: Message, command: CommandObject):
    await _chat_set(message, command, watch=False)


@router.message(Command("chatflag"), IS_ADMIN)
async def chatflag(message: Message, command: CommandObject):
    a = (command.args or "").split()
    if len(a) != 3 or a[1] not in ("morning_on", "night_on", "countdown_on", "quiz_on") or a[2] not in ("on", "off"):
        return await message.answer("Use: /chatflag CHAT_ID morning_on|night_on|countdown_on|quiz_on on|off")
    await _chat_set(message, CommandObject(command="chatflag", args=a[0]), **{a[1]: a[2] == "on"})


# ============================================================================
# BROADCAST CAMPAIGNS (groups/channels) — deletable as a whole
# ============================================================================
async def _campaign_send(message: Message, chat_ids: list[int], label: str) -> str:
    src = message.reply_to_message
    if not src:
        return "❌ Pehle jo message bhejna hai use Reply karke command likho."
    bot = message.bot
    kb = await sv.growth_kb(bot)
    async with async_session() as s:
        camp = BroadcastCampaign(label=label[:200], target=f"{len(chat_ids)} chats")
        s.add(camp)
        await s.commit()
        await s.refresh(camp)
    ok = fail = 0
    for cid in chat_ids:
        try:
            m = await src.copy_to(cid, reply_markup=kb)
            async with async_session() as s:
                s.add(BroadcastMessage(campaign_id=camp.id, chat_id=cid, message_id=m.message_id))
                await s.commit()
            await sv.schedule_delete(cid, m.message_id, hours=config.DEL_BROADCAST_HOURS, kind="broadcast")
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.06)
    async with async_session() as s:
        c = await s.get(BroadcastCampaign, camp.id)
        c.sent, c.failed = ok, fail
        await s.commit()
    return (f"📢 Campaign <b>#{camp.id}</b>: ✅ {ok} sent, ❌ {fail} failed\n"
            f"Auto-delete: {config.DEL_BROADCAST_HOURS}h • Delete now: /delete_broadcast {camp.id}")


@router.message(Command("broadcast_all"), IS_ADMIN)
async def broadcast_all(message: Message):
    ids = [c.id for c in await sv.enabled_chats()]
    await message.answer(await _campaign_send(message, ids, "all chats"))


@router.message(Command("broadcast_selected"), IS_ADMIN)
async def broadcast_selected(message: Message, command: CommandObject):
    ids = [int(x) for x in re.findall(r"-?\d+", command.args or "")]
    if not ids:
        return await message.answer("Use (reply karke): /broadcast_selected -100111 -100222")
    await message.answer(await _campaign_send(message, ids, "selected"))


async def _delete_campaign(bot: Bot, cid: int) -> tuple[int, int]:
    async with async_session() as s:
        msgs = (await s.execute(select(BroadcastMessage).where(BroadcastMessage.campaign_id == cid))).scalars().all()
    ok = 0
    for m in msgs:
        try:
            await bot.delete_message(m.chat_id, m.message_id)
            ok += 1
        except Exception:
            pass
    async with async_session() as s:
        await s.execute(delete(BroadcastMessage).where(BroadcastMessage.campaign_id == cid))
        c = await s.get(BroadcastCampaign, cid)
        if c:
            c.deleted_at = datetime.utcnow()
        await s.commit()
    return ok, len(msgs)


@router.message(Command("delete_broadcast"), IS_ADMIN)
async def delete_broadcast(message: Message, command: CommandObject):
    try:
        cid = int((command.args or "").strip())
    except Exception:
        return await message.answer("Use: /delete_broadcast CAMPAIGN_ID")
    ok, tot = await _delete_campaign(message.bot, cid)
    await message.answer(f"🗑 Campaign #{cid}: {ok}/{tot} messages delete hue.")


@router.message(Command("delete_all_broadcasts"), IS_ADMIN)
async def delete_all_broadcasts(message: Message):
    async with async_session() as s:
        ids = (await s.execute(select(BroadcastCampaign.id).where(BroadcastCampaign.deleted_at.is_(None)))).scalars().all()
    total = 0
    for i in ids:
        total += (await _delete_campaign(message.bot, i))[0]
    await message.answer(f"🗑 {len(ids)} campaigns, {total} messages delete hue.")


@router.message(Command("broadcast_history"), IS_ADMIN)
async def broadcast_history(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(BroadcastCampaign).order_by(BroadcastCampaign.id.desc()).limit(15))).scalars().all()
    if not rows:
        return await message.answer("Abhi tak koi broadcast nahi.")
    await message.answer("📜 <b>Broadcast history</b>\n" + "\n".join(
        f"#{r.id} • {r.created_at:%d %b %H:%M} • ✅{r.sent} ❌{r.failed} • {r.target}{' • 🗑' if r.deleted_at else ''}" for r in rows))


# ============================================================================
# SETTINGS / TOGGLES / OFFLINE
# ============================================================================
@router.message(Command("offline"), IS_ADMIN)
async def offline_cmd(message: Message, command: CommandObject):
    v = (command.args or "").strip().lower()
    if v not in ("on", "off", "auto"):
        cur = await sv.get_setting("offline_mode", "auto")
        return await message.answer(f"Offline mode: <b>{cur}</b>\nUse: /offline on|off|auto\n"
                                    "on = AI hamesha reply • off = sirf Professor • auto = idle/window par AI")
    await sv.set_setting("offline_mode", v)
    await message.answer(f"✅ Offline mode → <b>{v}</b>")


@router.message(Command("set_offline_hours"), IS_ADMIN)
async def set_offline_hours(message: Message, command: CommandObject):
    v = (command.args or "").strip()
    if v.lower() in ("off", "none", ""):
        await sv.set_setting("offline_hours", "")
        return await message.answer("✅ Offline window hata di.")
    if not re.fullmatch(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}", v):
        return await message.answer("Use: /set_offline_hours 23:00-07:00  (IST) ya off")
    await sv.set_setting("offline_hours", v)
    await message.answer(f"✅ Offline window: {v}")


def _text_setting(cmd: str, key: str, hint: str):
    @router.message(Command(cmd), IS_ADMIN)
    async def _h(message: Message, command: CommandObject):
        val = (command.args or "").strip()
        if not val and message.reply_to_message:
            val = message.reply_to_message.text or ""
        if not val:
            return await message.answer(f"Use: /{cmd} <text>\n{hint}")
        await sv.set_setting(key, val)
        await message.answer("✅ Saved.")
    return _h


_text_setting("set_welcome", "welcome_text", "{name} = member ka naam")
_text_setting("set_offline_message", "offline_message", "AI unavailable hone par ye message jayega")
_text_setting("set_credit", "credit", "Footer credit text")


@router.message(Command("set_backup", "set_backup_link"), IS_ADMIN)
async def set_backup(message: Message, command: CommandObject):
    v = (command.args or "").strip()
    if not v:
        return await message.answer(f"Current: {config.backup_link()}\nUse: /set_backup https://t.me/xyz")
    config.BACKUP_CHANNEL = v
    await sv.set_setting("backup_channel", v)
    await message.answer(f"✅ Backup link → {esc(config.backup_link())}")


@router.message(Command("set_exam_date"), IS_ADMIN)
async def set_exam_date(message: Message, command: CommandObject):
    v = (command.args or "").strip()
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except Exception:
        return await message.answer("Use: /set_exam_date 2027-05-24")
    await sv.set_setting("exam_date", v)
    await message.answer(f"✅ Exam date → {v}")


for _name, _key in (("morning", "morning_on"), ("night", "night_on"),
                    ("countdown", "countdown_on"), ("quiz", "quiz_on")):
    for _state in ("on", "off"):
        def _mk(name=_name, key=_key, state=_state):
            @router.message(Command(f"{name}_{state}"), IS_ADMIN)
            async def _h(message: Message):
                await sv.set_setting(key, "1" if state == "on" else "0")
                await message.answer(f"✅ {name} → {state.upper()}")
            return _h
        _mk()


@router.message(Command("notify"), IS_ADMIN)
async def notify_cmd(message: Message, command: CommandObject):
    v = (command.args or "").strip().lower()
    if v not in ("digest", "instant", "quiet"):
        return await message.answer("Use: /notify digest|instant|quiet\nDMs/payments hamesha turant aate hain.")
    await sv.set_setting("notify_mode", v)
    await message.answer(f"✅ Notify → {v}")


# ============================================================================
# PRODUCTS / LEADS
# ============================================================================
async def _products() -> list[dict]:
    try:
        return json.loads(await sv.get_setting("products", "[]"))
    except Exception:
        return []


@router.message(Command("product_add"), IS_ADMIN)
async def product_add(message: Message, command: CommandObject):
    parts = [p.strip() for p in (command.args or "").split("|")]
    if len(parts) < 3:
        return await message.answer("Use: /product_add Name|Price|Link|Description")
    items = await _products()
    items.append({"name": parts[0], "price": parts[1], "link": parts[2], "desc": parts[3] if len(parts) > 3 else ""})
    await sv.set_setting("products", json.dumps(items, ensure_ascii=False))
    await message.answer(f"✅ Product #{len(items)} added.")


@router.message(Command("product_remove"), IS_ADMIN)
async def product_remove(message: Message, command: CommandObject):
    items = await _products()
    try:
        items.pop(int((command.args or "").strip()) - 1)
    except Exception:
        return await message.answer("Use: /product_remove NUMBER")
    await sv.set_setting("products", json.dumps(items, ensure_ascii=False))
    await message.answer("✅ Removed.")


@router.message(Command("products"), IS_ADMIN)
async def products_cmd(message: Message):
    items = await _products()
    if not items:
        return await message.answer("Koi product nahi. /product_add Name|Price|Link|Description")
    await message.answer("🛍 <b>Products</b>\n\n" + "\n\n".join(
        f"{i}. <b>{esc(p['name'])}</b> — {esc(p['price'])}\n{esc(p['desc'])}\n{esc(p['link'])}" for i, p in enumerate(items, 1))[:3900],
        disable_web_page_preview=True)


@router.message(Command("leads"), IS_ADMIN)
async def leads(message: Message):
    async with async_session() as s:
        rows = (await s.execute(
            select(ContactMessage.user_id, func.count(ContactMessage.id), func.max(ContactMessage.created_at))
            .where(ContactMessage.direction == "in").group_by(ContactMessage.user_id)
            .order_by(func.max(ContactMessage.created_at).desc()).limit(20))).all()
    if not rows:
        return await message.answer("Abhi koi lead nahi.")
    await message.answer("🎯 <b>Recent leads</b> (jinhone Professor ko likha)\n" + "\n".join(
        f"<code>{u}</code> • {n} msg • {t:%d %b %H:%M}" for u, n, t in rows))


# ============================================================================
# ANALYTICS / DASHBOARD / EXPORTS / CLEANUP
# ============================================================================
async def _series(days: int):
    since = datetime.utcnow() - timedelta(days=days)
    labels = [(datetime.utcnow() - timedelta(days=i)).date() for i in range(days - 1, -1, -1)]
    data = {k: defaultdict(int) for k in ("join", "leave", "msgs", "dm")}
    async with async_session() as s:
        rows = (await s.execute(select(EventLog).where(EventLog.created_at >= since))).scalars().all()
        for r in rows:
            if r.kind in data:
                data[r.kind][r.created_at.date()] += r.n or 1
        users = (await s.execute(select(User.joined_at).where(User.joined_at >= since))).scalars().all()
    new_users = defaultdict(int)
    for j in users:
        new_users[j.date()] += 1
    return labels, data, new_users


def _render(labels, data, new_users, three_d: bool) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    series = [("New users", [new_users[d] for d in labels], "#2563eb"),
              ("Joins", [data["join"][d] for d in labels], "#16a34a"),
              ("Leaves", [data["leave"][d] for d in labels], "#dc2626"),
              ("DMs", [data["dm"][d] for d in labels], "#9333ea")]
    xs = list(range(len(labels)))
    ticks = [d.strftime("%d %b") for d in labels]
    fig = plt.figure(figsize=(9, 5))
    if three_d:
        ax = fig.add_subplot(111, projection="3d")
        for i, (name, vals, col) in enumerate(series):
            ax.bar(xs, vals, zs=i, zdir="y", color=col, alpha=0.85, width=0.6)
        ax.set_yticks(range(len(series)))
        ax.set_yticklabels([s[0] for s in series], fontsize=7)
        ax.set_xticks(xs[:: max(1, len(xs) // 7)])
        ax.set_xticklabels(ticks[:: max(1, len(xs) // 7)], fontsize=7, rotation=30)
    else:
        ax = fig.add_subplot(111)
        for name, vals, col in series:
            ax.plot(xs, vals, marker="o", label=name, color=col)
        ax.set_xticks(xs[:: max(1, len(xs) // 8)])
        ax.set_xticklabels(ticks[:: max(1, len(xs) // 8)], rotation=30, fontsize=8)
        ax.legend()
        ax.grid(alpha=0.3)
    ax.set_title(f"AI Helper Analytics — last {len(labels)} days")
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()


async def _analytics(message: Message, command: CommandObject, three_d: bool):
    try:
        days = max(3, min(90, int((command.args or "7").strip())))
    except Exception:
        days = 7
    labels, data, new_users = await _series(days)
    png = await asyncio.to_thread(_render, labels, data, new_users, three_d)
    cap = (f"📊 {days} din • New users {sum(new_users.values())} • Joins {sum(data['join'].values())} • "
           f"Leaves {sum(data['leave'].values())} • DMs {sum(data['dm'].values())}")
    await message.answer_photo(BufferedInputFile(png, "analytics.png"), caption=cap)


@router.message(Command("analytics"), IS_ADMIN)
async def analytics_cmd(message: Message, command: CommandObject):
    await _analytics(message, command, False)


@router.message(Command("analytics3d"), IS_ADMIN)
async def analytics3d_cmd(message: Message, command: CommandObject):
    await _analytics(message, command, True)


@router.message(Command("dashboard"), IS_ADMIN)
async def dashboard(message: Message):
    async with async_session() as s:
        users = (await s.execute(select(func.count(User.id)))).scalar() or 0
        today = (await s.execute(select(func.count(User.id)).where(User.joined_at >= datetime.utcnow() - timedelta(days=1)))).scalar() or 0
        chats = (await s.execute(select(func.count(ConnectedChat.id)))).scalar() or 0
        open_items = (await s.execute(select(func.count(InboxItem.id)).where(InboxItem.resolved == False))).scalar() or 0  # noqa: E712
        pend_del = (await s.execute(select(func.count(ScheduledDeletion.id)))).scalar() or 0
    mode = await sv.get_setting("offline_mode", "auto")
    off = await sv.admin_offline()
    await message.answer(
        f"📈 <b>Dashboard</b>\n👥 Users: {users} (+{today} 24h)\n💬 Chats: {chats}\n"
        f"📥 Open inbox: {open_items}\n🗑 Pending deletions: {pend_del}\n"
        f"🤖 AI: {'ACTIVE (admin offline)' if off else 'standby'} • mode {mode}\n"
        f"🧠 Gemini: {'ok' if ai.available() else 'no key'} • model {ai.last_model() or '-'}")


@router.message(Command("health", "health_check"), IS_ADMIN)
async def health(message: Message):
    ok_db = True
    try:
        async with async_session() as s:
            await s.execute(select(1))
    except Exception:
        ok_db = False
    bk = await sv.backup_status(message.bot, ADMIN_ID)
    await message.answer(f"🩺 DB: {'✅' if ok_db else '❌'} • Gemini: {'✅' if ai.available() else '❌'} "
                         f"({esc(ai.last_error() or 'ok')[:80]}) • Backup check: {bk}")


async def _csv(rows, header) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


@router.message(Command("export_users"), IS_ADMIN)
async def export_users(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(User).order_by(User.joined_at))).scalars().all()
    data = await _csv([(u.id, u.username, u.first_name, u.joined_at, u.is_banned, u.phone, u.ref_points)
                       for u in rows], ["id", "username", "name", "joined", "banned", "phone", "ref_points"])
    await message.answer_document(BufferedInputFile(data, "users.csv"), caption=f"👥 {len(rows)} users")


@router.message(Command("export_messages"), IS_ADMIN)
async def export_messages(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(ContactMessage).order_by(ContactMessage.id))).scalars().all()
    data = await _csv([(m.created_at, m.user_id, m.direction, m.content) for m in rows],
                      ["time", "user_id", "direction", "text"])
    await message.answer_document(BufferedInputFile(data, "messages.csv"), caption=f"💬 {len(rows)} messages")


@router.message(Command("delete_user_chat", "clear_chat"), IS_ADMIN)
async def delete_user_chat(message: Message, command: CommandObject):
    try:
        uid = int((command.args or "").strip())
    except Exception:
        return await message.answer("Use: /delete_user_chat USER_ID")
    async with async_session() as s:
        rows = (await s.execute(select(ScheduledDeletion).where(ScheduledDeletion.chat_id == uid))).scalars().all()
    ok = 0
    for r in rows:
        try:
            await message.bot.delete_message(r.chat_id, r.message_id)
            ok += 1
        except Exception:
            pass
    async with async_session() as s:
        await s.execute(delete(ScheduledDeletion).where(ScheduledDeletion.chat_id == uid))
        await s.commit()
    await message.answer(f"🗑 {ok}/{len(rows)} tracked bot messages delete hue (user {uid}).")


@router.message(Command("delete_chat_message"), IS_ADMIN)
async def delete_chat_message(message: Message, command: CommandObject):
    a = (command.args or "").split()
    try:
        await message.bot.delete_message(int(a[0]), int(a[1]))
        await message.answer("🗑 Deleted.")
    except Exception as e:  # noqa: BLE001
        await message.answer(f"❌ {esc(str(e))[:150]}\nUse: /delete_chat_message CHAT_ID MESSAGE_ID")


@router.message(Command("pending_inbox"), IS_ADMIN)
async def pending_inbox(message: Message):
    async with async_session() as s:
        rows = (await s.execute(select(InboxItem).where(InboxItem.resolved == False)  # noqa: E712
                                .order_by(InboxItem.id.desc()).limit(15))).scalars().all()
    if not rows:
        return await message.answer("✅ Inbox khaali hai.")
    await message.answer("📥 <b>Open inbox</b>\n" + "\n".join(
        f"#{r.id} • <code>{r.user_id}</code> • {r.created_at:%d %b %H:%M}" for r in rows))


@router.message(Command("set_online"), IS_ADMIN)
async def set_online(message: Message):
    await sv.set_setting("offline_mode", "off")
    await message.answer(card("ok", "Online", ["AI replies are OFF; only you answer."], "Use /offline auto to re-enable AI."))


@router.message(Command("set_offline"), IS_ADMIN)
async def set_offline(message: Message):
    await sv.set_setting("offline_mode", "on")
    await message.answer(card("warn", "Offline", ["AI answers every DM."], "Use /set_online when you return."))
