"""Core covered-call opportunity screening.

Design: the expensive/unpredictable part (yfinance calls) lives in
data_provider.py. Everything here is pure functions over plain data
(DataFrame rows, dates, floats) so it can be unit tested without network
access.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import pandas as pd

from src import data_provider
from src.greeks import call_delta


@dataclass
class Opportunity:
    ticker: str
    expiry: str
    dte: int
    strike: float
    premium: float
    delta: float
    annualized_return: float
    notes: list[str] = field(default_factory=list)

    def format(self) -> str:
        line = (
            f"{self.ticker} {self.strike:g}C {self.expiry} "
            f"(DTE {self.dte}) premium={self.premium:.2f} "
            f"delta={self.delta:.2f} 年化={self.annualized_return:.1%}"
        )
        if self.notes:
            line += " [" + "; ".join(self.notes) + "]"
        return line


def _event_within_contract_life(today: date, expiry_date: date, event_date: Optional[date]) -> bool:
    """True if an ex-dividend or earnings date falls during the contract's
    life (between today and expiry). Industry practice (Born to Sell, BCI
    methodology) is an unconditional exclusion here, not a tunable window:
    early-assignment/dividend-capture risk and earnings-driven gap risk
    both exist as long as the event happens before the option expires,
    regardless of how many days before."""
    if event_date is None:
        return False
    return today <= event_date <= expiry_date


def evaluate_expiry(
    spot: float,
    today: date,
    expiry_str: str,
    chain: pd.DataFrame,
    settings: dict,
    ex_div_date: Optional[date] = None,
    earnings_date: Optional[date] = None,
) -> list[Opportunity]:
    """Evaluate one expiry's call chain for a single ticker and return
    candidates passing delta/DTE/annualized-return filters, annotated with
    dividend/earnings exclusion notes rather than silently dropped when the
    exclusion applies but the rest of the contract still looks interesting
    for visibility - actual filtering out happens in `screen_candidates`.
    """
    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    dte = (expiry_date - today).days
    if dte < settings["dte_min"] or dte > settings["dte_max"]:
        return []
    if chain is None or chain.empty:
        return []

    results = []
    for _, row in chain.iterrows():
        strike = float(row.get("strike", 0) or 0)
        if strike <= spot:
            continue  # only out-of-the-money calls

        bid = float(row.get("bid", 0) or 0)
        ask = float(row.get("ask", 0) or 0)
        if bid <= 0 and ask <= 0:
            # No live quote (e.g. outside 9:30am-4pm ET market hours).
            # Yahoo's impliedVolatility in this state is a degenerate
            # solver artifact (observed values like 0.00001, then jumps
            # 0.03/0.0625/0.125/0.25 - a boundary pattern, not real IV),
            # so any delta computed from it would be meaningless. Skip
            # rather than risk a bogus but plausible-looking delta.
            continue

        iv = float(row.get("impliedVolatility", 0) or 0)
        delta = call_delta(spot, strike, dte, iv, settings["risk_free_rate"])
        if delta < settings["delta_min"] or delta > settings["delta_max"]:
            continue

        premium = bid if bid > 0 else float(row.get("lastPrice", 0) or 0)
        if premium <= 0:
            continue

        annualized_return = (premium / spot) * (365 / dte)
        if annualized_return < settings["min_annualized_return"]:
            continue

        notes = []
        if _event_within_contract_life(today, expiry_date, ex_div_date):
            notes.append(f"除息日{ex_div_date}在合約到期前")
        if _event_within_contract_life(today, expiry_date, earnings_date):
            notes.append(f"財報日{earnings_date}在合約到期前")

        results.append(
            Opportunity(
                ticker="",  # filled in by caller
                expiry=expiry_str,
                dte=dte,
                strike=strike,
                premium=premium,
                delta=delta,
                annualized_return=annualized_return,
                notes=notes,
            )
        )
    return results


def screen_candidates(candidates: list[Opportunity], top_n: int) -> list[Opportunity]:
    """Drop anything flagged by an exclusion window, then keep the top N by
    annualized return."""
    clean = [c for c in candidates if not c.notes]
    clean.sort(key=lambda c: c.annualized_return, reverse=True)
    return clean[:top_n]


def scan_ticker(ticker: str, settings: dict, today: Optional[date] = None) -> list[Opportunity]:
    """Live scan for one ticker: pulls spot price, ex-div/earnings dates,
    and every expiry within [dte_min, dte_max], then filters and ranks."""
    today = today or date.today()
    spot = data_provider.get_spot_price(ticker)
    if spot is None:
        return []

    ex_div_date = data_provider.get_next_ex_dividend_date(ticker)
    earnings_date = data_provider.get_next_earnings_date(ticker)

    candidates: list[Opportunity] = []
    for expiry_str in data_provider.get_expiries(ticker):
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        dte = (expiry_date - today).days
        if dte < settings["dte_min"] or dte > settings["dte_max"]:
            continue
        chain = data_provider.get_call_chain(ticker, expiry_str)
        candidates.extend(
            evaluate_expiry(spot, today, expiry_str, chain, settings, ex_div_date, earnings_date)
        )

    for c in candidates:
        c.ticker = ticker

    return screen_candidates(candidates, settings["top_n_per_ticker"])


def scan_all(tickers: list[str], settings: dict, today: Optional[date] = None) -> dict[str, list[Opportunity]]:
    return {ticker: scan_ticker(ticker, settings, today) for ticker in tickers}
