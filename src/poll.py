"""Command-polling entrypoint: reads new Telegram messages, applies any
slash commands (add/close/list/scan/holdings_add/holdings_remove/help), and
replies. Run every ~5 min by .github/workflows/poll_commands.yml.

Git commit/push of any changed data files is done by the workflow itself
after this script exits (not here) - keeps this script's job to "process
commands", not "manage git".
"""

from pathlib import Path

from src import holdings, positions as positions_module, scan, telegram_bot

OFFSET_PATH = Path(__file__).resolve().parent.parent / "data" / "telegram_offset.txt"


def load_offset() -> int:
    if not OFFSET_PATH.exists():
        return 0
    return int(OFFSET_PATH.read_text().strip() or "0")


def save_offset(offset: int) -> None:
    OFFSET_PATH.write_text(str(offset) + "\n")


def handle_command(cmd: str, args: list[str]) -> str:
    try:
        if cmd == "add":
            ticker, strike, expiry, premium = args[0], args[1], args[2], args[3]
            positions_module.add_position(ticker, float(strike), expiry, float(premium))
            return f"已記錄: {ticker.upper()} {strike}C {expiry} premium={premium}"

        if cmd == "close":
            ticker, strike, expiry = args[0], args[1], args[2]
            positions_module.close_position(ticker, float(strike), expiry)
            return f"已關閉: {ticker.upper()} {strike}C {expiry}"

        if cmd == "list":
            open_positions = positions_module.load_positions()
            if not open_positions:
                return "目前沒有open positions。"
            lines = [
                f"{p.ticker} {p.strike:g}C {p.expiry} premium={p.premium_sold:.2f} (DTE {p.dte()})"
                for p in open_positions
            ]
            return "\n".join(lines)

        if cmd == "holdings_add":
            ticker = args[0]
            tickers = holdings.add_holding(ticker)
            return f"持股清單: {', '.join(tickers)}"

        if cmd == "holdings_remove":
            ticker = args[0]
            tickers = holdings.remove_holding(ticker)
            return f"持股清單: {', '.join(tickers) if tickers else '(空)'}"

        if cmd == "scan":
            settings = scan.load_settings()
            return scan.build_message(settings)

        if cmd == "help":
            return telegram_bot.HELP_TEXT

        return f"不認識的指令: /{cmd}。輸入 /help 查看可用指令。"

    except (IndexError, ValueError) as e:
        return f"指令格式錯誤: {e}。輸入 /help 查看用法。"


def main():
    offset = load_offset()
    updates = telegram_bot.get_updates(offset)

    max_update_id = offset - 1
    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        message = update.get("message", {})
        text = message.get("text", "")
        parsed = telegram_bot.parse_command(text)
        if parsed is None:
            continue
        cmd, args = parsed
        reply = handle_command(cmd, args)
        telegram_bot.send_message(reply)

    if updates:
        save_offset(max_update_id + 1)


if __name__ == "__main__":
    main()
