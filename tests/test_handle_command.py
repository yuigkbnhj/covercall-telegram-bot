from src import handle_command, scan


def test_scan_command_returns_build_message_output(monkeypatch):
    monkeypatch.setattr(scan, "load_settings", lambda: {"fake": "settings"})
    monkeypatch.setattr(scan, "build_message", lambda settings: f"scanned with {settings}")

    reply = handle_command.handle_command("scan", [])

    assert reply == "scanned with {'fake': 'settings'}"
