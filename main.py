import logging
import asyncio
import os
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import HTTPException, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update, BotCommand, BotCommandScopeDefault, BotCommandScopeChat, ErrorEvent, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select, func

from config import BOT_TOKEN, WEBAPP_BASE_URL, PORT, BOT_NAME, ADMIN_ID
from database import (
    init_db, seed_sections, seed_courses, migrate_v2, migrate_v3, migrate_v4, migrate_v5,
    async_session, Section, Course, ConnectedChat, User, IS_SQLITE, DATABASE_URL,
)
from keyboards import get_line
from webapp_template import render_section_page
from security import (
    SecurityMiddleware, BackupGateCallbackMiddleware,
    register_dispatcher_auto_heal, state_backup_loop, restore_state_backup,
    _save_state_snapshot, daily_data_backup_task, morning_motivation_task,
    night_motivation_task,
)
from admin_handlers import AI_STATE
import user_handlers
import admin_handlers
import access
import features
import extras
import privacy
import manager_handlers
import scheduler_tasks
import services as sv
import config
import premium
import admin_suite
import production_hardening
from miniapp_portal import render_lms, render_ca, render_community

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# aiogram 3.7+ requires parse_mode via DefaultBotProperties, not a direct kwarg.
privacy.apply_outbound_proxy_env()
privacy.install_log_scrubber()
_session = privacy.make_session()
privacy.protect_session_middleware(_session)
bot: Bot | None = None
dp = Dispatcher(storage=MemoryStorage())

# 🛡️ ZERO-TRUST SECURITY FIREWALL ACTIVATION
dp.message.outer_middleware(features.LockdownMiddleware())
dp.message.outer_middleware(production_hardening.AdminPublicCommandIsolation())
dp.message.outer_middleware(production_hardening.AdminCommandAudit())
dp.callback_query.outer_middleware(features.LockdownMiddleware())
dp.message.outer_middleware(features.RefCapture())
dp.message.outer_middleware(premium.PhoneGateMiddleware())
dp.callback_query.outer_middleware(premium.PhoneGateMiddleware())
dp.message.middleware(SecurityMiddleware())
dp.callback_query.middleware(BackupGateCallbackMiddleware())  # gates inline-button taps too, not just commands
dp.message.middleware(access.LmsGateMiddleware())
dp.callback_query.middleware(access.LmsGateMiddleware())

@dp.message.outer_middleware()
async def _touch_admin_mw(handler, event, data):
    # any admin message counts as "Professor is online" for offline auto-detection
    if event.from_user and event.from_user.id == ADMIN_ID:
        await sv.mark_admin_seen()
    return await handler(event, data)


@dp.callback_query.outer_middleware()
async def _touch_admin_cb_mw(handler, event, data):
    if event.from_user and event.from_user.id == ADMIN_ID:
        await sv.mark_admin_seen()
    return await handler(event, data)


# Auto-recovers the dispatcher from certain classes of failure instead of the
# whole container needing a manual restart-loop.
register_dispatcher_auto_heal(dp)

# Fetched once at startup — used so the Mini App's "Buy Now" button can build
# a https://t.me/<username>?start=buy_<id> deep link back into this exact bot.
BOT_USERNAME = ""

# Admin commands registered before the generic user fallback (which lives at
# the bottom of user_handlers' router) so they're never swallowed by it.
dp.include_router(admin_handlers.router)
dp.include_router(access.router)
dp.include_router(manager_handlers.router)
dp.include_router(features.router)
dp.include_router(extras.router)   # inbox, chats, campaigns, analytics, toggles
dp.include_router(premium.router)
dp.include_router(admin_suite.router)
dp.include_router(user_handlers.router)       # MUST stay last (catch-all fallback)


@dp.error()
async def global_error_handler(event: ErrorEvent):
    """Catches any exception raised inside a handler so a bug never shows up
    to the user (or Professor) as total silence — logs it AND pings the
    admin with the short reason, which makes 'command not working' reports
    self-diagnosing instead of a mystery."""
    logger.exception(f"Unhandled error while processing update: {event.exception}")
    try:
        who = None
        update = event.update
        if update.message:
            who = update.message.from_user.id
        elif update.callback_query:
            who = update.callback_query.from_user.id
        await bot.send_message(
            ADMIN_ID,
            f"⚠️ <b>Bot error</b>\n\nUser: {who}\nError: <code>{str(event.exception)[:500]}</code>",
        )
    except Exception:
        pass
    return True


@dp.message(__import__("aiogram").filters.Command("menu"))
async def _menu_cmd(message):
    if message.from_user.id == ADMIN_ID: return
    u = await sv.ensure_user(message.from_user)
    if not u.phone_verified:
        await premium.show_phone_gate(message); return
    await message.answer("📚 LMS", reply_markup=__import__("keyboards").main_menu_kb())


@dp.message(__import__("aiogram").filters.Command("account"))
async def _account_cmd(message):
    if message.from_user.id == ADMIN_ID: return
    u=await sv.ensure_user(message.from_user)
    if not u.phone_verified: return await premium.show_phone_gate(message)
    from premium import active_membership
    comm=await active_membership(u.id,"community"); ca=await active_membership(u.id,"ca_tracker")
    from access import status_of
    st=await status_of(u.id)
    await message.answer(f"👤 <b>Account</b>\nLMS: {st}\nCommunity: {'active' if comm else 'inactive'}\nCA Tracker: {'active' if ca else 'inactive'}", reply_markup=__import__("keyboards").main_menu_kb())


@dp.message(__import__("aiogram").filters.Command("study"))
async def _study_cmd(message):
    if message.from_user.id == ADMIN_ID: return
    u=await sv.ensure_user(message.from_user)
    if not u.phone_verified: return await premium.show_phone_gate(message)
    await message.answer("🎯 Study tools: target, streak and reminders are available in LMS.", reply_markup=__import__("keyboards").main_menu_kb())


@dp.message(__import__("aiogram").filters.Command("support"))
async def _support_cmd(message):
    if message.from_user.id == ADMIN_ID: return
    u=await sv.ensure_user(message.from_user)
    if not u.phone_verified: return await premium.show_phone_gate(message)
    await message.answer("💬 Send your issue here. It will reach Admin.", reply_markup=__import__("keyboards").contact_cancel_kb())


@dp.message(__import__("aiogram").filters.Command("ask"))
async def _ask_cmd(message, state):
    if message.from_user.id == ADMIN_ID: return
    u=await sv.ensure_user(message.from_user)
    if not u.phone_verified: return await premium.show_phone_gate(message)
    from user_handlers import ProfessorAIFlow
    await state.set_state(ProfessorAIFlow.chatting)
    await message.answer("🤖 AI Helper ready. Apna sawaal bhejiye.", reply_markup=__import__("aiogram").types.InlineKeyboardMarkup(inline_keyboard=[[__import__("aiogram").types.InlineKeyboardButton(text="⬅ LMS",callback_data="menu:main")]]))

USER_COMMANDS = [
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
]

ADMIN_COMMANDS = [
    BotCommand(command="adminhelp", description="Admin control centre"),
    BotCommand(command="lms", description="LMS access & gate"),
    BotCommand(command="users", description="Users & profiles"),
    BotCommand(command="orders", description="Payments & grants"),
    BotCommand(command="content", description="Courses & sections"),
    BotCommand(command="subscriptions", description="Community & CA plans"),
    BotCommand(command="promo", description="Promo + 12h group broadcast"),
    BotCommand(command="broadcast", description="Broadcast messages"),
    BotCommand(command="schedule", description="Scheduled campaigns"),
    BotCommand(command="inbox", description="Support inbox"),
    BotCommand(command="groups", description="Connected groups/chats"),
    BotCommand(command="referrals", description="Referral audit"),
    BotCommand(command="analytics", description="Analytics"),
    BotCommand(command="ai", description="AI controls"),
    BotCommand(command="presence", description="Admin online/offline"),
    BotCommand(command="security", description="Security posture"),
    BotCommand(command="privacy", description="Privacy audit"),
    BotCommand(command="health", description="Runtime health"),
    BotCommand(command="backup", description="Data backup"),
    BotCommand(command="recovery", description="State recovery"),
    BotCommand(command="moderation", description="Ban/block/antispam"),
    BotCommand(command="resources", description="Resources"),
    BotCommand(command="notion", description="Notion / CA sync"),
    BotCommand(command="countdown", description="UPSC countdown"),
    BotCommand(command="settings", description="Runtime settings"),
    BotCommand(command="audit", description="Audit trail"),
    BotCommand(command="export", description="Controlled export"),
    BotCommand(command="system", description="System status"),
    BotCommand(command="lockdown", description="Emergency lockdown"),
]

# ========================================================
# ⚙️ 24-HOUR AUTO PROMOTION TASK (ZERO-COST MARKETING)
# ========================================================
async def daily_promotional_task(bot_instance: Bot):
    while True:
        await asyncio.sleep(24 * 3600)  # Runs every 24 Hours
        try:
            me = await bot_instance.get_me()
            bot_url = f"https://t.me/{me.username}?start=start"
            btn = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🤖 Message Official Bot", url=bot_url)]
            ])
            text = (
                f"🎓 <b>Welcome to the Official {BOT_NAME} Community!</b>\n\n"
                f"For premium courses, instant support, and exclusive study material, "
                f"interact with our Official Bot below. 👇"
            )
            
            async with async_session() as session:
                result = await session.execute(select(ConnectedChat))
                chats = result.scalars().all()
                for chat in chats:
                    try:
                        await bot_instance.send_message(chat.id, text, reply_markup=btn, parse_mode="HTML")
                    except Exception as e:
                        logger.error(f"Failed to send 24h message to {chat.id}: {e}")
        except Exception as e:
            logger.error(f"Daily task loop error: {e}")


def _bot_available() -> bool:
    return bot is not None


def _require_bot() -> Bot:
    if bot is None:
        raise HTTPException(status_code=503, detail="Telegram bot is not configured")
    return bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot, BOT_USERNAME

    await init_db()
    await seed_sections()
    await seed_courses()
    await migrate_v2()  # idempotent — restructures an existing DB to the v2 home-screen layout
    await migrate_v3()  # idempotent — collapses to the simplified v3 home screen
    await migrate_v4()  # idempotent — adds Aisha columns/tables to a live DB
    await migrate_v5()  # encrypted phone + paid membership tables
    await premium.ensure_system_products()
    await sv.load_runtime_settings()
    saved_backup = await sv.get_setting("backup_channel", "")
    if saved_backup:
        config.BACKUP_CHANNEL = saved_backup

    # Restore shadow-bans/freezes/mutes/threat-fingerprints AND the /toggle_ai
    # ON-OFF state from the last periodic snapshot. These functions already
    # existed in security.py but were never actually called from anywhere —
    # so every container restart silently reset all of it, including the AI
    # toggle flipping back to its default.
    # Redeploy-proof state: restore file + promos from the database when the disk was wiped.
    import json as _json, os as _os
    from security import STATE_BACKUP_PATH
    saved = await sv.get_setting("state_backup_json", "")
    if saved and not _os.path.exists(STATE_BACKUP_PATH):
        open(STATE_BACKUP_PATH, "w").write(saved)
    try:
        saved_promos=_json.loads(await sv.get_setting("promos_json", "{}")); admin_handlers.ACTIVE_PROMOS.update(saved_promos)
    except Exception:
        logger.exception("promo restore failed")
    restore_state_backup(AI_STATE)

    # A Vercel deployment must remain healthy even before the owner has added
    # Telegram/Gemini secrets. Never construct Bot() at module import time: a
    # missing or malformed BOT_TOKEN otherwise turns every HTTP request into a
    # 500 FUNCTION_INVOCATION_FAILED.
    bot = None
    if BOT_TOKEN:
        try:
            bot = Bot(token=BOT_TOKEN, session=_session, default=DefaultBotProperties(parse_mode="HTML"))
            app.state.bot = bot
        except Exception as exc:
            logger.warning("Telegram bot initialization skipped because BOT_TOKEN is missing/invalid: %s", type(exc).__name__)
            bot = None
            app.state.bot = None
    else:
        app.state.bot = None
        logger.warning("BOT_TOKEN is not configured; web health endpoints remain available, Telegram bot features are disabled.")

    if bot is not None:
        try:
            me = await bot.get_me()
            BOT_USERNAME = me.username or ""
        except Exception:
            logger.exception("Failed to fetch bot username via get_me() — Buy Now deep links will break!")

        try:
            await bot.set_my_commands([BotCommand(command="start", description="Verify & open LMS")], scope=BotCommandScopeDefault())
            if ADMIN_ID:
                await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=ADMIN_ID))
        except TelegramBadRequest:
            logger.exception("Failed to set bot commands")

        if WEBAPP_BASE_URL:
            webhook_url = f"{WEBAPP_BASE_URL}/webhook"
            try:
                await bot.set_webhook(webhook_url, drop_pending_updates=True, secret_token=privacy.webhook_secret(),
                                      allowed_updates=dp.resolve_used_update_types())
                logger.info(f"Webhook set to {webhook_url}")
            except Exception:
                logger.exception("Failed to set Telegram webhook — check WEBAPP_BASE_URL and Telegram connectivity")
        else:
            logger.warning("WEBAPP_BASE_URL not set — webhook NOT configured yet.")

        # Background loops run only on persistent local/VM deployments; Vercel uses /api/cron.
        if not os.environ.get("VERCEL"):
            asyncio.create_task(daily_promotional_task(bot))
    # Periodic snapshot so bans/freezes/AI-toggle survive the next restart
    # (every STATE_BACKUP_INTERVAL_SEC — was defined in security.py but
    # never scheduled, so restores above always had nothing to restore from
    # on a fresh container until this ran at least once).
    if not os.environ.get("VERCEL"):
        asyncio.create_task(state_backup_loop(AI_STATE))
    # Daily full data export to admin + morning/night motivational broadcasts
    if bot is not None and not os.environ.get("VERCEL"):
        asyncio.create_task(daily_data_backup_task(bot))
    if bot is not None and not os.environ.get("VERCEL"):
        scheduler_tasks.start(bot)   # GM/GN/countdown/quiz/deletions/digest/weekly (replaces old morning/night loops)

    yield

    if bot is not None and not os.environ.get("VERCEL"):
        scheduler_tasks.stop()
    _save_state_snapshot(AI_STATE)
    if bot is not None and not os.environ.get("VERCEL"):
        try:
            await bot.delete_webhook()
        except Exception:
            logger.exception("Failed to delete webhook during shutdown")
        await bot.session.close()
    bot = None
    app.state.bot = None


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' https://telegram.org; connect-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'"
    return response


@app.post("/webhook")
async def telegram_webhook(request: Request):
    current_bot = _require_bot()
    if not privacy.valid_webhook_header(request.headers.get("x-telegram-bot-api-secret-token")):
        raise HTTPException(status_code=404)
    length = request.headers.get("content-length")
    if length and int(length) > config.MAX_WEB_BODY_BYTES:
        raise HTTPException(status_code=413)
    data = await request.json()
    uid = data.get("update_id")
    if uid is not None and not await production_hardening.claim_update(uid):
        return {"ok": True, "duplicate": True}
    try:
        update = Update(**data)
        await dp.feed_update(current_bot, update)
        return {"ok": True}
    except Exception:
        if uid is not None:
            await production_hardening.release_update(uid)
        raise


@app.get("/")
@app.get("/api/health")
async def health():
    provider = "vercel" if os.environ.get("VERCEL") else "self_hosted"
    try:
        hb = await sv.get_runtime_heartbeat("cron")
    except Exception:
        return JSONResponse(
            {"status": "unavailable", "database": "unavailable", "provider": provider},
            status_code=503,
        )
    return {
        "status": "ok",
        "database": "ok",
        "database_storage": "ephemeral_sqlite" if IS_SQLITE else "persistent_postgresql",
        "database_config": (
            "sqlite_fallback" if IS_SQLITE and DATABASE_URL else
            "sqlite_default" if IS_SQLITE else
            "postgresql"
        ),
        "cron_heartbeat": hb or None,
        "provider": provider,
        "telegram_bot": "configured" if bot is not None else "not_configured",
    }


@app.get("/api/cron")
async def api_cron(request: Request):
    current_bot = _require_bot()
    # Vercel Cron uses Authorization: Bearer <CRON_SECRET>. A header-only
    # fallback is retained for controlled/manual invocations; query-string
    # secrets are deliberately rejected because URLs can be logged or cached.
    auth = request.headers.get("authorization", "")
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    secret = bearer or request.headers.get("x-cron-secret", "")
    if not config.CRON_SECRET or not __import__("hmac").compare_digest(str(secret), config.CRON_SECRET):
        raise HTTPException(status_code=404)
    from scheduler_tasks import serverless_tick
    return await serverless_tick(current_bot)


@app.get("/webapp/lms", response_class=HTMLResponse)
async def webapp_lms(request: Request):
    uid = privacy.verify_init_data(request.headers.get("x-init-data", ""))
    if not uid or not await premium.can_access_lms(uid):
        return HTMLResponse("<h3>Access required</h3><p>Verify your number and complete LMS access.</p>", status_code=403)
    return render_lms()


@app.get("/webapp/ca", response_class=HTMLResponse)
async def webapp_ca(request: Request):
    uid = privacy.verify_init_data(request.headers.get("x-init-data", ""))
    if not uid or not await premium.has_active_plan(uid, "ca_tracker"):
        return HTMLResponse("<h3>CA Tracker Pro</h3><p>Active monthly subscription required.</p>", status_code=403)
    return render_ca()


@app.get("/webapp/community", response_class=HTMLResponse)
async def webapp_community(request: Request):
    uid=privacy.verify_init_data(request.headers.get("x-init-data", ""))
    if not uid or not await premium.has_active_plan(uid,"community"):
        return HTMLResponse("<h3>Join Our Community</h3><p>Active monthly subscription required.</p>", status_code=403)
    return render_community()




@app.get("/api/lms/sections")
async def api_lms_sections(request: Request):
    uid=privacy.verify_init_data(request.headers.get("x-init-data", ""))
    if not uid or not await premium.can_access_lms(uid): return JSONResponse({"error":"access"},status_code=403)
    async with async_session() as session:
        rows=(await session.execute(select(Section).where(Section.is_active==True).order_by(Section.parent_id,Section.sort_order,Section.id))).scalars().all()
    return [{"key":x.key,"name":x.name,"parent_id":x.parent_id} for x in rows]


@app.get("/api/course-link/{course_id}")
async def api_course_link(course_id:int, request:Request):
    current_bot = _require_bot()
    uid=privacy.verify_init_data(request.headers.get("x-init-data", ""))
    if not uid or not await premium.can_access_lms(uid): return JSONResponse({"error":"access"},status_code=403)
    async with async_session() as session: c=await session.get(Course,course_id)
    if not c or not c.is_active or c.system_product: return JSONResponse({"error":"course"},status_code=404)
    me=await current_bot.get_me(); return {"url":f"https://t.me/{me.username}?start=buy_{course_id}"}


@app.get("/api/ca/items")
async def api_ca_items(request:Request, source:str="all", topic:str="", date:str="", q:str=""):
    uid=privacy.verify_init_data(request.headers.get("x-init-data", ""))
    if not uid or not await premium.has_active_plan(uid,"ca_tracker"): return JSONResponse({"error":"subscription"},status_code=403)
    from notion_sync import get_ca_items
    return await get_ca_items({"source":source,"topic":topic,"date":date,"q":q})


@app.get("/api/ca/dataset/{dataset}")
async def api_ca_dataset(dataset:str, request:Request, topic:str="", date:str="", q:str=""):
    uid=privacy.verify_init_data(request.headers.get("x-init-data", ""))
    if not uid or not await premium.has_active_plan(uid,"ca_tracker"):
        return JSONResponse({"error":"subscription"},status_code=403)
    if dataset not in {"daily","editorial","place_news","international"}:
        return JSONResponse({"error":"dataset"},status_code=404)
    from notion_sync import get_ca_dataset
    return await get_ca_dataset(dataset,{"topic":topic,"date":date,"q":q})


@app.get("/api/community/dashboard")
async def api_community_dashboard(request:Request):
    uid=privacy.verify_init_data(request.headers.get("x-init-data", ""))
    if not uid or not await premium.has_active_plan(uid,"community"): return JSONResponse({"error":"subscription"},status_code=403)
    from database import UserActivity, AiMemory, Streak
    async with async_session() as s:
        activity=(await s.execute(select(func.count()).select_from(UserActivity).where(UserActivity.user_id==uid))).scalar() or 0
        aiq=(await s.execute(select(func.count()).select_from(AiMemory).where(AiMemory.user_id==uid, AiMemory.role=="user"))).scalar() or 0
        st=await s.get(Streak,uid)
    return {"activity":activity,"ai_questions":aiq,"streak":int(st.current if st else 0)}


@app.post("/api/community/evaluate")
async def api_community_evaluate(request:Request):
    uid=privacy.verify_init_data(request.headers.get("x-init-data", ""))
    if not uid or not await premium.has_active_plan(uid,"community"): return JSONResponse({"error":"subscription"},status_code=403)
    body=await request.json(); answer=str(body.get("answer") or "")[:7000]
    if not answer: return JSONResponse({"error":"answer required"},status_code=400)
    import ai
    prompt="Evaluate this UPSC answer briefly. Give score out of 10, 2 strengths, 2 improvements, and one next action. Do not claim official UPSC evaluation.\n"+answer
    feedback=await ai.safe_generate(prompt,max_tokens=300,temperature=0.2,tier="lite")
    return {"feedback":feedback or "Evaluation service unavailable."}



@app.get("/webapp/section/{section_key}", response_class=HTMLResponse)
async def webapp_section(section_key: str):
    if section_key == "all":
        return render_section_page("all", "All Courses", get_line(), BOT_USERNAME)
    async with async_session() as session:
        result = await session.execute(select(Section).where(Section.key == section_key))
        section = result.scalar_one_or_none()
    title = section.name if section else section_key.replace("_", " ").title()
    return render_section_page(section_key, title, get_line(), BOT_USERNAME)


@app.get("/api/courses")
async def api_courses(section_key: str, request: Request):
    uid = privacy.verify_init_data(request.headers.get("x-init-data", ""))
    if not uid or not await premium.can_access_lms(uid):
        return JSONResponse({"error": "access"}, status_code=403)
    async with async_session() as session:
        if section_key == "all":
            result = await session.execute(select(Course).where(Course.is_active == True, Course.system_product.is_(None)))  # noqa: E712
            courses = result.scalars().all()
        else:
            result = await session.execute(select(Section).where(Section.key == section_key))
            section = result.scalar_one_or_none()
            if not section:
                return JSONResponse([])

            # Aggregate this section's own courses PLUS every descendant
            # section's courses (e.g. "UPSC Optional" has no courses of its
            # own — they live on its per-subject children) so a parent
            # section is never shown as empty when its children have data.
            all_sections_result = await session.execute(select(Section))
            all_sections = all_sections_result.scalars().all()
            children_by_parent = {}
            for s in all_sections:
                children_by_parent.setdefault(s.parent_id, []).append(s)

            def collect_ids(root_id):
                ids = [root_id]
                for child in children_by_parent.get(root_id, []):
                    ids.extend(collect_ids(child.id))
                return ids

            section_ids = set(collect_ids(section.id))
            seen = {}
            for s in all_sections:
                if s.id in section_ids:
                    for c in s.courses:
                        if c.is_active and c.system_product is None:
                            seen[c.id] = c
            courses = list(seen.values())

        community_included = await premium.has_active_plan(uid, "community")
        payload = [
            {
                "id": c.id, "name": c.name, "faculty": c.faculty, "medium": c.medium,
                "notes": c.notes, "price": float(c.price) if c.price is not None else None,
                "included": community_included,
            }
            for c in courses
        ]
    return JSONResponse(payload)


if __name__ == "__main__":
    import uvicorn
    # Pass the app object directly (not the "main:app" string) — using the
    # string form makes uvicorn re-import this file as a second module,
    # which re-runs all the router registration code and crashes with
    # "Router is already attached" the second time around.
    uvicorn.run(app, host="0.0.0.0", port=PORT, server_header=False, access_log=False)
