"""Alle Plattform-Backends muessen dieselbe open_url-Signatur haben: actions.run_website()
ruft open_url(url, new_window=...) plattformunabhaengig auf (Windows/macOS fielen sonst
mit TypeError aus, als nur linux.py den Parameter bekam). Reine Quelltext-Pruefung."""
import ast
from pathlib import Path

BACKENDS = Path(__file__).resolve().parent.parent / "streamdeck_driver" / "platform_backend"


def _open_url_params(name: str) -> list[str]:
    tree = ast.parse((BACKENDS / f"{name}.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "open_url")
    return [a.arg for a in fn.args.args]


def test_open_url_signature_is_identical_on_all_platforms():
    expected = _open_url_params("linux")
    assert "new_window" in expected
    for name in ("windows", "macos", "unsupported"):
        assert _open_url_params(name) == expected, name
