"""Paid plans, phone verification, protected referral links and compact user commands."""
import base64, hashlib, hmac, json, logging, time
from datetime import datetime, timedelta, timezone
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from sqlalchemy import select, func
import config
import services as sv
from database import async_session, User, Course, Membership, LmsAccess, Referral
from privacy import encrypt_secret_value, decrypt_secret_value, personal_data_hmac

logger = logging.getLogger(__name__)
router = Router()

PLANS = {
    "community": {
        "title": "Join Our Community",
        "price": config.COMMUNITY_PRICE_INR,
        "days": 30,
        "benefits": ["All courses available", "Personal AI tracking", "Answer evaluation"],
    },
    "ca_tracker": {
        "title": "CA TRACKER PRO by Professor 🥼",
        "price": config.CA_PRICE_INR,
        "days": 30,
        "benefits": ["The Hindu + Indian Express + PIB Daily in one place", "Editorial + concise summary", "Place in News", "International Organisations database", "Separate filters + search + zoom/reading mode", "Notion-synced updates"],
    },
}


def _token(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    secret = config.REFERRAL_SIGNING_SECRET or config.BOT_TOKEN
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).digest()[:18]
    return base64.urlsafe_b64encode(raw + b"." + sig).decode().rstrip("=")


def _verify_token(token: str) -> dict | None:
    try:
        pad = "=" * (-len(token) % 4)
        blob = base64.urlsafe_b64decode(token + pad)
        raw, sig = blob.rsplit(b".", 1)
        secret = config.REFERRAL_SIGNING_SECRET or config.BOT_TOKEN
        calc = hmac.new(secret.encode(), raw, hashlib.sha256).digest()[:18]
        if not hmac.compare_digest(calc, sig): return None
        payload = json.loads(raw.decode())
        if int(time.time()) > int(payload.get("exp", 0)): return None
        return payload
    except Exception:
        return None


async def referral_link(bot, user_id: int) -> str:
    me = await bot.get_me()
    now = int(time.time())
    token = _token({"uid": int(user_id), "iat": now, "exp": now + config.REFERRAL_TOKEN_TTL_DAYS * 86400, "v": 1})
    return f"https://t.me/{me.username}?start=r_{token}"


async def ensure_system_products():
    async with async_session() as s:
        existing = {c.system_product: c for c in (await s.execute(select(Course).where(Course.system_product.isnot(None)))).scalars().all()}
        changed = False
        for plan, data in PLANS.items():
            c = existing.get(plan)
            if not c:
                c = Course(name=data["title"], faculty="Professor", medium="", notes="System subscription product", price=data["price"], is_active=True, system_product=plan)
                s.add(c); changed = True
            else:
                c.name, c.price, c.system_product, c.is_active = data["title"], data["price"], plan, True
                changed = True
        if changed: await s.commit()


async def active_membership(user_id: int, plan: str) -> Membership | None:
    now = datetime.utcnow()
    async with async_session() as s:
        q = select(Membership).where(Membership.user_id == user_id, Membership.plan == plan, Membership.status == "active", Membership.expires_at > now).order_by(Membership.expires_at.desc())
        return (await s.execute(q)).scalars().first()


async def activate_membership(user_id: int, plan: str, order_id: int | None = None):
    data = PLANS[plan]
    now = datetime.utcnow()
    async with async_session() as s:
        q = select(Membership).where(Membership.user_id == user_id, Membership.plan == plan, Membership.status == "active").order_by(Membership.expires_at.desc())
        m = (await s.execute(q)).scalars().first()
        if m and m.expires_at > now:
            m.expires_at = m.expires_at + timedelta(days=data["days"])
        else:
            m = Membership(user_id=user_id, plan=plan, status="active", starts_at=now, expires_at=now + timedelta(days=data["days"]), order_id=order_id)
            s.add(m)
        m.updated_at = now
        await s.commit()


def plan_kb(plan: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"💳 Buy ₹{PLANS[plan]['price']}/30 days", callback_data=f"planbuy:{plan}")]]
    if config.WEBAPP_BASE_URL:
        label = "📚 Open LMS" if plan == "community" else "📰 Open CA Tracker Pro"
        path = "/webapp/lms" if plan == "community" else "/webapp/ca"
        from aiogram.types import WebAppInfo
        rows.append([InlineKeyboardButton(text=label, web_app=WebAppInfo(url=f"{config.WEBAPP_BASE_URL}{path}"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def phone_kb() -> ReplyKeyboardMarkup:
    from keyboards import phone_verification_kb
    return phone_verification_kb()


async def show_phone_gate(message: Message):
    await message.answer("📱 Mobile number verify karke LMS unlock karein.", reply_markup=phone_kb())


@router.message(F.contact)
async def receive_contact(message: Message):
    u = message.from_user
    c = message.contact
    if not u or message.chat.type != "private" or not c or c.user_id != u.id:
        return await message.answer("Apna hi mobile number Telegram contact button se share karein.")
    await sv.ensure_user(u)
    cipher = encrypt_secret_value(c.phone_number)
    async with async_session() as s:
        row = await s.get(User, u.id)
        row.phone_enc = cipher
        row.phone_hash = personal_data_hmac(c.phone_number)
        row.phone = None
        row.phone_verified = True
        row.phone_verified_at = datetime.utcnow()
        await s.commit()
    await sv.set_user_commands(message.bot, u.id, verified=True)
    await message.answer("✅ Number verified. Ab LMS open kar sakte hain.", reply_markup=ReplyKeyboardRemove())
    from keyboards import main_menu_kb
    await message.answer("📚 LMS ready.", reply_markup=main_menu_kb())


@router.message(Command("community"))
async def community_cmd(message: Message):
    u = await sv.ensure_user(message.from_user)
    if not u.phone_verified: return await show_phone_gate(message)
    d=PLANS["community"]
    active=await active_membership(u.id,"community")
    text=f"👥 <b>{d['title']}</b>\n\n₹{d['price']}/month\n" + "\n".join(f"• {x}" for x in d["benefits"])
    if active: text += f"\n\n✅ Active until {active.expires_at:%d %b %Y}"
    await message.answer(text, reply_markup=plan_kb("community"))


@router.message(Command("ca"))
async def ca_cmd(message: Message):
    u=await sv.ensure_user(message.from_user)
    if not u.phone_verified: return await show_phone_gate(message)
    d=PLANS["ca_tracker"]; active=await active_membership(u.id,"ca_tracker")
    text=(f"📰 <b>{d['title']}</b>\n\n⭐ {config.CA_DISPLAY_RATING}/5 · {config.CA_REVIEW_COUNT} users\n₹{d['price']}/month\n\n" + "\n".join(f"• {x}" for x in d["benefits"]))
    if active: text += f"\n\n✅ Active until {active.expires_at:%d %b %Y}"
    await message.answer(text, reply_markup=plan_kb("ca_tracker"))


@router.callback_query(F.data.startswith("plan:"))
async def plan_info(call: CallbackQuery):
    plan=call.data.split(":",1)[1]
    if plan not in PLANS: return await call.answer()
    d=PLANS[plan]
    text=f"<b>{d['title']}</b>\n\n₹{d['price']}/month\n"+"\n".join(f"• {x}" for x in d["benefits"])
    if plan=="ca_tracker": text += "\n\nAfter approval: CA Tracker Pro Mini App opens directly."
    await call.message.edit_text(text,reply_markup=plan_kb(plan)); await call.answer()


@router.callback_query(F.data.startswith("planbuy:"))
async def plan_buy(call: CallbackQuery):
    plan=call.data.split(":",1)[1]
    if plan not in PLANS: return await call.answer()
    u=await sv.ensure_user(call.from_user)
    if not u.phone_verified:
        await call.message.answer("📱 Number verify first.", reply_markup=phone_kb()); return await call.answer()
    await ensure_system_products()
    async with async_session() as s:
        product=(await s.execute(select(Course).where(Course.system_product==plan))).scalars().first()
    await call.message.answer(f"✅ {PLANS[plan]['title']} selected — ₹{PLANS[plan]['price']}/30 days.\nPayment proof flow ab open hoga.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Continue Payment", callback_data=f"buy:{product.id}")],[InlineKeyboardButton(text="⬅ Back",callback_data="menu:main")]]))
    await call.answer()


@router.message(Command("referral"))
async def referral_cmd(message: Message):
    u=await sv.ensure_user(message.from_user)
    if not u.phone_verified: return await show_phone_gate(message)
    link=await referral_link(message.bot,u.id)
    async with async_session() as s:
        v=(await s.execute(select(func.count()).select_from(Referral).where(Referral.referrer_id==u.id,Referral.status=="verified"))).scalar() or 0
        p=(await s.execute(select(func.count()).select_from(Referral).where(Referral.referrer_id==u.id,Referral.status=="pending"))).scalar() or 0
    await message.answer(f"🎁 <b>Referral</b>\nVerified: {v} · Pending: {p}\n\n<code>{link}</code>",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📤 Share Link",url=f"https://t.me/share/url?url={link}")],[InlineKeyboardButton(text="📚 Open LMS",url=f"https://t.me/{(await message.bot.get_me()).username}?start=start")]]))

PUBLIC_USER_COMMANDS = {"start", "menu", "trending", "account", "referral", "study", "support", "ask", "community", "ca"}
LEGACY_BLOCKED_COMMANDS = {"courses", "my_courses", "mycourses", "myorders", "applypromo", "wallet", "today", "target", "doubt", "remind", "reminders", "notify_me", "notify_off", "contact", "help", "faq", "myid", "privacy", "feedback", "certificate", "resources", "leaderboard"}


class PhoneGateMiddleware:
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user or user.id == config.ADMIN_ID:
            return await handler(event, data)
        # Only gate private-user actions. Group messages are handled by group features.
        chat = getattr(event, "chat", None) or getattr(getattr(event, "message", None), "chat", None)
        if not chat or chat.type != "private":
            return await handler(event, data)
        if isinstance(event, Message) and event.contact:
            return await handler(event, data)
        try:
            u = await sv.ensure_user(user)
            if u.phone_verified:
                # Block legacy public commands which would expose course lists in chat.
                text = (event.text or "").strip() if isinstance(event, Message) else ""
                if text.startswith("/"):
                    cmd = text[1:].split()[0].split("@")[0].lower()
                    if cmd in LEGACY_BLOCKED_COMMANDS:
                        await event.answer("📚 Open LMS for this feature.", reply_markup=__import__("keyboards").main_menu_kb())
                        return None
                return await handler(event, data)
            # /start is allowed to present the verification gate.
            if isinstance(event, Message) and (event.text or "").strip().startswith("/start"):
                return await handler(event, data)
            await show_phone_gate(event if isinstance(event, Message) else event.message)
            return None
        except Exception:
            logger.exception("phone gate failed")
            return None

async def has_active_plan(user_id:int, plan:str) -> bool:
    return bool(await active_membership(user_id, plan))


async def can_access_lms(user_id:int) -> bool:
    # Product requirement: phone verification is the user-facing LMS gate.
    # LmsAccess remains as an Admin audit/approval record, but is not required
    # to unlock the Mini App. A global emergency lockdown can still stop access.
    u=await sv.ensure_user_by_id(user_id)
    if not u or u.is_banned or not u.phone_verified: return False
    return await sv.get_setting("lockdown", "0") != "1" and await sv.get_setting("lms_gate", "1") != "0"
