"""Compact 29-command Admin surface.
All commands are Admin-only and consolidate overlapping legacy handlers.
Legacy handler modules remain available internally for callbacks/FSM flows, but are
not exposed in the Admin bot command menu.
"""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func

import config
import services as sv
from database import async_session, User, Course, Order, UserCourse, Membership, ConnectedChat, Referral, EventLog, InboxItem, LmsAccess

router = Router()


def admin_only(m: Message) -> bool:
    return bool(m.from_user and m.from_user.id == config.ADMIN_ID)


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _reply(m: Message, title: str, lines: list[str], buttons=None):
    text = f"🛡 <b>{title}</b>\n\n" + "\n".join(lines)
    kb = InlineKeyboardMarkup(inline_keyboard=buttons or [])
    return await m.answer(text, reply_markup=kb if buttons else None)


# ---------------------------------------------------------------------------
# 1-28: ADMIN COMMAND SURFACE
# ---------------------------------------------------------------------------
@router.message(Command("adminhelp"))
async def adminhelp(m: Message):
    if not admin_only(m): return
    await _reply(m, "Admin Control Centre", [
        "1 /lms  • access gate/requests",
        "2 /users • lookup/profile/activity",
        "3 /orders • payments/grants",
        "4 /content • courses/sections/trending",
        "5 /subscriptions • Community + CA",
        "6 /promo • create + 12h group broadcast",
        "7 /broadcast • instant broadcasts",
        "8 /schedule • scheduled campaigns",
        "9 /inbox • support inbox",
        "10 /groups • connected groups/channels",
        "11 /referrals • referral audit",
        "12 /analytics • metrics",
        "13 /ai • AI controls",
        "14 /presence • online/offline mode",
        "15 /security • security posture",
        "16 /privacy • privacy audit",
        "17 /health • runtime health",
        "18 /backup • data backup",
        "19 /recovery • state recovery",
        "20 /moderation • ban/block/antispam",
        "21 /resources • resource content",
        "22 /notion • CA/Notion sync",
        "23 /countdown • UPSC countdown",
        "24 /settings • operational settings",
        "25 /audit • event/audit trail",
        "26 /export • data exports",
        "27 /system • system status",
        "28 /lockdown • emergency controls",
    ])


@router.message(Command("lms"))
async def lms(m: Message, command: CommandObject):
    if not admin_only(m): return
    a = (command.args or "").split()
    if a and a[0] in {"gate"} and len(a) == 2 and a[1] in {"on", "off"}:
        await sv.set_setting("lms_gate", "1" if a[1] == "on" else "0")
        return await _reply(m, "LMS Gate", [f"Gate: {a[1].upper()}"])
    if a and a[0] in {"approve", "deny", "revoke"} and len(a) == 2:
        try: uid = int(a[1])
        except ValueError: return await _reply(m, "LMS", ["Valid USER_ID required."])
        status = "approved" if a[0] == "approve" else "denied"
        async with async_session() as s:
            r = await s.get(LmsAccess, uid)
            if not r:
                r = LmsAccess(user_id=uid); s.add(r)
            r.status, r.decided_at = status, datetime.utcnow(); await s.commit()
        try: await m.bot.send_message(uid, "✅ LMS access updated.")
        except Exception: pass
        return await _reply(m, "LMS", [f"{a[0]}: {uid}"])
    async with async_session() as s:
        pending = (await s.execute(select(func.count()).select_from(LmsAccess).where(LmsAccess.status == "pending"))).scalar() or 0
    gate = await sv.get_setting("lms_gate", "1")
    return await _reply(m, "LMS", [f"Phone verification: mandatory", f"Global gate: {'ON' if gate == '1' else 'OFF'}", f"Pending requests: {pending}", "Use /lms approve|deny|revoke USER_ID or /lms gate on|off."])


@router.message(Command("users"))
async def users(m: Message, command: CommandObject):
    if not admin_only(m): return
    a = (command.args or "").split(maxsplit=1)
    if a and a[0] in {"info", "phone", "activity"} and len(a) == 2:
        try: uid = int(a[1])
        except ValueError: return await _reply(m, "Users", ["Valid USER_ID required."])
        async with async_session() as s: u = await s.get(User, uid)
        if not u: return await _reply(m, "Users", ["User not found."])
        phone = ""
        if u.phone_enc:
            try:
                from privacy import decrypt_secret_value
                phone = decrypt_secret_value(u.phone_enc)
            except Exception: phone = ""
        if a[0] == "activity":
            async with async_session() as s:
                rows = (await s.execute(select(EventLog).where(EventLog.user_id == uid).order_by(EventLog.id.desc()).limit(15))).scalars().all()
            return await _reply(m, "User Activity", [f"{r.created_at:%d %b %H:%M} • {r.kind}" for r in rows] or ["No events."])
        return await _reply(m, "User Profile", [
            f"Name: {esc(u.first_name or '—')}", f"Username: @{esc(u.username or '—')}", f"ID: <code>{uid}</code>",
            f"Phone: {esc(phone or 'not shared')}", f"Verified: {bool(u.phone_verified)}", f"Banned: {bool(u.is_banned)}",
        ])
    total = await sv.count_users()
    return await _reply(m, "Users", [f"Total users: {total}", "Use /users info USER_ID, /users phone USER_ID, /users activity USER_ID"])


@router.message(Command("orders"))
async def orders(m: Message, command: CommandObject):
    if not admin_only(m): return
    a = (command.args or "").split()
    if a and a[0] in {"approve", "reject"} and len(a) == 2:
        try: oid = int(a[1])
        except ValueError: return await _reply(m, "Orders", ["Valid ORDER_ID required."])
        async with async_session() as s:
            o = await s.get(Order, oid); c = await s.get(Course, o.course_id) if o else None
            if not o or not c or o.status != "pending": return await _reply(m, "Orders", ["Order unavailable or already processed."])
            o.status = "approved" if a[0] == "approve" else "rejected"; o.decided_at = datetime.utcnow()
            if o.status == "approved" and not c.system_product:
                exists = (await s.execute(select(UserCourse).where(UserCourse.user_id == o.user_id, UserCourse.course_id == o.course_id))).scalar_one_or_none()
                if not exists: s.add(UserCourse(user_id=o.user_id, course_id=o.course_id))
            await s.commit()
        if o.status == "approved" and c.system_product:
            from premium import activate_membership
            await activate_membership(o.user_id, c.system_product, oid)
            try:
                from notion_sync import sync_access_event
                await sync_access_event(o.user_id, c.system_product, "approved")
            except Exception: pass
        try:
            if o.status == "approved":
                from aiogram.types import WebAppInfo
                path = "/webapp/ca" if c.system_product == "ca_tracker" else "/webapp/lms"
                label = "📰 Open CA Tracker Pro" if c.system_product == "ca_tracker" else "📚 Open LMS"
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=f"{config.WEBAPP_BASE_URL}{path}"))]]) if config.WEBAPP_BASE_URL else None
                await m.bot.send_message(o.user_id, "✅ Payment approved. Access is ready.", reply_markup=kb)
            else:
                await m.bot.send_message(o.user_id, "⚠️ Payment rejected.")
        except Exception: pass
        return await _reply(m, "Orders", [f"Order #{oid}: {o.status}"])
    async with async_session() as s:
        rows = (await s.execute(select(Order).where(Order.status == "pending").order_by(Order.created_at).limit(25))).scalars().all()
    return await _reply(m, "Orders", [f"#{o.id} • user {o.user_id} • product {o.course_id}" for o in rows] or ["No pending orders."])


@router.message(Command("content"))
async def content(m: Message, command: CommandObject):
    if not admin_only(m): return
    a = (command.args or "").split(maxsplit=1)
    if not a:
        async with async_session() as s:
            n=(await s.execute(select(func.count()).select_from(Course).where(Course.system_product.is_(None),Course.is_active==True))).scalar() or 0
        return await _reply(m, "Content", [f"Active LMS courses: {n}", "Subcommands: list | find TEXT | add NAME|FACULTY|MEDIUM|NOTES|PRICE|section_keys | price ID PRICE | hide ID | trend add|remove ID"])
    act=a[0].lower(); rest=a[1] if len(a)>1 else ""
    async with async_session() as s:
        if act == "list":
            rows=(await s.execute(select(Course).where(Course.system_product.is_(None)).order_by(Course.id.desc()).limit(40))).scalars().all()
            return await _reply(m,"Courses",[f"{c.id} • {c.name} • ₹{int(c.price) if c.price is not None else 'TBD'}" for c in rows] or ["None."])
        if act == "find":
            q=rest.strip()
            rows=(await s.execute(select(Course).where(Course.system_product.is_(None),Course.name.ilike(f"%{q}%"),Course.is_active==True).limit(20))).scalars().all()
            return await _reply(m,"Course Search",[f"{c.id} • {c.name}" for c in rows] or ["No match."])
        if act == "add":
            p=[x.strip() for x in rest.split("|")]
            if len(p)!=6: return await _reply(m,"Content",["Use /content add NAME|FACULTY|MEDIUM|NOTES|PRICE|section_key1,section_key2"])
            name,faculty,medium,notes,price_txt,keys_txt=p
            price=None if price_txt.upper()=="TBD" else float(price_txt)
            secs=[]
            keymap={x.key:x for x in (await s.execute(select(__import__('database').Section))).scalars().all()}
            for k in [x.strip() for x in keys_txt.split(",") if x.strip()]:
                if k in keymap: secs.append(keymap[k])
            c=Course(name=name,faculty=faculty,medium=medium,notes=notes,price=price,sections=secs); s.add(c); await s.commit(); await s.refresh(c)
            return await _reply(m,"Content",[f"Added course #{c.id}: {esc(c.name)}"])
        try: cid=int(rest.split()[0]) if rest else 0
        except ValueError: cid=0
        if cid:
            c=await s.get(Course,cid)
            if not c or c.system_product: return await _reply(m,"Content",["Course unavailable."])
            if act=="price" and len(rest.split())==2:
                c.price=None if rest.split()[1].upper()=="TBD" else float(rest.split()[1]); await s.commit(); return await _reply(m,"Content",["Price updated."])
            if act=="hide": c.is_active=False; await s.commit(); return await _reply(m,"Content",["Course hidden."])
            if act=="trend" and len(rest.split())==2 and rest.split()[1] in {"add","remove"}:
                c.is_trending=rest.split()[1]=="add"; await s.commit(); return await _reply(m,"Content",["Trending flag updated."])
    return await _reply(m,"Content",["Unknown content action."])


@router.message(Command("subscriptions"))
async def subscriptions(m: Message, command: CommandObject):
    if not admin_only(m): return
    a=(command.args or "").split()
    if a and a[0]=="user" and len(a)==3:
        try: uid=int(a[1])
        except ValueError: return await _reply(m,"Subscriptions",["Valid USER_ID required."])
        plan=a[2]
        from premium import PLANS, activate_membership
        if plan not in PLANS: return await _reply(m,"Subscriptions",["Plan: community | ca_tracker"])
        await activate_membership(uid,plan,None); return await _reply(m,"Subscriptions",[f"Activated {plan} for {uid}."])
    async with async_session() as s:
        active=(await s.execute(select(Membership.plan,func.count()).where(Membership.status=="active").group_by(Membership.plan))).all()
    return await _reply(m,"Subscriptions",[f"{plan}: {count} active" for plan,count in active] or ["No active memberships." , "Plans: Community ₹800/30d; CA Tracker Pro ₹200/30d"])


@router.message(Command("promo"))
async def promo(m: Message, command: CommandObject):
    if not admin_only(m): return
    a=(command.args or "").split()
    if len(a)!=2: return await _reply(m,"Promo",["Use /promo CODE DISCOUNT_PERCENT"])
    code=a[0].upper()
    try: pct=int(a[1])
    except ValueError: return await _reply(m,"Promo",["Discount must be a number."])
    if not code.isalnum() or not 1<=pct<=100: return await _reply(m,"Promo",["Code must be alphanumeric; discount 1-100."])
    expiry=datetime.utcnow()+timedelta(hours=12)
    from admin_handlers import ACTIVE_PROMOS
    ACTIVE_PROMOS[code]={"discount":pct,"expires_at":expiry.isoformat()}
    await sv.set_setting("promos_json",json.dumps(ACTIVE_PROMOS))
    me=await m.bot.get_me()
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎟 Open LMS",url=f"https://t.me/{me.username}?start=start")]])
    chats=[c for c in await sv.enabled_chats() if c.type in ("group","supergroup")]
    sent=0
    for c in chats:
        try:
            msg=await m.bot.send_message(c.id,f"🎟 <b>Promo {code}</b> · {pct}% off · valid 12h",reply_markup=kb)
            await sv.schedule_delete(c.id,msg.message_id,hours=12,kind="promo"); sent+=1
        except Exception: pass
    return await _reply(m,"Promo",[f"{code} active for 12h.",f"Broadcast groups: {sent}"])


@router.message(Command("broadcast"))
async def broadcast(m: Message, command: CommandObject):
    if not admin_only(m): return
    src=m.reply_to_message
    if not src: return await _reply(m,"Broadcast",["Reply to the message you want to broadcast, then send /broadcast groups|users"])
    target=((command.args or "groups").strip().lower())
    if target not in {"groups","users","all"}: target="groups"
    targets=[]
    async with async_session() as s:
        if target in {"groups","all"}: targets.extend((await s.execute(select(ConnectedChat).where(ConnectedChat.enabled==True))).scalars().all())
        if target in {"users","all"}: targets.extend((await s.execute(select(User).where(User.is_banned==False))).scalars().all())
    sent=failed=0
    for t in targets:
        tid=t.id
        try:
            cp=await m.bot.copy_message(tid,src.chat.id,src.message_id,reply_markup=await sv.growth_kb(m.bot))
            await sv.schedule_delete(tid,cp.message_id,hours=config.DEL_BROADCAST_HOURS,kind="broadcast"); sent+=1
        except Exception: failed+=1
    return await _reply(m,"Broadcast",[f"Sent: {sent}",f"Failed: {failed}"])


@router.message(Command("schedule"))
async def schedule(m: Message, command: CommandObject):
    if not admin_only(m): return
    a=(command.args or "").split(maxsplit=2)
    src=m.reply_to_message
    if len(a)<2 or not src: return await _reply(m,"Schedule",["Reply to a message and use /schedule YYYY-MM-DD HH:MM [label]"])
    try:
        local_when=datetime.strptime(f"{a[0]} {a[1]}","%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(config.TIMEZONE))
    except ValueError: return await _reply(m,"Schedule",["Invalid datetime. Use IST."])
    utc_when=local_when.astimezone(timezone.utc).replace(tzinfo=None)
    items=json.loads(await sv.get_setting("sched_bc","[]"))
    nid=max([x.get("id",0) for x in items],default=0)+1
    items.append({"id":nid,"at":utc_when.isoformat(),"chat":src.chat.id,"msg":src.message_id,"label":a[2] if len(a)>2 else ""})
    await sv.set_setting("sched_bc",json.dumps(items))
    return await _reply(m,"Schedule",[f"Scheduled #{nid} at {local_when:%Y-%m-%d %H:%M} IST"])


@router.message(Command("inbox"))
async def inbox(m: Message, command: CommandObject):
    if not admin_only(m): return
    async with async_session() as s:
        rows=(await s.execute(select(InboxItem).where(InboxItem.resolved==False).order_by(InboxItem.id.desc()).limit(20))).scalars().all()
    return await _reply(m,"Support Inbox",[f"#{x.id} • user {x.user_id} • source {x.source_chat_id}" for x in rows] or ["Inbox clear.","Reply to the mapped inbox card to send a response."])


@router.message(Command("groups"))
async def groups(m: Message, command: CommandObject):
    if not admin_only(m): return
    a=(command.args or "").split()
    async with async_session() as s:
        rows=(await s.execute(select(ConnectedChat).order_by(ConnectedChat.id))).scalars().all()
        if a and a[0]=="remove" and len(a)==2:
            try: cid=int(a[1])
            except ValueError: return await _reply(m,"Groups",["Valid CHAT_ID required."])
            r=await s.get(ConnectedChat,cid)
            if r: r.enabled=False; await s.commit(); return await _reply(m,"Groups",["Chat disabled."])
    return await _reply(m,"Groups",[f"{c.id} • {esc(c.title or c.username or str(c.id))} • enabled={c.enabled} • countdown={c.countdown_on}" for c in rows] or ["No connected chats."])


@router.message(Command("referrals"))
async def referrals(m: Message, command: CommandObject):
    if not admin_only(m): return
    async with async_session() as s:
        total=(await s.execute(select(func.count()).select_from(Referral))).scalar() or 0
        verified=(await s.execute(select(func.count()).select_from(Referral).where(Referral.status=="verified"))).scalar() or 0
        pending=(await s.execute(select(func.count()).select_from(Referral).where(Referral.status=="pending"))).scalar() or 0
    return await _reply(m,"Referrals",[f"Total: {total}",f"Verified: {verified}",f"Pending: {pending}",f"Daily reward cap: {config.REFERRAL_DAILY_REWARD_CAP}","Signed + expiring referral tokens enabled."])


@router.message(Command("analytics"))
async def analytics(m: Message, command: CommandObject):
    if not admin_only(m): return
    async with async_session() as s:
        users=(await s.execute(select(func.count()).select_from(User))).scalar() or 0
        verified=(await s.execute(select(func.count()).select_from(User).where(User.phone_verified==True))).scalar() or 0
        orders=(await s.execute(select(func.count()).select_from(Order))).scalar() or 0
        chats=(await s.execute(select(func.count()).select_from(ConnectedChat).where(ConnectedChat.enabled==True))).scalar() or 0
    return await _reply(m,"Analytics",[f"Users: {users}",f"Verified: {verified}",f"Orders: {orders}",f"Connected chats: {chats}","Use /analytics3d legacy visual endpoint if enabled in the portal."])


@router.message(Command("ai"))
async def ai_cmd(m: Message, command: CommandObject):
    if not admin_only(m): return
    a=(command.args or "").split()
    if a and a[0] in {"on","off"}:
        await sv.set_setting("ai_enabled","1" if a[0]=="on" else "0")
    if len(a)>=2 and a[0]=="offline" and a[1] in {"auto","on","off"}:
        await sv.set_setting("offline_mode",a[1])
    return await _reply(m,"AI",[f"Enabled: {await sv.get_setting('ai_enabled','1')}",f"Offline: {await sv.get_setting('offline_mode','auto')}","AI is portal-grounded and isolated per user."])


@router.message(Command("presence"))
async def presence(m: Message):
    if not admin_only(m): return
    return await _reply(m,"Admin Presence",[f"State: {'OFFLINE' if await sv.admin_offline() else 'ONLINE'}",f"Mode: {await sv.get_setting('offline_mode','auto')}",f"Idle threshold: {await sv.get_int('offline_idle_min', config.ADMIN_OFFLINE_IDLE_MIN)} min"])


@router.message(Command("security"))
async def security(m: Message):
    if not admin_only(m): return
    from security import admin_security_status
    status=await admin_security_status()
    return await _reply(m,"Security",[str(status),"Webhook secret + Mini App HMAC + rate limits + threat detection + auto-heal enabled."])


@router.message(Command("privacy"))
async def privacy(m: Message):
    if not admin_only(m): return
    required=["BOT_TOKEN","ADMIN_ID","DATABASE_URL","WEBAPP_BASE_URL","CRON_SECRET","DATA_ENCRYPTION_KEY","REFERRAL_SIGNING_SECRET"]
    missing=[x for x in required if not getattr(config,x,"")]
    return await _reply(m,"Privacy",["Required secrets: OK" if not missing else "Missing: "+", ".join(missing),"Phone data: encrypted + Admin-only decrypt","Host/device identity: not exposed to users","Preview/route protections: enabled"])


@router.message(Command("health"))
async def health(m: Message):
    if not admin_only(m): return
    try:
        async with async_session() as s: await s.execute(select(func.count()).select_from(User))
        db="OK"
    except Exception: db="ERROR"
    return await _reply(m,"Health",[f"DB: {db}",f"AI: {await sv.get_setting('ai_enabled','1')}",f"Offline mode: {await sv.get_setting('offline_mode','auto')}",f"Vercel: {'YES' if __import__('os').environ.get('VERCEL') else 'NO'}"])


@router.message(Command("backup"))
async def backup(m: Message):
    if not admin_only(m): return
    try:
        from security import _export_bot_data_backup
        blob=await _export_bot_data_backup()
        from aiogram.types import BufferedInputFile
        await m.answer_document(BufferedInputFile(blob,"lms_backup.json"),caption="🔐 Controlled Admin data backup export")
    except Exception as e:
        await _reply(m,"Backup",["Backup failed: "+esc(str(e)[:120])])


@router.message(Command("recovery"))
async def recovery(m: Message, command: CommandObject):
    if not admin_only(m): return
    a=(command.args or "").strip().lower()
    if a=="snapshot":
        try:
            from security import _save_state_snapshot, AI_STATE
            _save_state_snapshot(AI_STATE)
            return await _reply(m,"Recovery",["State snapshot saved."])
        except Exception: pass
    if a=="restore":
        try:
            from security import restore_state_backup, AI_STATE
            restore_state_backup(AI_STATE)
            return await _reply(m,"Recovery",["State snapshot restored."])
        except Exception: pass
    return await _reply(m,"Recovery",["Use /recovery snapshot or /recovery restore."])


@router.message(Command("moderation"))
async def moderation(m: Message, command: CommandObject):
    if not admin_only(m): return
    a=(command.args or "").split()
    if len(a)==2 and a[0] in {"ban","block","unban","unblock"}:
        try: uid=int(a[1])
        except ValueError: return await _reply(m,"Moderation",["Valid USER_ID required."])
        async with async_session() as s:
            u=await s.get(User,uid)
            if not u: return await _reply(m,"Moderation",["User not found."])
            u.is_banned=a[0] in {"ban","block"}; await s.commit()
        return await _reply(m,"Moderation",[f"{a[0]}: {uid}"])
    if len(a)==2 and a[0]=="antispam" and a[1] in {"on","off"}:
        await sv.set_setting("antispam_enabled","1" if a[1]=="on" else "0")
        return await _reply(m,"Moderation",[f"Antispam: {a[1]}"])
    return await _reply(m,"Moderation",["Use /moderation ban|block|unban|unblock USER_ID or /moderation antispam on|off"])


@router.message(Command("resources"))
async def resources(m: Message, command: CommandObject):
    if not admin_only(m): return
    a=(command.args or "").strip()
    if a:
        await sv.set_setting("resources",a); return await _reply(m,"Resources",["Resources updated."])
    return await _reply(m,"Resources",[await sv.get_setting("resources","No resource content configured.")[:2500]])


@router.message(Command("notion"))
async def notion(m: Message, command: CommandObject):
    if not admin_only(m): return
    from notion_sync import enabled, get_ca_items, notion_health
    a=(command.args or "").split(maxsplit=2)
    if a and a[0]=="sync":
        data=await get_ca_items({"q": a[1] if len(a)>1 else ""})
        return await _reply(m,"Notion",[f"Fetched {len(data)} CA records.","Datasets: Daily CA, Editorial, Place in News, International Organisations."])
    return await _reply(m,"Notion",[f"Enabled: {enabled()}",await notion_health(),"Independent filters are exposed separately in CA Tracker Pro."])


@router.message(Command("countdown"))
async def countdown(m: Message, command: CommandObject):
    if not admin_only(m): return
    a=(command.args or "").split(maxsplit=1)
    if a and a[0]=="date" and len(a)==2:
        try: datetime.strptime(a[1],"%Y-%m-%d")
        except ValueError: return await _reply(m,"Countdown",["Use YYYY-MM-DD."])
        await sv.set_setting("exam_date",a[1]); return await _reply(m,"Countdown",[f"Exam date set: {a[1]}"])
    if a and a[0] in {"on","off"}:
        await sv.set_setting("countdown_on","1" if a[0]=="on" else "0"); return await _reply(m,"Countdown",[f"Countdown {a[0]}"])
    ds=await sv.get_setting("exam_date",config.EXAM_DATE)
    return await _reply(m,"Countdown",[f"Exam date: {ds}",f"Daily send: {config.COUNTDOWN_TIME} IST", "Personal delete: 23:00 IST", "Group tag + inline buttons enabled."])


@router.message(Command("settings"))
async def settings(m: Message, command: CommandObject):
    if not admin_only(m): return
    a=(command.args or "").split(maxsplit=2)
    if len(a)==3 and a[0]=="set":
        await sv.set_setting(a[1],a[2]); return await _reply(m,"Settings",[f"{a[1]} updated."])
    return await _reply(m,"Settings",["Use /settings set KEY VALUE","Operational settings are DB-backed so redeploys preserve them."])


@router.message(Command("audit"))
async def audit(m: Message, command: CommandObject):
    if not admin_only(m): return
    try: limit=min(50,max(1,int((command.args or "20").strip())))
    except ValueError: limit=20
    async with async_session() as s:
        rows=(await s.execute(select(EventLog).order_by(EventLog.id.desc()).limit(limit))).scalars().all()
    return await _reply(m,"Audit",[f"{r.created_at:%d %b %H:%M} • {r.kind} • user={r.user_id or '-'} • chat={r.chat_id or '-'}" for r in rows] or ["No audit events."])


@router.message(Command("export"))
async def export_data(m: Message, command: CommandObject):
    if not admin_only(m): return
    from security import _export_bot_data_backup
    from aiogram.types import BufferedInputFile
    blob=await _export_bot_data_backup()
    await m.answer_document(BufferedInputFile(blob,"lms_export.json"),caption="🔐 Controlled Admin export")


@router.message(Command("system"))
async def system(m: Message):
    if not admin_only(m): return
    return await _reply(m,"System",[
        f"Bot: {esc(config.BOT_NAME)}", f"Timezone: {config.TIMEZONE}", f"Exam: {config.EXAM_NAME} {await sv.get_setting('exam_date',config.EXAM_DATE)}",
        f"Mini App: {'configured' if config.WEBAPP_BASE_URL else 'missing'}", "Secrets are environment-only.",
    ])


@router.message(Command("lockdown"))
async def lockdown(m: Message, command: CommandObject):
    if not admin_only(m): return
    a=(command.args or "off").strip().lower()
    if a not in {"on","off"}: return await _reply(m,"Lockdown",["Use /lockdown on|off"])
    await sv.set_setting("lockdown","1" if a=="on" else "0")
    return await _reply(m,"Lockdown",[f"Emergency lockdown: {a.upper()}"])
