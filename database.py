"""
Database: models + engine/session + initial section-tree seed + full course
catalog seed, all in one file.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, ForeignKey,
    DateTime, Table, Numeric, select
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import os
import logging
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from sqlalchemy import text, inspect, Index
from config import DATABASE_URL
from course_seed_data import COURSE_SEED

Base = declarative_base()

course_sections = Table(
    "course_sections",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("section_id", Integer, ForeignKey("sections.id", ondelete="CASCADE"), primary_key=True),
)


class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True)
    key = Column(String(80), nullable=False, unique=True)
    name = Column(String(120), nullable=False)
    emoji = Column(String(10), default="📘")
    parent_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    courses = relationship("Course", secondary=course_sections, back_populates="sections", lazy="selectin")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    faculty = Column(String(150), default="")
    medium = Column(String(50), default="")
    notes = Column(Text, default="")
    price = Column(Numeric(10, 2), nullable=True)   # NULL = "Coming Soon"
    group_link = Column(String(300), nullable=True)
    is_trending = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    system_product = Column(String(40), nullable=True, index=True)  # community / ca_tracker; excluded from LMS course catalog
    created_at = Column(DateTime, default=datetime.utcnow)

    sections = relationship("Section", secondary=course_sections, back_populates="courses", lazy="selectin")


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(150), nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)
    is_banned = Column(Boolean, default=False)
    has_joined_backup_channel = Column(Boolean, default=False)
    # --- v4 (merged Aisha) ---
    phone = Column(String(30), nullable=True)                 # legacy field; no longer used for verified storage
    phone_enc = Column(Text, nullable=True)                    # encrypted phone, only decrypted in authorized Admin flows
    phone_hash = Column(String(64), nullable=True, index=True) # one-way HMAC for anti-abuse / duplicate detection
    phone_verified = Column(Boolean, default=False)
    phone_verified_at = Column(DateTime, nullable=True)
    referrer_id = Column(BigInteger, nullable=True)
    ref_points = Column(Integer, default=0)
    last_seen = Column(DateTime, nullable=True)
    ban_reason = Column(String(200), nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    status = Column(String(20), default="pending")
    submission_type = Column(String(10), default="text")
    submission_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)


class UserCourse(Base):
    __tablename__ = "user_courses"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow)


class UserActivity(Base):
    __tablename__ = "user_activity"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    step = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    direction = Column(String(10), nullable=False)  # "in" (user->admin) or "out" (admin->user)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ConnectedChat(Base):
    __tablename__ = "connected_chats"

    id = Column(BigInteger, primary_key=True)
    type = Column(String(50)) # 'group', 'supergroup', or 'channel'
    added_at = Column(DateTime, default=datetime.utcnow)
    # --- v4 (merged Aisha) ---
    title = Column(String(250), nullable=True)
    username = Column(String(100), nullable=True)
    enabled = Column(Boolean, default=True)
    morning_on = Column(Boolean, default=True)
    night_on = Column(Boolean, default=True)
    countdown_on = Column(Boolean, default=True)
    quiz_on = Column(Boolean, default=True)
    watch = Column(Boolean, default=False)      # forward every message of this chat to admin inbox




# ======================= v4: tables added by the Aisha merge =======================
class ProcessedUpdate(Base):
    __tablename__ = "processed_updates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    update_id = Column(BigInteger, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class CronFence(Base):
    __tablename__ = "cron_fences"
    id = Column(Integer, primary_key=True, autoincrement=True)
    fence_key = Column(String(160), nullable=False)
    marker = Column(String(80), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    __table_args__ = (Index("ix_cron_fence_key_marker", "fence_key", "marker", unique=True),)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(120), primary_key=True)
    value = Column(Text, default="")


class InboxItem(Base):
    """Maps a message shown to the admin -> original user/chat so replies always route."""
    __tablename__ = "inbox_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_message_id = Column(BigInteger, index=True, nullable=False)
    source_chat_id = Column(BigInteger, nullable=False)
    source_message_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, index=True, nullable=False)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class BroadcastCampaign(Base):
    __tablename__ = "broadcast_campaigns"
    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String(200), default="")
    target = Column(String(50), default="all")
    sent = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)


class BroadcastMessage(Base):
    __tablename__ = "broadcast_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, index=True, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    message_id = Column(BigInteger, nullable=False)


class ScheduledDeletion(Base):
    __tablename__ = "scheduled_deletions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=False)
    message_id = Column(BigInteger, nullable=False)
    delete_after = Column(DateTime, index=True, nullable=False)
    kind = Column(String(30), default="misc")


class Referral(Base):
    __tablename__ = "referrals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    referrer_id = Column(BigInteger, index=True, nullable=False)
    referred_id = Column(BigInteger, unique=True, nullable=False)
    status = Column(String(20), default="pending")          # pending -> verified
    created_at = Column(DateTime, default=datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)


class EventLog(Base):
    __tablename__ = "event_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(30), index=True, nullable=False)   # join / leave / msgs / dm / spam / ai / ...
    chat_id = Column(BigInteger, nullable=True)
    user_id = Column(BigInteger, nullable=True)
    n = Column(Integer, default=1)
    meta = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class DigestItem(Base):
    __tablename__ = "digest_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(30), default="info")
    text = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    sent = Column(Boolean, default=False)


# ---------------- engine / session ----------------
_log = logging.getLogger(__name__)


def _prepare_url(url: str):
    """Return (sqlalchemy_url, connect_args, is_sqlite).

    The application is SQLAlchemy/ORM based, so only PostgreSQL and SQLite URLs
    are valid here. An accidental ``mongodb+srv://`` value must never reach
    ``create_async_engine``; SQLAlchemy has no built-in MongoDB dialect, which is
    exactly what produced the production ``NoSuchModuleError``.

    On Vercel, invalid/missing DB configuration falls back to /tmp SQLite so the
    HTTP function can still boot and report a useful health state. This fallback
    is intentionally ephemeral; production persistence still requires Neon or
    another hosted PostgreSQL URL.
    """
    raw = (url or "").strip()

    if not raw:
        if os.environ.get("VERCEL"):
            _log.warning("DATABASE_URL missing; using ephemeral Vercel SQLite fallback.")
            return "sqlite+aiosqlite:////tmp/aisha.db", {}, True
        os.makedirs("data", exist_ok=True)
        return "sqlite+aiosqlite:///data/aisha.db", {}, True

    lowered = raw.lower()
    if lowered.startswith("mongodb://") or lowered.startswith("mongodb+srv://"):
        _log.error(
            "Unsupported DATABASE_URL scheme %s. This app requires PostgreSQL/SQLite; "
            "falling back to ephemeral Vercel SQLite instead of crashing at import.",
            raw.split(":", 1)[0],
        )
        if os.environ.get("VERCEL"):
            return "sqlite+aiosqlite:////tmp/aisha.db", {}, True
        os.makedirs("data", exist_ok=True)
        return "sqlite+aiosqlite:///data/aisha.db", {}, True

    if lowered.startswith("sqlite://") or lowered.startswith("sqlite+aiosqlite://"):
        if "+aiosqlite" not in lowered:
            raw = raw.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return raw, {}, True

    if lowered.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
        lowered = raw.lower()
    if lowered.startswith("postgresql+psycopg://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql+psycopg://"):]
        lowered = raw.lower()
    elif lowered.startswith("postgresql://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://"):]
        lowered = raw.lower()

    if not lowered.startswith("postgresql+asyncpg://"):
        _log.error(
            "Unsupported DATABASE_URL scheme. Expected PostgreSQL or SQLite; "
            "falling back to ephemeral SQLite.",
        )
        if os.environ.get("VERCEL"):
            return "sqlite+aiosqlite:////tmp/aisha.db", {}, True
        os.makedirs("data", exist_ok=True)
        return "sqlite+aiosqlite:///data/aisha.db", {}, True

    parts = urlsplit(raw)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    ssl_mode = q.pop("sslmode", None)
    q.pop("channel_binding", None)
    connect_args = {}
    if ssl_mode in ("require", "verify-ca", "verify-full", "prefer") or "neon.tech" in (parts.hostname or ""):
        connect_args["ssl"] = True
    normalized = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))
    return normalized, connect_args, False


_URL, _CONNECT_ARGS, IS_SQLITE = _prepare_url(DATABASE_URL)
if IS_SQLITE:
    engine = create_async_engine(_URL, echo=False, connect_args={"timeout": 30})
else:
    # Keep connection health checks enabled for pooled hosted Postgres.
    engine = create_async_engine(
        _URL, echo=False, pool_pre_ping=True, pool_recycle=1800,
        connect_args=_CONNECT_ARGS,
    )
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if IS_SQLITE:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")


# columns added to tables that may already exist in a live (Railway) database
_ADDED_COLUMNS = {
    "users": [
        ("phone", "VARCHAR(30)"), ("phone_enc", "TEXT"), ("phone_hash", "VARCHAR(64)"), ("phone_verified", "BOOLEAN DEFAULT FALSE"), ("phone_verified_at", "TIMESTAMP"),
        ("referrer_id", "BIGINT"), ("ref_points", "INTEGER DEFAULT 0"),
        ("last_seen", "TIMESTAMP"), ("ban_reason", "VARCHAR(200)"),
    ],
    "courses": [("system_product", "VARCHAR(40)")],
    "connected_chats": [
        ("title", "VARCHAR(250)"), ("username", "VARCHAR(100)"),
        ("enabled", "BOOLEAN DEFAULT TRUE"), ("morning_on", "BOOLEAN DEFAULT TRUE"),
        ("night_on", "BOOLEAN DEFAULT TRUE"), ("countdown_on", "BOOLEAN DEFAULT TRUE"),
        ("quiz_on", "BOOLEAN DEFAULT TRUE"), ("watch", "BOOLEAN DEFAULT FALSE"),
    ],
}


async def migrate_v4():
    """Idempotent: adds the v4 columns to pre-existing tables (no-op on a fresh DB)."""
    async with engine.begin() as conn:
        def _do(sync_conn):
            insp = inspect(sync_conn)
            existing_tables = set(insp.get_table_names())
            for table, cols in _ADDED_COLUMNS.items():
                if table not in existing_tables:
                    continue
                have = {c["name"] for c in insp.get_columns(table)}
                for name, ddl in cols:
                    if name not in have:
                        sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                        _log.info("migrate_v4: added %s.%s", table, name)
        await conn.run_sync(_do)


async def log_step(user_id: int, step: str):
    try:
        async with async_session() as session:
            session.add(UserActivity(user_id=user_id, step=step))
            await session.commit()
    except Exception:
        pass


async def migrate_v5():
    """Idempotent v5 migration: encrypted phone and subscription tables."""
    async with engine.begin() as conn:
        def _do(sync_conn):
            insp = inspect(sync_conn)
            tables = set(insp.get_table_names())
            users_have = {c["name"] for c in insp.get_columns("users")} if "users" in tables else set()
            for name, ddl in (("phone_enc", "TEXT"), ("phone_verified_at", "TIMESTAMP")):
                if "users" in tables and name not in users_have:
                    sync_conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
            if "memberships" not in tables:
                Membership.__table__.create(sync_conn)
        await conn.run_sync(_do)


# ---------------- initial section tree ----------------
def _slug(s: str) -> str:
    return s.lower().replace(" ", "_").replace("&", "and").replace("/", "_")


OPTIONAL_SUBJECTS = [
    "Anthropology", "PSIR", "Sociology", "History", "Geography", "Philosophy",
    "Public Administration", "Psychology", "Commerce & Accountancy",
    "Hindi Literature", "Mathematics", "Economics", "Law", "Forestry",
    "Geology", "Agriculture",
]

SECTION_TREE = {
    ("upsc", "UPSC", "🏛"): [
        ("upsc_foundation", "Foundation", "⌂"),
        ("upsc_csat", "CSAT", "🧮"),
        ("upsc_pyq", "PYQ / Answer Practice", "🗂"),
        ("upsc_crash", "Crash Course", "⚡"),
        ("upsc_ca", "Current Affairs", "📰"),
    ],
    ("prelims_mains", "Prelims & Mains Course", "♛"): [
        ("upsc_prelims", "Prelims Specific", "◎"),
        ("upsc_mains", "Mains Specific", "♛"),
    ],
    ("test_series", "Test Series", "📝"): [
        ("upsc_ts_prelims", "Prelims Test Series", "📝"),
        ("upsc_ts_mains", "Mains Test Series", "📝"),
    ],
    ("subject_specific", "Subject Specific Course", "🧑‍🏫"): [
        ("subj_economy", "Economics (incl. Mrunal)", "💹"),
        ("subj_geography", "Geography (incl. Sudarshan Gujjar)", "🗺"),
        ("subj_polity", "Polity & Governance (incl. Jatin Gupta)", "🏛"),
        ("subj_environment_scitech", "Environment + Sci-Tech", "🌱"),
        ("subj_history", "History", "📜"),
        ("subj_ir", "International Relations", "🌐"),
        ("subj_public_admin", "Public Administration", "🏢"),
        ("upsc_ethics", "Ethics (GS-4)", "⚖️"),
        ("upsc_essay", "Essay", "✍️"),
        ("upsc_subject_specific", "Other Subject Courses", "📚"),
    ],
    ("upsc_optional", "UPSC Optional", "📗"): [
        (f"optional_{_slug(s)}", s, "📗") for s in OPTIONAL_SUBJECTS
    ],
    ("state_psc", "All State PSC", "🏢"): [
        ("uppsc", "UPPSC", "🏢"),
        ("bpsc", "BPSC", "🏢"),
        ("rpsc", "RPSC", "🏢"),
        ("jpsc", "JPSC", "🏢"),
        ("ukpsc", "UKPSC", "🏢"),
    ],
    ("net_jrf", "NET / JRF", "🎓"): [
        ("net_jrf_all", "All Subjects", "🎓"),
    ],
    ("combo", "Combo Deals & Bundles", "🎁"): [
        ("combo_deals", "Combo Deals", "🎁"),
    ],
    ("other", "Other Courses", "📦"): [
        ("other_misc", "Miscellaneous", "📦"),
    ],
}


async def seed_sections():
    async with async_session() as session:
        existing = (await session.execute(select(Section))).scalars().first()
        if existing:
            return
        for (top_key, top_name, top_emoji), children in SECTION_TREE.items():
            top = Section(key=top_key, name=top_name, emoji=top_emoji, parent_id=None)
            session.add(top)
            await session.flush()
            for key, name, emoji in children:
                session.add(Section(key=key, name=name, emoji=emoji, parent_id=top.id))
        await session.commit()


async def seed_courses():
    async with async_session() as session:
        existing = (await session.execute(select(Course))).scalars().first()
        if existing:
            return
        result = await session.execute(select(Section))
        sections_by_key = {s.key: s for s in result.scalars().all()}

        for name, faculty, medium, notes, price, section_keys, batch_id in COURSE_SEED:
            course = Course(name=name, faculty=faculty, medium=medium, notes=notes, price=price)
            for key in section_keys:
                sec = sections_by_key.get(key)
                if sec:
                    course.sections.append(sec)
            session.add(course)
        await session.commit()


# ---------------- v2 migration (safe on existing/deployed DBs) ----------------
NEW_TOP_SECTIONS = [
    ("prelims_mains", "Prelims & Mains Course", "♛"),
    ("test_series", "Test Series", "📝"),
    ("subject_specific", "Subject Specific Course", "🧑‍🏫"),
]

NEW_SUBJECT_CHILDREN = [
    ("subj_economy", "Economics (incl. Mrunal)", "💹"),
    ("subj_geography", "Geography (incl. Sudarshan Gujjar)", "🗺"),
    ("subj_polity", "Polity & Governance (incl. Jatin Gupta)", "🏛"),
    ("subj_environment_scitech", "Environment + Sci-Tech", "🌱"),
    ("subj_history", "History", "📜"),
    ("subj_ir", "International Relations", "🌐"),
    ("subj_public_admin", "Public Administration", "🏢"),
]

REPARENT = [
    ("upsc_prelims", "prelims_mains"),
    ("upsc_mains", "prelims_mains"),
    ("upsc_ts_prelims", "test_series"),
    ("upsc_ts_mains", "test_series"),
    ("upsc_ethics", "subject_specific"),
    ("upsc_essay", "subject_specific"),
    ("upsc_subject_specific", "subject_specific"),
]

KEYWORD_SECTION_MAP = [
    (["mrunal", "economy", "economics", "pcb", "shivin", "jayant", "aditya kaliya",
      "basava", "rishi jain", "bookstawa"], "subj_economy"),
    (["geography", "gujjar", "gurjar", "thapa", "himanshu"], "subj_geography"),
    (["polity", "governance", "jatin gupta", "sidharth arora", "laxmikanth"], "subj_polity"),
    (["environment", "sci-tech", "sci & tech", "science", "ecology", "pmf",
      "cp kaushik", "ravi agrahari"], "subj_environment_scitech"),
    (["history"], "subj_history"),
    (["international relations", "ir ", "chetan"], "subj_ir"),
    (["public administration", "pub ad"], "subj_public_admin"),
]

EXPLICIT_NEW_COURSES = [
    ("Polity & Governance — Jatin Gupta", "Jatin Gupta", "", "", None, ["subj_polity"]),
]


async def migrate_v2():
    async with async_session() as session:
        result = await session.execute(select(Section))
        sections = {s.key: s for s in result.scalars().all()}
        if not sections:
            return  

        changed = False

        for key, name, emoji in NEW_TOP_SECTIONS:
            if key not in sections:
                sec = Section(key=key, name=name, emoji=emoji, parent_id=None)
                session.add(sec)
                await session.flush()
                sections[key] = sec
                changed = True

        for key, name, emoji in NEW_SUBJECT_CHILDREN:
            if key not in sections:
                parent = sections["subject_specific"]
                sec = Section(key=key, name=name, emoji=emoji, parent_id=parent.id)
                session.add(sec)
                await session.flush()
                sections[key] = sec
                changed = True

        for child_key, new_parent_key in REPARENT:
            child = sections.get(child_key)
            parent = sections.get(new_parent_key)
            if child and parent and child.parent_id != parent.id:
                child.parent_id = parent.id
                changed = True

        if changed:
            await session.commit()

        catchall = sections.get("upsc_subject_specific")
        if catchall:
            result = await session.execute(select(Course))
            all_courses = result.scalars().all()
            catchall_courses = [
                c for c in all_courses if any(s.key == "upsc_subject_specific" for s in c.sections)
            ]
            for course in catchall_courses:
                haystack = f"{course.name} {course.faculty}".lower()
                existing_keys = {s.key for s in course.sections}
                for keywords, target_key in KEYWORD_SECTION_MAP:
                    if target_key in existing_keys:
                        continue
                    if any(kw in haystack for kw in keywords):
                        target_sec = sections.get(target_key)
                        if target_sec:
                            course.sections.append(target_sec)
            await session.commit()

        result = await session.execute(select(Course.name))
        existing_names = {n for (n,) in result.all()}
        for name, faculty, medium, notes, price, section_keys in EXPLICIT_NEW_COURSES:
            if name in existing_names:
                continue
            course = Course(name=name, faculty=faculty, medium=medium, notes=notes, price=price)
            for key in section_keys:
                sec = sections.get(key)
                if sec:
                    course.sections.append(sec)
            session.add(course)
        await session.commit()

        result = await session.execute(select(Course))
        db_courses = result.scalars().all()
        
        seed_dict = {}
        for name, faculty, medium, notes, price, section_keys, batch_id in COURSE_SEED:
            seed_dict[name] = {
                "faculty": faculty, "medium": medium, "notes": notes, 
                "price": price, "section_keys": section_keys
            }

        courses_changed = False
        
        for course in db_courses:
            if course.name in seed_dict:
                seed_data = seed_dict[course.name]
                course.price = seed_data["price"]
                course.faculty = seed_data["faculty"]
                course.medium = seed_data["medium"]
                course.notes = seed_data["notes"]
                course.is_active = True
                del seed_dict[course.name]
                courses_changed = True
            else:
                if course.is_active:
                    course.is_active = False
                    courses_changed = True

        for name, seed_data in seed_dict.items():
            new_course = Course(
                name=name, 
                faculty=seed_data["faculty"], 
                medium=seed_data["medium"], 
                notes=seed_data["notes"], 
                price=seed_data["price"],
                is_active=True
            )
            for key in seed_data["section_keys"]:
                sec = sections.get(key)
                if sec:
                    new_course.sections.append(sec)
            session.add(new_course)
            courses_changed = True
            
        if courses_changed:
            await session.commit()


# ---------------- v3 migration: simplified home screen ----------------
V3_REPARENT = [
    ("upsc_optional", "upsc"),
    ("upsc_ts_prelims", "upsc"),
    ("upsc_ts_mains", "upsc"),
    ("net_jrf_all", "subject_specific"),
    ("combo_deals", "subject_specific"),
    ("other_misc", "subject_specific"),
]

V3_ADDITIVE_TAGS = [
    ("upsc_csat", "upsc_prelims"),
    ("upsc_pyq", "upsc_prelims"),
    ("upsc_pyq", "upsc_mains"),
    ("upsc_ca", "upsc_foundation"),
]

V3_RENAME = {
    "upsc_ts_prelims": "Prelims Test Series 2027",
    "upsc_ts_mains": "Mains Test Series 2027",
}


async def migrate_v3():
    async with async_session() as session:
        result = await session.execute(select(Section))
        sections = {s.key: s for s in result.scalars().all()}
        if not sections:
            return

        changed = False
        for child_key, new_parent_key in V3_REPARENT:
            child = sections.get(child_key)
            parent = sections.get(new_parent_key)
            if child and parent and child.parent_id != parent.id:
                child.parent_id = parent.id
                changed = True

        for key, new_name in V3_RENAME.items():
            sec = sections.get(key)
            if sec and sec.name != new_name:
                sec.name = new_name
                changed = True

        if changed:
            await session.commit()

        result = await session.execute(select(Course))
        all_courses = result.scalars().all()
        for source_key, target_key in V3_ADDITIVE_TAGS:
            source_sec = sections.get(source_key)
            target_sec = sections.get(target_key)
            if not source_sec or not target_sec:
                continue
            tagged = [c for c in all_courses if any(s.key == source_key for s in c.sections)]
            for course in tagged:
                existing_keys = {s.key for s in course.sections}
                if target_key not in existing_keys:
                    course.sections.append(target_sec)
        await session.commit()


# ======================= v5: access gate, coins, AI memory, engagement =======================
class LmsAccess(Base):
    """LMS (course library) access is granted per user, only after admin approval."""
    __tablename__ = "lms_access"
    user_id = Column(BigInteger, primary_key=True)
    status = Column(String(12), default="pending")            # pending / approved / denied
    requested_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)



class Membership(Base):
    __tablename__ = "memberships"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    plan = Column(String(40), index=True, nullable=False)  # community / ca_tracker
    status = Column(String(20), default="active")
    starts_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, index=True, nullable=False)
    order_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

class CoinLedger(Base):
    """Immutable audit trail of every coin credit/debit (balance lives in users.ref_points)."""
    __tablename__ = "coin_ledger"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    delta = Column(Integer, nullable=False)
    reason = Column(String(60), default="")
    ref = Column(String(60), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class AiMemory(Base):
    """Permanent per-user conversation memory (never expires, never shared across users)."""
    __tablename__ = "ai_memory"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    role = Column(String(10), nullable=False)                 # user / assistant
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AiProfile(Base):
    """Long-term facts learned about a student (exam, medium, optional, weak areas...)."""
    __tablename__ = "ai_profile"
    user_id = Column(BigInteger, primary_key=True)
    facts = Column(Text, default="")
    turns_since_update = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Streak(Base):
    __tablename__ = "streaks"
    user_id = Column(BigInteger, primary_key=True)
    current = Column(Integer, default=0)
    best = Column(Integer, default=0)
    last_day = Column(String(10), default="")                 # YYYY-MM-DD (IST)
    target = Column(String(300), default="")


class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    text = Column(String(300), nullable=False)
    due_at = Column(DateTime, index=True, nullable=False)     # UTC
    sent = Column(Boolean, default=False)


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    question = Column(Text, nullable=False)
    ai_answer = Column(Text, default="")
    status = Column(String(12), default="ai_answered")        # ai_answered / open / answered / closed
    created_at = Column(DateTime, default=datetime.utcnow)


class Interest(Base):
    __tablename__ = "interests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    keyword = Column(String(60), nullable=False)
