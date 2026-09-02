# Lessons Learned

Dieses Dokument enthält alle Erkenntnisse, Beobachtungen und Erfahrungen, die während der Entwicklung gesammelt werden.

Ziel ist es, Entscheidungen nicht mehrfach treffen zu müssen und zukünftige Implementierungen zu verbessern.

---

# 2026-09-01

## Speech-Response liefert Usage, aber keinen fertigen Geldbetrag

### Erkenntnis

Die offizielle OpenAI-Speech-Dokumentation unterscheidet zwischen binärem Audio-Streaming und SSE-Ereignissen. Im SSE-Modus enthält `speech.audio.done` die tatsächlichen Input-, Output- und Gesamttokens des abgeschlossenen Requests. Ein abgerechneter Dollarbetrag ist dagegen nicht Teil dieses Speech-Ereignisses.

Die OpenAI-Anbindung dekodiert deshalb `speech.audio.delta`, verlangt vor der atomaren Veröffentlichung ein gültiges Abschlussereignis und gibt dessen Usage strukturiert an die Anwendung zurück. Kosten werden separat aus diesen tatsächlichen Tokens und datierten, extern konfigurierten Preisen berechnet. Die Ausgabe bezeichnet sie ausdrücklich als berechnet und nennt den Preisstand. Unit-Tests bestätigen SSE-Audiorekonstruktion, Abbruch ohne Usage-Abschluss, Fortschrittsereignisse, Aggregation, Kostenrechnung und UTF-8-Dateilogging.

Ein realer API-Lauf mit dem bereinigten TC-007-Sprechtext bestätigte den produktiven Pfad: 303 gesendete Zeichen ergaben 115 Input-Tokens, 552 Audio-Output-Tokens und 667 Gesamttokens. Mit dem konfigurierten Preisstand von 0,60 USD je Million Text-Input-Tokens und 12,00 USD je Million Audio-Output-Tokens wurden 0,006693 USD berechnet. Die erzeugte MP3 besitzt 24 kHz, einen Kanal, 23,952 Sekunden Dauer und 383.232 Byte. Das UTF-8-Log enthielt keine Treffer für Authorization-, Bearer- oder API-Key-Muster.

Fortschritt, Usage und Logging sollten nicht unabhängig voneinander implementiert werden. Ein gemeinsames providerunabhängiges Ereignis nach jedem erfolgreich abgeschlossenen TTS-Aufruf hält Konsolenausgabe, Laufzeitsumme und Logdatei konsistent. Fremdbibliothekslogger bleiben dabei auf `WARNING`, damit detailliertes Projektlogging nicht versehentlich vertrauliche HTTP-Daten ausgibt.

---

## Jeder TTS-Request kann eine hörbare Einschwingphase besitzen

### Erkenntnis

Ein Hörtest zeigte, dass der Anfang jeder Synthese etwas anders klingt als der vollständige restliche Request. Beim direkten Zusammenfügen wird diese wiederkehrende Einschwingphase als Chunk-Grenze hörbar. Die Beobachtung trat bereits unabhängig in einem anderen TTS-Projekt auf.

Der Qualitätsmodus verwendet deshalb einen identischen, konfigurierbaren Vorspannsatz für jeden Chunk. Eine separate WAV-Synthese kalibriert dessen ungefähre Dauer für die exakte Kombination aus Modell, Profil, Stimme, Geschwindigkeit und Instructions. Im Chunk-WAV wird anschließend nahe dieser Dauer nicht nach digitaler Nullstille, sondern nach einer ausreichend langen energiearmen Passage gesucht und in deren Mitte geschnitten.

Die Kalibrierung sollte nicht manuell über benannte Dateien verwaltet werden. Ein kanonischer Hash über alle tatsächlich wirksamen Werte einschließlich Vorspanntrenner, Provider und Ausgabeformat ermöglicht einen automatischen Cache: Inhaltliche Änderungen erzeugen sicher eine neue Kalibrierung, reine Änderungen an der JSON-Formatierung dagegen nicht. Ein expliziter Refresh bleibt für gezielte Hörtests verfügbar.

Die PCM-Analyse wurde mit nicht vollständig stillen synthetischen WAV-Passagen technisch validiert. Ein erster realer OpenAI-Kalibrierungsversuch zeigte außerdem, dass eine gestreamte WAV-Datei im Header eine Platzhalterlänge von `0xFFFFFFFF` tragen kann. Diese darf nicht als echte Framezahl interpretiert oder in neue WAVs kopiert werden. Die Anwendung zählt deshalb bei einem unplausiblen Header die tatsächlich lesbaren PCM-Frames und schreibt einen regulären Header. Die Korrektur ist durch einen synthetischen Regressionstest und spätere reale Läufe belegt.

Ein realer Ein-Chunk-Lauf zeigte außerdem, dass die zur Kalibrierungsmitte nächste
Ruhephase bereits nach den ersten Nutzwörtern liegen kann. Die sichere Auswahl nimmt
deshalb die letzte Ruhephase, die vor der kalibrierten Grenze beginnt, und schneidet
mit 0,15 Sekunden Reserve vor ihrer Mitte. Beim Folgetest lag die erkannte
Übergangspause bei 3,960–4,520 Sekunden und der Schnitt bei 4,090 Sekunden; danach
blieben 0,428 Sekunden Anfangsruhe vor dem Nutzsignal erhalten.

WAV-Zwischendateien ermöglichen samplegenaue Schnitte und eine einzige verlustbehaftete MP3-Kodierung am Ende. Die normalisierte Kalibrierungs-WAV wird zusammen mit den JSON-Messwerten aufbewahrt. Scheitert die Chunk-Verarbeitung, bleiben auch alle bis dahin erzeugten Arbeitsdateien für die Ursachenanalyse erhalten, ohne als fertige Ausgabe veröffentlicht zu werden. Ob der Ansatz die realen OpenAI-Chunk-Grenzen hörbar verbessert, bleibt durch Kalibrierung und AB-Hörtest zu bestätigen.

Für den AB-Hörvergleich müssen sowohl Provider-Rohfassungen als auch die wirklich verwendeten getrimmten WAV-Chunks zugänglich sein. Ein expliziter `--keep-chunks`-Schalter bewahrt deshalb nach einem erfolgreichen Qualitätslauf `raw-*.wav`, `trimmed-*.wav` und `combined.wav` gemeinsam auf. Ohne Schalter bleibt das automatische Aufräumen aktiv, damit Diagnosebedarf nicht zum dauerhaften Standard-Speicherverbrauch wird.

---

## Sprachprofile brauchen einen Katalog, keine CLI-Sonderfälle

### Erkenntnis

JSON-Profile lassen sich über eine kleine providerunabhängige Katalog-Komponente deterministisch entdecken, auf eindeutige Namen prüfen und wahlweise per Kurzname oder explizitem Dateipfad laden. Dadurch bleibt der Speech Renderer ausschließlich für die Übersetzung eines bereits gewählten Profils in eine TTS-Anfrage verantwortlich.

Die vier Profile `coaching`, `audiobook`, `podcast` und `meditation` wurden technisch auf Laden, Auflisten, Auswahl und Weitergabe von Stimme, Geschwindigkeit und globalen Anweisungen geprüft. Die verwendeten Voice-Bezeichner werden von der aktuell installierten OpenAI-SDK-Version akzeptiert. Diese technische Validierung ist keine Aussage über die subjektive Klangqualität; dafür bleiben reproduzierbare Hörvergleiche erforderlich.

---

## MP3-Stream-Copy technisch validiert

### Erkenntnis

Die beiden real erzeugten TTS-Chunks wurden mit FFmpeg ohne Re-Encoding zusammengeführt. FFprobe bestätigte für Quellen und Ziel MP3, 24 kHz, Mono und ungefähr 128 kbit/s. Die fertige Datei ist 4.771.245 Byte groß und 298,176 Sekunden lang; ihre Dauer entspricht exakt der Summe der beiden Quelldauern.

Der Audio Joiner prüft deshalb die Streamparameter vor dem Merge und die resultierende Dauer danach. Er arbeitet in einem temporären Verzeichnis und veröffentlicht nur ein vollständig validiertes Ergebnis. Der technische Merge ist damit belegt; ob der Übergang zwischen den Chunks subjektiv unauffällig klingt, bleibt ein eigener Hörtest.

---

## OpenAI-Multi-Chunk-Synthese technisch validiert

### Erkenntnis

Der reale Referenztext wurde erfolgreich über zwei kostenpflichtige OpenAI-TTS-Aufrufe verarbeitet und anschließend als vollständiger Batch veröffentlicht. Die erzeugten Dateien wurden unabhängig mit `ffprobe` geprüft:

- Chunk 1: MP3, 24 kHz, Mono, 128 kbit/s, 237,264 Sekunden, 3.796.224 Byte
- Chunk 2: MP3, 24 kHz, Mono, 128 kbit/s, 60,912 Sekunden, 974.592 Byte

Damit sind API-Anbindung, Chunk-Request-Erzeugung, temporäre Batch-Ausgabe und endgültige Veröffentlichung technisch validiert. Hörqualität und Übergangswirkung bleiben separate subjektive Experimente.

---

## Multi-Chunk-Ausgabe wird als vollständiger Batch veröffentlicht

### Erkenntnis

Mehrere kostenpflichtige Provideraufrufe dürfen nicht sofort einzeln unter ihren endgültigen Dateinamen erscheinen. Schlägt ein späterer Chunk fehl, würde sonst eine unvollständige Serie wie ein erfolgreiches Endergebnis wirken.

Die Multi-Chunk-Anwendung prüft deshalb vor dem ersten Provideraufruf sämtliche Zielnamen, erzeugt alle nummerierten Dateien in einem Arbeitsunterordner und veröffentlicht sie erst nach erfolgreicher Gesamterzeugung. Ein simulierter Fehler beim zweiten Chunk hinterlässt keine endgültige Audiodatei, bewahrt aber den bereits bezahlten und erzeugten ersten Chunk im protokollierten Diagnoseordner auf.

---

## Satzzeichenreine Blöcke gehören nicht in die Hörfassung

### Erkenntnis

Ein alleinstehender Punkt ist gültiger Textinhalt und wird vom Markdown-Parser deshalb korrekt als Absatz erhalten. Ob dieser Inhalt gesprochen wird, entscheidet erst der Semantic Renderer.

Blöcke, die ausschließlich aus Satz-, Leer- oder Sonderzeichen bestehen, werden nun standardmäßig aus der Hörfassung entfernt. Satzzeichen innerhalb eines Textblocks mit Buchstaben oder Ziffern bleiben vollständig erhalten. Die Regel ist über `remove_punctuation_only_blocks` konfigurierbar.

---

## Semantisches Chunking vor Audioerzeugung

### Erkenntnis

Chunking lässt sich vollständig providerunabhängig auf den strukturierten Blöcken des Semantic Renderers durchführen. Absätze, die vollständig in einen Chunk passen, bleiben ungeteilt. Nur überlange Blöcke werden schrittweise an Struktur-, Satz-, Teilsatz-, Komma- oder zuletzt Wortgrenzen getrennt.

Das Größenlimit gehört in eine Konfigurationsdatei. Die aktuelle OpenAI-Konfiguration verwendet 3.800 Zeichen als Sicherheitsabstand zum dokumentierten Maximum von 4.096 Zeichen im Speech-`input`; das Modell nennt zusätzlich ein Maximum von 2.000 Eingabetokens. Nach der Bereinigung satzzeichenreiner Blöcke erzeugt die Chunk-Vorschau des langen Referenztexts reproduzierbar zwei Chunks mit 3.627 und 903 Zeichen.

---

## TTS-Instructions sind globale Request-Anweisungen

### Erkenntnis

Die OpenAI-Speech-API bietet pro Request ein globales `instructions`-Feld, aber keine dokumentierte Steuerung einzelner Textspannen. Eine Anweisung wie „Betone die Phrase X“ kann höchstens als nicht garantierte Prompt-Heuristik verstanden werden.

Passagengenaue Betonung ist für dieses Projekt nicht erforderlich. Entscheidend ist ein gut verständlicher, natürlich gegliederter Sprechtext. Der Speech Renderer verwendet deshalb nur das kompakte globale Sprachprofil. Fett- und Kursiv-Spannen bleiben intern als Dokumentsemantik erhalten, werden aber nicht an den aktuellen Provider übersetzt.

---

# 2026-08-31

## AST-Diagnose ist keine Sprachvorschau

### Erkenntnis

Eine reine Klartextdarstellung des AST entfernt sichtbare Markdown-Zeichen, kann deren erhaltene Semantik aber nicht zeigen. Sie ist deshalb als Vorschau der späteren Hörfassung missverständlich.

Die Hörfassung wird ausschließlich durch einen eigenen Semantic Renderer erzeugt.

Dieser Renderer:

- formuliert nummerierte Listen sprechbar
- entfernt standardmäßig Tabellen, alleinstehende Codeblöcke, Bilder und Fußnoten
- bewahrt Fett und Kursiv als positionsgenaue semantische Hinweise

Parser und Semantic Renderer bleiben getrennt, damit Dokumentsemantik erhalten bleibt und Ausspracheregeln konfigurierbar sind.

---

## Projektstart

### Erkenntnis

Das Projekt soll keine einfache Text-to-Speech-Konvertierung sein.

Ziel ist eine hochwertige Hörbuch- bzw. Podcast-Ausgabe, die sich natürlich anhört und die Struktur des ursprünglichen Dokuments berücksichtigt.

---

## Dokumentstruktur besitzt Bedeutung

Markdown ist nicht nur Formatierung.

Markdown transportiert semantische Informationen über die Bedeutung eines Textes.

Beispiele:

- Überschriften
- Listen
- Hervorhebungen
- Zitate
- Trennlinien

Diese Informationen sollen möglichst erhalten und für die Sprachgestaltung genutzt werden.

---

## Nicht alles entfernen

Frühe Überlegung:

Markdown vollständig entfernen.

Neue Erkenntnis:

Markdown sollte zunächst vollständig geparst werden.

Erst danach wird entschieden, welche Informationen für die Sprachausgabe relevant sind.

---

## Entfernen

Folgende Inhalte werden grundsätzlich entfernt:

- URLs
- Zeilen beginnend mit "Quelle:"
- Datumsangaben im Format
  Datum: YYYY-MM-DD
- YAML Frontmatter
- HTML-Kommentare
- Linkdefinitionen

---

## Chunking

Texte dürfen niemals blind nach Zeichenanzahl getrennt werden.

Bevorzugte Reihenfolge:

1. Kapitel
2. Absatz
3. Satz
4. Komma

Nur im Ausnahmefall erfolgt eine Trennung innerhalb eines Satzes.

---

## Architektur

Parser und OpenAI-Anbindung werden vollständig voneinander getrennt.

Die OpenAI-API soll austauschbar sein.

Dadurch wird später auch ElevenLabs oder ein lokales Modell problemlos möglich.

---

## Sprachprofile

Sprachprofile werden nicht im Code gespeichert.

Alle Parameter werden extern konfiguriert.

Dadurch können neue Profile erstellt werden, ohne den Programmcode zu ändern.

Geplante Profile:

- Coaching
- Hörbuch
- Podcast
- Meditation

---

## Konfiguration statt Hardcoding

Alle Regeln sollen konfigurierbar sein.

Beispiele:

- Pausen
- Betonungen
- Chunkgrößen
- Stimmen
- Geschwindigkeit

Dadurch kann später dieselbe Konfiguration sowohl von Python als auch von Node.js verwendet werden.

---

## Zielarchitektur

Markdown

↓

Parser

↓

Dokumentstruktur (AST)

↓

Semantic Renderer

↓

Speech Renderer

↓

OpenAI TTS

↓

Audio Joiner

↓

MP3

---

## Qualitätsziel

Das Projekt orientiert sich nicht an klassischen TTS-Programmen.

Qualitätsziel:

"Ein Ergebnis erzeugen, das möglichst nah an einem professionell produzierten Hörbuch oder Podcast liegt."

Natürlichkeit hat Vorrang vor maximaler Verarbeitungsgeschwindigkeit.

---

## Offene Fragestellungen

Diese Punkte sollen später durch Tests beantwortet werden.

### OpenAI TTS

- Welche Stimme eignet sich am besten für Coaching-Texte?
- Welche Geschwindigkeit klingt am natürlichsten?
- Wie stark beeinflussen Instructions die Prosodie?
- Wie groß dürfen Chunks werden, bevor die Qualität sinkt?

---

### Semantik

Welche Markdown-Elemente verbessern tatsächlich die Sprachqualität?

Zu untersuchen:

- Überschriften
- Listen
- Zitate
- Tabellen
- Inline-Code
- Codeblöcke
- Trennlinien

Fett und Kursiv bleiben als Dokumentsemantik erhalten, werden vom aktuellen Speech Renderer aber nicht in passagengenaue TTS-Anweisungen übersetzt.

---

### Audio

Zu testen:

- optimale Pausenlängen
- Kapitelpausen
- Absatzpausen
- Satzpausen

---

## Grundprinzip

Wenn eine Entscheidung zwischen

- einfacher Implementierung

und

- besserer Audioqualität

getroffen werden muss,

hat die Audioqualität Vorrang.

---

## Langfristige Vision

Das Projekt soll als universelle Engine zur Umwandlung strukturierter Dokumente in hochwertige Sprachaufnahmen dienen.

Markdown ist lediglich das erste unterstützte Eingabeformat.

Später denkbare Erweiterungen:

- DOCX
- PDF
- HTML
- EPUB
- Obsidian Vaults
- Webseiten
- Notion-Export
- RSS-Feeds

Die Kernarchitektur soll unabhängig vom Eingabeformat bleiben.
