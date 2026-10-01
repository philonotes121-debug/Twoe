"""Colour-coded, concise message cards. Telegram cannot colour text, so a colour dot + quote block is used.

  🔵 info   🟢 success   🟡 reminder   🔴 urgent/error   🟣 offer
Every user-facing card ends with an explicit 'Next:' step.
"""
from html import escape

DOT = {"info": "🔵", "ok": "🟢", "warn": "🟡", "err": "🔴", "offer": "🟣"}


def esc(t) -> str:
    return escape(str(t if t is not None else ""), quote=False)


def card(kind: str, title: str, lines=(), nxt: str | None = None, *, raw: bool = False) -> str:
    """lines: iterable of short strings. raw=True keeps HTML in lines (caller escapes)."""
    body = "\n".join(l if raw else esc(l) for l in lines if l)
    out = f"{DOT.get(kind, '🔵')} <b>{esc(title)}</b>"
    if body:
        out += f"\n<blockquote>{body}</blockquote>"
    if nxt:
        out += f"\n➡️ <b>Next:</b> {esc(nxt)}"
    return out


def bar(value: int, total: int, width: int = 10) -> str:
    filled = max(0, min(width, round(width * value / total))) if total else 0
    return "▰" * filled + "▱" * (width - filled)
