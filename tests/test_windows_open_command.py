"""Windows-Start von Programmen: Auswahl des Befehls (original_path vor linux_command)
und die Uebersetzung Linux-typischer Befehle (xdg-open, 'steam steam://...') in
os.startfile(). Die Windows-Tests laufen nur auf Windows."""
import subprocess
import sys

import pytest

from streamdeck_driver import actions


def test_windows_prefers_original_path(monkeypatch):
    monkeypatch.setattr(actions, "_IS_WINDOWS", True)
    assert actions._resolve_open_cmd({"original_path": "C:/x/app.exe", "linux_command": "app"}) == "C:/x/app.exe"
    assert actions._resolve_open_cmd({"linux_command": "app"}) == "app"


def test_linux_uses_linux_command(monkeypatch):
    monkeypatch.setattr(actions, "_IS_WINDOWS", False)
    assert actions._resolve_open_cmd({"original_path": "C:/x/app.exe", "linux_command": "app"}) == "app"
    assert actions._resolve_open_cmd({"original_path": "C:/x/app.exe"}) is None


@pytest.mark.skipif(sys.platform != "win32", reason="nur Windows-Backend")
class TestWindowsOpenCommand:
    @pytest.fixture
    def win(self, monkeypatch):
        import os
        from streamdeck_driver.platform_backend import windows
        calls = {"startfile": [], "popen": []}
        monkeypatch.setattr(os, "startfile", lambda p: calls["startfile"].append(p), raising=False)
        monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls["popen"].append(args))
        return windows, calls

    def test_xdg_open_becomes_startfile(self, win):
        windows, calls = win
        windows.open_command("xdg-open C:\\Ordner")
        assert calls["startfile"] == ["C:\\Ordner"] and not calls["popen"]

    def test_linux_style_steam_uri_goes_to_protocol_handler(self, win):
        windows, calls = win
        windows.open_command("steam steam://rungameid/1262600")
        assert calls["startfile"] == ["steam://rungameid/1262600"] and not calls["popen"]

    def test_single_token_uses_startfile(self, win):
        windows, calls = win
        windows.open_command("notepad")
        assert calls["startfile"] == ["notepad"] and not calls["popen"]

    def test_program_with_arguments_uses_popen(self, win):
        windows, calls = win
        windows.open_command("prog.exe --flag")
        assert calls["popen"] == [["prog.exe", "--flag"]] and not calls["startfile"]
