#!/bin/bash
# Oeffnet ComfyUI im Browser. Laeuft seit dem 2026-09-02-Dienst-Umbau als
# systemd --user Service (comfyui.service) statt als loser Hintergrund-
# prozess - diese Taste startet den Dienst bei Bedarf (No-Op falls schon
# aktiv) und wartet kurz, bevor sie den Browser oeffnet.

systemctl --user start comfyui.service

for i in $(seq 1 30); do
    curl -s -m 2 "http://localhost:8188/" -o /dev/null && break
    sleep 1
done

xdg-open "http://localhost:8188" >/dev/null 2>&1
