# PyInstaller-Spec fuer eine eigenstaendige Windows-.exe - buendelt den
# Daemon + alle Abhaengigkeiten, damit Endnutzer kein Python installieren
# muessen. Build+Lauf am 2026-09-03 live gegen echte Hardware verifiziert
# (DECK ONE + Elgato Mini verbinden, Config/Icons laden korrekt) - 'hidapi'
# buendelt sauber, kein Zadig/libusb-DLL-Aerger. Einziger dabei gefundener
# Bug (jetzt gefixt): das Analysis-Zielskript darf NICHT direkt
# streamdeck_driver/daemon.py sein - PyInstaller fuehrt es dann als nacktes
# __main__ ohne Paket-Kontext aus, die relativen Importe dort
# (`from . import ...`) brechen mit ImportError. Deshalb der Umweg ueber
# run_daemon.py (Projekt-Root, absoluter Import) als Einstiegspunkt.
#
# Die Settings-GUI (gui/server.py) laeuft eingebettet im selben Prozess (siehe
# gui/server.py::start_in_thread(), genutzt vom 'open_gui'-Aktionstyp) - kein
# separates Skript/keine zweite .exe noetig. Damit das in der gebauten .exe
# funktioniert, brauchte es zwei Anpassungen, die schon im Code stecken (NICHT
# hier im Spec): streamdeck_driver/paths.py loest config/assets-Pfade relativ
# zur .exe statt zu einem PyInstaller-Temp-Ordner auf (sys.frozen-Check), und
# gui/server.py's STATIC_DIR zeigt in der .exe auf das unten per 'datas'
# gebuendelte gui/static/index.html (sys._MEIPASS statt Pfad neben der .exe -
# das ist gebuendelte App-Ressource, kein vom Nutzer editierbarer Ordner).
#
# Bauen (auf Windows, im aktivierten venv mit installiertem PyInstaller):
#   pyinstaller tools/build_windows_exe.spec
# Ergebnis landet in dist/CVA-DeckControl/CVA-DeckControl.exe
from __future__ import annotations

import sys
from pathlib import Path

block_cipher = None
PROJECT_ROOT = Path(SPECPATH).resolve().parent  # linux-driver/, trotz des Namens auch der Windows-Projektordner

a = Analysis(
    [str(PROJECT_ROOT / "run_daemon.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        (str(PROJECT_ROOT / "gui" / "static" / "index.html"), "gui/static"),
    ],
    hiddenimports=[
        "hid",
        "usb.core",
        "usb.util",
        "usb.backend.libusb1",
        "PIL._tkinter_finder",
        "streamdeck_driver.platform_backend.windows",
        "gui.server",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CVA-DeckControl",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # kein Konsolenfenster mehr (v.a. fuer Autostart) - Logs
                     # gehen stattdessen immer in logs\daemon.log neben der
                     # .exe (siehe daemon.py::main(), RotatingFileHandler),
                     # WICHTIG genau deswegen: ohne Konsole gibt es unter
                     # Windows kein sys.stderr mehr, ein reines
                     # logging.StreamHandler-Setup wuerde sonst abstuerzen
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="CVA-DeckControl",
)
