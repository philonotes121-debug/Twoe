"""Compact Admin command surface. Legacy handlers remain available internally but are not exposed in Admin autocomplete."""
import json
from datetime import datetime
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select, func
import config
import services as sv
from database import async_session, User, LmsAccess, Order, Course, ConnectedChat

router=Router()

def admin_only(m:Message)->bool: return bool(m.from_user and m.from_user.id==config.ADMIN_ID)

@router.message(Command("lms"))
async def lms(message:Message, command:CommandObject):
    if not admin_only(message): return
    args=(command.args or "").split()
    if not args:
        async with async_session() as s:
            p=(await s.execute(select(func.count()).select_from(LmsAccess).where(LmsAccess.status=="pending"))).scalar() or 0
            gate=await sv.get_setting("lms_gate","1")
        return await message.answer(f"🛡 LMS Control\nGate: {'ON' if gate=='1' else 'OFF'}\nPending requests: {p}\nUse: /lms approve|deny|revoke USER_ID")
    act=args[0].lower()
    if act in ("approve","deny","revoke") and len(args)==2:
        try: uid=int(args[1])
        except: return await message.answer("USER_ID required.")
        status="approved" if act=="approve" else "denied"
        async with async_session() as s:
            r=await s.get(LmsAccess,uid)
            if not r: r=LmsAccess(user_id=uid); s.add(r)
            r.status=status; r.decided_at=datetime.utcnow(); await s.commit()
        try: await message.bot.send_message(uid, "✅ LMS access updated." if status=="approved" else "⚠️ LMS access updated: not active.")
        except: pass
        return await message.answer(f"✅ {act}: {uid}")
    if act=="gate" and len(args)==2 and args[1] in ("on","off"):
        await sv.set_setting("lms_gate","1" if args[1]=="on" else "0"); return await message.answer(f"✅ LMS gate {args[1]}")
    return await message.answer("Use: /lms approve|deny|revoke USER_ID or /lms gate on|off")

@router.message(Command("orders"))
async def orders(message:Message, command:CommandObject):
    if not admin_only(message): return
    args=(command.args or "").split()
    if args and args[0].lower() in ("approve","reject") and len(args)==2:
        try: oid=int(args[1])
        except: return await message.answer("ORDER_ID required.")
        async with async_session() as s:
            o=await s.get(Order,oid); c=await s.get(Course,o.course_id) if o else None
            if not o or o.status!="pending" or not c: return await message.answer("Order unavailable/already processed.")
            o.status="approved" if args[0].lower()=="approve" else "rejected"; o.decided_at=datetime.utcnow()
            if args[0].lower()=="approve" and not c.system_product:
                from database import UserCourse
                s.add(UserCourse(user_id=o.user_id,course_id=o.course_id))
            await s.commit()
        if args[0].lower()=="approve" and c.system_product:
            from premium import activate_membership
            await activate_membership(o.user_id,c.system_product,o.id)
            try:
                from notion_sync import sync_access_event; await sync_access_event(o.user_id,c.system_product,"approved")
            except: pass
        try: await message.bot.send_message(o.user_id, "✅ Payment approved. Open LMS to continue." if not c.system_product else f"✅ {c.system_product} subscription activated.")
        except: pass
        return await message.answer(f"✅ Order {oid}: {args[0].lower()}")
    async with async_session() as s:
        rows=(await s.execute(select(Order).where(Order.status=="pending").order_by(Order.created_at).limit(25))).scalars().all()
    if not rows: return await message.answer("✅ No pending orders.")
    await message.answer("\n".join(f"#{x.id} · User {x.user_id} · Product {x.course_id}" for x in rows))

@router.message(Command("users"))
async def users(message:Message, command:CommandObject):
    if not admin_only(message): return
    args=(command.args or "").split()
    if args and args[0].lower() in ("info","activity") and len(args)>1:
        try: uid=int(args[1])
        except: return await message.answer("USER_ID required.")
        async with async_session() as s: u=await s.get(User,uid)
        if not u: return await message.answer("User not found.")
        phone=""
        if u.phone_enc:
            from privacy import decrypt_secret_value; phone=decrypt_secret_value(u.phone_enc)
        text=f"👤 {u.first_name or '—'}\nUsername: @{u.username or '—'}\nID: {uid}\nPhone: {phone or 'not shared'}\nVerified: {bool(u.phone_verified)}\nBanned: {bool(u.is_banned)}"
        return await message.answer(text)
    total=await sv.count_users(); return await message.answer(f"👥 Users: {total}\nUse /users info USER_ID")

@router.message(Command("content"))
async def content(message:Message, command:CommandObject):
    if not admin_only(message): return
    args=(command.args or "").split()
    if not args:
        async with async_session() as s: n=(await s.execute(select(func.count()).select_from(Course).where(Course.system_product.is_(None)))).scalar() or 0
        return await message.answer(f"📚 Content: {n} LMS courses\nUse /content find TEXT or /content trending ID")
    if args[0]=="find":
        q=" ".join(args[1:]).lower()
        async with async_session() as s: rows=(await s.execute(select(Course).where(Course.system_product.is_(None),Course.name.ilike(f"%{q}%"),Course.is_active==True).limit(20))).scalars().all()
        return await message.answer("\n".join(f"{c.id} · {c.name}" for c in rows) or "No match.")
    if args[0]=="trending" and len(args)==3 and args[1] in ("add","remove"):
        try: cid=int(args[2])
        except: return await message.answer("COURSE_ID required.")
        async with async_session() as s:
            c=await s.get(Course,cid)
            if not c or c.system_product: return await message.answer("Course unavailable.")
            c.is_trending=args[1]=="add"; await s.commit()
        return await message.answer("✅ Updated")
    return await message.answer("Use /content find TEXT or /content trending add|remove COURSE_ID")

@router.message(Command("promo"))
async def promo(message:Message, command:CommandObject):
    if not admin_only(message): return
    args=(command.args or "").split()
    if len(args)!=2: return await message.answer("Use: /promo CODE DISCOUNT_PERCENT")
    try: code=args[0].upper(); pct=int(args[1])
    except ValueError: return await message.answer("Discount must be a number.")
    if not code.isalnum() or not 1<=pct<=100: return await message.answer("Code must be alphanumeric; discount 1-100%.")
    from datetime import timedelta
    import json
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    expiry=datetime.utcnow()+timedelta(hours=12)
    from admin_handlers import ACTIVE_PROMOS
    ACTIVE_PROMOS[code]={"discount":pct,"expires_at":expiry.isoformat()}
    await sv.set_setting("promos_json",json.dumps(ACTIVE_PROMOS))
    me=await message.bot.get_me(); kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎟 Open LMS",url=f"https://t.me/{me.username}?start=start")]])
    chats=[c for c in await sv.enabled_chats() if c.type in ("group","supergroup")]
    sent=0
    for c in chats:
        try:
            m=await message.bot.send_message(c.id,f"🎟 <b>Promo active: {code}</b> · {pct}% off · valid 12h",reply_markup=kb)
            await sv.schedule_delete(c.id,m.message_id,hours=12,kind="promo"); sent+=1
        except Exception: pass
    await message.answer(f"✅ {code} active for 12h. Sent to {sent} groups.")

@router.message(Command("ai"))
async def ai_control(message:Message, command:CommandObject):
    if not admin_only(message): return
    arg=(command.args or "").strip().lower()
    if arg in ("on","off"):
        await sv.set_setting("ai_enabled","1" if arg=="on" else "0")
        return await message.answer(f"✅ AI {arg}")
    if arg.startswith("offline "):
        mode=arg.split()[1]
        if mode not in ("auto","on","off"): return await message.answer("/ai offline auto|on|off")
        await sv.set_setting("offline_mode",mode); return await message.answer(f"✅ Offline mode: {mode}")
    return await message.answer(f"AI enabled: {await sv.get_setting('ai_enabled','1')} · Offline: {await sv.get_setting('offline_mode','auto')}")

@router.message(Command("privacy"))
async def privacy_cmd(message:Message):
    if not admin_only(message): return
    missing=[]
    for k in ("BOT_TOKEN","ADMIN_ID","DATABASE_URL","WEBAPP_BASE_URL","CRON_SECRET","DATA_ENCRYPTION_KEY"):
        if not getattr(config,k,""): missing.append(k)
    await message.answer("🔐 Privacy audit\nRequired env missing: " + (", ".join(missing) if missing else "none"))

@router.message(Command("health"))
async def health_cmd(message:Message):
    if not admin_only(message): return
    try:
        async with async_session() as s: await s.execute(select(func.count()).select_from(User))
        db="OK"
    except Exception: db="ERROR"
    await message.answer(f"🩺 Health\nDB: {db}\nAI: {await sv.get_setting('ai_enabled','1')}\nOffline: {await sv.get_setting('offline_mode','auto')}")
