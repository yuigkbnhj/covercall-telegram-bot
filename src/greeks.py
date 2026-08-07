"""Black-Scholes call delta. yfinance's option chain has no delta column,
only impliedVolatility, so we derive delta ourselves."""

import math

from scipy.stats import norm


def call_delta(spot: float, strike: float, dte_days: int, iv: float, risk_free_rate: float) -> float:
    """Delta of a European call under Black-Scholes.

    dte_days: calendar days to expiry (converted to years using 365).
    Returns a value in [0, 1]. Falls back to 0.0 if inputs are degenerate
    (e.g. iv <= 0, dte <= 0) since those quotes are unusable anyway.
    """
    if spot <= 0 or strike <= 0 or dte_days <= 0 or iv <= 0:
        return 0.0

    t = dte_days / 365.0
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * iv ** 2) * t) / (iv * math.sqrt(t))
    return float(norm.cdf(d1))
