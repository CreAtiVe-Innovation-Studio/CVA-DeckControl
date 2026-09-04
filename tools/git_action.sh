#!/bin/bash
# Terminal-Taste fuer git status/pull/push: gleiche Projektauswahl wie
# claude_project_picker.sh, fuehrt danach den uebergebenen git-Befehl aus und
# haelt das Terminal offen, bis man Enter drueckt (sonst schliesst es sofort
# und man kann die Ausgabe nicht lesen).
# Aufruf: git_action.sh status|pull|push

set -e

action="${1:?Usage: git_action.sh status|pull|push}"
BASE="$HOME/Dokumente/KI/Projekte"
cd "$BASE"

mapfile -t projects < <(find . -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)

echo "Projekte in $BASE:"
for i in "${!projects[@]}"; do
    printf "  %d) %s\n" "$((i + 1))" "${projects[$i]}"
done
echo
read -rp "Welches Projekt (Nummer)? " choice

if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt "${#projects[@]}" ]; then
    echo "Ungueltige Auswahl."
    read -rp "Enter zum Schliessen ..."
    exit 1
fi

cd "$BASE/${projects[$((choice - 1))]}"
echo
echo "=== git $action in $PWD ==="
git "$action"
echo
read -rp "Enter zum Schliessen ..."
