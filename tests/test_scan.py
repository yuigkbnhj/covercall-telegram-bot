from src.scan import _most_critical_flag


def test_most_critical_flag_prefers_delta_over_expiry_and_profit():
    flags = ["剩餘3天到期，考慮roll或讓其到期", "delta已達0.48(門檻0.45)，考慮roll up-and-out"]
    assert "delta" in _most_critical_flag(flags)


def test_most_critical_flag_prefers_expiry_over_profit_capture():
    flags = ["獲利已達60%(門檻50%)，考慮roll鎖定利潤", "剩餘3天到期，考慮roll或讓其到期"]
    assert "到期" in _most_critical_flag(flags)


def test_most_critical_flag_falls_back_to_first_when_only_profit_capture():
    flags = ["獲利已達60%(門檻50%)，考慮roll鎖定利潤"]
    assert _most_critical_flag(flags) == flags[0]
