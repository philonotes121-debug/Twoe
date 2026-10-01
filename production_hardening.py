"""Production hardening for the single-app Vercel/AioGram LMS.

This module adds controls that are easy to miss in a bot that grew organically:
- admin-side isolation from the public command surface
- privacy-preserving admin command audit
- cross-instance webhook idempotency
- small helpers for safe admin diagnostics
"""
from __future__ import annotations
import re
from aiogram import BaseMiddleware
from sqlalchemy.exc import IntegrityError
from database import async_session, ProcessedUpdate
import config
import services as sv

PUBLIC_USER_COMMANDS = {
    "start","menu","trending","account","referral","study","support","ask","community","ca"
}

class AdminPublicCommandIsolation(BaseMiddleware):
    """Admin may never enter the public user's command handlers by accident.

    Public user commands are silently ignored for the Admin account. Admin
    workflows are available only through the dedicated Admin command surface.
    """
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user and user.id == config.ADMIN_ID:
            text = (getattr(event, "text", "") or "").strip()
            if text.startswith("/"):
                cmd = text[1:].split()[0].split("@")[0].lower()
                if cmd in PUBLIC_USER_COMMANDS:
                    return None
        return await handler(event, data)


class AdminCommandAudit(BaseMiddleware):
    """Log command names, never raw arguments, for Admin accountability."""
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        text = (getattr(event, "text", "") or "").strip()
        if user and user.id == config.ADMIN_ID and text.startswith("/"):
            cmd = re.sub(r"[^a-z0-9_:-]", "", text[1:].split()[0].split("@")[0].lower())
            await sv.log_event("admin_command", user_id=config.ADMIN_ID, meta=cmd[:80])
        return await handler(event, data)


async def claim_update(update_id: int) -> bool:
    """Return True only once per Telegram update_id across Vercel instances."""
    try:
        async with async_session() as s:
            s.add(ProcessedUpdate(update_id=int(update_id)))
            await s.commit()
            return True
    except IntegrityError:
        return False
    except Exception:
        return False


async def release_update(update_id: int) -> None:
    """Release a claimed update if downstream processing failed, allowing Telegram retry."""
    try:
        async with async_session() as s:
            row = (await s.execute(__import__("sqlalchemy").select(ProcessedUpdate).where(ProcessedUpdate.update_id == int(update_id)))).scalars().first()
            if row:
                await s.delete(row)
                await s.commit()
    except Exception:
        pass
