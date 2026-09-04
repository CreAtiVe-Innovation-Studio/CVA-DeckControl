#!/bin/bash
# Schaltet den Standard-Audioausgang zwischen den beiden echten Ausgaengen
# dieser Maschine um: HDMI/DisplayPort (Lautsprecher) und dem analogen
# Kopfhoerer-Ausgang der Onboard-Karte (Built-in Audio).
# Aufruf: audio_output.sh speakers|headphones

set -euo pipefail

target="${1:?Usage: audio_output.sh speakers|headphones}"

find_sink_id() {
    wpctl status \
        | sed -n '/Audio$/,/^Video$/p' \
        | sed -n '/Sinks:/,/Sink endpoints:/p' \
        | grep -F "$1" \
        | head -1 \
        | sed -E 's/^[^0-9]*([0-9]+).*/\1/'
}

find_device_id() {
    wpctl status \
        | sed -n '/Audio$/,/^Video$/p' \
        | sed -n '/Devices:/,/Sinks:/p' \
        | grep -F "$1" \
        | head -1 \
        | sed -E 's/^[^0-9]*([0-9]+).*/\1/'
}

case "$target" in
    speakers)
        sink_id="$(find_sink_id "HDA ATI HDMI")"
        ;;
    headphones)
        # Built-in-Audio-Karte braucht ein Output-faehiges Profil (Duplex haelt
        # das Analog-Mikrofon gleichzeitig aktiv), sonst existiert kein Sink.
        # Geraete-ID per Namenssuche statt fest verdrahtet, da PipeWire/
        # WirePlumber die IDs bei Reconnects/Neustarts neu vergibt (2026-09-01
        # beobachtet: Built-in Audio wechselte von ID 50 auf 51).
        device_id="$(find_device_id "Built-in Audio")"
        if [ -z "$device_id" ]; then
            echo "Kein Geraet 'Built-in Audio' gefunden" >&2
            exit 1
        fi
        wpctl set-profile "$device_id" 1
        sleep 0.3
        sink_id="$(find_sink_id "Built-in Audio")"
        ;;
    *)
        echo "Unbekanntes Ziel: $target" >&2
        exit 1
        ;;
esac

if [ -z "$sink_id" ]; then
    echo "Kein Sink fuer '$target' gefunden" >&2
    exit 1
fi

wpctl set-default "$sink_id"
