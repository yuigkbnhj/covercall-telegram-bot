"""Core covered-call opportunity screening.

Design: the expensive/unpredictable part (yfinance calls) lives in
data_provider.py. Everything here is pure functions over plain data
(DataFrame rows, dates, floats) so it can be unit tested without network
access.
"""

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import pandas as pd

from src import data_provider
from src.greeks import call_delta


def _breach_risk_note(
    spot: float, strike: float, dte: int, historical_vol: Optional[float], settings: dict
) -> Optional[str]:
    """IV-derived delta trusts the option market's own volatility estimate.
    This is a second, independent check using the stock's actual recent
    realized volatility: if the strike is closer to spot than one
    historical-vol-implied standard deviation move over the contract's
    life, flag it - a low delta can still hide a strike that recent real
    price action would have blown through, which matters most for
    headline-driven names (single-tweet/earnings-gap risk) where IV can
    understate near-term move size."""
    if historical_vol is None or dte <= 0:
        return None
    expected_move_pct = historical_vol * math.sqrt(dte / 365)
    otm_pct = (strike - spot) / spot
    if otm_pct < expected_move_pct * settings.get("min_otm_vs_hv_move", 1.0):
        return (
            f"近期實現波動率隱含{expected_move_pct:.1%}的移動幅度，"
            f"超過strike的OTM距離{otm_pct:.1%}，可能被穿過"
        )
    return None


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
    warnings: list[str] = field(default_factory=list)

    def format(self) -> str:
        line = (
            f"{self.ticker} {self.strike:g}C {self.expiry} "
            f"(DTE {self.dte}) premium={self.premium:.2f} "
            f"delta={self.delta:.2f} 年化={self.annualized_return:.1%}"
        )
        annotations = self.notes + self.warnings
        if annotations:
            line += " [" + "; ".join(annotations) + "]"
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
    historical_vol: Optional[float] = None,
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

        if bid <= 0:
            # We're the seller - the fill price is the bid. No bid means no
            # trade at any size; lastPrice can be a stale print from a very
            # different market.
            continue
        premium = bid

        annualized_return = (premium / spot) * (365 / dte)
        if annualized_return < settings["min_annualized_return"]:
            continue

        notes = []
        if _event_within_contract_life(today, expiry_date, ex_div_date):
            notes.append(f"除息日{ex_div_date}在合約到期前")
        if _event_within_contract_life(today, expiry_date, earnings_date):
            notes.append(f"財報日{earnings_date}在合約到期前")

        warnings = []
        breach_note = _breach_risk_note(spot, strike, dte, historical_vol, settings)
        if breach_note is not None:
            warnings.append(breach_note)

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
                warnings=warnings,
            )
        )
    return results


def find_near_miss(
    spot: float,
    today: date,
    expiry_str: str,
    chain: pd.DataFrame,
    settings: dict,
    ex_div_date: Optional[date] = None,
    earnings_date: Optional[date] = None,
    historical_vol: Optional[float] = None,
) -> Optional[Opportunity]:
    """Best OTM, live-quoted contract for this expiry regardless of whether
    it clears the delta/return filters, annotated with why it falls short.
    Used so a ticker with zero qualifying opportunities still shows the
    closest real candidate instead of nothing."""
    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    dte = (expiry_date - today).days
    if dte <= 0 or chain is None or chain.empty:
        return None

    candidates = []
    for _, row in chain.iterrows():
        strike = float(row.get("strike", 0) or 0)
        if strike <= spot:
            continue

        bid = float(row.get("bid", 0) or 0)
        if bid <= 0:
            # We're the seller - the fill price is the bid. No bid means no
            # trade at any size.
            continue
        premium = bid

        iv = float(row.get("impliedVolatility", 0) or 0)
        delta = call_delta(spot, strike, dte, iv, settings["risk_free_rate"])
        annualized_return = (premium / spot) * (365 / dte)

        reasons = []
        if delta < settings["delta_min"] or delta > settings["delta_max"]:
            reasons.append(f"delta {delta:.2f}(門檻{settings['delta_min']}~{settings['delta_max']})")
        if annualized_return < settings["min_annualized_return"]:
            reasons.append(f"年化{annualized_return:.1%}(門檻{settings['min_annualized_return']:.0%})")
        if _event_within_contract_life(today, expiry_date, ex_div_date):
            reasons.append(f"除息日{ex_div_date}在合約到期前")
        if _event_within_contract_life(today, expiry_date, earnings_date):
            reasons.append(f"財報日{earnings_date}在合約到期前")
        breach_note = _breach_risk_note(spot, strike, dte, historical_vol, settings)
        if breach_note is not None:
            reasons.append(breach_note)

        candidates.append(
            Opportunity(
                ticker="",
                expiry=expiry_str,
                dte=dte,
                strike=strike,
                premium=premium,
                delta=delta,
                annualized_return=annualized_return,
                notes=reasons,
            )
        )

    if not candidates:
        return None
    candidates.sort(key=lambda c: c.annualized_return, reverse=True)
    return candidates[0]


def screen_candidates(candidates: list[Opportunity], top_n: int) -> list[Opportunity]:
    """Drop anything flagged by an exclusion window, then keep the top N by
    annualized return."""
    clean = [c for c in candidates if not c.notes]
    clean.sort(key=lambda c: c.annualized_return, reverse=True)
    return clean[:top_n]


def scan_ticker(
    ticker: str, settings: dict, today: Optional[date] = None
) -> tuple[list[Opportunity], Optional[Opportunity]]:
    """Live scan for one ticker: pulls spot price, ex-div/earnings dates,
    and every expiry within [dte_min, dte_max], then filters and ranks.

    Returns (qualifying opportunities, near-miss) where near-miss is the
    single best real (live-quoted) contract across all evaluated expiries
    when nothing qualifies - so a ticker with no hits still shows where the
    market actually is instead of nothing."""
    today = today or date.today()
    spot = data_provider.get_spot_price(ticker)
    if spot is None:
        return [], None

    ex_div_date = data_provider.get_next_ex_dividend_date(ticker)
    earnings_date = data_provider.get_next_earnings_date(ticker)
    historical_vol = data_provider.get_historical_volatility(ticker)

    candidates: list[Opportunity] = []
    near_misses: list[Opportunity] = []
    for expiry_str in data_provider.get_expiries(ticker):
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        dte = (expiry_date - today).days
        if dte < settings["dte_min"] or dte > settings["dte_max"]:
            continue
        chain = data_provider.get_call_chain(ticker, expiry_str)
        candidates.extend(
            evaluate_expiry(
                spot, today, expiry_str, chain, settings, ex_div_date, earnings_date, historical_vol
            )
        )
        near_miss = find_near_miss(
            spot, today, expiry_str, chain, settings, ex_div_date, earnings_date, historical_vol
        )
        if near_miss is not None:
            near_misses.append(near_miss)

    for c in candidates:
        c.ticker = ticker

    qualifying = screen_candidates(candidates, settings["top_n_per_ticker"])

    near_miss_result = None
    if not qualifying and near_misses:
        near_misses.sort(key=lambda c: c.annualized_return, reverse=True)
        near_miss_result = near_misses[0]
        near_miss_result.ticker = ticker

    return qualifying, near_miss_result


def scan_all(
    tickers: list[str], settings: dict, today: Optional[date] = None
) -> dict[str, tuple[list[Opportunity], Optional[Opportunity]]]:
    return {ticker: scan_ticker(ticker, settings, today) for ticker in tickers}
