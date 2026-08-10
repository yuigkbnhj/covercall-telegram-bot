"""Daily entrypoint: scan holdings for new covered-call opportunities,
check open positions for roll signals, send one summary message to
Telegram. Run by .github/workflows/daily_scan.yml after US market close."""

from datetime import date

import yaml

from src import data_provider, holdings, positions as positions_module, telegram_bot
from src.greeks import call_delta
from src.screener import format_table, scan_all, scan_ticker, warning_footnotes

SETTINGS_PATH = "config/settings.yaml"


def load_settings(path: str = SETTINGS_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_opportunities_section(settings: dict, today: date = None) -> str:
    today = today or date.today()
    tickers = holdings.load_holdings()
    if not tickers:
        return "持股清單是空的，用 /holdings_add TICKER 加入股票。"

    results = scan_all(tickers, settings)
    lines = [f"<b>Covered Call 機會</b> ({today.isoformat()})"]
    any_found = False
    for ticker, (opps, near_miss) in results.items():
        if opps:
            any_found = True
            lines.append(f"\n🟢 <b>{ticker}</b>")
            lines.append(format_table(opps))
            lines.extend(warning_footnotes(opps))
        elif near_miss is not None:
            lines.append(f"\n⚪ <b>{ticker}</b>（沒有符合條件的機會，最接近的候選）")
            lines.append(format_table([near_miss]))
            lines.extend(warning_footnotes([near_miss]))
        else:
            lines.append(f"\n⚪ <b>{ticker}</b>：沒有可用的報價資料。")

    if not any_found:
        lines.insert(1, "今天沒有符合條件的機會，以下是各股最接近的候選供參考：")
    return "\n".join(lines)


def build_positions_section(settings: dict, today: date = None) -> str:
    today = today or date.today()
    open_positions = positions_module.load_positions()
    if not open_positions:
        return ""

    lines = ["\n<b>現有倉位</b>"]
    for pos in open_positions:
        chain = data_provider.get_call_chain(pos.ticker, pos.expiry)
        current_price = None
        delta = None
        if not chain.empty:
            match = chain[chain["strike"] == pos.strike]
            if not match.empty:
                bid = float(match.iloc[0].get("bid", 0) or 0)
                ask = float(match.iloc[0].get("ask", 0) or 0)
                current_price = bid if bid > 0 else float(match.iloc[0].get("lastPrice", 0) or 0)
                if bid > 0 or ask > 0:
                    spot_price = data_provider.get_spot_price(pos.ticker)
                    iv = float(match.iloc[0].get("impliedVolatility", 0) or 0)
                    if spot_price is not None:
                        delta = call_delta(spot_price, pos.strike, pos.dte(today), iv, settings["risk_free_rate"])

        flags = positions_module.roll_flags(pos, current_price, settings, today, delta)
        status = _most_critical_flag(flags) if flags else "正常，無需動作"
        marker = "🔴" if flags else "🟢"
        lines.append(
            f"  {marker} {pos.ticker} {pos.strike:g}C {pos.expiry} "
            f"(賣出價{pos.premium_sold:.2f}) - {status}"
        )
    return "\n".join(lines)


def _most_critical_flag(flags: list[str]) -> str:
    """roll_flags() can return multiple simultaneous reasons; showing all of
    them in one line makes the mobile message noisy. Assignment risk
    (defensive delta) is the most time-sensitive, then approaching
    expiry, then profit-capture (already-banked gains, least urgent)."""
    for keyword in ("delta", "到期"):
        for flag in flags:
            if keyword in flag:
                return flag
    return flags[0]


def build_ticker_detail_message(ticker: str, settings: dict) -> str:
    """Deeper look at a single ticker: wider delta net and more candidates
    than the daily digest (which caps at top_n_per_ticker per ticker to
    keep the daily message short). Same screening logic, just less pruned -
    for when the user wants to see what's available beyond the top picks,
    including lower-delta (safer) contracts that delta_min would otherwise
    hide."""
    ticker = ticker.upper()
    wide_settings = dict(settings, delta_min=0.05, top_n_per_ticker=15)
    opps, near_miss = scan_ticker(ticker, wide_settings)

    lines = [
        f"<b>{ticker} 詳細機會</b> ({date.today().isoformat()}) "
        f"(delta {wide_settings['delta_min']}~{wide_settings['delta_max']})"
    ]
    if opps:
        lines.append(format_table(opps))
        lines.extend(warning_footnotes(opps))
    elif near_miss is not None:
        lines.append("沒有符合條件的機會，最接近的候選:")
        lines.append(format_table([near_miss]))
        lines.extend(warning_footnotes([near_miss]))
    else:
        lines.append("沒有可用的報價資料。")
    return "\n".join(lines)


def build_message(settings: dict) -> str:
    today = date.today()
    return build_opportunities_section(settings, today) + build_positions_section(settings, today)


def main():
    settings = load_settings()
    telegram_bot.send_message(build_message(settings))


if __name__ == "__main__":
    main()
