import random
import logging

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from config import WEBAPP_BASE_URL, PAYMENT_HELP_LINK, PROFESSOR_CONTACT_LINK

logger = logging.getLogger(__name__)

# Telegram Mini Apps refuse to open over anything but https:// — if
# WEBAPP_BASE_URL is ever misconfigured (http://, trailing slash typo, a
# non-URL value), every webapp button in the bot would silently fail to
# open with no error shown to the user. Catch it loudly at import time
# instead, once, so it shows up in the deploy logs immediately.
def _validate_webapp_base_url(url: str) -> str:
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned:
        logger.warning("WEBAPP_BASE_URL is empty — all Mini App buttons will be broken until it's set.")
    elif not cleaned.startswith("https://"):
        logger.warning(
            f"WEBAPP_BASE_URL='{cleaned}' does not start with https:// — Telegram will refuse to "
            "open the Mini App for every button using it. Fix this env var on Railway."
        )
    return cleaned


WEBAPP_BASE_URL = _validate_webapp_base_url(WEBAPP_BASE_URL)

# ---------------- header tagline ----------------
TAGLINE = "Verified courses. Trusted faculty. Lifetime access."


def get_line() -> str:
    return TAGLINE


# ---------------- welcome messages ----------------
# A different short welcome message for (almost) every user — picked
# randomly per /start so the bot doesn't feel copy-pasted. Kept short &
# Hinglish-friendly to match Professor's own tone.
WELCOME_MESSAGES = [
    "Swagat hai, {name}! Aapki UPSC/State PSC journey ke liye sahi jagah pe aa gaye ho.",
    "Namaste {name} 🙏 — Professor ke curated courses ab ek click door hain.",
    "Hello {name}! Tayyari ko next level pe le jaane ka time aa gaya hai.",
    "Welcome {name} — verified faculty, sahi price, lifetime access. Let's begin.",
    "{name}, aapka istaqbaal hai! Neeche se apna section choose karo.",
    "Good to see you, {name}! Course dhoondhna ab bohot easy ho gaya hai.",
    "Namaskar {name} — Professor ki taraf se best courses ka collection yahin hai.",
    "Hey {name}! Ek qadam aur apni manzil ke kareeb — chuno apna course.",
    "{name}, tayyari shuru karte hain — sahi resource, sahi guidance.",
    "Welcome aboard, {name}! Foundation se Test Series tak, sab kuch yahin milega.",
]


def get_welcome_message(name: str) -> str:
    safe_name = (name or "Aspirant").strip() or "Aspirant"
    return random.choice(WELCOME_MESSAGES).format(name=safe_name)


# ---------------- section titles (for leaf sections that route to Mini App) ----------------
SECTION_TITLES = {
    "upsc_foundation": "UPSC Foundation",
    "upsc_csat": "CSAT",
    "upsc_pyq": "PYQ / Answer Practice",
    "upsc_crash": "UPSC Crash Course",
    "upsc_ca": "Current Affairs",
    "upsc_prelims": "Prelims Specific",
    "upsc_mains": "Mains Specific",
    "upsc_ts_prelims": "Prelims Test Series 2027",
    "upsc_ts_mains": "Mains Test Series 2027",
    "subj_economy": "Economics",
    "subj_geography": "Geography",
    "subj_polity": "Polity & Governance",
    "subj_environment_scitech": "Environment + Sci-Tech",
    "subj_history": "History",
    "subj_ir": "International Relations",
    "subj_public_admin": "Public Administration",
    "upsc_ethics": "Ethics (GS-4)",
    "upsc_essay": "Essay",
    "upsc_subject_specific": "Other Subject Courses",
    "uppsc": "UPPSC",
    "bpsc": "BPSC",
    "rpsc": "RPSC",
    "jpsc": "JPSC",
    "ukpsc": "UKPSC",
    "net_jrf": "NET / JRF",
    "net_jrf_all": "NET / JRF — All Subjects",
    "combo_deals": "Combo Deals & Bundles",
    "other": "Other Courses",
    "other_misc": "Other Courses",
}


# ---------------- FSM states ----------------
class BuyFlow(StatesGroup):
    waiting_for_gift_card = State()


class AdminAddCourse(StatesGroup):
    name = State()
    faculty = State()
    medium = State()
    notes = State()
    price = State()
    section = State()


class AdminBroadcast(StatesGroup):
    waiting_message = State()


class ContactFlow(StatesGroup):
    waiting_for_message = State()


class AdminReplyFlow(StatesGroup):
    waiting_for_reply = State()


class ProfessorAIFlow(StatesGroup):
    """Tracks 'user is inside Chat with AI Helper'. Needed so that when the
    admin's global AI toggle (/toggle_ai) is OFF — Professor is online — the AI
    still answers questions asked specifically inside this flow, without
    hijacking every random message elsewhere in the bot."""
    chatting = State()


# ---------------- keyboards ----------------
def phone_verification_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Verify Mobile Number", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True, input_field_placeholder="Tap to verify your number",
    )


def main_menu_kb() -> InlineKeyboardMarkup:
    """Post-verification menu: categories link/open the same LMS Mini App; no course cards are rendered in chat."""
    rows = []
    if WEBAPP_BASE_URL:
        rows.append([InlineKeyboardButton(text="📚 Open LMS", web_app=WebAppInfo(url=f"{WEBAPP_BASE_URL}/webapp/lms"))])
    rows += [
        [InlineKeyboardButton(text="⭐ Trending Courses", callback_data="trending:open")],
        [InlineKeyboardButton(text="👤 My Account", callback_data="account:open"),
         InlineKeyboardButton(text="🎁 Referral", callback_data="referral:open")],
        [InlineKeyboardButton(text="👥 Join Our Community ₹800/month", callback_data="plan:community")],
        [InlineKeyboardButton(text="📰 CA TRACKER PRO ₹200/month", callback_data="plan:ca_tracker")],
        [InlineKeyboardButton(text="🤖 AI Helper", callback_data="professor_ai:open"),
         InlineKeyboardButton(text="💬 Support", callback_data="contact:open")],
        [InlineKeyboardButton(text="📅 UPSC 2027 Countdown", callback_data="countdown:open")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def home_kb() -> InlineKeyboardMarkup:
    """Menu for users who joined the backup channel but are not LMS-approved yet."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔓 Unlock LMS (verify mobile)", callback_data="lms:open")],
        [InlineKeyboardButton(text="👤 My Account", callback_data="account:open"),
         InlineKeyboardButton(text="🎁 Referral", callback_data="referral:open")],
        [InlineKeyboardButton(text="👥 Join Our Community ₹800/month", callback_data="plan:community")],
        [InlineKeyboardButton(text="📰 CA TRACKER PRO ₹200/month", callback_data="plan:ca_tracker")],
        [InlineKeyboardButton(text="🤖 AI Helper", callback_data="professor_ai:open"),
         InlineKeyboardButton(text="💬 Support", callback_data="contact:open")],
        [InlineKeyboardButton(text="📅 UPSC 2027 Countdown", callback_data="countdown:open")],
    ])


def miniapp_back_kb(path: str = "/webapp/lms", label: str = "📚 Open LMS") -> InlineKeyboardMarkup:
    if WEBAPP_BASE_URL:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=label, web_app=WebAppInfo(url=f"{WEBAPP_BASE_URL}{path}"))]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[])


def short_inline_kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows])


def state_psc_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="UPPSC", callback_data="sec:uppsc")],
        [InlineKeyboardButton(text="BPSC", callback_data="sec:bpsc")],
        [InlineKeyboardButton(text="RPSC", callback_data="sec:rpsc")],
        [InlineKeyboardButton(text="JPSC", callback_data="sec:jpsc")],
        [InlineKeyboardButton(text="UKPSC", callback_data="sec:ukpsc")],
        [InlineKeyboardButton(text="⬅ Back", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upsc_subsections_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="⌂ Foundation", callback_data="sec:upsc_foundation")],
        [InlineKeyboardButton(text="📗 UPSC Optional", callback_data="upscopt:open")],
        [InlineKeyboardButton(text="⚡ Crash Course", callback_data="sec:upsc_crash")],
        [InlineKeyboardButton(text="📝 Prelims Test Series 2027", callback_data="sec:upsc_ts_prelims")],
        [InlineKeyboardButton(text="📝 Mains Test Series 2027", callback_data="sec:upsc_ts_mains")],
        [InlineKeyboardButton(text="⬅ Back", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def optional_subjects_kb() -> InlineKeyboardMarkup:
    from database import OPTIONAL_SUBJECTS, _slug
    rows = [
        [InlineKeyboardButton(text=f"📗 {subj}", callback_data=f"sec:optional_{_slug(subj)}")]
        for subj in OPTIONAL_SUBJECTS
    ]
    rows.append([InlineKeyboardButton(text="⬅ Back", callback_data="topsec:upsc")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def prelims_mains_kb() -> InlineKeyboardMarkup:
    """Opens the Mini App directly for each — skips the old intermediate
    'leaf section' screen (which only ever showed one more button to press)
    to cut a full navigation step. Trade-off: this bypasses the generic
    empty_section_kb() fallback normally shown when a section has zero
    courses — acceptable here since Prelims/Mains Specific are core,
    always-populated sections."""
    prelims_url = f"{WEBAPP_BASE_URL}/webapp/section/upsc_prelims"
    mains_url = f"{WEBAPP_BASE_URL}/webapp/section/upsc_mains"
    rows = [
        [InlineKeyboardButton(text="◎ Prelims Specific — Open Courses", web_app=WebAppInfo(url=prelims_url))],
        [InlineKeyboardButton(text="♛ Mains Specific — Open Courses", web_app=WebAppInfo(url=mains_url))],
        [InlineKeyboardButton(text="⬅ Back", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subject_specific_kb() -> InlineKeyboardMarkup:
    """Every entry opens its Mini App directly (same one-less-step pattern
    as prelims_mains_kb) — and labels are now just the subject name, no
    faculty names baked in (those change over time and cluttered the menu;
    the Mini App itself already shows faculty per-course). 'Combo Deals &
    Bundles' removed — that concept was dropped earlier in this project."""
    def wa(key, text):
        return [InlineKeyboardButton(text=text, web_app=WebAppInfo(url=f"{WEBAPP_BASE_URL}/webapp/section/{key}"))]

    rows = [
        wa("subj_economy", "💹 Economics"),
        wa("subj_geography", "🗺 Geography"),
        wa("subj_polity", "🏛 Polity & Governance"),
        wa("subj_environment_scitech", "🌱 Environment + Sci-Tech"),
        wa("subj_history", "📜 History"),
        wa("subj_ir", "🌐 International Relations"),
        wa("subj_public_admin", "🏢 Public Administration"),
        wa("upsc_ethics", "⚖️ Ethics (GS-4)"),
        wa("upsc_essay", "✍️ Essay"),
        wa("net_jrf_all", "🎓 NET / JRF"),
        wa("upsc_subject_specific", "📚 Other Subject Courses"),
        [InlineKeyboardButton(text="⬅ Back", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def section_webapp_kb(section_key: str, section_title: str) -> InlineKeyboardMarkup:
    url = f"{WEBAPP_BASE_URL}/webapp/section/{section_key}"
    rows = [
        [InlineKeyboardButton(text=f"📂 Open {section_title} Courses", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(text="⬅ Back", callback_data="menu:back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def all_courses_webapp_kb() -> InlineKeyboardMarkup:
    url = f"{WEBAPP_BASE_URL}/webapp/section/all"
    rows = [
        [InlineKeyboardButton(text="🔍 Open Full Course Catalog", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(text="⬅ Back", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def empty_section_kb() -> InlineKeyboardMarkup:
    """Shown instead of the Mini-App button when a section currently has
    zero listed courses — routes straight into the in-bot Contact Professor
    flow instead of opening an empty catalog."""
    rows = [
        [InlineKeyboardButton(text="💬 Contact Professor for this", callback_data="contact:open")],
        [InlineKeyboardButton(text="⬅ Back", callback_data="menu:back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_method_kb(course_id: int) -> InlineKeyboardMarkup:
    """First payment screen — user picks a method."""
    rows = [
        [InlineKeyboardButton(text="🎁 Amazon Pay Gift Card", callback_data=f"paym:amazon:{course_id}")],
        [InlineKeyboardButton(text="💳 Pay via UPI (+₹10 extra)", callback_data=f"paym:upi:{course_id}")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def amazon_gift_intro_kb(course_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎁 How to buy Amazon Pay Gift Card (any UPI app)", url=PAYMENT_HELP_LINK)],
        [InlineKeyboardButton(text="📤 Send Amazon Pay Gift Card", callback_data=f"sendgc:{course_id}")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gift_card_collect_kb() -> InlineKeyboardMarkup:
    """Shown while we're collecting the gift card proof — up to 3 messages."""
    rows = [
        [InlineKeyboardButton(text="🎁 How to buy Amazon Pay Gift Card (any UPI app)", url=PAYMENT_HELP_LINK)],
        [InlineKeyboardButton(text="✅ Done — I've sent everything", callback_data="gcdone")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upi_contact_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💬 Contact Support for UPI payment", callback_data="contact:open")],
        [InlineKeyboardButton(text="🎁 Use Amazon Pay Gift Card instead", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_order_decision_kb(order_id: int) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="✅ Approve", callback_data=f"adm_ok:{order_id}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"adm_no:{order_id}"),
    ]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def join_channel_kb(channel_username: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📢 Join Backup Channel", url=channel_username if str(channel_username).startswith("http") else f"https://t.me/{str(channel_username).lstrip('@')}")],
        [InlineKeyboardButton(text="✅ I've Joined — Continue", callback_data="checkjoin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def help_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💬 Contact Professor (in this bot)", callback_data="contact:open")],
        [InlineKeyboardButton(text="💬 Contact Support", callback_data="contact:open")],
        [InlineKeyboardButton(text="❓ FAQ", callback_data="faq:open")],
        [InlineKeyboardButton(text="⬅ Back", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def contact_cancel_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💬 Contact Support instead", callback_data="contact:open")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def group_broadcast_kb(bot_username: str, label: str = "🤖 Open Bot") -> InlineKeyboardMarkup:
    """Every message the bot sends into a group — promo, good morning/night,
    an ad, anything — should carry this button so a tap drops the person
    straight into /start (via the ?start=start deep link) instead of them
    having to find and open the bot manually. Callers (daily_promotional_task,
    morning_motivation_task, night_motivation_task, and any future group
    broadcast) should all use this one function so the behaviour stays
    identical everywhere instead of each place building its own button."""
    url = f"https://t.me/{bot_username}?start=start"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=url)]])
