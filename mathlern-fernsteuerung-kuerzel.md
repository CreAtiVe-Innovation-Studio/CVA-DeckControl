# MathLern: Fernsteuerung per Stream Deck (Kürzel-Vorlage)

Ziel: Ein Stream Deck soll im Admin-Bereich Tabs wechseln und Aktionen auslösen (Generieren, Whiteboard scharf schalten, A4-Modus usw.).
Die Tabs im Schülerprofil haben keine eigenen URLs und viele Aktionen kein Tastenkürzel. Deshalb braucht MathLern **globale Tastenkürzel**.
Das Deck sendet sie an das Firefox-Fenster; die Seite reagiert darauf.

## Warum F13–F24?
- Sie existieren in keiner Anwendung als Funktion und kollidieren daher mit nichts.
- Strg+Alt scheidet aus: unter deutschem Layout ist das AltGr (erzeugt @, €, Klammern usw.).
- Ohne Umschalt, mit Umschalt und mit Strg ergeben sich 3 × 12 = 36 Kürzel, mit Strg+Umschalt noch 12 weitere.
- Browser melden sie als `event.key === "F13"` … `"F24"`, unabhängig vom Tastaturlayout.

## Kürzel (42 Stück)
Die Aktions-Kürzel (Strg / Strg+Umschalt) sollen **bei Bedarf selbst in den richtigen Tab wechseln**, danach den Knopf drücken (ca. 400 ms warten, bis der Tab gerendert ist).

| Kürzel | Beschriftung am Deck | Wirkung |
|---|---|---|
| `F13` | Übersicht | Tab 'Übersicht' |
| `F14` | Aktuelle Aufgabe | Tab 'Aktuelle Aufgabe' |
| `F15` | Verlauf | Tab 'Verlauf' |
| `F16` | Themen | Tab 'Themen' |
| `F17` | Schwächen | Tab 'Schwächen' |
| `F18` | Hausaufgaben | Tab 'Hausaufgaben' |
| `F19` | Klausuren | Tab 'Klausuren' |
| `F20` | Noten | Tab 'Noten' |
| `F21` | Abi | Tab 'Abi' |
| `F22` | Quiz | Tab 'Quiz' |
| `F23` | Quiz-Ergebnisse | Tab 'Quiz-Ergebnisse' |
| `F24` | Lernspiele | Tab 'Lernspiele' |
| `shift+F13` | Kontingent | Tab 'Kontingent' |
| `shift+F14` | Missionen | Tab 'Missionen' |
| `shift+F15` | Präsentation | Tab 'Präsentation' |
| `shift+F16` | Whiteboard | Tab 'Whiteboard' |
| `shift+F17` | Bewertungen | Tab 'Bewertungen' |
| `shift+F18` | KI-Tipps | Tab 'KI-Tipps' |
| `shift+F19` | Stunden | Tab 'Stunden' |
| `shift+F20` | Für Schüler | Editor: 'Für Schüler in neuem Tab zeigen' (im Tab Whiteboard: 'Für Schüler' beim obersten Eintrag) |
| `shift+F21` | Scharf | Editor: 'Scharf schalten (Vorrang vor Missionen)' - Umschalter |
| `shift+F22` | A4-Modus | Editor: 'A4-Seitenmodus einschalten/ausschalten' - Umschalter |
| `shift+F23` | PDF A4 | Editor: 'PDF (DIN A4, mehrseitig)' |
| `shift+F24` | PDF 1 Seite | Editor: 'PDF (1 Seite, hohe Qualität)' |
| `ctrl+F13` | HA generieren | Hausaufgaben: '✨ Generieren' |
| `ctrl+F14` | HA KI | Hausaufgaben: '🤖 KI generieren' |
| `ctrl+F15` | HA Referenz | Hausaufgaben: '🔍 Referenz suchen' |
| `ctrl+F16` | HA bewerten | Hausaufgaben: '✏️ Bewerten' |
| `ctrl+F17` | Quiz generieren | Quiz: '✨ Quiz generieren' |
| `ctrl+F18` | Quiz Referenz | Quiz: '📂 Referenz aus Scanpool' |
| `ctrl+F19` | Trainer-HA | Lernspiele: '🤖 Trainer-HA generieren' |
| `ctrl+F20` | Merkzettel | Lernspiele: '🃏 Merkzettel generieren' |
| `ctrl+F21` | KI-Vorschlag | Missionen: '🤖 KI-Vorschlag' |
| `ctrl+F22` | Mission generieren | Missionen: 'Generieren →' |
| `ctrl+F23` | Neues Whiteboard | Tab Whiteboard: '▶ Neues Whiteboard starten' |
| `ctrl+F24` | Präs. starten | Präsentation: '▶ Präsentation starten' |
| `ctrl+shift+F13` | Präs. beenden | Präsentation: '✕ Verweigern / Beenden' |
| `ctrl+shift+F14` | Mission Thema | Missionen: Quelle '📚 Thema' |
| `ctrl+shift+F15` | Mission Referenz | Missionen: Quelle '📋 Referenz' |
| `ctrl+shift+F16` | Mission Bild | Missionen: Quelle '📷 Bild' |
| `ctrl+shift+F17` | KI auswerten | Schwächen: 'KI auswerten' |
| `ctrl+shift+F18` | Stadt vorab | Übersicht: 'Stadt vorab generieren' |

Bewusst **nicht** belegt (zerstörend): Löschen, „Alles löschen“, „Stunde abschließen“, Deaktivieren.
Die Zeichenwerkzeuge im Whiteboard-Editor (D, R, O, L, T, E, V, H, S, M) existieren bereits und werden vom Deck direkt genutzt.

## Referenz-Implementierung (JavaScript, einmal global laden)
Sie sucht Knöpfe über den sichtbaren Text (ohne Emoji, ohne Zähler wie „(3)“). Das funktioniert ohne Änderung der Seitenstruktur.
Besser (stabiler gegen Textänderungen): `data-remote="tab-whiteboard"` o. ä. an den Knöpfen und danach im Skript per Attribut suchen.

```js
// MathLern-Fernsteuerung per Stream Deck: F13-F24 (+ Umschalt / Strg) als globale Kürzel.
// Ctrl+Alt wird bewusst NICHT benutzt: unter deutschem Layout ist das AltGr (@, €, Klammern usw.).
(() => {
  if (window.__mlRemote) return; window.__mlRemote = true;
  const norm = s => (s || "").replace(/[^\p{L}\p{N}\- ()]/gu, "").replace(/\s*\(\d+\)\s*$/, "").replace(/\s+/g, " ").trim();
  const visible = e => !!(e.offsetParent || e.getClientRects().length);
  const buttons = () => [...document.querySelectorAll("button")].filter(visible);
  const byText = t => buttons().find(b => norm(b.textContent) === t) || buttons().find(b => norm(b.textContent).startsWith(t));
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const MAP = {
    "F13": {"tab": "Übersicht"},  // Übersicht,
    "F14": {"tab": "Aktuelle Aufgabe"},  // Aktuelle Aufgabe,
    "F15": {"tab": "Verlauf"},  // Verlauf,
    "F16": {"tab": "Themen"},  // Themen,
    "F17": {"tab": "Schwächen"},  // Schwächen,
    "F18": {"tab": "Hausaufgaben"},  // Hausaufgaben,
    "F19": {"tab": "Klausuren"},  // Klausuren,
    "F20": {"tab": "Noten"},  // Noten,
    "F21": {"tab": "Abi"},  // Abi,
    "F22": {"tab": "Quiz"},  // Quiz,
    "F23": {"tab": "Quiz-Ergebnisse"},  // Quiz-Ergebnisse,
    "F24": {"tab": "Lernspiele"},  // Lernspiele,
    "shift+F13": {"tab": "Kontingent"},  // Kontingent,
    "shift+F14": {"tab": "Missionen"},  // Missionen,
    "shift+F15": {"tab": "Präsentation"},  // Präsentation,
    "shift+F16": {"tab": "Whiteboard"},  // Whiteboard,
    "shift+F17": {"tab": "Bewertungen"},  // Bewertungen,
    "shift+F18": {"tab": "KI-Tipps"},  // KI-Tipps,
    "shift+F19": {"tab": "Stunden"},  // Stunden,
    "shift+F20": {"tab": null, "click": "Für Schüler"},  // Für Schüler,
    "shift+F21": {"tab": null, "click": "Scharf schalten"},  // Scharf,
    "shift+F22": {"tab": null, "click": "A4-Seitenmodus"},  // A4-Modus,
    "shift+F23": {"tab": null, "click": "PDF DIN A4 mehrseitig"},  // PDF A4,
    "shift+F24": {"tab": null, "click": "PDF 1 Seite hohe Qualität"},  // PDF 1 Seite,
    "ctrl+F13": {"tab": "Hausaufgaben", "click": "Generieren"},  // HA generieren,
    "ctrl+F14": {"tab": "Hausaufgaben", "click": "KI generieren"},  // HA KI,
    "ctrl+F15": {"tab": "Hausaufgaben", "click": "Referenz suchen"},  // HA Referenz,
    "ctrl+F16": {"tab": "Hausaufgaben", "click": "Bewerten"},  // HA bewerten,
    "ctrl+F17": {"tab": "Quiz", "click": "Quiz generieren"},  // Quiz generieren,
    "ctrl+F18": {"tab": "Quiz", "click": "Referenz aus Scanpool"},  // Quiz Referenz,
    "ctrl+F19": {"tab": "Lernspiele", "click": "Trainer-HA generieren"},  // Trainer-HA,
    "ctrl+F20": {"tab": "Lernspiele", "click": "Merkzettel generieren"},  // Merkzettel,
    "ctrl+F21": {"tab": "Missionen", "click": "KI-Vorschlag"},  // KI-Vorschlag,
    "ctrl+F22": {"tab": "Missionen", "click": "Generieren"},  // Mission generieren,
    "ctrl+F23": {"tab": "Whiteboard", "click": "Neues Whiteboard starten"},  // Neues Whiteboard,
    "ctrl+F24": {"tab": "Präsentation", "click": "Präsentation starten"},  // Präs. starten,
    "ctrl+shift+F13": {"tab": "Präsentation", "click": "Verweigern Beenden"},  // Präs. beenden,
    "ctrl+shift+F14": {"tab": "Missionen", "click": "Thema"},  // Mission Thema,
    "ctrl+shift+F15": {"tab": "Missionen", "click": "Referenz"},  // Mission Referenz,
    "ctrl+shift+F16": {"tab": "Missionen", "click": "Bild"},  // Mission Bild,
    "ctrl+shift+F17": {"tab": "Schwächen", "click": "KI auswerten"},  // KI auswerten,
    "ctrl+shift+F18": {"tab": "Übersicht", "click": "Stadt vorab generieren"},  // Stadt vorab
  };
  addEventListener("keydown", async e => {
    if (!/^F(1[3-9]|2[0-4])$/.test(e.key) || e.altKey || e.metaKey) return;
    const act = MAP[(e.ctrlKey ? "ctrl+" : "") + (e.shiftKey ? "shift+" : "") + e.key];
    if (!act) return;
    e.preventDefault();
    // Tab zuerst, falls die Aktion in einem Tab liegt (Tab-Wechsel nur, wenn der Tab da ist -> im Whiteboard-Editor gibt es keine)
    if (act.tab) { const t = byText(act.tab); if (t) { t.click(); if (act.click) await wait(450); } }
    if (act.click) { const b = byText(act.click); if (b) b.click(); else console.warn("[ml-remote] Knopf nicht gefunden:", act.click); }
  }, true);
})();
```

## Hinweise
- Umschalter („Scharf schalten“, „A4-Seitenmodus“) ändern ihren Text je nach Zustand. Die Referenz sucht mit `startsWith`, das reicht für „Scharf schalten …“ / „A4-Seitenmodus …“.
  Wenn der Zustand anders beschriftet ist, bitte anpassen.
- Wenn mehrere Whiteboards gelistet sind, soll „Für Schüler“ das oberste (aktuellste) nehmen.
- Das Deck holt das Admin-Firefox-Fenster vor jedem Kürzel selbst in den Vordergrund.
- Kein Passwort, keine Schülerdaten und keine Netzwerkanfragen nötig: alles läuft rein im Browser.
