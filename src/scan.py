"""Daily entrypoint: scan holdings for new covered-call opportunities,
check open positions for roll signals, send one summary message to
Telegram. Run by .github/workflows/daily_scan.yml after US market close."""

from datetime import date

import yaml

from src import data_provider, holdings, positions as positions_module, telegram_bot
from src.greeks import call_delta
from src.screener import scan_all, scan_ticker

SETTINGS_PATH = "config/settings.yaml"


def load_settings(path: str = SETTINGS_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_opportunities_section(settings: dict) -> str:
    tickers = holdings.load_holdings()
    if not tickers:
        return "持股清單是空的，用 /holdings_add TICKER 加入股票。"

    results = scan_all(tickers, settings)
    lines = ["<b>Covered Call 機會</b>"]
    any_found = False
    for ticker, (opps, near_miss) in results.items():
        lines.append(f"\n{ticker}:")
        if opps:
            any_found = True
            for opp in opps:
                lines.append("  " + opp.format())
        elif near_miss is not None:
            lines.append("  沒有符合條件的機會，最接近的候選:")
            lines.append("  " + near_miss.format())
        else:
            lines.append("  沒有可用的報價資料。")

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
        status = "、".join(flags) if flags else "正常，無需動作"
        lines.append(
            f"  {pos.ticker} {pos.strike:g}C {pos.expiry} "
            f"(賣出價{pos.premium_sold:.2f}) - {status}"
        )
    return "\n".join(lines)


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

    lines = [f"<b>{ticker} 詳細機會</b> (delta {wide_settings['delta_min']}~{wide_settings['delta_max']})"]
    if opps:
        for opp in opps:
            lines.append(opp.format())
    elif near_miss is not None:
        lines.append("沒有符合條件的機會，最接近的候選:")
        lines.append(near_miss.format())
    else:
        lines.append("沒有可用的報價資料。")
    return "\n".join(lines)


def build_message(settings: dict) -> str:
    return build_opportunities_section(settings) + build_positions_section(settings)


def main():
    settings = load_settings()
    telegram_bot.send_message(build_message(settings))


if __name__ == "__main__":
    main()
