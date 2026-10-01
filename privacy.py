"""Owner / host privacy + anti-tracking helpers.

What this can and cannot do (honest scope):
 * Users never see admin username/ID, host, IP or stack details; all contact is relayed by the bot.
 * Telegram never learns the owner's device: the bot talks to Telegram from the server, not from the owner's phone.
 * A VPN cannot be installed *inside* a bot. OUTBOUND_PROXY routes the server's own outbound traffic
   (Telegram API + Gemini) through a proxy/VPN gateway you control, so the hosting IP is not exposed either.
"""
import hashlib
import hmac
import json
import logging
import os
import re
import time
from urllib.parse import parse_qsl

import config

# ------------------------------------------------------------------ webhook secret
def webhook_secret() -> str:
    """Stable secret derived from the bot token: Telegram sends it back in a header on every update,
    so forged POSTs to /webhook from anyone else are rejected."""
    return hashlib.sha256(("aisha-wh|" + config.BOT_TOKEN).encode()).hexdigest()[:48]


def valid_webhook_header(value: str | None) -> bool:
    return bool(value) and hmac.compare_digest(value, webhook_secret())


# ------------------------------------------------------------------ Mini App auth
def verify_init_data(init_data: str, max_age: int = 86400) -> int | None:
    """Validate Telegram WebApp initData (HMAC per Telegram docs). Returns user id or None."""
    try:
        pairs = dict(parse_qsl(init_data or "", keep_blank_values=True))
        got = pairs.pop("hash", None)
        if not got:
            return None
        check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, got):
            return None
        if time.time() - int(pairs.get("auth_date", 0)) > max_age:
            return None
        return int(json.loads(pairs["user"])["id"])
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ log scrubbing
class ScrubFilter(logging.Filter):
    """Removes bot token, API keys, admin id/username and raw IPs from every log line."""
    def __init__(self):
        super().__init__()
        secrets = [config.BOT_TOKEN, config.GEMINI_API_KEY, str(config.ADMIN_ID), config.ADMIN_USERNAME]
        self._plain = [s for s in secrets if s and len(s) >= 5]
        self._ip = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")

    def _clean(self, s: str) -> str:
        for p in self._plain:
            s = s.replace(p, "[hidden]")
        return self._ip.sub("[ip]", s)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = self._clean(record.getMessage())
            record.args = ()
        except Exception:  # noqa: BLE001
            pass
        return True


def install_log_scrubber():
    f = ScrubFilter()
    for h in logging.getLogger().handlers:
        h.addFilter(f)
    logging.getLogger().addFilter(f)


# ------------------------------------------------------------------ outbound proxy (VPN gateway)
def outbound_proxy() -> str:
    return os.environ.get("OUTBOUND_PROXY", "").strip()


def apply_outbound_proxy_env():
    p = outbound_proxy()
    if p:
        os.environ.setdefault("HTTPS_PROXY", p)   # picked up by the Gemini client (httpx)
        os.environ.setdefault("HTTP_PROXY", p)


def make_session():
    """aiogram session that sends all Telegram API calls through OUTBOUND_PROXY when set."""
    from aiogram.client.session.aiohttp import AiohttpSession
    p = outbound_proxy()
    return AiohttpSession(proxy=p) if p else AiohttpSession()


# ------------------------------------------------------------------ sensitive-message protection
def protect_session_middleware(session):
    """Marks messages carrying invite/join links as protect_content (no forward / save)."""
    from aiogram.client.session.middlewares.base import BaseRequestMiddleware
    from aiogram.methods import SendMessage

    class _Protect(BaseRequestMiddleware):
        _uname = None
        async def __call__(self, make_request, bot, method):
            if isinstance(method, SendMessage):
                if method.text and re.search(r"t\.me/(\+|joinchat)", method.text):
                    method.protect_content = True
                # Every user-facing plain message gets at least one inline action; Admin messages keep their own controls.
                try:
                    chat_id = int(method.chat_id)
                except Exception:
                    chat_id = 0
                if chat_id and chat_id != config.ADMIN_ID and method.reply_markup is None:
                    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
                    rows=[]
                    if config.WEBAPP_BASE_URL and chat_id > 0:
                        rows.append([InlineKeyboardButton(text="📚 Open LMS", web_app=WebAppInfo(url=f"{config.WEBAPP_BASE_URL}/webapp/lms"))])
                    else:
                        if self._uname is None:
                            try: self._uname=(await bot.get_me()).username or ""
                            except Exception: self._uname=""
                        if self._uname:
                            rows.append([InlineKeyboardButton(text="🤖 Open Official Bot", url=f"https://t.me/{self._uname}?start=start")])
                    if rows: method.reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
            return await make_request(bot, method)

    session.middleware(_Protect())

# ------------------------------------------------------------------ one-way personal-data fingerprint
def personal_data_hmac(value: str | None) -> str:
    """One-way HMAC for duplicate/abuse checks; never reversible and never logged."""
    raw = (value or "").strip()
    key = (os.environ.get("PERSONAL_DATA_HMAC_KEY") or config.DATA_ENCRYPTION_KEY or config.BOT_TOKEN).encode()
    return hmac.new(key, raw.encode(), hashlib.sha256).hexdigest() if raw else ""


# ------------------------------------------------------------------ encrypted personal data
_FERNET = None

def _fernet():
    global _FERNET
    if _FERNET is None:
        if not config.DATA_ENCRYPTION_KEY:
            return None
        try:
            from cryptography.fernet import Fernet
            _FERNET = Fernet(config.DATA_ENCRYPTION_KEY.encode())
        except Exception:
            return None
    return _FERNET


def encrypt_secret_value(value: str | None) -> str | None:
    if not value:
        return None
    f = _fernet()
    if not f:
        raise RuntimeError("DATA_ENCRYPTION_KEY is required for personal-data encryption")
    return f.encrypt(value.encode()).decode()


def decrypt_secret_value(value: str | None) -> str:
    if not value:
        return ""
    f = _fernet()
    if not f:
        return ""
    try:
        return f.decrypt(value.encode()).decode()
    except Exception:
        return ""


def mask_secret_value(value: str | None) -> str:
    value = value or ""
    if len(value) <= 4:
        return "••••"
    return "•" * max(0, len(value)-4) + value[-4:]
