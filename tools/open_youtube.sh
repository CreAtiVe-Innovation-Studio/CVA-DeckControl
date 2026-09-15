#!/bin/bash
# YouTube-Taste: Lautstaerke erst auf 5% (YouTube startet gerne unerwartet
# laut), dann in einem neuen Firefox-Fenster oeffnen (Nutzerwunsch 2026-09-15:
# Firefox statt Chromium, da dort ueberall angemeldet).
wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%
firefox --new-window https://www.youtube.com
