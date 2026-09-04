#!/bin/bash
# YouTube-Taste: Lautstaerke erst auf 5% (YouTube startet gerne unerwartet
# laut), dann eigenes App-Fenster oeffnen.
wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%
/snap/bin/chromium --app=https://www.youtube.com
