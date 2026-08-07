"""Read/write data/positions.yaml and decide when an open covered call
should be flagged for roll consideration."""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml

POSITIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "positions.yaml"


@dataclass
class Position:
    ticker: str
    strike: float
    expiry: str  # YYYY-MM-DD
    premium_sold: float
    opened_date: str  # YYYY-MM-DD

    def expiry_date(self) -> date:
        return datetime.strptime(self.expiry, "%Y-%m-%d").date()

    def dte(self, today: Optional[date] = None) -> int:
        today = today or date.today()
        return (self.expiry_date() - today).days

    def key(self) -> tuple:
        return (self.ticker.upper(), self.strike, self.expiry)


def load_positions(path: Path = POSITIONS_PATH) -> list[Position]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return [Position(**p) for p in raw.get("positions", [])]


def save_positions(positions: list[Position], path: Path = POSITIONS_PATH) -> None:
    data = {
        "positions": [
            {
                "ticker": p.ticker,
                "strike": p.strike,
                "expiry": p.expiry,
                "premium_sold": p.premium_sold,
                "opened_date": p.opened_date,
            }
            for p in positions
        ]
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 目前開倉的covered call\n")
        f.write("# 用 /add TICKER STRIKE EXPIRY PREMIUM 透過Telegram新增\n")
        f.write("# 用 /close TICKER STRIKE EXPIRY 關閉\n")
        f.write("# expiry格式: YYYY-MM-DD\n\n")
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def add_position(ticker: str, strike: float, expiry: str, premium: float, opened_date: Optional[str] = None,
                  path: Path = POSITIONS_PATH) -> list[Position]:
    positions = load_positions(path)
    opened_date = opened_date or date.today().isoformat()
    new_pos = Position(ticker.upper(), float(strike), expiry, float(premium), opened_date)
    positions = [p for p in positions if p.key() != new_pos.key()]
    positions.append(new_pos)
    save_positions(positions, path)
    return positions


def close_position(ticker: str, strike: float, expiry: str, path: Path = POSITIONS_PATH) -> list[Position]:
    positions = load_positions(path)
    target_key = (ticker.upper(), float(strike), expiry)
    positions = [p for p in positions if p.key() != target_key]
    save_positions(positions, path)
    return positions


def roll_flags(position: Position, current_market_price: Optional[float], settings: dict,
                today: Optional[date] = None, delta: Optional[float] = None) -> list[str]:
    """Returns human-readable reasons this position should be considered
    for a roll. Empty list means no action needed yet."""
    flags = []
    dte = position.dte(today)
    if dte <= settings["roll_dte_threshold"]:
        flags.append(f"剩餘{dte}天到期，考慮roll或讓其到期")

    if current_market_price is not None:
        threshold = position.premium_sold * (1 - settings["roll_profit_capture"])
        if current_market_price <= threshold:
            captured_pct = 1 - (current_market_price / position.premium_sold)
            flags.append(f"獲利已達{captured_pct:.0%}(門檻{settings['roll_profit_capture']:.0%})，考慮roll鎖定利潤")

    if delta is not None and delta >= settings["roll_defensive_delta_threshold"]:
        # Defensive roll trigger: delta ~0.45-0.50 is where extrinsic value
        # peaks (max near the money), so this is the point where rolling
        # captures the best net credit - waiting for DTE to run out or for
        # the stock to actually cross the strike is strictly later and
        # worse, since this scanner only runs once a day and an overnight
        # gap can push a spot-crossing trigger well past this point before
        # anyone sees the alert.
        flags.append(
            f"delta已達{delta:.2f}(門檻{settings['roll_defensive_delta_threshold']:.2f})，"
            f"時間價值接近高點、assignment風險上升，考慮roll up-and-out"
        )

    return flags
