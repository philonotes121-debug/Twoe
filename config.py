"""Central configuration. Secrets are environment-only; no host/provider fallbacks."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv("app.env")
    load_dotenv(".env")
except Exception:
    pass


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default

BOT_TOKEN = _env("BOT_TOKEN")
BOT_NAME = _env("BOT_NAME", "UPSC Course Zone by Professor")
AI_NAME = "AI Helper"
CREDIT = _env("CREDIT", "Professor 🥼")
ADMIN_ID = _int("ADMIN_ID", 0)
ADMIN_USERNAME = _env("ADMIN_USERNAME", "").lstrip("@")
ADMIN_SECONDARY_SECRET = _env("ADMIN_SECONDARY_SECRET")

BACKUP_CHANNEL = _env("BACKUP_CHANNEL", "")
BACKUP_CHAT_ID = _env("BACKUP_CHAT_ID", "")
HELP_BOT_USERNAME = _env("HELP_BOT_USERNAME", "")


def backup_username() -> str:
    raw = BACKUP_CHANNEL.strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    raw = raw.split("?")[0].strip("/")
    if raw.startswith("+") or raw.startswith("joinchat"):
        return ""
    return "@" + raw.lstrip("@") if raw else ""


def backup_chat_ref():
    if BACKUP_CHAT_ID:
        try:
            return int(BACKUP_CHAT_ID)
        except ValueError:
            return BACKUP_CHAT_ID
    return backup_username()


def backup_link() -> str:
    raw = BACKUP_CHANNEL.strip()
    if raw.startswith("http"):
        return raw
    return f"https://t.me/{raw.lstrip('@')}" if raw else ""

PROFESSOR_CONTACT_LINK = ""
PAYMENT_HELP_LINK = ""

# Prefer a usable PostgreSQL/SQLite URL. Vercel/Neon integrations may expose one
# of several Postgres variable names; an old/accidental MongoDB URI must never
# be handed to SQLAlchemy because this application uses SQLAlchemy ORM models.
_DATABASE_URL_CANDIDATES = (
    "DATABASE_URL",
    "POSTGRES_URL",
    "POSTGRES_PRISMA_URL",
    "POSTGRES_URL_NON_POOLING",
    "DATABASE_URL_UNPOOLED",
    "NEON_DATABASE_URL",
    "NEON_DATABASE_URL_UNPOOLED",
)

def _looks_like_sql_url(value: str) -> bool:
    v = (value or "").strip().lower()
    return v.startswith((
        "postgres://", "postgresql://", "postgresql+asyncpg://",
        "postgresql+psycopg://", "sqlite://", "sqlite+aiosqlite://",
    ))

DATABASE_URL = ""
for _db_env_name in _DATABASE_URL_CANDIDATES:
    _candidate = _env(_db_env_name)
    if _looks_like_sql_url(_candidate):
        DATABASE_URL = _candidate
        break
if not DATABASE_URL:
    # Preserve the raw value for diagnostics/fallback handling below.
    DATABASE_URL = _env("DATABASE_URL")
PORT = _int("PORT", 8080)
VERCEL_URL = _env("VERCEL_URL")
WEBAPP_BASE_URL = (_env("WEBAPP_BASE_URL") or (f"https://{VERCEL_URL}" if VERCEL_URL else "")).rstrip("/")

GEMINI_API_KEY = _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
GEMINI_MODELS = [m.strip() for m in _env("GEMINI_MODELS", _env("GEMINI_MODEL_PRIMARY")).split(",") if m.strip()]
GEMINI_MODELS += [m.strip() for m in _env("GEMINI_MODEL_FALLBACK").split(",") if m.strip()]

TIMEZONE = _env("BOT_TIMEZONE", "Asia/Kolkata")
EXAM_NAME = _env("EXAM_NAME", "UPSC Prelims 2027")
# Official UPSC calendar date; can be overridden explicitly if required.
EXAM_DATE = _env("EXAM_DATE", "2027-05-23")
GOOD_MORNING_TIME = _env("GOOD_MORNING_TIME", "06:00")
COUNTDOWN_TIME = _env("COUNTDOWN_TIME", "07:30")
QUIZ_TIME = _env("QUIZ_TIME", "08:00")
GOOD_NIGHT_TIME = _env("GOOD_NIGHT_TIME", "23:00")

DEL_PERSONAL_HOURS = _int("DEL_PERSONAL_HOURS", 24)
DEL_BROADCAST_HOURS = _int("DEL_BROADCAST_HOURS", 48)
DEL_ROUTINE_HOURS = _int("DEL_ROUTINE_HOURS", 6)
DEL_WELCOME_MIN = _int("DEL_WELCOME_MIN", 2)
DEL_QUIZ_HOURS = _int("DEL_QUIZ_HOURS", 12)

PAYMENT_PROVIDER_TOKEN = _env("PAYMENT_PROVIDER_TOKEN")
STARS_PER_INR = float(_env("STARS_PER_INR", "0") or 0)
BACKUP_FAIL_OPEN_GROUPS = _env("BACKUP_FAIL_OPEN_GROUPS", "0") == "1"
REQUIRE_BACKUP_FOR_FEATURES = _env("REQUIRE_BACKUP_FOR_FEATURES", "0") == "1"

REFERRAL_SIGNING_SECRET = _env("REFERRAL_SIGNING_SECRET")
REFERRAL_TOKEN_TTL_DAYS = _int("REFERRAL_TOKEN_TTL_DAYS", 365)
REFERRAL_DAILY_REWARD_CAP = _int("REFERRAL_DAILY_REWARD_CAP", 20)
PERSONAL_DATA_HMAC_KEY = _env("PERSONAL_DATA_HMAC_KEY")
MAX_WEB_BODY_BYTES = _int("MAX_WEB_BODY_BYTES", 256_000)
CRON_STALE_MINUTES = _int("CRON_STALE_MINUTES", 10)

DATA_ENCRYPTION_KEY = _env("DATA_ENCRYPTION_KEY")
CRON_SECRET = _env("CRON_SECRET")
OUTBOUND_PROXY = _env("OUTBOUND_PROXY")
ADMIN_OFFLINE_IDLE_MIN = _int("ADMIN_OFFLINE_IDLE_MIN", 20)

COMMUNITY_PRICE_INR = _int("COMMUNITY_PRICE_INR", 800)
CA_PRICE_INR = _int("CA_PRICE_INR", 200)
COMMUNITY_GROUP_LINK = _env("COMMUNITY_GROUP_LINK")
CA_DISPLAY_RATING = _env("CA_DISPLAY_RATING", "4.5")
CA_REVIEW_COUNT = _int("CA_REVIEW_COUNT", 50)
NOTION_API_TOKEN = _env("NOTION_API_TOKEN")
NOTION_CA_SOURCE_ID = _env("NOTION_CA_SOURCE_ID")
NOTION_EDITORIAL_SOURCE_ID = _env("NOTION_EDITORIAL_SOURCE_ID")
NOTION_PLACE_NEWS_SOURCE_ID = _env("NOTION_PLACE_NEWS_SOURCE_ID")
NOTION_INTERNATIONAL_ORGS_SOURCE_ID = _env("NOTION_INTERNATIONAL_ORGS_SOURCE_ID")
NOTION_ACCESS_SOURCE_ID = _env("NOTION_ACCESS_SOURCE_ID")
NOTION_VERSION = _env("NOTION_VERSION", "2022-06-28")
