from src import handle_command, scan


def test_scan_command_returns_build_message_output(monkeypatch):
    monkeypatch.setattr(scan, "load_settings", lambda: {"fake": "settings"})
    monkeypatch.setattr(scan, "build_message", lambda settings: f"scanned with {settings}")

    reply = handle_command.handle_command("scan", [])

    assert reply == "scanned with {'fake': 'settings'}"


def test_scan_command_with_ticker_arg_returns_ticker_detail(monkeypatch):
    monkeypatch.setattr(scan, "load_settings", lambda: {"fake": "settings"})
    calls = []

    def fake_detail(ticker, settings):
        calls.append((ticker, settings))
        return f"detail for {ticker}"

    monkeypatch.setattr(scan, "build_ticker_detail_message", fake_detail)

    reply = handle_command.handle_command("scan", ["tsla"])

    assert reply == "detail for tsla"
    assert calls == [("tsla", {"fake": "settings"})]
