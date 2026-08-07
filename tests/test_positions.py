from datetime import date, timedelta

from src.positions import Position, add_position, close_position, load_positions, roll_flags

SETTINGS = {
    "roll_dte_threshold": 5,
    "roll_profit_capture": 0.50,
}


def test_add_and_load_position(tmp_path):
    path = tmp_path / "positions.yaml"
    add_position("aapl", 220, "2026-09-18", 1.5, opened_date="2026-08-01", path=path)
    positions = load_positions(path)
    assert len(positions) == 1
    p = positions[0]
    assert p.ticker == "AAPL"
    assert p.strike == 220
    assert p.premium_sold == 1.5


def test_add_position_replaces_same_key(tmp_path):
    path = tmp_path / "positions.yaml"
    add_position("AAPL", 220, "2026-09-18", 1.5, opened_date="2026-08-01", path=path)
    add_position("AAPL", 220, "2026-09-18", 2.0, opened_date="2026-08-02", path=path)
    positions = load_positions(path)
    assert len(positions) == 1
    assert positions[0].premium_sold == 2.0


def test_close_position_removes_it(tmp_path):
    path = tmp_path / "positions.yaml"
    add_position("AAPL", 220, "2026-09-18", 1.5, path=path)
    add_position("MSFT", 400, "2026-09-18", 3.0, path=path)
    remaining = close_position("AAPL", 220, "2026-09-18", path=path)
    assert len(remaining) == 1
    assert remaining[0].ticker == "MSFT"


def test_load_positions_missing_file_returns_empty(tmp_path):
    path = tmp_path / "does_not_exist.yaml"
    assert load_positions(path) == []


def test_roll_flags_near_expiry():
    today = date(2026, 1, 1)
    pos = Position("AAPL", 220, (today + timedelta(days=3)).isoformat(), 1.5, "2025-12-01")
    flags = roll_flags(pos, current_market_price=1.4, settings=SETTINGS, today=today)
    assert any("到期" in f for f in flags)


def test_roll_flags_profit_capture():
    today = date(2026, 1, 1)
    pos = Position("AAPL", 220, (today + timedelta(days=30)).isoformat(), 2.0, "2025-12-01")
    flags = roll_flags(pos, current_market_price=0.9, settings=SETTINGS, today=today)  # 55% captured
    assert any("獲利" in f for f in flags)


def test_roll_flags_none_when_healthy():
    today = date(2026, 1, 1)
    pos = Position("AAPL", 220, (today + timedelta(days=30)).isoformat(), 2.0, "2025-12-01")
    flags = roll_flags(pos, current_market_price=1.8, settings=SETTINGS, today=today)
    assert flags == []


def test_roll_flags_defensive_when_spot_reaches_strike():
    today = date(2026, 1, 1)
    pos = Position("AAPL", 220, (today + timedelta(days=30)).isoformat(), 2.0, "2025-12-01")
    flags = roll_flags(pos, current_market_price=1.8, settings=SETTINGS, today=today, spot_price=221.0)
    assert any("up-and-out" in f for f in flags)


def test_roll_flags_defensive_not_triggered_when_spot_below_strike():
    today = date(2026, 1, 1)
    pos = Position("AAPL", 220, (today + timedelta(days=30)).isoformat(), 2.0, "2025-12-01")
    flags = roll_flags(pos, current_market_price=1.8, settings=SETTINGS, today=today, spot_price=215.0)
    assert flags == []
