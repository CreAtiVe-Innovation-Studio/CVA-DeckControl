#!/usr/bin/env bash
# Einfaches Setup fuer Linux: eigenes venv anlegen, Abhaengigkeiten
# installieren, Konfig-Vorlagen kopieren (falls noch keine eigene Config da
# ist - bestehende Dateien werden NIE ueberschrieben).
#
# Ausfuehren: ./install.sh
set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR=".venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "==> Pruefe Python..."
"$PYTHON_BIN" --version

echo "==> Lege venv an: $VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"

echo "==> Installiere Abhaengigkeiten"
"$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
"$VENV_DIR/bin/pip" install -r requirements.txt

echo "==> Kopiere Konfig-Vorlagen (nur falls noch nicht vorhanden)"
for name in profiles location ha_secrets; do
  if [ ! -f "config/${name}.yaml" ]; then
    cp "config/${name}.example.yaml" "config/${name}.yaml"
    echo "    config/${name}.yaml angelegt - bitte mit echten Werten fuellen"
  else
    echo "    config/${name}.yaml existiert schon - unveraendert gelassen"
  fi
done

echo
echo "Fertig. Naechste Schritte:"
echo "  1. config/profiles.yaml nach eigenem Bedarf anpassen (siehe SEITEN-LOGIK.md)"
echo "  2. config/location.yaml mit eigenen Koordinaten fuellen (fuer die Radar-Seite)"
echo "  3. Ordner 'assets/' NEBEN diesem Projektordner anlegen (fuer Icons/Sounds/Avatare)"
echo "  4. Starten: $VENV_DIR/bin/python3 -m streamdeck_driver.daemon"
