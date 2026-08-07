"""Minimal Telegram bot client: send messages, poll for updates, and parse
slash commands. No webhook/server - poll.py calls get_updates() once per
GitHub Actions run (long polling would need an always-on process, which we
explicitly decided against)."""

import os
from typing import Optional

import requests

API_BASE = "https://api.telegram.org/bot{token}"


def _token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable not set")
    return token


def _chat_id() -> str:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID environment variable not set")
    return chat_id


def send_message(text: str, chat_id: Optional[str] = None) -> None:
    url = API_BASE.format(token=_token()) + "/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id or _chat_id(), "text": text, "parse_mode": "HTML"},
        timeout=15,
    )
    resp.raise_for_status()


def get_updates(offset: int) -> list[dict]:
    """offset: smallest update_id to return (i.e. last processed id + 1)."""
    url = API_BASE.format(token=_token()) + "/getUpdates"
    resp = requests.get(url, params={"offset": offset, "timeout": 0}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("result", [])


def parse_command(text: str) -> Optional[tuple[str, list[str]]]:
    """'/add AAPL 220 2026-09-18 1.5' -> ('add', ['AAPL', '220', '2026-09-18', '1.5'])
    Returns None if text isn't a slash command."""
    text = text.strip()
    if not text.startswith("/"):
        return None
    parts = text[1:].split()
    if not parts:
        return None
    return parts[0].lower(), parts[1:]


HELP_TEXT = """可用指令:
/add TICKER STRIKE EXPIRY PREMIUM - 記錄新開的covered call (EXPIRY用YYYY-MM-DD)
/close TICKER STRIKE EXPIRY - 關閉倉位
/list - 列出目前所有open positions
/holdings_add TICKER - 加入長期持股清單
/holdings_remove TICKER - 從長期持股清單移除
/help - 顯示這份說明"""
