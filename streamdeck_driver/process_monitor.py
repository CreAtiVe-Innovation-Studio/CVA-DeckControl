"""Ermittelt die Top-Prozesse fuer CPU/RAM/GPU-Auslastung und zeigt sie in
einem kleinen Popup an (siehe platform_backend.show_message_popup) -
ausgeloest durch Druecken der jeweiligen Prozent-Taste auf der DECK-ONE
'system'-Seite."""
from __future__ import annotations

import json
import logging
import subprocess
import threading
import time

import psutil

from . import platform_backend

logger = logging.getLogger("streamdeck_driver.process_monitor")

MIN_PERCENT = 5.0
TOP_N = 5
CPU_SAMPLE_DELAY_S = 0.6


def top_processes_by_cpu(n: int = TOP_N, min_percent: float = MIN_PERCENT) -> list[tuple[str, float]]:
    procs = list(psutil.process_iter(["name"]))
    for p in procs:
        try:
            p.cpu_percent(None)  # erster Aufruf primt die Messung (siehe psutil-Doku)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(CPU_SAMPLE_DELAY_S)
    results = []
    for p in procs:
        try:
            pct = p.cpu_percent(None)
            if pct >= min_percent:
                results.append((p.info["name"] or f"pid{p.pid}", pct))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:n]


def top_processes_by_ram(n: int = TOP_N, min_percent: float = MIN_PERCENT) -> list[tuple[str, float]]:
    results = []
    for p in psutil.process_iter(["name"]):
        try:
            pct = p.memory_percent()
            if pct >= min_percent:
                results.append((p.info["name"] or f"pid{p.pid}", pct))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:n]


def top_processes_by_gpu(n: int = TOP_N, min_percent: float = MIN_PERCENT) -> list[tuple[str, float]]:
    """Nutzt rocm-smi --showpids --json (VRAM pro Prozess) als GPU-Auslastungs-
    Proxy, da CU-Auslastung pro Prozess auf dieser Hardware/diesem ROCm-Stand
    zuverlaessig 'unknown' liefert. Reales Ausgabeformat (verifiziert 2026-08-21,
    weicht von der rocm-smi-Doku ab): {"system": {"PID<pid>": "<name>, <n_gpus>,
    <vram_bytes>, <?>, <cu_occupancy>"}} - also ein flacher String pro PID, KEIN
    verschachteltes Objekt mit benannten Feldern."""
    try:
        proc = subprocess.run(
            ["rocm-smi", "--showpids", "--json"], capture_output=True, text=True, timeout=5,
        )
        data = json.loads(proc.stdout)
    except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("GPU-Prozessliste nicht lesbar: %s", exc)
        return []

    total_vram = None
    try:
        stats = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--json"], capture_output=True, text=True, timeout=5,
        )
        vram_data = json.loads(stats.stdout)
        card = next(iter(vram_data.values()))
        total_vram = float(card.get("VRAM Total Memory (B)", 0)) or None
    except Exception:
        pass

    entries = data.get("system", {}) if isinstance(data, dict) else {}
    results = []
    for pid_key, raw in entries.items():
        if not pid_key.startswith("PID") or not isinstance(raw, str):
            continue
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 3:
            continue
        name = parts[0]
        try:
            vram_bytes = float(parts[2])
        except ValueError:
            continue
        pct = (vram_bytes / total_vram * 100) if total_vram else None
        results.append((name, pct if pct is not None else vram_bytes))

    if total_vram:
        results = [(n_, p) for n_, p in results if p >= min_percent]
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:n]


_METRIC_FUNCS = {
    "cpu": top_processes_by_cpu,
    "ram": top_processes_by_ram,
    "gpu_load": top_processes_by_gpu,
}

_METRIC_TITLES = {
    "cpu": "Top-Prozesse nach CPU-Last",
    "ram": "Top-Prozesse nach RAM-Nutzung",
    "gpu_load": "Top-Prozesse nach GPU/VRAM-Nutzung",
}


def show_top_processes(metric: str) -> None:
    """Sammelt die Top-Prozesse fuer die Metrik (blockierend, deshalb IMMER
    in einem eigenen Thread aufrufen, siehe _run_async) und zeigt sie per
    zenity an (Popen, nicht-blockierend, damit das Fenster beliebig lange
    offen bleiben kann ohne irgendetwas einzufrieren)."""
    func = _METRIC_FUNCS.get(metric)
    if func is None:
        return
    try:
        results = func()
    except Exception:
        logger.exception("Fehler beim Ermitteln der Top-Prozesse fuer %s", metric)
        return

    title = _METRIC_TITLES.get(metric, "Top-Prozesse")
    if not results:
        text = "Kein Prozess ueber 5% Auslastung gefunden."
    else:
        lines = [f"{i+1}. {name}  —  {pct:.1f}%" for i, (name, pct) in enumerate(results)]
        text = "\n".join(lines)

    platform_backend.show_message_popup(title, text)


def show_top_processes_async(metric: str) -> None:
    """Startet show_top_processes() in einem eigenen Thread - die CPU-Messung
    braucht ~0.6s Wartezeit, das darf die DECK-ONE-Ereignisschleife nicht
    blockieren (gleiches Muster wie beim Screenshot-Fix in actions.py)."""
    threading.Thread(target=show_top_processes, args=(metric,), daemon=True).start()
