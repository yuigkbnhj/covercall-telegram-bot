"""Read/write config/holdings.yaml - the list of tickers to scan."""

from pathlib import Path

import yaml

HOLDINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "holdings.yaml"


def load_holdings(path: Path = HOLDINGS_PATH) -> list[str]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return list(raw.get("tickers", []))


def save_holdings(tickers: list[str], path: Path = HOLDINGS_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 長期持有、想做covered call的股票代號清單\n")
        f.write("# 用 /holdings_add TICKER 和 /holdings_remove TICKER 透過Telegram維護\n")
        f.write("# 也可以直接編輯這個檔案\n\n")
        yaml.safe_dump({"tickers": tickers}, f, allow_unicode=True, sort_keys=False)


def add_holding(ticker: str, path: Path = HOLDINGS_PATH) -> list[str]:
    tickers = load_holdings(path)
    ticker = ticker.upper()
    if ticker not in tickers:
        tickers.append(ticker)
        save_holdings(tickers, path)
    return tickers


def remove_holding(ticker: str, path: Path = HOLDINGS_PATH) -> list[str]:
    tickers = load_holdings(path)
    ticker = ticker.upper()
    tickers = [t for t in tickers if t != ticker]
    save_holdings(tickers, path)
    return tickers
