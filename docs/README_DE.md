# CVA-DeckControl

[![Tests](https://github.com/CreAtiVe-Innovation-Studio/CVA-DeckControl/actions/workflows/tests.yml/badge.svg)](https://github.com/CreAtiVe-Innovation-Studio/CVA-DeckControl/actions/workflows/tests.yml)

**In anderen Sprachen lesen:** 🇬🇧 [English](../README.md) · [Changelog](../CHANGELOG.md)

Selbstgebauter Treiber mit offen einsehbarem Quellcode (Source-Available,
siehe "Lizenz" unten) für den **Elgato Stream Deck Mini** und die
**Streamplify DECK ONE** — komplett YAML-konfiguriert, kein Code nötig für
eigene Tasten/Seiten/Profile. Kein offizieller Treiber, kein SDK Dritter:
die USB-Protokolle beider Geräte wurden dafür direkt gegen echte Hardware
reverse-engineered.

Entstanden als persönliches Projekt, weil die offizielle Software fehlende
Features (Live-Wetterradar? Timer mit Analog-Anzeige? ein reaktiver
Avatar, der auf Flugverkehr vorm Fenster reagiert?) nicht bot — und weil es
einfach Spaß gemacht hat, die Hardware selbst anzusprechen.

## Was kann es

- **Beliebig viele Tasten/Seiten/Profile**, rein per YAML definiert — neue
  Taste anlegen heißt: YAML-Block ergänzen, Treiber neu starten, fertig
- **Live-Radar**: Flugverkehr (adsb.lol) + Niederschlag + Blitzortung, zu
  einem 15-Kacheln-Kartenbild komponiert, inkl. reaktivem Mii/VTuber-Avatar
  der auf Wetter/Flugverkehr reagiert
- **Timer/Stopwatch** mit digitaler oder analoger Anzeige direkt auf der Taste
- **Browser-Settings-GUI** zum Bearbeiten aller Tasten/Seiten/Profile ohne
  YAML von Hand anzufassen — inkl. Seiten/Profile anlegen, Tasten von
  bestehenden Vorlagen übernehmen
- **Live-Webansicht** beider Geräte (rein zum Spaß, zeigt im Browser was
  gerade auf der echten Hardware zu sehen ist)
- **Import/Export** für Elgato-/Streamplify-Profile UND fürs eigene
  YAML-Format, um Setups mit anderen zu teilen
- **Standort-Karte ("Wo ist?")**: gleiches Prinzip wie das Radar (ein großes
  Kartenbild in Kacheln zerschnitten), zeigt getrackte Personen über Home
  Assistant mit automatischer Zoom-Anpassung — getestet, aber nicht
  ausgiebig (siehe eigener Abschnitt unten)
- **Regen-Vorhersage-Karte**: eine eigene, reduzierte Kartenseite die nur
  RainViewers Niederschlags-*Vorhersage* zeigt (nächste ~30-60min), ohne
  Flugverkehr/Blitz-Schnickschnack — getestet, aber nicht ausgiebig
- **Wettervorhersage-Kacheln**: ein `weather_forecast`-Aktionstyp für
  einfache Vorhersage-Karten pro Taste (Temperatur/Wetterlage, beliebiger
  Tag/Stunde im Voraus), über Home Assistants Vorhersage-Service
- Aktionstypen: Hotkeys, Programme/URLs öffnen, App-Lautstärke, Live-System-
  Kennzahlen (CPU/RAM/GPU), Home-Assistant-Steuerung, uvm. — volle Liste in
  [SEITEN-LOGIK.md](../SEITEN-LOGIK.md)

## Performance

Bewusst so gebaut, dass es im Hintergrund kaum auffällt, statt Ressourcen
zu fressen:

- **Idle-Speicherverbrauch: ~20MB RSS**, CPU-Last praktisch 0% zwischen
  Tastendrücken/Renderzyklen (gemessen auf der Referenz-Linux-Installation,
  reale Werte hängen natürlich von der Hardware ab).
- Netzwerklastige Features sind gecacht statt live abgefragt: Niederschlags-
  Kacheln für den Radar 5 Minuten, GPU-Stats unter Windows alle 5s im
  Hintergrund aktualisiert und gecacht — kein Render-Zyklus wartet je auf
  einen Netzwerk-Roundtrip.
- Icon-Rendering passiert einmal pro Config-Änderung/Seitenwechsel, nicht
  pro Frame.
- Die Live-Webansicht ist komplett inaktiv, wenn sie ausgeschaltet ist (Standard) —
  der Schnappschuss-Speicher dahinter ist dann ein reiner No-Op-Aufruf,
  kein messbarer Overhead.
- Hintergrund-Threads (GPU-Stats, Timer-Ticker, USB-Event-Loops) sind
  leichte Polling-Schleifen mit Mehrsekunden-Intervallen, keine engen
  Schleifen, die eine CPU-Ader dauerhaft belegen.

## Unterstützte Hardware

| Gerät | Tasten | Status |
|---|---|---|
| Elgato Stream Deck Mini | 6 | Verifiziert |
| Streamplify DECK ONE | 15 | Verifiziert |
| Elgato Original / MK.2 / XL | 15 / 15 / 32 | Experimentell, siehe unten |

Andere Elgato-Modelle laufen über einen generischen Code-Pfad
(`streamdeck_driver/devices/elgato_generic.py`), aber ohne echte Hardware
zum Testen bleibt das ungetestet — siehe "Plattform-Unterstützung" unten.

## Setup

**Linux:** `./install.sh` erledigt venv + Abhängigkeiten + Konfig-Vorlagen
in einem Schritt (überschreibt nie bestehende `config/*.yaml`). Danach:

```
.venv/bin/python3 -m streamdeck_driver.daemon
```

**Windows:** entweder Python selbst installieren + `pip install -r requirements.txt`,
oder unter [Releases](https://github.com/CreAtiVe-Innovation-Studio/CVA-DeckControl/releases)
nach einer fertig gebauten `.exe` schauen (kein Python nötig) — siehe
"Fertige Windows-.exe" unten für den aktuellen Stand. Zum SELBER bauen:
`tools\build_windows_exe.bat` (braucht Python im PATH) — der Build-Pfad ist
live gegen echte Hardware verifiziert (beide Geräte verbinden, Icons/Config
laden korrekt, Autostart funktioniert).

**Manuell (jede Plattform):**
1. `pip install -r requirements.txt`
2. Konfiguration aus den Vorlagen anlegen:
   ```
   cp config/profiles.example.yaml config/profiles.yaml
   cp config/location.example.yaml config/location.yaml
   cp config/ha_secrets.example.yaml config/ha_secrets.yaml   # nur falls Home-Assistant genutzt wird
   ```
   Eigene Koordinaten/Zugangsdaten eintragen, `profiles.yaml` nach eigenem
   Bedarf umbauen (siehe SEITEN-LOGIK.md für alle Aktions-/Icon-Typen, oder
   einfach die Settings-GUI benutzen, siehe unten).
3. `assets/` muss als Ordner NEBEN diesem Repo-Ordner liegen (nicht darin) —
   für generierte Icons/Sounds/Avatare, siehe `tools/generate_*.py`. Ohne
   eigene Assets fällt das Icon-Rendering auf prozedural gezeichnete
   Platzhalter zurück, der Treiber läuft trotzdem.
4. Starten: `python3 -m streamdeck_driver.daemon`

## Fertige Windows-.exe

Der komplette Quellcode hier ist für nicht-kommerzielle Nutzung frei (siehe
"Lizenz" unten) — jede:r kann sich mit `tools\build_windows_exe.bat` selbst
eine `.exe` bauen, kostet nichts. Eine fertig gebaute `.exe` soll als Anhang
an einen [Release](https://github.com/CreAtiVe-Innovation-Studio/CVA-DeckControl/releases)
kommen — dort zuerst nachschauen; hängt (noch) keine dran, ist Selberbauen
schnell erledigt und genauso ohne Umweg. Wer das Projekt trotzdem
unterstützen möchte: es gibt ein optionales
[Buy Me a Coffee](https://buymeacoffee.com/creativeinw) — komplett
freiwillig, an nichts gekoppelt.

Ergebnis liegt unter `dist\CVA-DeckControl\`. `config\` (eigene
`profiles.yaml`/`location.yaml`/`ha_secrets.yaml`, siehe Schritt 2 oben) muss
dort HINEIN kopiert werden, `assets\` daneben, als Geschwister-Ordner von
`CVA-DeckControl\` selbst (spiegelt exakt die Quellcode-Struktur):
```
dist\
  assets\
  CVA-DeckControl\
    CVA-DeckControl.exe
    config\
```
Die Settings-GUI ist in der `.exe` mit eingebaut (kein separates Python-Skript
nötig) — per `open_gui`-Taste oder direkt `http://127.0.0.1:8420` erreichbar,
sobald `CVA-DeckControl.exe` läuft.

## Settings-GUI

`python3 gui/server.py` — lokale Browser-Oberfläche (kein Flask/FastAPI,
reine Python-Standardbibliothek) zum Bearbeiten aller Tasten/Seiten/Profile
statt YAML von Hand zu editieren, unter `http://127.0.0.1:8420`. Kann auch per
physischer Taste geöffnet werden (Aktions-Typ `open_gui` — startet die GUI
falls sie nicht läuft und öffnet sie im Browser).

Neben dem Bearbeiten einzelner Tasten (freie Auswahl aus allen Aktions-/
Icon-Typen) können direkt in der GUI auch **neue Seiten und Profile
angelegt, umbenannt und gelöscht** werden (+/✎/✕-Icons neben jedem Eintrag
in der Seitenleiste) — neue DECK-ONE-Seiten bekommen automatisch
`page_next`/`page_previous`-Tasten verdrahtet, sofern die Ziel-Tastenplätze
frei sind. Im Tasten-Editor gibt es zusätzlich "Von bestehender Taste
übernehmen" — eine Liste aller bereits konfigurierten Tasten im System, mit
der man Aktion+Icon einer vorhandenen Taste als Ausgangspunkt für eine neue
übernehmen kann, statt alles neu einzutippen.

## Eigene Features bauen

Drei Stufen, je nachdem was du brauchst:

1. **Neue Taste/Seite/Profil** — komplett über die Settings-GUI (siehe oben)
   oder von Hand in `profiles.yaml`. Kein Code, kein Neustart-Risiko: falsche
   YAML-Werte landen höchstens als `unmapped`-Taste, nichts crasht.
2. **Bestehenden Aktions-/Icon-Typ neu kombinieren** — z.B. eigene Hotkeys,
   Programme, Live-Kennzahlen, Home-Assistant-Entities. Volle Feldreferenz
   mit Beispiel-YAML für jeden Typ: [SEITEN-LOGIK.md](../SEITEN-LOGIK.md).
3. **Komplett neuer Aktions-Typ** (etwas, das es noch nicht gibt) — eine
   Funktion in `streamdeck_driver/actions.py` + ein Zweig in `dispatch()`,
   optional eine Farbe in `icon_render.py`. Kochrezept mit Code-Stellen:
   Abschnitt 6 in [SEITEN-LOGIK.md](../SEITEN-LOGIK.md).

[SEITEN-LOGIK.md](../SEITEN-LOGIK.md) ist bewusst so geschrieben, dass sowohl
eine KI (Claude Code o.ä.) als auch ein Mensch direkt damit arbeiten kann —
jede Angabe ist gegen den echten Code verifiziert, keine Vermutungen.

## Profile importieren/teilen

- Echtes Elgato-/Streamplify-Profil (Export-Datei/-Ordner) übernehmen:
  `python3 tools/import_deck_profile.py <pfad> --name <profilname>`
- Eigenes Profil an jemand anderen weitergeben:
  `python3 tools/export_profile.py <profilname>`
- Von jemand anderem erhaltenes Profil einbauen:
  `python3 tools/import_native_profile.py <datei> --name <eigener-name>`

Unbekannte Aktionen landen als `needs_review`/`unmapped` statt zu crashen
oder geraten zu werden — danach in der Settings-GUI nachbearbeiten.

## Standort-Karte ("Wo ist?")

**Getestet, aber nicht ausgiebig** — die Render-/Zoom-Logik wurde gegen
simulierte Tracker-Daten geprüft, aber nicht gegen ein echtes, über Tage/
Wochen laufendes Tracking-Setup. Falls etwas komisch aussieht (falscher
Zoom, Pin an falscher Stelle, Absturz) bitte ein Issue aufmachen.

Ein eigenes Profil, nach demselben Prinzip wie das Radar gebaut (ein großes
Kartenbild in Kacheln zerschnitten), das zeigt wo getrackte Personen gerade
sind, automatisch so gezoomt dass alle (und zuhause) sichtbar bleiben. Es
spricht bewusst **nicht** direkt mit Apple Find My oder WhatsApp — für
keins von beiden gibt es eine stabile API zum Draufbauen (Find My hat nur
inoffizielle, leicht brechende Wrapper; WhatsApps Live-Standort hat gar
keine API). Stattdessen liest es, was Home Assistant bereits als
`person`/`device_tracker`-Entities bereitstellt — jede Quelle, die HA
unterstützt, funktioniert also: die eigene GPS-Position über die
HA-Companion-App, Life360, oder die Community-Integration
[iCloud3](https://github.com/gcobb321/icloud3) für Apple Find My.

**Einrichtung:**
1. Mindestens eine `person.*`- oder `device_tracker.*`-Entity mit
   GPS-Koordinaten in Home Assistant einrichten (jede Integration geht,
   siehe oben).
2. `config/ha_secrets.yaml` muss ausgefüllt sein (siehe FAQ oben) —
   dieselben Zugangsdaten wie für die anderen Home-Assistant-Features.
3. Zum `wo_ist`-Profil wechseln (irgendwo eine `switch_profile`-Taste dafür
   anlegen, siehe [SEITEN-LOGIK.md](../SEITEN-LOGIK.md) fürs allgemeine
   Muster).

`person.*`-Entities werden bevorzugt (haben einen richtigen Anzeigenamen);
`device_tracker.*` ist der Rückfallpunkt, falls keine `person`-Entity
Koordinaten hat. Ohne eingerichteten Tracker zeigt die Seite eine
"Keine Tracker gefunden"-Karte statt einer leeren oder kaputten Karte. Eine
Pin-Taste antippen zeigt Name/Entfernung/Richtung von zuhause; nochmal
antippen blendet es wieder aus.

## Wettervorhersage

**Getestet, aber nicht ausgiebig** — gleicher Vorbehalt wie bei der
Standort-Karte: gegen echte Daten geprüft, aber nicht über einen längeren
Zeitraum. Falls etwas komisch aussieht, bitte ein Issue aufmachen.

Zwei unabhängige Teile, beide über Home Assistants Wettervorhersage-Service
(keine zusätzliche Einrichtung nötig außer `config/ha_secrets.yaml` und
einer `weather.*`-Entity — derselben, die HA für die eigene Vorhersage-
Karte nutzt):

- **`weather_forecast`-Aktionstyp** — eine einfache Karte pro Taste (siehe
  [SEITEN-LOGIK.md](../SEITEN-LOGIK.md) Abschnitt 4.10) mit Temperatur und
  Wetterlage für einen beliebigen Tag/Stunde im Voraus.
- **`wetter_vorhersage`-Profil** — eine eigene Kartenseite (eigenes Profil,
  nicht Teil des Radars), die *nur* RainViewers Niederschlags-Vorhersage
  zeigt (die nächsten ~30-60 Minuten, in ~10-Minuten-Schritten), ohne
  Flugverkehr/Blitze drauf. Taste unten rechts wechselt durch die
  verfügbaren Vorhersage-Frames. RainViewer garantiert Vorhersage-Daten
  nicht für jeden Ort/Zeitpunkt — die Seite zeigt dann "keine Daten" statt
  einer leeren oder kaputten Karte.

## Plattform-Unterstützung

| Plattform | Status |
|---|---|
| Linux | Getestet, produktiv im Einsatz |
| Windows | Getestet gegen echte Hardware (DECK ONE + Elgato Mini, Hotkeys, Lautstärke, Screenshot, Ton, GUI, gebaute `.exe`) |
| macOS | **Experimentell, ungetestet** — keine Mac-Maschine verfügbar |
| Elgato Original/MK.2/XL | **Experimentell, ungetestet** — nur die Mini ist verifiziert |

Bei Fehlern auf einer der experimentellen Plattformen/Geräte: bitte ein
Issue aufmachen (Plattform/Modell + Logausgabe) statt stillschweigend
aufzugeben — ohne echte Hardware-Rückmeldung lassen sich diese Stellen
nicht weiter absichern. Details/Vorbehalte stehen jeweils direkt im
betroffenen Modul (`streamdeck_driver/platform_backend/macos.py`,
`streamdeck_driver/devices/elgato_generic.py`).

## Häufige Fragen

**Brauche ich Home Assistant?** Nein — nur für die optionalen
`ha_toggle`/`ha_cover`/`ha_sensor`-Aktionstypen und die Blitzortung im Radar.
Ohne `config/ha_secrets.yaml` laufen diese Features einfach nicht mit, der
Rest bleibt unberührt.

**Ist meine Konfiguration/mein Standort öffentlich, wenn ich das Repo nutze?**
Nein — `config/*.yaml` (deine echten Tasten, Koordinaten, Zugangsdaten) ist
per `.gitignore` ausgeschlossen. Committed sind nur `*.example.yaml`-Vorlagen
mit Platzhalterwerten.

**Ich habe keine Ahnung von Python — kann ich trotzdem eigene Tasten bauen?**
Ja, über die Settings-GUI (siehe oben) oder direkt in `profiles.yaml` nach
den Beispielen aus [SEITEN-LOGIK.md](../SEITEN-LOGIK.md) — Code-Änderungen
braucht es dafür nicht.

**Was, wenn mein Gerät/Betriebssystem als "experimentell" markiert ist?**
Der Code dafür existiert und ist nach bestem Wissen geschrieben, aber ohne
echte Hardware zum Gegenchecken nicht abgesichert. Ein Issue mit Log/Fehler
hilft mehr als stillschweigend aufzugeben.

## Mitmachen / Fehler melden

Issues sind willkommen — am hilfreichsten sind: welches Gerät/welche
Plattform, was genau nicht funktioniert, und wenn möglich die Log-Ausgabe.
Besonders für die als experimentell markierten Stellen (macOS, andere
Elgato-Modelle) ist echtes Feedback der einzige Weg, die abzusichern.

Es gibt eine automatisierte Testsuite (`pip install -r requirements.txt -r requirements-dev.txt && pytest`,
läuft bei jedem Push über GitHub Actions) für die reine Logik — Kachel-
Geometrie, Zoom-Berechnungen, den Timer-Zustandsautomaten. Deckt bewusst
NICHT ab (und kann es auch nicht), was echte Hardware oder eine laufende
Home-Assistant-Instanz braucht — siehe [tests/README.md](../tests/README.md)
für den genauen Umfang.

## Lizenz

[PolyForm Noncommercial License 1.0.0](../LICENSE) — frei nutzbar, veränderbar
und weitergebbar für **nicht-kommerzielle Zwecke** (privat, Hobby, Lernen,
Forschung, gemeinnützige/öffentliche Einrichtungen). Für **kommerzielle
Nutzung** (Firmen, Einbau in ein eigenes Produkt/Angebot) wird eine separate
Lizenz benötigt — dafür einfach Kontakt aufnehmen: creative.info@gmx.de.

## Nicht anfassen

`streamdeck_driver/devices/base.py`, `deckone.py`, `elgato_mini.py` (USB/HID-
Protokoll, gegen echte Hardware reverse-engineered — nur bei echten
Hardware-Problemen ändern) sowie `manifest_parser.py`/`action_translation.py`
(ursprüngliches Einmal-Migrationsscript, für eigene Importe stattdessen
`tools/import_deck_profile.py` benutzen).
