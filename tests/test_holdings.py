from src.holdings import add_holding, load_holdings, remove_holding


def test_add_holding_appends_uppercased(tmp_path):
    path = tmp_path / "holdings.yaml"
    add_holding("aapl", path=path)
    assert load_holdings(path) == ["AAPL"]


def test_add_holding_no_duplicates(tmp_path):
    path = tmp_path / "holdings.yaml"
    add_holding("AAPL", path=path)
    add_holding("AAPL", path=path)
    assert load_holdings(path) == ["AAPL"]


def test_remove_holding(tmp_path):
    path = tmp_path / "holdings.yaml"
    add_holding("AAPL", path=path)
    add_holding("MSFT", path=path)
    remaining = remove_holding("AAPL", path=path)
    assert remaining == ["MSFT"]


def test_load_holdings_missing_file(tmp_path):
    path = tmp_path / "missing.yaml"
    assert load_holdings(path) == []
