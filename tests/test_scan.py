from datetime import date

from src import scan
from src.scan import _most_critical_flag, build_opportunities_section


def test_most_critical_flag_prefers_delta_over_expiry_and_profit():
    flags = ["剩餘3天到期，考慮roll或讓其到期", "delta已達0.48(門檻0.45)，考慮roll up-and-out"]
    assert "delta" in _most_critical_flag(flags)


def test_most_critical_flag_prefers_expiry_over_profit_capture():
    flags = ["獲利已達60%(門檻50%)，考慮roll鎖定利潤", "剩餘3天到期，考慮roll或讓其到期"]
    assert "到期" in _most_critical_flag(flags)


def test_most_critical_flag_falls_back_to_first_when_only_profit_capture():
    flags = ["獲利已達60%(門檻50%)，考慮roll鎖定利潤"]
    assert _most_critical_flag(flags) == flags[0]


def test_build_opportunities_section_title_shows_given_date(monkeypatch):
    monkeypatch.setattr(scan.holdings, "load_holdings", lambda: [])
    result = build_opportunities_section({}, today=date(2026, 3, 15))
    assert result == "持股清單是空的，用 /holdings_add TICKER 加入股票。"

    monkeypatch.setattr(scan.holdings, "load_holdings", lambda: ["TSLA"])
    monkeypatch.setattr(scan, "scan_all", lambda tickers, settings: {"TSLA": ([], None)})
    result = build_opportunities_section({}, today=date(2026, 3, 15))
    assert "2026-03-15" in result
