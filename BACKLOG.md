# Aufgaben

## Hohe Priorität

### Parser

- [x] Markdown laden
- [x] UTF-8 prüfen
- [x] YAML Frontmatter aus dem Sprachinhalt entfernen
- [x] URLs entfernen
- [x] Quelle entfernen
- [x] Datum entfernen

---

### Markdown

- [x] Überschriften erkennen
- [x] Listen erkennen
- [x] Tabellen semantisch erkennen und aus der Hörfassung ausschließen
- [x] Inline Code behandeln
- [x] Codeblöcke behandeln
- [x] Fett erkennen
- [x] Kursiv erkennen
- [x] Blockquotes erkennen
- [x] Alleinstehende Satz- und Sonderzeichen aus der Hörfassung entfernen

---

### Renderer

- [x] Dokumentstruktur erzeugen
- [x] Sprachstruktur erzeugen
- [x] Kapitel über Überschriften als Chunk-Grenzen erkennen
- [x] Absätze erkennen

---

### Chunking

- [x] Maximale Chunkgröße konfigurierbar einhalten
- [x] Trennung an Satzgrenzen
- [x] Kapitel bevorzugen
- [x] Absatz bevorzugen
- [x] Kostenfreie Chunk-Vorschau
- [x] Multi-Chunk-Synthese

---

### OpenAI

- [x] API-Key aus konfigurierbarer Umgebungsvariable laden
- [x] Verbindung und Multi-Chunk-Synthese live testen
- [x] Einzelne MP3 atomar erzeugen
- [x] Retry konfigurierbar implementieren

---

### Audio

- [x] Nummerierte Einzeldateien transaktional erzeugen
- [x] MP3 per geprüftem FFmpeg Stream-Copy zusammenfügen
- [x] Temporäre Join-Dateien automatisch löschen
- [x] Festen Prefill-Satz und Request-Zeichenreserve konfigurieren
- [x] Prefill-Dauer per kanonischem Konfigurations-Fingerprint automatisch zwischenspeichern
- [x] Kalibrierungs-Cache bei Bedarf per `--refresh-calibration` erneuern
- [x] Energiearme WAV-Passage nahe der Kalibrierung erkennen
- [x] Prefill samplegenau aus WAV-Chunks entfernen
- [x] Bereinigte WAV-Chunks zusammenfügen und final einmalig als MP3 kodieren
- [x] Bereits erzeugte Chunk-Artefakte bei Fehlern für die Diagnose aufbewahren
- [x] Normalisierte Kalibrierungs-WAV zusammen mit den JSON-Messwerten dauerhaft speichern
- [x] Streaming-WAV-Platzhalterlängen anhand tatsächlich lesbarer PCM-Frames korrigieren
- [x] Roh-, getrimmte und zusammengefügte WAVs per `--keep-chunks` für Hörtests aufbewahren
- [ ] Prefill-Qualitätsmodus mit realen OpenAI-WAV-Chunks hörend validieren

---

## Mittlere Priorität

- [x] Speech Profiles für Coaching, Hörbuch, Podcast und Meditation
- [x] Vier abgestufte Coaching-Level von tiefenentspannt bis enthusiastisch, jeweils männlich und weiblich
- [x] Profile per CLI auflisten, anzeigen und nach Namen auswählen
- [ ] YAML Konfiguration
- [x] Konfigurierbares Konsolen- und UTF-8-Dateilogging
- [x] Tatsächliche Speech-Usage aus OpenAI-SSE auslesen und Kosten konfigurationsbasiert berechnen
- [x] Fortschrittsanzeige pro abgeschlossenem TTS-Aufruf und Gesamtsumme
- [x] SSE-Usage, Kostenformatierung und Loghygiene mit realem OpenAI-Aufruf validieren

---

## Niedrige Priorität

- [ ] GUI
- [ ] Drag & Drop
- [ ] Docker
- [ ] Node.js Migration
