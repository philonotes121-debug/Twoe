"""
Shared services used by every module.

- settings (DB backed + cache)          - persistent auto-delete queue (survives restarts)
- growth keyboard on every bot message  - backup-channel membership check
- admin activity / offline detection    - admin notifications with quiet digest (no spam)
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, delete, func

import config
from database import (
    async_session, User, Setting, ScheduledDeletion, EventLog, DigestItem, ConnectedChat, CronFence,
)

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.utcnow()


# =============================== settings ===============================
_cache: dict[str, str] = {}


async def get_setting(key: str, default: str = "") -> str:
    if key in _cache:
        return _cache[key]
    async with async_session() as s:
        row = await s.get(Setting, key)
    val = row.value if row and row.value is not None else default
    if row:
        _cache[key] = val
    return val


async def set_setting(key: str, value) -> None:
    value = str(value)
    async with async_session() as s:
        row = await s.get(Setting, key)
        if row:
            row.value = value
        else:
            s.add(Setting(key=key, value=value))
        await s.commit()
    _cache[key] = value


async def get_int(key: str, default: int) -> int:
    try:
        return int(await get_setting(key, str(default)))
    except ValueError:
        return default


async def load_runtime_settings() -> None:
    """Applies admin-edited values (backup link) over the env defaults at startup."""
    link = await get_setting("backup_link", "")
    if link:
        config.BACKUP_CHANNEL = link


# =============================== bot / keyboards ===============================
_bot_username = ""


async def bot_username(bot: Bot) -> str:
    global _bot_username
    if not _bot_username:
        _bot_username = (await bot.get_me()).username or ""
    return _bot_username


async def growth_kb(bot: Bot, extra: Optional[list] = None, *, refer: bool = True, open_bot: bool = True) -> InlineKeyboardMarkup:
    """Inline buttons attached to EVERY message the bot sends outside a menu:
    backup-channel join (editable link) + open bot + refer & earn."""
    uname = await bot_username(bot)
    rows = [list(r) for r in (extra or [])]
    rows.append([InlineKeyboardButton(text="📢 Backup Channel Join करें", url=config.backup_link())])
    second = []
    if open_bot and uname:
        second.append(InlineKeyboardButton(text="🤖 Courses & AI Helper", url=f"https://t.me/{uname}?start=start"))
    if refer and uname:
        second.append(InlineKeyboardButton(text="🎁 Refer & Earn", url=f"https://t.me/{uname}?start=refer"))
    if second:
        rows.append(second)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def custom_rows(lines: str) -> list:
    """'Text | https://link' per line -> keyboard rows (invalid lines ignored)."""
    rows = []
    for line in (lines or "").splitlines():
        if "|" not in line:
            continue
        label, url = [p.strip() for p in line.split("|", 1)]
        if label and url.startswith(("http://", "https://", "tg://")):
            rows.append([InlineKeyboardButton(text=label[:60], url=url)])
    return rows


# =============================== persistent auto-delete ===============================
async def schedule_delete(chat_id: int, message_id: int, *, hours: float = 0, minutes: float = 0, kind: str = "misc") -> None:
    when = utcnow() + timedelta(hours=hours, minutes=minutes)
    try:
        async with async_session() as s:
            s.add(ScheduledDeletion(chat_id=chat_id, message_id=message_id, delete_after=when, kind=kind))
            await s.commit()
    except Exception:  # noqa: BLE001
        logger.exception("schedule_delete failed")


async def send_temp(bot: Bot, chat_id: int, text: str, *, minutes: float = 0, hours: float = 0,
                    kb: Optional[InlineKeyboardMarkup] = None, kind: str = "temp", **kw):
    m = await bot.send_message(chat_id, text, reply_markup=kb, **kw)
    await schedule_delete(chat_id, m.message_id, hours=hours, minutes=minutes, kind=kind)
    return m


async def run_deletions(bot: Bot, limit: int = 150) -> int:
    """Called every minute by the scheduler. Rows survive restarts because they live in the DB."""
    done = 0
    async with async_session() as s:
        rows = (await s.execute(
            select(ScheduledDeletion).where(ScheduledDeletion.delete_after <= utcnow())
            .order_by(ScheduledDeletion.delete_after).limit(limit)
        )).scalars().all()
        for r in rows:
            try:
                await bot.delete_message(r.chat_id, r.message_id)
            except TelegramRetryAfter as exc:
                await asyncio.sleep(min(exc.retry_after, 20))
                continue                      # keep row, retry next minute
            except Exception:                 # already deleted / no rights / chat gone
                pass
            await s.delete(r)
            done += 1
        await s.commit()
    return done


# =============================== events / analytics ===============================
_msg_counter: dict[int, int] = {}


def bump_activity(chat_id: int) -> None:
    _msg_counter[chat_id] = _msg_counter.get(chat_id, 0) + 1


async def flush_activity() -> None:
    if not _msg_counter:
        return
    snap = dict(_msg_counter)
    _msg_counter.clear()
    async with async_session() as s:
        for chat_id, n in snap.items():
            s.add(EventLog(kind="msgs", chat_id=chat_id, n=n))
        await s.commit()


async def log_event(kind: str, chat_id: Optional[int] = None, user_id: Optional[int] = None, meta: str = "", n: int = 1) -> None:
    try:
        async with async_session() as s:
            s.add(EventLog(kind=kind, chat_id=chat_id, user_id=user_id, meta=meta[:500], n=n))
            await s.commit()
    except Exception:  # noqa: BLE001
        logger.exception("log_event failed")


# =============================== users ===============================
async def ensure_user(tg_user) -> User:
    async with async_session() as s:
        u = await s.get(User, tg_user.id)
        if u is None:
            u = User(id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name)
            s.add(u)
        else:
            u.username = tg_user.username
            u.first_name = tg_user.first_name
        u.last_seen = utcnow()
        await s.commit()
        await s.refresh(u)
        return u


async def ensure_user_by_id(user_id: int):
    async with async_session() as s:
        return await s.get(User, user_id)

# =============================== backup channel ===============================
_alerted: dict[str, float] = {}


async def alert_once(bot: Bot, key: str, text: str, every_hours: float = 6) -> None:
    if time.time() - _alerted.get(key, 0) < every_hours * 3600:
        return
    _alerted[key] = time.time()
    await notify_admin(bot, text, urgent=True)


async def backup_status(bot: Bot, user_id: int) -> Optional[bool]:
    """True = joined, False = definitely not joined, None = could not check (bot not admin etc.)."""
    ref = config.backup_chat_ref()
    if not ref:
        return None
    try:
        m = await bot.get_chat_member(chat_id=ref, user_id=user_id)
        if m.status in ("member", "administrator", "creator"):
            return True
        if m.status == "restricted":
            return bool(getattr(m, "is_member", False))
        return False                      # left / kicked
    except TelegramBadRequest as exc:
        low = str(exc).lower()
        if "participant_id_invalid" in low or "user not found" in low:
            return False
        await alert_once(bot, "backup_check", (
            "⚠️ <b>Backup channel check fail ho raha hai</b>\n"
            f"Reason: <code>{str(exc)[:200]}</code>\n\n"
            "Bot ko backup channel me <b>Admin</b> banayein, warna mandatory-join verify nahi ho paata."))
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("backup_status error: %s", exc)
        return None


# =============================== admin presence / offline detection ===============================
_admin_last_seen = time.time()


def touch_admin() -> None:
    global _admin_last_seen
    _admin_last_seen = time.time()


async def mark_admin_seen() -> None:
    global _admin_last_seen
    _admin_last_seen = time.time()
    try:
        await set_setting("admin_last_seen", str(_admin_last_seen))
    except Exception:
        pass


def _in_window(window: str) -> bool:
    """'23:30-06:00' in IST."""
    try:
        a, b = window.split("-")
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(config.TIMEZONE))
        cur = now.hour * 60 + now.minute
        s = int(a[:2]) * 60 + int(a[3:5])
        e = int(b[:2]) * 60 + int(b[3:5])
        return (s <= cur < e) if s <= e else (cur >= s or cur < e)
    except Exception:  # noqa: BLE001
        return False


async def admin_offline() -> bool:
    """Telegram does not expose a person's presence to bots, so 'offline' means:
    manual /offline on, OR (auto mode) no admin activity in the bot for N minutes, OR quiet-hours window."""
    mode = await get_setting("offline_mode", "auto")
    if mode == "on":
        return True
    if mode == "off":
        return False
    idle_min = await get_int("offline_idle_min", 20)
    persisted = await get_setting("admin_last_seen", "")
    try:
        last = max(_admin_last_seen, float(persisted or 0))
    except Exception:
        last = _admin_last_seen
    if time.time() - last > idle_min * 60:
        return True
    window = await get_setting("offline_hours", "")
    return bool(window) and _in_window(window)


async def ai_active() -> bool:
    if (await get_setting("ai_enabled", "1")) != "1":
        return False
    return await admin_offline()


# =============================== notifications (no spam) ===============================
async def notify_admin(bot: Bot, text: str, *, urgent: bool = False, kind: str = "info",
                       kb: Optional[InlineKeyboardMarkup] = None) -> None:
    """urgent (DMs, payments, errors): instant WITH sound.
    everything else: queued into a silent digest (or sent instantly-silent if /notify instant)."""
    mode = await get_setting("notify_mode", "digest")
    try:
        if urgent:
            await bot.send_message(config.ADMIN_ID, text, reply_markup=kb, disable_web_page_preview=True)
        elif mode == "instant":
            await bot.send_message(config.ADMIN_ID, text, reply_markup=kb, disable_notification=True,
                                   disable_web_page_preview=True)
        else:
            async with async_session() as s:
                s.add(DigestItem(kind=kind, text=text[:600]))
                await s.commit()
    except Exception:  # noqa: BLE001
        logger.exception("notify_admin failed")


async def flush_digest(bot: Bot) -> bool:
    mode = await get_setting("notify_mode", "digest")
    async with async_session() as s:
        if mode == "quiet":
            await s.execute(delete(DigestItem).where(DigestItem.created_at < utcnow() - timedelta(days=2)))
            await s.commit()
            return False
        items = (await s.execute(select(DigestItem).where(DigestItem.sent == False).order_by(DigestItem.id).limit(400))).scalars().all()  # noqa: E712
        if not items:
            return False
        lines = [i.text for i in items]
        shown = lines[:25]
        more = len(lines) - len(shown)
        text = "🗒 <b>Activity digest</b> (silent)\n\n" + "\n".join(shown)
        if more > 0:
            text += f"\n… aur {more} events — /dashboard me poora summary."
        try:
            await bot.send_message(config.ADMIN_ID, text[:4000], disable_notification=True, disable_web_page_preview=True)
        except Exception:  # noqa: BLE001
            logger.exception("digest send failed")
            return False
        for i in items:
            i.sent = True
        await s.commit()
        await s.execute(delete(DigestItem).where(DigestItem.sent == True, DigestItem.created_at < utcnow() - timedelta(days=1)))  # noqa: E712
        await s.commit()
    return True


# =============================== chats ===============================
async def enabled_chats(flag: Optional[str] = None) -> list[ConnectedChat]:
    async with async_session() as s:
        q = select(ConnectedChat).where(ConnectedChat.enabled == True)  # noqa: E712
        if flag:
            q = q.where(getattr(ConnectedChat, flag) == True)  # noqa: E712
        return list((await s.execute(q)).scalars().all())


async def count_users() -> int:
    async with async_session() as s:
        return (await s.execute(select(func.count(User.id)))).scalar() or 0

# =============================== per-chat command scopes ===============================
async def set_user_commands(bot: Bot, user_id: int, *, verified: bool) -> None:
    """Show only a compact User menu; Admin gets a separate menu in main.py."""
    from aiogram.types import BotCommand, BotCommandScopeChat
    cmds = [
        BotCommand(command="start", description="Verify & open LMS"),
        BotCommand(command="menu", description="Open LMS"),
        BotCommand(command="trending", description="Trending (private chat)"),
        BotCommand(command="account", description="Account, access & orders"),
        BotCommand(command="referral", description="Referral & rewards"),
        BotCommand(command="study", description="Target, streak & reminders"),
        BotCommand(command="support", description="Support & doubt"),
        BotCommand(command="ask", description="AI Helper"),
        BotCommand(command="community", description="Join Our Community ₹800/month"),
        BotCommand(command="ca", description="CA Tracker Pro ₹200/month"),
    ] if verified else [BotCommand(command="start", description="Verify mobile & open LMS")]
    try:
        await bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=user_id))
    except Exception:
        logger.exception("set_user_commands failed")


def admin_activity_touch_sync() -> None:
    """Compatibility no-op; persistent heartbeat is written by the Admin middleware."""
    return None


# =============================== production fences ===============================
async def claim_fence(fence_key: str, marker: str, *, keep_days: int = 60) -> bool:
    """Cross-instance idempotency fence backed by the DB. Returns True only for first claimant."""
    from sqlalchemy.exc import IntegrityError
    try:
        async with async_session() as s:
            s.add(CronFence(fence_key=fence_key[:160], marker=str(marker)[:80]))
            await s.commit()
            await s.execute(delete(CronFence).where(CronFence.created_at < utcnow() - timedelta(days=keep_days)))
            await s.commit()
        return True
    except IntegrityError:
        return False
    except Exception:
        logger.exception("claim_fence failed: %s", fence_key)
        return False


async def set_runtime_heartbeat(kind: str) -> None:
    await set_setting(f"heartbeat:{kind}", utcnow().isoformat())


async def get_runtime_heartbeat(kind: str) -> str:
    return await get_setting(f"heartbeat:{kind}", "")
