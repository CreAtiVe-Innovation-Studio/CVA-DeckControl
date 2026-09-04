"""Einstiegspunkt fuer die per PyInstaller gebaute .exe (siehe
tools/build_windows_exe.spec). Reiner Wrapper - der eigentliche Code bleibt
in streamdeck_driver/daemon.py.

Grund fuer diese extra Datei: PyInstaller fuehrt das Analysis-Zielskript als
nacktes __main__ ohne Paket-Kontext aus. daemon.py selbst nutzt relative
Importe (`from . import ...`), die genau diesen Paket-Kontext brauchen - im
normalen Betrieb liefert `python -m streamdeck_driver.daemon` ihn, in der
.exe gibt es kein Aequivalent dazu. Dieses Skript liegt auf Projekt-Root-Ebene
und importiert streamdeck_driver ganz normal als Paket (absoluter Import),
das funktioniert in beiden Faellen (`python run_daemon.py` UND als
PyInstaller-Entrypoint)."""
import sys

from streamdeck_driver.daemon import main

if __name__ == "__main__":
    sys.exit(main())
