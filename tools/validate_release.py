"""Static release validator; does not require runtime bot dependencies."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
main_text = (ROOT / "main.py").read_text(encoding="utf-8")
fm = json.loads((ROOT / "feature_matrix.json").read_text(encoding="utf-8"))


def cmds(block_name: str, next_marker: str):
    block = main_text.split(block_name, 1)[1].split(next_marker, 1)[0]
    return re.findall(r'BotCommand\(command="([^"]+)"', block)


user = cmds("USER_COMMANDS = [", "ADMIN_COMMANDS")
admin = cmds("ADMIN_COMMANDS = [", "\n\n# ========================================================")
assert len(user) == 10, user
assert 25 <= len(admin) <= 35, admin
assert not (set(user) & set(admin)), set(user) & set(admin)
assert len(user) == len(set(user)), user
assert len(admin) == len(set(admin)), admin
assert fm["total"] == 287
assert fm["counts"] == {"USER": 90, "ADMIN": 88, "SECURITY": 88, "AI": 21}
assert all(x["final_policy"] for x in fm["features"])

# Parse every application Python file, including tool scripts.
py_files = [p for p in ROOT.rglob("*.py") if "_archive_original" not in p.parts]
for p in py_files:
    ast.parse(p.read_text(encoding="utf-8"), filename=str(p))

secret_rx = re.compile(
    r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b|AIza[A-Za-z0-9_-]{30,}|\bsk-[A-Za-z0-9]{20,}\b"
)
for p in py_files:
    text = p.read_text(encoding="utf-8", errors="ignore")
    assert not secret_rx.search(text), p

assert "Authorization" in main_text
assert "ProcessedUpdate" in (ROOT / "database.py").read_text(encoding="utf-8")
assert "CronFence" in (ROOT / "database.py").read_text(encoding="utf-8")
assert "AdminPublicCommandIsolation" in (ROOT / "production_hardening.py").read_text(encoding="utf-8")
assert "claim_fence" in (ROOT / "services.py").read_text(encoding="utf-8")
assert (ROOT / "PRODUCTION_GAP_AUDIT.md").exists()
assert (ROOT / "VERCEL_DEPLOY.md").exists()
assert (ROOT / "FEATURE_CHECKLIST_SOURCE.xlsx").exists()

# Vercel configuration: native FastAPI zero-config entrypoint + cron.
vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
assert "crons" in vercel and vercel["crons"][0]["path"] == "/api/cron"
assert vercel["crons"][0]["schedule"] == "0 14 * * *"
assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.13"
assert not (ROOT / "pyproject.toml").exists()
assert (ROOT / "app.py").exists()
assert "from main import app" in (ROOT / "app.py").read_text(encoding="utf-8")

requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
assert not re.search(r"(?m)^\s*psycopg2(?:-|_)?", requirements), "psycopg2 must not be deployed; asyncpg is used"
required_pins = {
    "aiogram": "3.31.0",
    "pydantic": "2.13.3",
    "aiohttp": "3.14.0",
    "fastapi": "0.115.5",
    "uvicorn": "0.32.0",
    "SQLAlchemy": "2.0.36",
    "asyncpg": "0.30.0",
    "aiosqlite": "0.20.0",
    "google-genai": "2.23.0",
    "Pillow": "11.0.0",
    "APScheduler": "3.10.4",
    "aiohttp-socks": "0.10.1",
}
for pkg, ver in required_pins.items():
    assert re.search(rf"(?m)^\s*{re.escape(pkg)}=={re.escape(ver)}\s*$", requirements), (pkg, ver)
assert re.search(r"(?m)^\s*cryptography(?:==|>=|<=|~=|>|<)", requirements)
# uvicorn is allowed only inside the local-development __main__ guard.
main_tree = ast.parse(main_text, filename="main.py")
top_level_uvicorn = []
local_guard_uvicorn = []
for node in main_tree.body:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
        if any(name == "uvicorn" or name.startswith("uvicorn.") for name in names):
            top_level_uvicorn.append(node.lineno)
    if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
        src = ast.get_source_segment(main_text, node.test) or ""
        if "__name__" in src and "__main__" in src:
            for child in ast.walk(node):
                if isinstance(child, ast.Import):
                    names = [a.name for a in child.names]
                    if any(name == "uvicorn" or name.startswith("uvicorn.") for name in names):
                        local_guard_uvicorn.append(child.lineno)
assert not top_level_uvicorn, top_level_uvicorn
assert local_guard_uvicorn, "local __main__ uvicorn import missing"

# All direct third-party imports used by runtime code must be declared.
import_roots: dict[str, set[str]] = {}
for p in py_files:
    tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                import_roots.setdefault(a.name.split(".")[0], set()).add(p.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            import_roots.setdefault(node.module.split(".")[0], set()).add(p.name)
package_roots = {
    "aiogram": "aiogram",
    "aiohttp": "aiohttp",
    "apscheduler": "APScheduler",
    "fastapi": "fastapi",
    "sqlalchemy": "SQLAlchemy",
    "dotenv": "python-dotenv",
    "google": "google-genai",
    "PIL": "Pillow",
    "matplotlib": "matplotlib",
    "cryptography": "cryptography",
    "aiohttp_socks": "aiohttp-socks",
    "uvicorn": "uvicorn",
}
for root, pkg in package_roots.items():
    if root in import_roots:
        assert re.search(rf"(?m)^\s*{re.escape(pkg)}(?:==|>=|<=|~=|>|<)", requirements), (root, pkg)

# FastAPI routes and deployment-sensitive paths must remain present.
for marker in [
    '@app.post("/webhook")',
    '@app.get("/")',
    '@app.get("/api/health")',
    '@app.get("/api/cron")',
    '@app.get("/webapp/lms"',
    '@app.get("/webapp/ca"',
    '@app.get("/webapp/community"',
]:
    assert marker in main_text, marker

print("PASS")
print("user_commands=", len(user))
print("admin_commands=", len(admin))
print("features=", fm["total"], fm["counts"])
print("python_files=", len(py_files))
print("vercel_config=PASS")
print("dependency_manifest=PASS")
