"""Thin wrapper around yfinance. Isolated here so the rest of the code
doesn't care where market data comes from - swapping to Tradier/IBKR later
means only this file changes.
"""

from datetime import date, datetime
from typing import Optional

import pandas as pd
import yfinance as yf


def get_spot_price(ticker: str) -> Optional[float]:
    try:
        fast = yf.Ticker(ticker).fast_info
        price = fast.get("lastPrice") or fast.get("last_price")
        return float(price) if price else None
    except Exception:
        return None


def get_expiries(ticker: str) -> list[str]:
    """Returns expiry date strings (YYYY-MM-DD) available for this ticker."""
    try:
        return list(yf.Ticker(ticker).options)
    except Exception:
        return []


def get_call_chain(ticker: str, expiry: str) -> pd.DataFrame:
    """Calls chain for one expiry. Empty DataFrame if unavailable.

    yfinance leaves bid/ask/impliedVolatility as NaN for illiquid contracts
    rather than 0 - filled here because `float("nan") or 0` evaluates to
    NaN (NaN is truthy), which would silently bypass downstream `<= 0`
    filters instead of getting rejected by them.
    """
    try:
        chain = yf.Ticker(ticker).option_chain(expiry)
        return chain.calls.fillna(0)
    except Exception:
        return pd.DataFrame()


def get_next_ex_dividend_date(ticker: str) -> Optional[date]:
    """Best-effort. Returns None when yfinance has no data - callers must
    treat None as 'unknown', not 'no dividend'."""
    try:
        info = yf.Ticker(ticker).get_info()
        ts = info.get("exDividendDate")
        if not ts:
            return None
        return datetime.fromtimestamp(ts).date()
    except Exception:
        return None


def get_next_earnings_date(ticker: str) -> Optional[date]:
    """Best-effort. Returns None when yfinance has no data."""
    try:
        df = yf.Ticker(ticker).get_earnings_dates(limit=4)
        if df is None or df.empty:
            return None
        today = pd.Timestamp.now(tz=df.index.tz)
        future = df.index[df.index >= today]
        if len(future) == 0:
            return None
        return future.min().date()
    except Exception:
        return None
