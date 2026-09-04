#!/bin/bash
# Terminal-Menue fuer die KI-Taste "Claude Code": zeigt bestehende Projekte
# unter ~/Dokumente/KI/Projekte nummeriert an, eine Zahl waehlt ein bestehendes
# Projekt, ein Textname legt einen neuen Ordner an - danach startet Claude Code
# direkt in diesem Ordner.

set -e

BASE="$HOME/Dokumente/KI/Projekte"
mkdir -p "$BASE"
cd "$BASE"

mapfile -t projects < <(find . -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)

echo "Projekte in $BASE:"
for i in "${!projects[@]}"; do
    printf "  %d) %s\n" "$((i + 1))" "${projects[$i]}"
done
echo
read -rp "Nummer waehlen oder neuen Projektnamen eingeben: " choice

if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#projects[@]}" ]; then
    target="${projects[$((choice - 1))]}"
else
    target="$choice"
    mkdir -p "$target"
fi

cd "$BASE/$target"
echo "Starte Claude Code in $BASE/$target ..."
exec claude-code
