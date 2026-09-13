#!/usr/bin/env python3
"""Steuert die Medien-Wiedergabe (Play/Pause/Stop/Weiter/Zurueck/Shuffle).

BUG GEFUNDEN 2026-09-13 (live gemeldet: "Audio-Seite funktioniert nicht mit
mpv, kann nicht stoppen/vorspulen/zurueck/shuffle"): die Audio-Seite sendet
bisher nur die klassischen XF86Audio*-Medientasten per ydotool. Die kommen
bei Spotify & Co an, weil Desktop-Umgebungen sie global abfangen und per
MPRIS (org.mpris.MediaPlayer2) an den laufenden Player weiterreichen - mpv
registriert sich aber OHNE Zusatz-Skript gar nicht als MPRIS-Player (live
geprueft: kein mpris-Paket, kein ~/.config/mpv/scripts/ vorhanden), die
Tasten haben also nirgendwo ein Ziel.

Deshalb hier stattdessen zuerst ueber mpvs EIGENEN JSON-IPC-Socket steuern
(https://mpv.io/manual/stable/#json-ipc) - funktioniert unabhaengig von
Fensterfokus und MPRIS, solange mpv mit 'input-ipc-server=/tmp/mpvsocket'
gestartet wurde (siehe ~/.config/mpv/mpv.conf). NUR falls dieser Socket
nicht erreichbar ist (mpv laeuft nicht, oder eine sehr alte mpv-Instanz ohne
diese Konfig), Ruckfall auf den klassischen Medientasten-Druck per ydotool -
fuer Spotify & Co, die MPRIS/Fokus-basiert reagieren.

Aufruf: mpv_media_key.py <play_pause|stop|next|prev|shuffle>
"""
import json
import socket
import subprocess
import sys

MPV_SOCKET = "/tmp/mpvsocket"

# mpv-IPC-Kommando je Aktion, siehe mpv-Handbuch "List of Input Commands".
MPV_COMMANDS = {
    "play_pause": {"command": ["cycle", "pause"]},
    "stop": {"command": ["stop"]},
    "next": {"command": ["playlist-next"]},
    "prev": {"command": ["playlist-prev"]},
    "shuffle": {"command": ["playlist-shuffle"]},
}

# Rueckfall: Linux-Eingabe-Event-Codes der Standard-Medientasten (siehe
# vkeycode_map.py, KEY_PLAYPAUSE/KEY_STOPCD/KEY_NEXTSONG/KEY_PREVIOUSSONG).
# 'shuffle' hat keine echte Medientaste im Standard - F22 (192) ist der
# Wert, der schon aus dem urspruenglichen Windows-Manifest-Import kam.
FALLBACK_KEYCODES = {
    "play_pause": 164,
    "stop": 166,
    "next": 163,
    "prev": 165,
    "shuffle": 192,
}


def try_mpv_ipc(action: str) -> bool:
    """True wenn das Kommando erfolgreich an mpv geschickt wurde."""
    command = MPV_COMMANDS[action]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            sock.connect(MPV_SOCKET)
            sock.sendall((json.dumps(command) + "\n").encode("utf-8"))
        return True
    except OSError as exc:
        print(f"mpv-IPC nicht erreichbar ({exc}), Rueckfall auf Medientaste", file=sys.stderr)
        return False


def fallback_hotkey(action: str) -> None:
    code = FALLBACK_KEYCODES[action]
    subprocess.run(["ydotool", "key", f"{code}:1", f"{code}:0"])


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in MPV_COMMANDS:
        print(f"Nutzung: {sys.argv[0]} <{'|'.join(MPV_COMMANDS)}>", file=sys.stderr)
        sys.exit(1)
    action = sys.argv[1]
    if not try_mpv_ipc(action):
        fallback_hotkey(action)


if __name__ == "__main__":
    main()
