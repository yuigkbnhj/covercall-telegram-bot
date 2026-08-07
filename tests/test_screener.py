from datetime import date, timedelta

import pandas as pd

from src.screener import evaluate_expiry, find_near_miss, screen_candidates, Opportunity

SETTINGS = {
    "delta_min": 0.15,
    "delta_max": 0.30,
    "dte_min": 21,
    "dte_max": 45,
    "min_annualized_return": 0.08,
    "risk_free_rate": 0.04,
    "top_n_per_ticker": 3,
}


def make_chain(rows):
    return pd.DataFrame(rows)


def test_evaluate_expiry_filters_by_dte():
    today = date(2026, 1, 1)
    expiry = today + timedelta(days=10)  # below dte_min
    chain = make_chain([{"strike": 110, "impliedVolatility": 0.3, "bid": 2.0, "lastPrice": 2.0}])
    result = evaluate_expiry(100, today, expiry.isoformat(), chain, SETTINGS)
    assert result == []


def test_evaluate_expiry_keeps_in_range_delta_and_return():
    today = date(2026, 1, 1)
    expiry = today + timedelta(days=30)
    # strike well OTM, moderate IV -> delta should land in [0.15, 0.30] range typically
    chain = make_chain(
        [
            {"strike": 108, "impliedVolatility": 0.35, "bid": 1.5, "lastPrice": 1.5},
            {"strike": 95, "impliedVolatility": 0.35, "bid": 6.0, "lastPrice": 6.0},  # ITM-ish, excluded (strike<=spot skip not applicable but delta too high)
        ]
    )
    result = evaluate_expiry(100, today, expiry.isoformat(), chain, SETTINGS)
    assert len(result) >= 1
    opp = result[0]
    assert SETTINGS["delta_min"] <= opp.delta <= SETTINGS["delta_max"]
    assert opp.annualized_return >= SETTINGS["min_annualized_return"]


def test_evaluate_expiry_rejects_itm_strike():
    today = date(2026, 1, 1)
    expiry = today + timedelta(days=30)
    chain = make_chain([{"strike": 90, "impliedVolatility": 0.3, "bid": 12.0, "lastPrice": 12.0}])
    result = evaluate_expiry(100, today, expiry.isoformat(), chain, SETTINGS)
    assert result == []


def test_evaluate_expiry_annotates_ex_dividend_before_expiry():
    today = date(2026, 1, 1)
    expiry = today + timedelta(days=30)
    ex_div = expiry - timedelta(days=1)  # ex-div happens during contract life
    chain = make_chain([{"strike": 108, "impliedVolatility": 0.35, "bid": 1.5, "lastPrice": 1.5}])
    result = evaluate_expiry(100, today, expiry.isoformat(), chain, SETTINGS, ex_div_date=ex_div)
    assert len(result) == 1
    assert any("除息日" in note for note in result[0].notes)


def test_evaluate_expiry_no_note_when_ex_dividend_after_expiry():
    today = date(2026, 1, 1)
    expiry = today + timedelta(days=30)
    ex_div = expiry + timedelta(days=5)  # ex-div happens after contract expires - no risk
    chain = make_chain([{"strike": 108, "impliedVolatility": 0.35, "bid": 1.5, "lastPrice": 1.5}])
    result = evaluate_expiry(100, today, expiry.isoformat(), chain, SETTINGS, ex_div_date=ex_div)
    assert len(result) == 1
    assert result[0].notes == []


def test_evaluate_expiry_skips_contract_with_no_live_quote():
    today = date(2026, 1, 1)
    expiry = today + timedelta(days=30)
    # bid=ask=0 mimics Yahoo outside market hours, where impliedVolatility
    # is a degenerate solver artifact rather than a real quote.
    chain = make_chain([{"strike": 108, "impliedVolatility": 0.0625, "bid": 0.0, "ask": 0.0, "lastPrice": 1.3}])
    result = evaluate_expiry(100, today, expiry.isoformat(), chain, SETTINGS)
    assert result == []


def test_evaluate_expiry_rejects_low_annualized_return():
    today = date(2026, 1, 1)
    expiry = today + timedelta(days=30)
    chain = make_chain([{"strike": 108, "impliedVolatility": 0.35, "bid": 0.05, "lastPrice": 0.05}])
    result = evaluate_expiry(100, today, expiry.isoformat(), chain, SETTINGS)
    assert result == []


def test_find_near_miss_returns_best_live_quoted_contract_with_reason():
    today = date(2026, 1, 1)
    expiry = today + timedelta(days=30)
    # delta way above delta_max -> should be flagged as the reason it fails
    chain = make_chain([{"strike": 101, "impliedVolatility": 0.5, "bid": 8.0, "ask": 8.2, "lastPrice": 8.1}])
    result = find_near_miss(100, today, expiry.isoformat(), chain, SETTINGS)
    assert result is not None
    assert any("delta" in note for note in result.notes)


def test_find_near_miss_skips_contracts_with_no_live_quote():
    today = date(2026, 1, 1)
    expiry = today + timedelta(days=30)
    chain = make_chain([{"strike": 108, "impliedVolatility": 0.0625, "bid": 0.0, "ask": 0.0, "lastPrice": 1.3}])
    result = find_near_miss(100, today, expiry.isoformat(), chain, SETTINGS)
    assert result is None


def test_find_near_miss_none_when_chain_empty():
    today = date(2026, 1, 1)
    expiry = today + timedelta(days=30)
    result = find_near_miss(100, today, expiry.isoformat(), make_chain([]), SETTINGS)
    assert result is None


def test_screen_candidates_drops_flagged_and_sorts_by_return():
    clean_high = Opportunity("X", "2026-02-01", 30, 110, 2.0, 0.2, 0.15, notes=[])
    clean_low = Opportunity("X", "2026-02-01", 30, 108, 1.0, 0.18, 0.10, notes=[])
    flagged = Opportunity("X", "2026-02-01", 30, 112, 5.0, 0.25, 0.50, notes=["財報日..."])
    result = screen_candidates([clean_low, clean_high, flagged], top_n=3)
    assert result == [clean_high, clean_low]


def test_screen_candidates_respects_top_n():
    opps = [Opportunity("X", "2026-02-01", 30, 100 + i, 1.0, 0.2, 0.08 + i * 0.01) for i in range(5)]
    result = screen_candidates(opps, top_n=2)
    assert len(result) == 2
    assert result[0].annualized_return >= result[1].annualized_return
