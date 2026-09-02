# Architecture Decisions

Dieses Dokument enthält alle grundlegenden Architekturentscheidungen des Projekts.

---

## ADR-001
### Markdown wird semantisch interpretiert

Status:
Accepted

Entscheidung:

Markdown wird nicht einfach entfernt.

Die Markdown-Struktur enthält semantische Informationen über Bedeutung und Gliederung des Textes.

Beispiele:

- Überschriften
- Listen
- Zitate
- Fett
- Kursiv
- Trennlinien

Begründung:

Ein Hörbuch soll die Struktur des Ausgangstextes verständlich wiedergeben. Daraus folgt keine Anforderung an eine passagengenaue Stimmsteuerung.

---

## ADR-002
### URLs werden entfernt

Status:
Accepted

Alle URLs werden vollständig entfernt.

Begründung:

URLs verschlechtern den Hörfluss erheblich.

---

## ADR-003
### Quellenangaben werden entfernt

Status:
Accepted

Zeilen beginnend mit

Quelle:

werden entfernt.

Begründung:

Die Quellen interessieren den Hörer normalerweise nicht.

---

## ADR-004
### Datum wird entfernt

Status:
Accepted

Zeilen wie

Datum: YYYY-MM-DD

werden entfernt.

Begründung:

Das Datum trägt nichts zum Hörverständnis bei.

---

## ADR-005
### Chunking erfolgt an Satzgrenzen

Status:
Accepted

Texte werden niemals mitten im Satz getrennt.

Priorität:

1. Kapitel
2. Absatz
3. Satz
4. Notfalls Komma

Begründung:

Dadurch bleibt die Prosodie erhalten.

---

## ADR-006
### Speech Profiles

Status:
Accepted

Die Sprachparameter werden niemals im Code hinterlegt.

Stattdessen existieren Profile.

Beispiele:

- coaching
- audiobook
- podcast
- meditation

Jedes Profil ist eine JSON-Datei mit eindeutigem Namen, Stimme, Geschwindigkeit und globalen Sprachanweisungen. Die Anwendung entdeckt Profile über ein konfigurierbares Verzeichnis. CLI-Aufrufe können ein Profil kurz über seinen Namen oder abwärtskompatibel über einen expliziten Dateipfad auswählen.

Die Profilauflistung und Namensauflösung liegen in einer eigenen Katalog-Komponente. Der Speech Renderer erhält weiterhin nur ein bereits geladenes Profil und bleibt von Dateisuche und CLI unabhängig.

---

## ADR-007
### Konfigurationsdateien statt Hardcoding

Status:
Accepted

Alle Regeln werden über YAML oder JSON konfiguriert.

Begründung:

Python und Node.js können dieselben Regeln verwenden.

---

## ADR-008
### Modulare Architektur

Status:
Accepted

Parser

↓

Semantic Renderer

↓

Speech Renderer

↓

OpenAI TTS

↓

Audio Joiner

Jedes Modul besitzt genau eine Aufgabe.

---

## ADR-009
### API unabhängig halten

Status:
Accepted

Die OpenAI-Kommunikation wird vollständig gekapselt.

Ein späterer Wechsel auf ElevenLabs oder andere Anbieter soll ohne Änderungen am Parser möglich sein.

---

## ADR-010
### AST und Hörfassung bleiben getrennt

Status:
Accepted

Entscheidung:

Der Parser bewahrt die semantische Dokumentstruktur im AST. Der Semantic Renderer entscheidet anschließend, welche Inhalte gesprochen und wie sie für Sprache formuliert werden.

Nicht sprechbare Inhalte wie Tabellen, alleinstehende Codeblöcke, Fußnoten und eigenständige Blöcke ohne Buchstaben oder Ziffern bleiben dadurch erkennbar, werden aber standardmäßig aus der Hörfassung ausgeschlossen.

Fett und Kursiv werden nicht als Markdown-Zeichen gesprochen. Ihre Position bleibt als providerunabhängige Semantik erhalten, ohne daraus zwingend eine lokale TTS-Steuerung abzuleiten.

Begründung:

Eine technische Klartextansicht darf nicht mit der tatsächlich vorgesehenen Hörfassung verwechselt werden. Gleichzeitig darf die für Prosodie wichtige Markdown-Semantik nicht verloren gehen.

---

## ADR-011
### TTS-Anweisungen gelten global pro Request

Status:
Accepted

Entscheidung:

Der Speech Renderer sendet ausschließlich die globalen Anweisungen des gewählten Sprachprofils. Er formuliert keine Listen einzelner Fett- oder Kursiv-Phrasen für den TTS-Provider.

Positionsgenaue Semantik-Cues dürfen für Diagnose und spätere providerabhängige Erweiterungen erhalten bleiben, sind aber nicht Bestandteil der aktuellen TTS-Anfrage.

Begründung:

Die OpenAI-Speech-API dokumentiert ein einzelnes globales `instructions`-Feld pro Request, jedoch keine verlässliche Zuordnung von Anweisungen zu Textspannen. Passagengenaue Betonung ist für das Projekt keine Anforderung. Kompakte globale Anweisungen sind vorhersehbarer und verbrauchen weniger Eingabetokens.

---

## ADR-012
### Semantisches Chunking bleibt providerunabhängig

Status:
Accepted

Entscheidung:

Der Semantic Chunker arbeitet auf dem Ergebnis des Semantic Renderers und kennt weder OpenAI noch Audiodateiformate. Größenlimits und Trennzeichen werden aus `config/chunking.json` geladen.

Die Trennreihenfolge lautet:

1. Überschrift beziehungsweise Kapitel
2. vollständiger Absatz oder anderer semantischer Block
3. Strukturgrenze innerhalb eines Blocks, beispielsweise ein Listeneintrag
4. Satzende
5. Teilsatzzeichen
6. Komma
7. im Ausnahmefall eine Wortgrenze

Es wird niemals mitten in einem Wort getrennt. Kann selbst an einer Wortgrenze kein gültiger Chunk erzeugt werden, bricht der Chunker mit einer verständlichen Fehlermeldung ab.

Begründung:

Die Prosodie soll durch natürliche Grenzen geschützt werden, während verschiedene TTS-Provider abweichende Eingabelimits konfigurieren können. Für OpenAI GPT-4o Mini TTS sind derzeit 3.800 Zeichen als Sicherheitsabstand zum dokumentierten 4.096-Zeichen-Limit konfiguriert.

---

## ADR-013
### Multi-Chunk-Audio wird transaktional veröffentlicht

Status:
Accepted

Entscheidung:

Die Multi-Chunk-Anwendung erzeugt nummerierte Audiodateien zunächst in einem Arbeitsunterordner. Erst wenn alle Provideraufrufe erfolgreich waren, werden sämtliche Dateien unter ihren endgültigen Namen veröffentlicht. Nach Erfolg wird der Arbeitsordner entfernt. Bei einem Fehler bleibt er mitsamt bereits erzeugten Chunks als Diagnosematerial erhalten und sein Pfad wird protokolliert.

Vor dem ersten kostenpflichtigen Aufruf werden alle erwarteten Zieldateien auf Namenskollisionen geprüft. Ohne ausdrückliches `--overwrite` wird keine vorhandene Datei ersetzt.

Begründung:

Eine teilweise erzeugte Dateiserie darf nicht mit einem erfolgreichen Gesamtergebnis verwechselt werden. Die Transaktionsgrenze gehört in die Anwendungsschicht; einzelne Provider bleiben weiterhin nur für die atomare Erzeugung genau einer Audiodatei verantwortlich.

---

## ADR-014
### Kompatible MP3-Chunks werden per FFmpeg Stream-Copy zusammengeführt

Status:
Accepted

Entscheidung:

Die Audio-Zusammenführung bleibt eine eigenständige, providerunabhängige Komponente. Sie prüft alle Eingaben mit FFprobe auf übereinstimmenden Codec, Abtastrate und Kanalzahl und verwendet anschließend den FFmpeg-Concat-Demuxer mit `-c copy`.

Die Ausgabe entsteht zunächst temporär. Nach dem Merge werden Streamparameter und Gesamtdauer erneut geprüft. Nur eine gültige Datei wird atomar unter dem endgültigen Zielnamen veröffentlicht; vorhandene Ziele bleiben ohne ausdrückliches `--overwrite` unangetastet.

Begründung:

Die von einem Multi-Chunk-TTS-Lauf erzeugten Dateien besitzen identische Streamparameter. Stream-Copy vermeidet Qualitätsverlust, zusätzliche Kodierzeit und unerwünschte Klangänderungen. Die Prüfung vor und nach dem Merge verhindert, dass inkompatible oder unvollständige Dateien als fertiges Ergebnis erscheinen.

---

## ADR-015
### Hörbare Request-Anfänge werden über kalibrierten WAV-Prefill entfernt

Status:
Accepted

Entscheidung:

Der Qualitätsmodus stellt jedem TTS-Chunk denselben konfigurierten Vorspannsatz voran. Seine Dauer wird einmalig mit exakt demselben Profil, derselben Stimme, Geschwindigkeit, Instructions und demselben Modell als WAV kalibriert. Der Chunker reserviert die Zeichen des Vorspanns innerhalb des bestehenden Request-Limits.

Der normale Syntheseaufruf verwaltet diese Kalibrierung automatisch. Ein kanonischer SHA-256-Fingerprint aus den wirksamen Werten für Vorspann und Trenner, Profil, Stimme, Geschwindigkeit, Instructions, Provider, Modell und Ausgabeformat adressiert ein Cache-Paar aus JSON-Metadaten und normalisierter WAV-Aufnahme. Ein Cache-Miss erzeugt das Paar; ein Treffer verwendet es wieder. `--refresh-calibration` erzwingt eine Neuerzeugung. Kalibrierungen anderer Fingerprints werden nicht gelöscht. Ein expliziter Kalibrierungspfad und der separate Kalibrierungsbefehl bleiben als Expertenwerkzeuge erhalten, sind aber keine Voraussetzung für den Qualitätsmodus.

Nach jedem TTS-Aufruf sucht eine providerunabhängige PCM-WAV-Analyse nahe der kalibrierten Dauer nach einer ausreichend langen Passage unterhalb einer konfigurierten dBFS-Grenze. Streaming-WAVs mit Platzhalterlängen im Header werden über ihre tatsächlich lesbaren PCM-Frames vermessen und mit regulärem Header weitergeschrieben. Es wird nicht auf digitale Nullstille gewartet. Der Schnitt erfolgt samplegenau in der Mitte der ausgewählten Ruhepassage. Ohne sichere Fundstelle wird der gesamte Lauf abgebrochen und keine finale Datei veröffentlicht; bereits vorhandene Roh- und Zwischen-WAVs bleiben im protokollierten Diagnoseordner erhalten.

Bei mehreren Ruhepassagen wird die letzte Passage gewählt, die spätestens an der
kalibrierten Grenze beginnt. Dadurch kann eine kurze Pause in den ersten Nutzwörtern
nicht mehr gegenüber der eigentlichen Prefill-Grenze gewinnen. Der Schnitt liegt um
den konfigurierten Wert `cut_safety_seconds` vor der Passagenmitte und wird am
Passagenanfang begrenzt; standardmäßig bleiben 0,15 Sekunden Sicherheitsreserve.

Bereinigte WAV-Chunks werden ohne Re-Encoding zusammengefügt. Erst das Gesamtergebnis wird einmalig als MP3 kodiert. Der bestehende MP3-Stream-Copy-Modus aus ADR-014 bleibt als schneller, günstigerer Alternativpfad bestehen.

Nach einem erfolgreichen Qualitätslauf werden die Arbeits-WAVs standardmäßig entfernt. Der explizite Schalter `--keep-chunks` bewahrt originale `raw-*.wav`, tatsächlich verwendete `trimmed-*.wav` und `combined.wav` in einem eindeutigen Arbeitsordner auf und meldet dessen Pfad. So bleibt die normale Ausführung aufgeräumt, während reproduzierbare Hörtests die Zwischenstufen direkt vergleichen können. Fehlerartefakte werden unabhängig von diesem Schalter erhalten.

Begründung:

Ein Hörtest zeigte reproduzierbar, dass der Anfang einer Synthese anders klingen kann als der restliche Request und dadurch harte Chunk-Grenzen hörbar werden. WAV-Zwischendateien vermeiden MP3-Framegrenzen, Encoder-Delay und wiederholte verlustbehaftete Kodierung beim Entfernen dieses Einschwingbereichs. Der Fingerprint über wirksame Werte verhindert sowohl die versehentliche Wiederverwendung einer unpassenden Kalibrierung als auch unnötige Neuerzeugungen nach rein formatierenden JSON-Änderungen.

---

## ADR-016
### Speech-Usage ist Response-Datum, Kosten sind eine konfigurierte Berechnung

Status:
Accepted

Entscheidung:

Der OpenAI-Provider verwendet für `gpt-4o-mini-tts` das dokumentierte SSE-Streamformat und veröffentlicht Audio erst nach einem gültigen `speech.audio.done`-Ereignis. Der providerunabhängige Synthesevertrag liefert neben dem Ausgabepfad optionale Usage-Daten mit Input-, Audio-Output- und Gesamttokens.

Anwendungskomponenten emittieren nach jedem abgeschlossenen kostenpflichtigen Aufruf ein providerunabhängiges Fortschrittsereignis. Die CLI formatiert diese Ereignisse, aggregiert den Lauf und kann dieselben Informationen zusätzlich in ein UTF-8-Log schreiben.

Dollarbeträge werden nicht als Teil der OpenAI-Speech-Response behauptet. Die Berechnung verwendet tatsächliche Response-Tokens und datierte Preise aus der Provider-JSON. Ausgabe und Dokumentation kennzeichnen den Betrag als lokal berechnet und nennen die Preisquelle. Externe SDK- und HTTP-Logger bleiben zum Schutz vertraulicher Requestdaten mindestens auf `WARNING`.

Begründung:

Die dokumentierte Speech-Response enthält Token-Usage, aber keinen fertigen Geldbetrag. Die Trennung verhindert irreführende Genauigkeit, hält Preise ohne Codeänderung aktualisierbar und bewahrt die Provider-Austauschbarkeit. Fortschritt, Logging und Kostenübersicht basieren dadurch auf demselben strukturierten Ereignis statt auf voneinander abweichenden Sonderlösungen.

---

## ADR-017
### Der schnelle Multi-Chunk-Modus veröffentlicht eine fertige MP3

Status:
Accepted

Entscheidung:

`synthesize-chunks` behandelt den optionalen Ausgabepfad als finale MP3. Fehlt er,
wird die Eingabe-Endung durch `.mp3` ersetzt. Die nummerierten MP3-Chunks werden in
einem Verzeichnis mit demselben Ausgabestamm ohne `.mp3` erzeugt und anschließend
per Stream-Copy zusammengeführt.

Nach erfolgreicher Zusammenführung werden ausschließlich die in diesem Lauf
veröffentlichten Chunk-Dateien entfernt. Das Verzeichnis wird nur gelöscht, wenn es
danach leer ist. Bei einem Fehler, mit `--keep-chunks` oder bei fremden verbliebenen
Dateien bleibt es bestehen. Die Existenz der finalen MP3 wird vor dem ersten
kostenpflichtigen Provideraufruf geprüft.

Begründung:

Der Standardaufruf soll unmittelbar ein nutzbares Hörstück liefern, ohne einen
separaten `merge`-Schritt zu verlangen. Der vorhersagbare Ordnername erleichtert die
Diagnose, während das gezielte Aufräumen keine bereits vorhandenen fremden Dateien
entfernt.

---

## ADR-018
### Einzelrequests werden lokal begrenzt und Providerfehler bleiben konkret

Status:
Accepted

Entscheidung:

`synthesize` prüft den vollständig gerenderten Sprechtext vor dem Provideraufruf
gegen `max_characters` aus der Chunking-Konfiguration. Bei Überschreitung wird kein
kostenpflichtiger Request begonnen und auf die beiden Chunk-fähigen Befehle
verwiesen.

Schlägt ein OpenAI-Aufruf dennoch fehl, übernimmt der Provider die kurze
SDK- beziehungsweise SSE-Fehlermeldung und gegebenenfalls den HTTP-Status. Er gibt
weder vollständige Response-Bodies noch Request-Inhalte aus.

Begründung:

Eine lokale, konservative Zeichengrenze liefert vorhersagbares Verhalten, obwohl
das Modelllimit tokenbasiert ist. Konkrete Providerdetails unterscheiden etwa zu
lange Eingaben, Authentifizierungsfehler und Verbindungsprobleme, ohne unnötig
sensible Daten offenzulegen.

---

## ADR-019
### Der befehlslose Syntheseaufruf wählt den Verarbeitungsweg automatisch

Status:
Accepted

Entscheidung:

Beginnt der CLI-Aufruf direkt mit einer Markdown-Eingabedatei, wird intern der
automatische Synthesemodus verwendet. Er rendert den Sprechtext vor dem ersten
Provideraufruf und verwendet bis einschließlich `max_characters` den direkten
Einzelrequest. Oberhalb dieses Limits verwendet er automatisch den
Prefill-Qualitätsmodus einschließlich semantischem Chunking.

Die expliziten Befehle `synthesize`, `synthesize-chunks` und
`synthesize-prefill` bleiben unverändert verfügbar. Damit kann ein Nutzer den
gewünschten Verarbeitungsweg weiterhin bewusst erzwingen.

Begründung:

Der Normalfall benötigt dadurch nur Eingabe und optionales Ausgabeziel, ohne dass
der Nutzer die gerenderte Textlänge vorab kennen muss. Die Auswahl erfolgt lokal
und verursacht keinen zusätzlichen API-Aufruf.
