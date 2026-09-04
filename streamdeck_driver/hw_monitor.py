"""Liest System-Kennzahlen (CPU/RAM/GPU) fuer die DECK-ONE-Anzeige aus.
CPU/RAM ueber psutil, GPU unter Linux ueber rocm-smi --json (AMD/ROCm -
passend zur in diesem Projekt durchgehend verwendeten RX 9060 XT).

NEU 2026-09-03 (Windows-Testsession): GPU-Last/VRAM zusaetzlich fuer Windows
implementiert, herstellerunabhaengig (funktioniert auch fuer AMD, ohne
ROCm/Adrenalin-SDK) ueber die eingebauten Windows-Performance-Counter:
- Last: Summe von '\\GPU Engine(*engtype_3D)\\Utilization Percentage' ueber
  alle Prozesse (jeder Prozess bekommt seinen Anteil der 3D-Engine-Zeit
  gemeldet, Summe ergibt die Gesamtauslastung).
- VRAM: Summe von '\\GPU Process Memory(*)\\Dedicated Usage' (Bytes) geteilt
  durch die tatsaechliche Gesamt-VRAM-Groesse. WICHTIG: NICHT ueber
  Win32_VideoController.AdapterRAM (WMI) - das liefert bei dieser RX 9060 XT
  faelschlich nur 4 GB (32-Bit-Overflow-Bug, bekanntes WMI-Problem bei allen
  Karten mit >4GB VRAM), obwohl die Karte 16GB hat. Stattdessen der 64-Bit-
  Registry-Wert 'HardwareInformation.qwMemorySize' unter dem Grafiktreiber-
  Klassenschluessel, live verifiziert: liefert korrekt 15.9GB.
- Temperatur: bewusst NICHT implementiert - es gibt keinen herstellerneutralen
  Weg dafuer unter Windows ohne Vendor-SDK (AMD ADL) oder einen zusaetzlichen
  Kernel-Treiber (wie ihn z.B. LibreHardwareMonitor mitbringt) - bleibt `None`,
  Aufrufer/Anzeige kommt damit bereits klar (zeigt "--")."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time

import psutil

logger = logging.getLogger("streamdeck_driver.hw_monitor")

_IS_WINDOWS = sys.platform == "win32"
_GPU_VRAM_TOTAL_BYTES: float | None = None
_GPU_VRAM_TOTAL_CHECKED = False

# NEU 2026-09-03: der PowerShell-Aufruf fuer die Windows-GPU-Stats braucht
# ca. 3s allein fuer den Prozessstart (gemessen) - bei einem 3s-Refresh-
# Intervall (siehe deckone_controller.SYSTEM_REFRESH_INTERVAL_S) wuerde jeder
# einzelne Refresh-Zyklus dadurch komplett blockieren. Gleiches Cache-Muster
# wie schon in radar.py::_fetch_aircraft: ein Hintergrund-Thread aktualisiert
# den Wert alle paar Sekunden, get_gpu_stats() liest nur den letzten Stand
# und blockiert nie.
#
# BUG GEFUNDEN UND GEFIXT (live gemeldet nach Umstellung der .exe auf
# console=False): jeder subprocess.run(["powershell", ...]) OHNE
# creationflags=CREATE_NO_WINDOW oeffnet unter Windows ein NEUES, sichtbares
# Konsolenfenster, sobald der aufrufende Prozess selbst KEINE eigene Konsole
# hat (was bei console=False der Fall ist - vorher, mit console=True, hat
# der PowerShell-Kindprozess die Konsole des Elternprozesses mitbenutzt,
# der Effekt war unsichtbar). Bei alle 5s wiederholtem Aufruf: ein staendig
# aufblitzendes leeres Terminal-Fenster. Alle drei PowerShell-Aufrufe in
# diesem Modul haben deshalb jetzt creationflags=subprocess.CREATE_NO_WINDOW.
_GPU_STATS_CACHE = {"load": None, "vram": None, "temp": None}
_GPU_STATS_REFRESH_INTERVAL_S = 5.0
_gpu_stats_thread_started = False
_gpu_stats_lock = threading.Lock()

# Gleitender Durchschnitt pro Metrik fuer die Ampel-Farbwahl (siehe
# rolling_average()) - NICHT fuer den angezeigten Zahlenwert selbst, der
# bleibt der aktuelle Momentanwert. Zweck: verhindert staendiges Umspringen
# der Kartenfarbe (gruen/gelb/rot), wenn ein Wert knapp um eine Schwelle
# herum schwankt.
_HISTORY: dict[str, list[tuple[float, float]]] = {}
ROLLING_WINDOW_S = 120.0


def rolling_average(metric: str, value: float | None) -> float | None:
    if value is None:
        return None
    now = time.monotonic()
    hist = _HISTORY.setdefault(metric, [])
    hist.append((now, value))
    cutoff = now - ROLLING_WINDOW_S
    while hist and hist[0][0] < cutoff:
        hist.pop(0)
    return sum(v for _, v in hist) / len(hist)


def get_recent_values(metric: str) -> list[float]:
    """Rohe Werte der letzten ROLLING_WINDOW_S Sekunden fuer diese Metrik,
    aeltester zuerst - fuer die Verlaufsgraph-Darstellung. Nutzt dieselbe
    Historie wie rolling_average() (wird dort befuellt/bereinigt)."""
    return [v for _, v in _HISTORY.get(metric, [])]


def get_cpu_percent() -> float:
    return psutil.cpu_percent(interval=None)


def get_cpu_temp() -> float | None:
    try:
        temps = psutil.sensors_temperatures()
        pkg = temps.get("coretemp", [])
        for entry in pkg:
            if "Package" in entry.label:
                return entry.current
        return pkg[0].current if pkg else None
    except Exception as exc:
        logger.debug("CPU-Temperatur nicht lesbar: %s", exc)
        return None


def get_ram_percent() -> float:
    return psutil.virtual_memory().percent


def get_ram_used_total_gb() -> tuple[float, float]:
    vm = psutil.virtual_memory()
    return vm.used / 1e9, vm.total / 1e9


def get_disk_percent(path: str = "/") -> float | None:
    try:
        return psutil.disk_usage(path).percent
    except Exception as exc:
        logger.debug("Festplatten-Auslastung nicht lesbar (%s): %s", path, exc)
        return None


def _get_gpu_vram_total_bytes_windows() -> float | None:
    """Gesamt-VRAM in Bytes, EINMALIG per PowerShell/Registry ermittelt und
    danach gecacht (aendert sich zur Laufzeit nicht). Bewusst NICHT ueber
    Win32_VideoController.AdapterRAM (WMI) - liefert bei Karten mit >4GB VRAM
    einen falschen (gekappten) Wert, siehe Modul-Docstring."""
    global _GPU_VRAM_TOTAL_BYTES, _GPU_VRAM_TOTAL_CHECKED
    if _GPU_VRAM_TOTAL_CHECKED:
        return _GPU_VRAM_TOTAL_BYTES
    _GPU_VRAM_TOTAL_CHECKED = True
    try:
        proc = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-ItemProperty -Path "
                "'HKLM:\\SYSTEM\\ControlSet001\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}\\*' "
                "-Name 'HardwareInformation.qwMemorySize' -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty 'HardwareInformation.qwMemorySize' | "
                "Select-Object -First 1",
            ],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        _GPU_VRAM_TOTAL_BYTES = float(proc.stdout.strip())
    except (subprocess.SubprocessError, ValueError) as exc:
        logger.debug("GPU-VRAM-Gesamtgroesse nicht lesbar: %s", exc)
    return _GPU_VRAM_TOTAL_BYTES


def _get_gpu_stats_windows() -> dict:
    result = {"load": None, "vram": None, "temp": None}
    try:
        proc = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "$l=(Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage' "
                "-ErrorAction SilentlyContinue).CounterSamples | "
                "Measure-Object -Property CookedValue -Sum | Select-Object -ExpandProperty Sum; "
                "$v=(Get-Counter '\\GPU Process Memory(*)\\Dedicated Usage' "
                "-ErrorAction SilentlyContinue).CounterSamples | "
                "Measure-Object -Property CookedValue -Sum | Select-Object -ExpandProperty Sum; "
                "\"$l|$v\"",
            ],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        load_str, vram_str = proc.stdout.strip().split("|")
        result["load"] = min(100.0, float(load_str))
        vram_total = _get_gpu_vram_total_bytes_windows()
        if vram_total:
            result["vram"] = min(100.0, float(vram_str) / vram_total * 100.0)
    except (subprocess.SubprocessError, ValueError, IndexError) as exc:
        logger.debug("GPU-Stats (Windows) nicht lesbar: %s", exc)
    # Temperatur bewusst nicht implementiert, siehe Modul-Docstring.
    return result


def _gpu_stats_refresh_loop() -> None:
    while True:
        try:
            stats = _get_gpu_stats_windows()
            with _gpu_stats_lock:
                _GPU_STATS_CACHE.update(stats)
        except Exception:
            logger.exception("Fehler im GPU-Stats-Hintergrund-Thread")
        time.sleep(_GPU_STATS_REFRESH_INTERVAL_S)


def get_gpu_stats() -> dict:
    """Gibt {'load': float|None, 'vram': float|None, 'temp': float|None} zurueck.
    None bei jedem Feld, das nicht ausgelesen werden konnte (z.B. rocm-smi fehlt)
    - Aufrufer muss damit umgehen koennen, kein Absturz bei fehlender GPU-Info."""
    if _IS_WINDOWS:
        # Liest NUR den Cache, blockiert nie (siehe Kommentar bei
        # _GPU_STATS_CACHE oben) - ein Hintergrund-Thread fuellt ihn alle
        # paar Sekunden per (langsamem) PowerShell-Aufruf.
        global _gpu_stats_thread_started
        if not _gpu_stats_thread_started:
            _gpu_stats_thread_started = True
            threading.Thread(target=_gpu_stats_refresh_loop, name="gpu-stats-refresh", daemon=True).start()
        with _gpu_stats_lock:
            return dict(_GPU_STATS_CACHE)
    result = {"load": None, "vram": None, "temp": None}
    try:
        proc = subprocess.run(
            ["rocm-smi", "--showuse", "--showmemuse", "--showtemp", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        data = json.loads(proc.stdout)
        card = next(iter(data.values()))
        if "GPU use (%)" in card:
            result["load"] = float(card["GPU use (%)"])
        if "GPU Memory Allocated (VRAM%)" in card:
            result["vram"] = float(card["GPU Memory Allocated (VRAM%)"])
        if "Temperature (Sensor edge) (C)" in card:
            result["temp"] = float(card["Temperature (Sensor edge) (C)"])
    except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError, StopIteration, ValueError) as exc:
        logger.debug("GPU-Stats nicht lesbar: %s", exc)
    return result


def snapshot() -> dict:
    """Ein kompletter Kennzahlen-Schnappschuss fuer die 'system'-Seite."""
    gpu = get_gpu_stats()
    ram_used, ram_total = get_ram_used_total_gb()
    return {
        "cpu": get_cpu_percent(),
        "cpu_temp": get_cpu_temp(),
        "ram": get_ram_percent(),
        "ram_used_gb": ram_used,
        "ram_total_gb": ram_total,
        "gpu_load": gpu["load"],
        "gpu_vram": gpu["vram"],
        "gpu_temp": gpu["temp"],
        "disk": get_disk_percent("/"),
    }
