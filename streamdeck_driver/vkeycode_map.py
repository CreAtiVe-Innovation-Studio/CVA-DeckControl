"""Windows-VKeyCode -> Linux evdev-Keycode Tabelle.

Nur die VKeyCodes, die in den vorhandenen Manifesten tatsaechlich vorkommen
(siehe grep-Auswertung aller *.json unter dokumentation/*-manifests/), wurden
hier aufgenommen. Fuer die Standard-Multimedia-Tasten (173-179) ist die Win32-
VK-Tabelle eindeutig und gut dokumentiert (VK_VOLUME_MUTE=0xAD usw.) - diese
Zuordnungen sind mit hoher Sicherheit korrekt.

Fuer die VKeyCodes im "Streaming"-Profil (33,34,37,39,40,47,61,92,96,106,110,
111,125,127,155,222) folgen die Namen der Buttons keinem erkennbaren Muster
(Fantasienamen wie "Kassengold", "Abflug") - das sind mit hoher Wahrscheinlich-
keit an AutoHotkey/OBS-Skripte gebundene, selten genutzte Tasten (Numpad,
F13-F24, Windows-Taste etc.), die als reine Hotkey-Trigger missbraucht wurden,
NICHT die tatsaechlich sichtbare Taste. Diese Zuordnungen sind Bestapproximation
nach der offiziellen Win32-VK-Konstantentabelle, aber NICHT gegen echte Hardware
verifiziert (auf diesem Rechner gibt es kein Windows/AutoHotkey zum Gegenpruefen).
Siehe SETUP.md "Bekannte Grenzen".

Linux-Keycodes (linux/input-event-codes.h) werden numerisch verwendet, weil das
robuster mit ydotool funktioniert als symbolische Namen (nicht jede ydotool-
Version kennt KEY_*-Namen).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyMapping:
    name: str
    linux_keycode: int
    verified: bool


# Linux evdev keycodes (linux/input-event-codes.h) fuer Modifier
KEY_LEFTCTRL = 29
KEY_LEFTSHIFT = 42
KEY_LEFTALT = 56
KEY_LEFTMETA = 125

VK_TO_LINUX: dict[int, KeyMapping] = {
    # --- Standard Multimedia-Tasten (Win32 VK 0xAD-0xB3), sicher ---
    173: KeyMapping("Mute", 113, True),  # KEY_MUTE
    174: KeyMapping("VolumeDown", 114, True),  # KEY_VOLUMEDOWN
    175: KeyMapping("VolumeUp", 115, True),  # KEY_VOLUMEUP
    176: KeyMapping("MediaNextTrack", 163, True),  # KEY_NEXTSONG
    177: KeyMapping("MediaPrevTrack", 165, True),  # KEY_PREVIOUSSONG
    178: KeyMapping("MediaStop", 166, True),  # KEY_STOPCD
    179: KeyMapping("MediaPlayPause", 164, True),  # KEY_PLAYPAUSE
    # --- Sonstige Standard-VK-Codes, sicher ---
    44: KeyMapping("PrintScreen", 99, True),  # KEY_SYSRQ
    83: KeyMapping("S", 31, True),
    89: KeyMapping("Y", 21, True),
    90: KeyMapping("Z", 44, True),
    37: KeyMapping("Left", 105, True),
    39: KeyMapping("Right", 106, True),
    40: KeyMapping("Down", 108, True),
    33: KeyMapping("PageUp", 104, True),
    34: KeyMapping("PageDown", 109, True),
    # --- Vermutlich AutoHotkey/OBS-Trigger-Tasten, NICHT gegen Hardware
    #     verifiziert (siehe Moduldoc) ---
    92: KeyMapping("RWin", 126, False),  # KEY_RIGHTMETA
    96: KeyMapping("Numpad0", 82, False),  # KEY_KP0
    106: KeyMapping("NumpadMultiply", 55, False),  # KEY_KPASTERISK
    110: KeyMapping("NumpadDecimal", 83, False),  # KEY_KPDOT
    111: KeyMapping("NumpadDivide", 98, False),  # KEY_KPSLASH
    125: KeyMapping("F14", 184, False),
    127: KeyMapping("F16", 186, False),
    131: KeyMapping("F20", 190, False),
    132: KeyMapping("F21", 191, False),
    133: KeyMapping("F22", 192, False),
    155: KeyMapping("F24_approx", 194, False),  # unsicher, evtl. andere Taste
    222: KeyMapping("Apostrophe", 40, False),  # KEY_APOSTROPHE
    61: KeyMapping("Unknown_0x3D", -1, False),  # kein Standard-VK, keine Zuordnung
}


def resolve(vkeycode: int, ctrl: bool, shift: bool, alt: bool, meta: bool = False):
    """Gibt eine Liste von Linux-Keycodes (Modifier zuerst, Hauptaste zuletzt)
    zurueck, oder None, wenn vkeycode nicht bekannt/nicht sinnvoll abbildbar ist."""
    mapping = VK_TO_LINUX.get(vkeycode)
    if mapping is None or mapping.linux_keycode < 0:
        return None
    codes = []
    if ctrl:
        codes.append(KEY_LEFTCTRL)
    if shift:
        codes.append(KEY_LEFTSHIFT)
    if alt:
        codes.append(KEY_LEFTALT)
    if meta:
        codes.append(KEY_LEFTMETA)
    codes.append(mapping.linux_keycode)
    return codes
