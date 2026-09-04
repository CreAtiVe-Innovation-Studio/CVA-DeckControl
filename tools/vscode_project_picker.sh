#!/bin/bash
# Terminal-Menue fuer die Coding-Taste "VS Code": gleiche Projektauswahl wie
# claude_project_picker.sh, oeffnet aber VS Code statt Claude Code CLI und
# triggert danach automatisch das Claude-Code-Panel ueber den Standard-
# Shortcut Ctrl+Shift+Escape (claude-vscode.editor.open, siehe
# anthropic.claude-code Extension - kein CLI-Weg dafuer verfuegbar).

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

echo "Oeffne VS Code in $BASE/$target ..."
code "$BASE/$target"

( sleep 3 && ydotool key 29:1 42:1 1:1 1:0 42:0 29:0 >/dev/null 2>&1 ) &
disown
