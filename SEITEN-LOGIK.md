# Stream Deck: Seiten-/Aktions-Logik (Referenz zum Erweitern)

Dieses Dokument beschreibt, wie Seiten, Profile, Tasten, Aktionen und Icons
fuer beide unterstuetzten Geraete konfiguriert sind - fuer eigene
Tasten/Seiten/Aktionen, egal ob von Hand editiert oder mit Hilfe einer KI
(z.B. Claude Code), ohne den Python-Code lesen zu muessen. Alle Angaben sind
aus dem tatsaechlichen Code verifiziert (Stand 2026-08-26), keine Vermutungen.

Betroffene Geraete:
- **Elgato Stream Deck Mini** (6 Tasten) - reine Moduswahl, schaltet DECK ONE um
- **Streamplify DECK ONE** (15 Tasten) - das eigentliche Aktions-Raster, 5 Profile

Zentrale Datei: [`config/profiles.yaml`](config/profiles.yaml) - **alles**, was
eine KI zum Hinzufuegen neuer Tasten/Seiten braucht, steht dort als Daten, kein
Code-Aendern noetig. Die Python-Module (`streamdeck_driver/*.py`) lesen diese
YAML-Datei nur aus.

Start beider Geraete zusammen: `python3 -m streamdeck_driver.daemon`
([`streamdeck_driver/daemon.py`](streamdeck_driver/daemon.py))

---

## 1. Grundstruktur von `profiles.yaml`

```yaml
version: 1
elgato:
  pages: { ... }        # siehe Abschnitt 2
deckone:
  active_profile: nachhilfe   # welches Profil beim Start aktiv ist
  profiles: { ... }     # siehe Abschnitt 3
```

Beide Geraete haben **komplett unterschiedliche Navigationsmodelle** - das ist
der wichtigste Punkt zum Verstehen, bevor man etwas ergaenzt:

| | Elgato Mini | DECK ONE |
|---|---|---|
| Tasten | 6 | 15 |
| Bildgroesse | 80x80 px | 100x100 px |
| Navigationseinheit | "Seiten" (`elgato.pages`, beliebig viele) | "Profile" (`deckone.profiles`, 5 Stueck), **jedes Profil hat wiederum eine Liste von `pages`** |
| Zweck | Waehlt aus, welches DECK-ONE-Profil aktiv ist | Zeigt die eigentlichen Aktionstasten des gewaehlten Profils |
| Seitenwechsel-Reihenfolge | dynamisch: Einfuegereihenfolge von `elgato.pages` in der YAML | dynamisch: Laenge von `profile["pages"]` in der YAML |

Ein Tastendruck auf dem Elgato Mini (z.B. "Nachhilfe") ruft
`DeckOneController.switch_profile("nachhilfe")` auf und schaltet damit das
DECK ONE komplett um. Die beiden Geraete sind also gekoppelt, aber die
Seiten-Navigation *innerhalb* eines Profils betrifft nur das DECK ONE.

---

## 2. Elgato Mini: `elgato.pages`

Die Seitenreihenfolge kommt direkt aus der Einfuegereihenfolge von
`elgato.pages` in der YAML (`ElgatoController._switch_page()` in `daemon.py`
liest das dynamisch) - eine neue Elgato-Seite ist also, wie beim DECK ONE,
rein ein YAML-Eintrag, KEIN Code-Change mehr noetig. Solange mindestens eine
Taste vom Typ `page_next`/`page_previous` existiert, wird jede neue Seite
automatisch mit eingereiht.

Struktur pro Taste (0-5, Index = physische Tastenposition):

```yaml
elgato:
  pages:
    modi:
      keys:
        0:
          name: Open              # interner Name (aus altem Windows-Manifest, meist irrelevant)
          title: Streaming        # Text/Label (aktuell nicht auf Elgato-Icons gerendert)
          action:
            type: switch_profile
            profile: streaming     # muss ein Key unter deckone.profiles sein
          icon:
            type: asset
            path: assets/modi-icons/streaming.png
```

Elgato-spezifische Action-Types (werden in `daemon.py::handle_key()` direkt
behandelt, NICHT ueber `actions.dispatch()`):
- `switch_profile` - `profile: <name>`, muss zu einem Key in `deckone.profiles` passen
- `page_next` / `page_previous` - wechselt zwischen `modi`/`modi_studium`

Alle anderen Action-Types (z.B. `hotkey`) werden auf dem Elgato Mini ganz normal
ueber `actions.dispatch()` ausgefuehrt (siehe Abschnitt 4) - macht auf 6 Tasten
aber wenig Sinn, da hier hauptsaechlich Moduswahl passiert.

---

## 3. DECK ONE: `deckone.profiles`

```yaml
deckone:
  active_profile: nachhilfe
  profiles:
    nachhilfe:
      color: null                  # optional, aktuell nicht ausgewertet
      pages:
      - name: Seite 1
        keys:
          0: { ... }
          1: { ... }
          # ... bis 14 (15 Tasten, 0-basiert)
      - name: Seite 2
        keys: { ... }
```

Wichtig: **`pages` ist pro Profil eine LISTE**, nicht ein Dict mit Namen wie
beim Elgato. Eine neue Seite in einem Profil hinzuzufuegen heisst einfach:
einen weiteren Listeneintrag mit `name` + `keys` anhaengen. Der
Seitenwechsel-Index wird dynamisch aus `len(profile["pages"])` berechnet
(`deckone_controller.py`), also **kein Code-Change noetig**, anders als beim
Elgato Mini.

Ein Profil braucht selbst KEINE explizite `page_next`/`page_previous`-Taste,
wenn es nur eine Seite hat - aber wenn mehrere Seiten existieren, muss
mindestens eine Taste pro Seite mit `type: page_next`/`page_previous`
vorhanden sein, sonst kommt man nicht weiter (Beispiel siehe `system`-Profil,
Taste 14 = "Previous page").

**Neues Profil hinzufuegen:** einfach einen neuen Top-Level-Key unter
`deckone.profiles` anlegen (mit mind. einer Seite) UND eine `switch_profile`-
Taste dorthin in `elgato.pages` (Abschnitt 2) ergaenzen, sonst ist das neue
Profil vom Elgato Mini aus nicht erreichbar.

---

## 4. Action-Types (Tastenverhalten)

Jede Taste hat ein `action:`-Objekt mit einem Pflichtfeld `type`. Verarbeitung:
- Seiten-/Profil-Aktionen (`page_next`, `page_previous`, `switch_profile`,
  `live_stat`) werden **pro Geraet unterschiedlich** direkt in
  `deckone_controller.py::handle_key()` bzw. `daemon.py::ElgatoController.handle_key()`
  behandelt.
- Alle anderen Types gehen an [`streamdeck_driver/actions.py::dispatch()`](streamdeck_driver/actions.py) -
  **geraeteunabhaengig**, funktioniert identisch auf beiden Geraeten.

### 4.1 `hotkey` - Tastenkombination simulieren

```yaml
action:
  type: hotkey
  vkeycode: 175       # Windows-VKeyCode (siehe vkeycode_map.py)
  ctrl: false
  shift: false
  alt: false
```

Wird ueber `ydotool` an den Linux-Input-Stack gesendet. Der `vkeycode` ist
eine **Windows-VKeyCode-Zahl** (Erbe der alten Windows-Manifeste), keine
Linux-Taste direkt - `vkeycode_map.py::VK_TO_LINUX` uebersetzt sie in Linux-
evdev-Keycodes. **Beim Hinzufuegen einer neuen Hotkey-Taste**: entweder einen
bereits in `VK_TO_LINUX` vorhandenen `vkeycode` wiederverwenden, oder in
`vkeycode_map.py` einen neuen Eintrag ergaenzen (Format:
`vkeycode: KeyMapping(name, linux_keycode, verified)` - `linux_keycode` aus
`linux/input-event-codes.h`, z.B. `KEY_F5 = 63`). Ist der `vkeycode` nicht in
der Tabelle, wird die Taste stillschweigend ignoriert (nur ein Log-Warning).

Sonderfall Screenshot: es gibt **keinen eigenen `type: screenshot`**. Eine
Hotkey-Taste loest stattdessen automatisch `run_screenshot()` aus, wenn ihr
`title`/`name` das Wort "screenshot" enthaelt (Gross-/Kleinschreibung egal) -
siehe `actions.py:154`. Grund: `ydotool`-simulierte PrintScreen-Taste loest
unter GNOME/Wayland keinen echten Screenshot aus, also gibt es einen
Spezialpfad ueber `gnome-screenshot --area` + `wl-copy`.

### 4.2 `open` - Programm/Datei starten

```yaml
action:
  type: open
  linux_command: firefox      # muss gesetzt sein, sonst wird die Taste ignoriert
```

Startet `linux_command.split()` per `subprocess.Popen` (kein Shell-Escaping,
also keine Pipes/Env-Vars im Befehl). Alte Manifest-Felder wie
`original_path`, `needs_review`, `note`, `display_name`, `icon_asset` sind
reine Doku-Reste aus dem Windows-Import und werden zur Laufzeit ignoriert
(nur `linux_command` zaehlt).

### 4.3 `open_sequence` - mehrere Programme nacheinander

```yaml
action:
  type: open_sequence
  steps:
  - linux_command: firefox
  - linux_command: xdg-open https://excalidraw.com
```

Jeder Schritt mit `linux_command` wird nacheinander per `Popen` gestartet
(kein Warten zwischen den Schritten).

### 4.4 `website` - URL im Standardbrowser oeffnen

```yaml
action:
  type: website
  url: https://example.com
```

`xdg-open <url>`. **Aktuell in keiner Profil-Datei tatsaechlich benutzt**,
der Code dafuer existiert aber vollstaendig in `actions.py::run_website()` -
kann direkt per YAML verwendet werden.

### 4.5 `app_volume` - Lautstaerke einer einzelnen App

```yaml
action:
  type: app_volume
  app_name: fortnite    # Teilstring, matcht gegen wpctl-Stream-Namen (case-insensitive)
  direction: up          # oder: down
```

Sucht in `wpctl status` unter "Streams:" nach einem laufenden Audio-Stream,
dessen Name `app_name` enthaelt, und aendert dessen Lautstaerke um 5%
(Schrittweite ist in `run_app_volume()` als `step_percent=5` hart codiert).
Spielt die App gerade keinen Ton ab, passiert nichts (kein Fehler).

### 4.6 `live_stat` - System-Kennzahl live anzeigen (nur DECK ONE)

```yaml
action:
  type: live_stat
  metric: cpu    # siehe Tabelle unten
```

**Nicht** ueber `actions.dispatch()`, sondern komplett in
`deckone_controller.py` behandelt: Taste zeigt eine Live-Kachel (Wert +
Ampelfarbe + Sparkline-Verlauf, siehe Abschnitt 5.4) und wird per
Hintergrund-Thread alle paar Sekunden neu gerendert. Ein Druck auf die Taste
selbst:
1. rendert die aktuelle Seite sofort neu (Sofort-Refresh)
2. bei `metric` in `cpu`/`ram`/`gpu_load` zusaetzlich: oeffnet ein
   `zenity`-Popup mit den Top-5-Prozessen fuer diese Metrik
   ([`process_monitor.py`](streamdeck_driver/process_monitor.py))

Verfuegbare `metric`-Werte (aus [`hw_monitor.py::snapshot()`](streamdeck_driver/hw_monitor.py)):

| metric | Quelle | Einheit | Top-5-Popup bei Tastendruck? |
|---|---|---|---|
| `cpu` | `psutil.cpu_percent()` | % | ja |
| `cpu_temp` | `psutil.sensors_temperatures()["coretemp"]` | °C | nein |
| `ram` | `psutil.virtual_memory().percent` | % | ja |
| `ram_gb` | `psutil.virtual_memory()` used/total | GB (zeigt "used/total") | nein (nutzt intern trotzdem die RAM-%-Ampel) |
| `gpu_load` | `rocm-smi --showuse` | % | ja (nutzt VRAM-pro-Prozess als Proxy, da CU-Auslastung pro Prozess auf dieser Hardware "unknown" liefert) |
| `gpu_vram` | `rocm-smi --showmemuse` | % | nein |
| `gpu_temp` | `rocm-smi --showtemp` | °C | nein |
| `disk` | `psutil.disk_usage("/")` | % | nein |

Neue Metrik hinzufuegen = neue Funktion in `hw_monitor.py` schreiben + in
`snapshot()` eintragen + `metric: <name>` in der YAML verwenden. Ampelfarbe
kommt automatisch aus `_stat_color()` (Abschnitt 5.4), solange der Wert eine
Prozentzahl 0-100 ist.

### 4.7 `page_next` / `page_previous` / `switch_profile`

Bereits in Abschnitt 2/3 beschrieben. Auf dem DECK ONE wechselt `page_next`/
`page_previous` zwischen den Eintraegen der `pages`-Liste des AKTIVEN Profils
(zirkulaer, modulo Laenge). `switch_profile` gibt es auf dem DECK ONE selbst
NICHT als sinnvolle Taste (das Profil wird vom Elgato Mini aus gewechselt) -
`deckone_controller.py::switch_profile()` ist die Zielfunktion, die vom
Elgato-Handler aufgerufen wird.

### 4.8 `unmapped` - Platzhalter fuer "kein Linux-Aequivalent gefunden"

Reiner Doku-Marker aus dem alten Windows-Import (z.B. fuer Tasten, die auf ein
Netzlaufwerk `Z:` verwiesen, das unter Linux nicht existiert). Wird geloggt
und sonst ignoriert. Fuer neue Tasten nicht relevant, nur zur Erklaerung falls
in der bestehenden Config sichtbar.

### 4.9 `open_gui` - Settings-GUI starten und oeffnen

```yaml
action:
  type: open_gui
  port: 8420    # optional, Default 8420
```

Prueft per Socket-Connect, ob `gui/server.py` auf dem Port schon laeuft; falls
nicht, startet `actions.py::run_open_gui()` sie im Hintergrund (`platform_backend.open_command()`,
wartet bis zu 5s auf Erreichbarkeit) und oeffnet danach den Browser darauf
(`platform_backend.open_url()`) - macht die GUI von einer physischen Taste aus
erreichbar, ohne Terminal.

### 4.10 `weather_forecast` - Wettervorhersage-Kachel (nur DECK ONE, braucht Home Assistant)

```yaml
action:
  type: weather_forecast
  entity_id: weather.home    # eine 'weather.*'-Entity in Home Assistant
  forecast_type: daily       # 'daily', 'hourly' oder 'twice_daily' - je nach Wetter-Integration
  offset: 1                  # 0 = naechster Eintrag der Granularitaet, 1 = der danach, ...
```

Passive Anzeige-Kachel wie `ha_sensor`, aber fuer die VORHERSAGE statt den
aktuellen Zustand - `ha_client.py::get_forecast()` ruft dafuer den
`weather.get_forecasts`-Service auf (seit HA 2023.9 der Weg dafuer, das alte
`forecast`-Attribut direkt auf der Entity gibt es nicht mehr), 15min gecacht.
Rendering ueber `icon_render.py::render_weather_forecast_card()` - eigene
Farblogik nach Wetterlage (blau=Regen, gelb=sonnig, grau=bewoelkt, ...) statt
der Ampel-Prozent-Faerbung von `render_stat_card`. `offset` ist NICHT
zwingend "heute"/"morgen" - bei `forecast_type: daily` haengt es von der
Wetter-Integration ab, ob Index 0 der Rest des heutigen Tages oder schon
morgen ist.

### 4.11 Sonderfall `wetter_vorhersage`-Profil - reine Niederschlags-Vorhersage-Karte

Wie das `radar`-Profil (Abschnitt 3) eine Sonderbehandlung in
`deckone_controller.py::_render_forecast_page()`: EIN grosses Kartenbild
statt Taste-fuer-Taste aus der YAML, hier aber bewusst NUR Regen-Vorhersage
(RainViewer-"Nowcast", naechste ~30-60min) ohne Flugzeuge/Blitze/Avatar -
siehe `radar.py::build_forecast_frame()`. Taste unten rechts = naechster
Vorhersage-Frame (zyklisch, wie die manuelle Zoom-Taste beim Radar). Kann
"keine Daten" anzeigen statt einer Karte - RainViewer garantiert Nowcast-
Daten nicht immer/ueberall, das ist kein Bug.

```yaml
deckone:
  profiles:
    wetter_vorhersage:
      color: '#38BDF8'
      pages:
      - name: Regenvorhersage
        keys: {}    # bleibt leer, wird komplett prozedural gerendert
```

### 4.12 `action_long` - anderes Verhalten bei langem Tastendruck

```yaml
0:
  name: Mikro
  title: Mikro
  action:
    type: app_volume
    app_name: mikrofon
    direction: down
  action_long:
    type: open_gui
```

Optionales zweites `action:`-Objekt auf JEDER Taste (jeder Aktions-Typ aus
diesem Abschnitt 4 ist erlaubt, auch als `action_long`). Ab
`LONG_PRESS_THRESHOLD_S` (0.6s, `deckone_controller.py`) Haltedauer zwischen
Druecken und Loslassen wird `action_long` statt `action` ausgeloest -
darunter (oder wenn `action_long` fehlt) ganz normal `action`.

**Wichtige Verhaltensaenderung, die das mit sich bringt**: die Aktion wird
jetzt beim LOSLASSEN ausgeloest, nicht mehr beim Druecken - vorher war es
umgekehrt. Bei normalen (kurzen) Druecken ist der Unterschied nur
Sekundenbruchteile und in der Praxis nicht spuerbar, aber wichtig zu wissen,
falls man den Code liest oder eigene Timing-Annahmen hat. Der Zoom-Puls
(visuelles Feedback) bleibt bewusst auf dem Druecken selbst - nur die
eigentliche Aktion wartet aufs Loslassen.

Gilt nur fuer normale YAML-Tasten, NICHT fuer die prozedural gerenderten
Sonderseiten (`radar`, `wetter_vorhersage`, `wo_ist`) - deren eigene
Tasten (Zoom-Zyklus, Info-Karten-Toggle) reagieren weiterhin wie bisher
direkt beim Druecken, ohne lang/kurz-Unterscheidung.

---

### 4.13 `auto_profile_switch` - automatischer Profilwechsel je nach aktiver App

Kein `action`-Feld, sondern ein eigener TOP-LEVEL-Schluessel in
`profiles.yaml` (Geschwister von `elgato:`/`deckone:`, nicht darunter):

```yaml
auto_profile_switch:
  enabled: true
  poll_interval_s: 3
  apps:
    obs: streaming
    firefox: buero
```

`apps` bildet einen Teilstring der App-Kennung auf einen DECK-ONE-Profilnamen
ab (Schluessel des jeweiligen Profils unter `deckone.profiles`). Alle
`poll_interval_s` Sekunden wird die aktuell fokussierte App abgefragt
(`platform_backend.py::get_active_app_id()`); wechselt sie zu einer neu
zugeordneten App, schaltet DECK ONE automatisch auf das passende Profil um -
wie ein automatisch ausgeloester `switch_profile`-Tastendruck.

**Flanken-, kein Dauer-Trigger**: die Umschaltung passiert nur GENAU EINMAL
beim Fokuswechsel, nicht bei jeder Abfrage erneut. Schaltet man danach von
Hand (Elgato Mini) auf ein anderes Profil, bleibt das so bestehen, solange
dieselbe App weiter fokussiert ist - erst der naechste Fokuswechsel auf eine
andere zugeordnete App loest wieder eine automatische Umschaltung aus. Ohne
diese Regel wuerde jede manuelle Wahl beim naechsten Poll sofort wieder
ueberschrieben.

**Plattform-Einschraenkung (wichtig unter Linux)**: `get_active_app_id()`
braucht unter Wayland/GNOME die GNOME-Shell-Erweiterung "Window Calls"
(`window-calls@domandoman.xyz`, https://github.com/ickyicky/window-calls) -
es gibt sonst keinen verlaesslichen, erweiterungsfreien Weg an das
fokussierte Fenster heran (X11-Tools wie xdotool/wmctrl funktionieren unter
Wayland nicht). Fehlt die Erweiterung oder laeuft eine andere Desktop-
Umgebung (KDE, Sway, ...), wird das einmalig geloggt und das Feature bleibt
inaktiv, kein Fehler/Absturz. Windows (`GetForegroundWindow` + psutil) und
macOS (AppleScript/System Events) sind analog implementiert, aber wie der
Rest von `platform_backend/windows.py`/`macos.py` UNGETESTET.

Bewusst wird nur die App-Kennung (Linux: `wm_class`, Windows: Prozessname,
macOS: App-Name) ausgewertet, NIE der Fenstertitel - der kann sensible
Inhalte wie Suchbegriffe oder Chat-Vorschauen enthalten.

---

## 5. Icons (`icon:`-Feld pro Taste)

Drei Typen, verarbeitet von [`icon_render.py::render_key_icon()`](streamdeck_driver/icon_render.py)
(Fallback-Reihenfolge: `app_icon` → `asset` → falls Datei fehlt automatisch
`generated`):

### 5.1 `asset` - statisches PNG

```yaml
icon:
  type: asset
  path: assets/modi-icons/streaming.png   # relativ zum Projektordner
```

Wird direkt geladen und auf die Zielgroesse skaliert. Fehlt die Datei, faellt
der Code automatisch auf einen prozedural generierten Icon-Typ zurueck (kein
Absturz).

### 5.2 `generated` - prozedural gezeichnete Karte

```yaml
icon:
  type: generated
```

Zeichnet eine abgerundete Farbkarte + Symbol, Farbe/Symbol kommen aus der
`action_type` der Taste (siehe `_TYPE_STYLE`-Tabelle in `icon_render.py`):

| action_type | Farbe (Top-Verlauf) |
|---|---|
| `hotkey` | Violett |
| `open` / `open_sequence` | Tuerkis |
| `website` | Blau |
| `page_previous` / `page_next` | Grau |
| `switch_profile` | Magenta |
| `app_volume` | Cyan |
| `unmapped` | Rot (Warnfarbe) |
| (unbekannt/anderer Typ) | Standard-Blau (`_DEFAULT_STYLE`) |

Titeltext wird automatisch unter das Symbol gerendert. Das ist der einfachste
Icon-Typ fuer neue Tasten - **kein Asset noetig**, einfach `type: generated`
setzen und die Farbe ergibt sich automatisch aus dem Action-Type.

### 5.3 `app_icon` - KI-generiertes Logo mit Titelleiste

```yaml
icon:
  type: app_icon
  path: assets/generated-icons/firefox.png
```

Wie `asset`, aber mit einer zusaetzlich eingeblendeten Titelleiste/Rahmen
(Composite-Look fuer "App-Start"-Tasten). Fehlt die Datei ebenfalls
automatischer Fallback auf `generated`.

### 5.4 Live-Stat-Karte (kein eigener `icon.type`, sondern automatisch bei `action.type: live_stat`)

Wird NICHT ueber `render_key_icon()`, sondern ueber
`deckone_controller.py::_render_stat_key()` → `icon_render.py::render_stat_card()`
gerendert - das `icon:`-Feld einer `live_stat`-Taste wird dabei ignoriert
(kann trotzdem `type: generated` als Konvention/Platzhalter enthalten, wie in
der bestehenden Config). Farblogik (`_stat_color()`):

| Wert (%) | Farbe |
|---|---|
| < 60 | gruen |
| 60-84 | gelb/orange |
| ≥ 85 | rot |
| `None` (nicht lesbar) | grau |

Zusaetzlich ein 120-Sekunden-Sparkline-Verlauf im Kartenhintergrund
(`hw_monitor.get_recent_values()`/`rolling_average()`).

### 5.5 Fehler-Badge - sichtbare Warnung statt stillem Log-Eintrag

Wenn die letzte Anfrage an Home Assistant fehlgeschlagen ist, bekommen alle
HA-abhaengigen Kacheln automatisch eine kleine rote Kreis-Badge mit `!` oben
rechts ueberblendet (`icon_render.py::add_error_badge()`), statt dass der
Fehler nur im Log landet und die Kachel weiterhin harmlos `--`/den letzten
bekannten Zustand zeigt. Betroffen: `ha_sensor`, `weather_forecast`,
`ha_toggle`, `ha_cover` (`deckone_controller.py::_render_ha_key()` /
`_render_weather_forecast_key()` / `_render_key_icon_for()`).

Die Erkennung laeuft ueber `ha_client.py::is_healthy()` - ein modulweiter
Merker, der bei jeder Art von HA-API-Aufruf (Zustaende lesen, Service
aufrufen, Vorhersage holen) auf `True`/`False` gesetzt wird, je nachdem ob
die letzte Anfrage erfolgreich war. Kein separater Health-Check-Call noetig,
kein Timeout-Grace-Fenster - sobald der naechste HA-Aufruf (egal welcher)
wieder klappt, verschwindet die Badge beim naechsten Rendern von selbst.

Andere Fehlerquellen (fehlgeschlagener Hotkey, `open`-Befehl nicht gefunden
usw.) loesen aktuell weiterhin nur einen Log-Eintrag aus, keine Badge - das
sind einmalige Fire-and-Forget-Aktionen ohne eine dauerhaft angezeigte
"Live"-Kachel, auf der eine Badge sinnvoll haengen bleiben koennte.

---

## 6. Eine neue Taste/Seite hinzufuegen - Kochrezept

**Einfachster Fall: neue Aktions-Taste auf einer bestehenden DECK-ONE-Seite**

1. In `profiles.yaml` unter `deckone.profiles.<profil>.pages[<seitenindex>].keys`
   einen neuen Key mit freiem Index (0-14) anlegen.
2. `name`/`title` setzen (Anzeigetext).
3. `action:` mit passendem `type` aus Abschnitt 4 setzen.
4. `icon: { type: generated }` reicht fuer den Start (Farbe kommt automatisch).
5. Treiber neu starten (`python3 -m streamdeck_driver.daemon`) - kein Code-Change.

**Neue Seite in einem bestehenden DECK-ONE-Profil**

1. Unter `deckone.profiles.<profil>.pages` einen neuen Listeneintrag
   `{ name: "...", keys: { ... } }` anhaengen.
2. Sicherstellen, dass auf JEDER Seite dieses Profils (inkl. der neuen) eine
   `page_next`/`page_previous`-Taste existiert, sonst ist die neue Seite von
   den anderen aus nicht erreichbar.
3. Kein Code-Change noetig (Seitenzahl wird dynamisch aus der Listenlaenge
   berechnet).

**Neues DECK-ONE-Profil**

1. Neuen Top-Level-Key unter `deckone.profiles` anlegen (mind. 1 Seite, s.o.).
2. In `elgato.pages.modi` (oder `modi_studium`) eine `switch_profile`-Taste
   mit `profile: <neuer-name>` ergaenzen, sonst nicht erreichbar.

**Neue Elgato-Mini-Seite** (selten noetig, nur 6 Tasten)

1. Neuen Key unter `elgato.pages` anlegen.
2. Sicherstellen, dass eine `page_next`/`page_previous`-Taste existiert.
3. Kein Code-Change noetig - die Reihenfolge ergibt sich dynamisch aus der
   YAML-Einfuegereihenfolge (`ElgatoController._switch_page()` in `daemon.py`).

**Neuer Action-Type** (z.B. eine ganz neue Aktionsart, die es noch nicht gibt)

1. `run_<name>(action)`-Funktion in `actions.py` ergaenzen.
2. In `dispatch()` (`actions.py:149`) einen `elif action_type == "<name>":`-Zweig ergaenzen.
3. Optional: Farbe in `icon_render.py::_TYPE_STYLE` ergaenzen, sonst wird die
   Standardfarbe verwendet (kein Fehler).

---

## 7. Nicht Teil der "Seiten-Logik" (zur Abgrenzung)

Diese Module wurden fuer dieses Dokument mitgelesen, sind aber fuer das reine
Hinzufuegen von Seiten/Tasten nicht relevant und muessen normalerweise nicht
angefasst werden:
- `streamdeck_driver/devices/base.py`, `deckone.py`, `elgato_mini.py` - Low-Level-USB-Protokoll (Wake/Bild-Upload/Tastenevents), nur bei Hardware-Problemen relevant, siehe Memory `project_streamdeck_deckone_protocol`
- `streamdeck_driver/manifest_parser.py`, `action_translation.py` - Einmal-Import der alten Windows-Manifeste, nicht mehr im Normalbetrieb genutzt
- `streamdeck_driver/process_monitor.py` - nur das Top-5-Prozesse-Popup hinter `live_stat` (Abschnitt 4.6), kein eigener Action-Type
