"""Preview or import Livegram contacts from JSON or pipe-separated text."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def load_users(path: Path) -> list[tuple[int, str | None]]:
    users: dict[int, str | None] = {}
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as source:
            payload = json.load(source)
        records = payload.get("users") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("JSON must be a list of users or an object with a 'users' list")
        rows = []
        for row_number, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                raise ValueError(f"users[{row_number - 1}] must be an object")
            rows.append((record.get("id"), record.get("username"), row_number))
    else:
        rows = []
        with path.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("|", maxsplit=1)
                if len(parts) != 2:
                    raise ValueError(f"line {line_number}: expected ID | username")
                username = parts[1].strip()
                if username.lower().startswith("username:"):
                    username = username.split(":", maxsplit=1)[1].strip()
                if username.lower() in {"", "null", "none"}:
                    username = None
                rows.append((parts[0].strip(), username, line_number))

    for raw_id, username, row_number in rows:
        valid_id = (
            isinstance(raw_id, int) and not isinstance(raw_id, bool)
        ) or (isinstance(raw_id, str) and raw_id.strip().isdecimal())
        if not valid_id:
            raise ValueError(f"row {row_number}: id must be a positive integer")
        user_id = int(raw_id)
        if user_id <= 0:
            raise ValueError(f"row {row_number}: id must be a positive integer")
        if username is not None and not isinstance(username, str):
            raise ValueError(f"row {row_number}: username must be text or null")
        username = username.strip().lstrip("@") if username else None
        if username and len(username) > 100:
            raise ValueError(f"row {row_number}: username exceeds 100 characters")
        if username or user_id not in users:
            users[user_id] = username or None

    return sorted(users.items())


async def import_users(users: list[tuple[int, str | None]]) -> tuple[int, int]:
    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from config import DATABASE_URL
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required; refusing the local SQLite fallback")

    from database import IS_SQLITE, User, async_session, engine, init_db
    if IS_SQLITE:
        raise RuntimeError("A PostgreSQL DATABASE_URL is required for this migration")

    from sqlalchemy import select

    inserted = 0
    updated = 0
    try:
        await init_db()
        async with async_session() as session:
            for offset in range(0, len(users), 500):
                batch = users[offset:offset + 500]
                ids = [user_id for user_id, _username in batch]
                existing = (
                    await session.execute(select(User).where(User.id.in_(ids)))
                ).scalars().all()
                by_id = {user.id: user for user in existing}

                for user_id, username in batch:
                    user = by_id.get(user_id)
                    if user is None:
                        session.add(User(id=user_id, username=username))
                        inserted += 1
                    elif username is not None and user.username != username:
                        user.username = username
                        updated += 1
            await session.commit()
    finally:
        await engine.dispose()
    return inserted, updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Livegram JSON export or ID | username text file")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write users to DATABASE_URL (default is preview only)",
    )
    args = parser.parse_args()

    users = load_users(args.input)
    with_usernames = sum(username is not None for _user_id, username in users)
    print(f"Valid unique users: {len(users)}")
    print(f"Users with usernames: {with_usernames}")
    if not args.apply:
        print("Preview only. Add --apply to import into DATABASE_URL.")
        return

    try:
        inserted, updated = asyncio.run(import_users(users))
    except RuntimeError as exc:
        parser.error(str(exc))
    print(f"Imported: {inserted}; usernames updated: {updated}; existing data preserved.")


if __name__ == "__main__":
    main()