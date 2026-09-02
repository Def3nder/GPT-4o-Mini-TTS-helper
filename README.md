# Markdown TTS

> High-quality Markdown to Speech engine using OpenAI GPT-4o Mini TTS.

---

## Vision

Markdown TTS ist keine einfache Text-to-Speech-Anwendung.

Das Ziel des Projekts besteht darin, strukturierte Dokumente (beginnend mit Markdown) in hochwertige Sprachaufnahmen umzuwandeln, die sich möglichst wie professionell produzierte Hörbücher oder Podcasts anhören.

Der Schwerpunkt liegt auf:

- natürlicher Sprachqualität
- semantischer Interpretation von Dokumenten
- reproduzierbarer Audioqualität
- modularer Architektur
- langfristiger Erweiterbarkeit

---

# Projektziele

Dieses Projekt soll:

- Markdown intelligent interpretieren
- Dokumentstruktur erhalten
- natürliche Sprachpausen erzeugen
- verschiedene Sprachprofile unterstützen
- hochwertige MP3-Dateien erzeugen
- leicht auf andere Eingabeformate erweiterbar sein
- später problemlos nach Node.js portiert werden können

Nicht-Ziele:

- möglichst kurze Entwicklungszeit
- möglichst wenig Code
- möglichst schnelle Verarbeitung

Qualität besitzt Vorrang.

---

# Hauptfunktionen

## Dokumentbereinigung

Automatisches Entfernen von

- URLs
- Quellenangaben
- Datumsangaben
- YAML Frontmatter
- HTML-Kommentaren
- Referenzdefinitionen
- eigenständigen Blöcken, die ausschließlich aus Satz- oder Sonderzeichen bestehen

---

## Semantische Interpretation

Markdown wird nicht gelöscht.

Es wird interpretiert.

Beispiele:

- Überschriften
- Absätze
- Listen
- Zitate
- Hervorhebungen
- Trennlinien

Diese Informationen beeinflussen später die Sprachgestaltung.

Dabei wird zwischen Dokumentsemantik und TTS-Steuerung unterschieden:

- Überschriften, Absätze und Listen beeinflussen den sprechbaren Text, seine Gliederung und später das Chunking.
- Fett und Kursiv bleiben intern als semantische Textspannen erkennbar, werden in der Hörfassung aber als normaler Text ausgegeben.
- Der TTS-Provider erhält pro Anfrage ausschließlich globale Sprachanweisungen. Eine passagengenaue Betonungssteuerung wird nicht vorausgesetzt.

---

## Sprachprofile

Verfügbare Profile:

| Profilname | Stimme | Geschwindigkeit | Ausrichtung |
|------------|--------|-----------------|-------------|
| `coaching` | `cedar` | 0,95 | warm, klar und ruhig |
| `audiobook` | `marin` | 0,95 | gleichmäßiger professioneller Erzählfluss |
| `podcast` | `coral` | 1,0 | lebendig, direkt und nahbar |
| `meditation` | `sage` | 0,85 | langsam, sanft und gelassen |
| `coaching-level1-m` | `echo` | 1,0 | tiefenentspannt, sanft und schützend; männlich |
| `coaching-level1-w` | `nova` | 1,0 | tiefenentspannt, sanft und schützend; weiblich |
| `coaching-level2-m` | `cedar` | 1,0 | klar, reflektiert und empathisch; männlich |
| `coaching-level2-w` | `marin` | 1,0 | klar, reflektiert und empathisch; weiblich |
| `coaching-level3-m` | `onyx` | 1,0 | motivierend und aktivierend; männlich |
| `coaching-level3-w` | `marin` | 1,0 | motivierend und aktivierend; weiblich |
| `coaching-level4-m` | `onyx` | 1,0 | enthusiastisch und inspirierend; männlich |
| `coaching-level4-w` | `shimmer` | 1,0 | enthusiastisch und inspirierend; weiblich |

Jedes JSON-Profil definiert Name, Stimme, Geschwindigkeit und globale Sprachanweisungen. Pausen und Betonung werden innerhalb dieser globalen Anweisungen beschrieben. Die aktuellen Werte sind reproduzierbare Ausgangskonfigurationen; ihre subjektive Klangqualität wird später über die in `EXPERIMENTS.md` vorgesehenen Hörvergleiche optimiert.

---

## Chunking

Lange Dokumente werden automatisch in sinnvolle Blöcke aufgeteilt.

Priorität:

1. Kapitel
2. Absatz
3. Satz
4. Komma

Dadurch bleiben Sprachfluss und Prosodie möglichst natürlich.

---

## Audio

Der Qualitätsmodus erzeugt

↓

WAV-Chunks mit identischem Vorspannsatz

↓

am energiearmen Übergang getrimmte WAV-Chunks

↓

eine einmalig kodierte fertige MP3-Datei

Der schnelle Modus erzeugt nummerierte MP3-Chunks und fügt sie anschließend per
Stream-Copy zu einer fertigen MP3 zusammen. Nach Erfolg werden die Chunks
standardmäßig entfernt.

---

# Architektur

```
Markdown

↓

Parser

↓

AST (Dokumentstruktur)

↓

Semantic Renderer

↓

Speech Renderer

↓

OpenAI TTS

↓

Prefill Trimmer / Audio Joiner / finaler Encoder

↓

MP3
```

---

# Projektstruktur

```
markdown-tts/

README.md

CONTEXT.md
ARCHITECTURE.md
DECISIONS.md
PROJECT_RULES.md
ROADMAP.md
BACKLOG.md
LESSONS-LEARNED.md
EXPERIMENTS.md
TEST_CORPUS.md

config/
    parser_rules.json
    semantic_renderer.json
    chunking.json
    tts_provider.json
    tts_provider_wav.json
    audio_joiner.json
    audio_encoder.json
    prefill.json

speech_profiles/
    audiobook.json
    coaching.json
    coaching-level1-m.json
    coaching-level1-w.json
    coaching-level2-m.json
    coaching-level2-w.json
    coaching-level3-m.json
    coaching-level3-w.json
    coaching-level4-m.json
    coaching-level4-w.json
    meditation.json
    podcast.json

src/
    markdown_tts/
        audio/
        prefill.py

tests/
```

---

# Dokumentation

| Datei | Inhalt |
|--------|---------|
| README.md | Projektübersicht |
| CONTEXT.md | Vision und Motivation |
| ARCHITECTURE.md | Systemarchitektur |
| DECISIONS.md | Architekturentscheidungen |
| PROJECT_RULES.md | Entwicklungsregeln |
| ROADMAP.md | Versionsplanung |
| BACKLOG.md | Detaillierte Aufgaben |
| TODO.md | Kompakter Projektstatus |
| LESSONS-LEARNED.md | Erkenntnisse |
| EXPERIMENTS.md | Experimente |
| TEST_CORPUS.md | Referenztests |

---

# Aktueller Implementierungsstand

Der erste MVP-Baustein ist verfügbar:

- striktes UTF-8-Laden
- semantisches, providerunabhängiges Dokument-AST
- Erkennung von Überschriften, Absätzen, Listen, Zitaten, Hervorhebungen und Code
- semantische Erkennung von Tabellen und Fußnoten
- konfigurierbares Entfernen von Frontmatter, URLs, Quellenzeilen, Datumszeilen und HTML-Kommentaren
- sprechbare Textausgabe mit ausgeschlossenen Tabellen, Codeblöcken, Bildern und Fußnoten
- konfigurierbares Entfernen alleinstehender Satz- und Sonderzeichenblöcke
- deutsche Formulierungen für nummerierte Listen
- intern positionsgenau erhaltene Fett- und Kursiv-Semantik für Diagnose und spätere Erweiterungen
- kompakte globale Sprachanweisungen ohne nicht garantierte Phrasensteuerung
- mehrere auswählbare JSON-Sprachprofile einschließlich vier Coaching-Energiestufen mit je einer männlichen und weiblichen Stimme
- Profilauflistung und Detailansicht über die CLI
- providerunabhängiges semantisches Chunking mit konfigurierbarem Zeichenlimit
- Trennung an Überschriften, Absätzen, Sätzen, Teilsätzen und als letzter Rückfall an Wortgrenzen
- kostenfreie Chunk-Vorschau mit exakter Zeichenzahl
- Prefill-aware Chunk-Vorschau mit reservierter Request-Kapazität
- transaktionale Multi-Chunk-Synthese in nummerierte Audiodateien
- automatisch zwischengespeicherte Prefill-Kalibrierung als JSON plus normalisierte Referenz-WAV mit Konfigurations-Fingerprint
- samplegenaues WAV-Trimming in einer energiearmen, nicht zwingend vollständig stillen Passage
- transaktionaler Qualitätsmodus mit WAV-Zwischendateien und einmaliger finaler MP3-Kodierung
- optionale Aufbewahrung von Roh-, getrimmten und zusammengefügten WAVs für Übergangs-Hörtests
- formatierte Fortschrittsanzeige mit tatsächlichen Speech-Tokenwerten pro API-Aufruf
- lokal berechnete Kostenübersicht auf Basis konfigurierter, datierter Modellpreise
- konfigurierbares Konsolen- und UTF-8-Dateilogging ohne API-Key-Ausgabe
- FFmpeg-basierte MP3-Zusammenführung per Stream-Copy ohne erneute Kodierung
- Prüfung kompatibler Streamparameter und der resultierenden Gesamtdauer
- austauschbare TTS-Provider-Schnittstelle
- gekapselte OpenAI-Anbindung mit konfigurierbarem Retry
- atomare MP3-Ausgabe mit Überschreibschutz
- Unit- und Referenztests für Loader, Struktur, Bereinigung und Semantic Renderer

Kurze Dokumente können als einzelne MP3 erzeugt werden. Lange Dokumente werden
semantisch aufgeteilt, als nummerierte MP3-Dateien synthetisiert und anschließend
ohne erneute Audiokodierung zu einer fertigen MP3 zusammengeführt.

## Installation für die Entwicklung

```powershell
uv sync
```

## Sprachprofile anzeigen und auswählen

Alle verfügbaren Profile lassen sich ohne API-Aufruf anzeigen:

```powershell
uv run markdown-tts profiles
```

Die vollständigen Einstellungen eines Profils zeigt ein optionaler Profilname:

```powershell
uv run markdown-tts profiles audiobook
```

Die vier Coaching-Energiestufen besitzen jeweils eine männliche Variante mit dem Suffix `-m` und eine weibliche Variante mit `-w`, beispielsweise `coaching-level2-m` und `coaching-level2-w`.

Für die normale Verwendung genügt die Eingabedatei. Die Anwendung misst den
tatsächlich gerenderten Sprechtext und wählt automatisch `synthesize` bis zum
konfigurierten Zeichenlimit beziehungsweise `synthesize-prefill` für längere
Texte:

```powershell
uv run markdown-tts input.md
```

Der optionale zweite Pfad ist die Ausgabedatei. Ohne ihn entsteht `input.mp3` am
Ort der Eingabedatei. Die Befehle `synthesize`, `synthesize-chunks` und
`synthesize-prefill` bleiben verfügbar, wenn der Verarbeitungsweg ausdrücklich
festgelegt werden soll.

Bei der Synthese wird das Profil über seinen Namen ausgewählt. Ohne `--profile` bleibt `coaching` der Standard:

```powershell
uv run markdown-tts synthesize input.md output.mp3 --profile audiobook

uv run markdown-tts synthesize-chunks input.md output\podcast.mp3 --profile podcast
```

Bei `synthesize` und `synthesize-prefill` ist die Ausgabedatei optional. Ohne sie
wird die Endung der Eingabedatei durch `.mp3` ersetzt und die MP3 direkt neben der
Eingabedatei gespeichert:

```powershell
uv run markdown-tts synthesize input.md
```

Mit `--append-profile-name` wird der tatsächlich geladene Profilname an den
Dateistamm angehängt. Der folgende Aufruf erzeugt `input_audiobook.mp3`:

```powershell
uv run markdown-tts synthesize input.md --profile audiobook --append-profile-name
```

Ein direkter Pfad zu einer eigenen JSON-Datei bleibt ebenfalls möglich:

```powershell
uv run markdown-tts synthesize input.md output.mp3 `
  --profile speech_profiles\meditation.json
```

Für ein anderes Profilverzeichnis steht zusätzlich `--profiles-dir` zur Verfügung.

## Parser verwenden

```python
from markdown_tts import (
    MarkdownParser,
    ParserRules,
    SemanticRenderer,
    SemanticRendererRules,
    load_markdown,
)

rules = ParserRules.from_file("config/parser_rules.json")
document = MarkdownParser(rules).parse(load_markdown("artikel.md"))

renderer_rules = SemanticRendererRules.from_file("config/semantic_renderer.json")
speech_document = SemanticRenderer(renderer_rules).render(document)
print(speech_document.text)
```

Die Funktion `document_text` aus `ast.py` ist ausschließlich eine technische AST-Diagnose. Für die vorgesehene Hörfassung wird immer der `SemanticRenderer` verwendet.

## Sprachvorschau

```powershell
uv run markdown-tts preview tests\corpus\tc_007_v1.md --show-cues
```

Die Vorschau zeigt den später zu sprechenden Text. `--show-cues` zeigt zusätzlich die intern erhaltenen Fett-/Kursiv-Spannen zur Diagnose; diese Hinweise werden nicht als passagengenaue Anweisungen an OpenAI TTS gesendet.

## Chunk-Vorschau

Für lange Dokumente zeigt `--show-chunks` vor einem API-Aufruf die geplanten Grenzen und die exakte Zeichenzahl jedes Chunks:

```powershell
uv run markdown-tts preview 2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.md --show-chunks
```

Das Standardlimit steht in `config/chunking.json` und beträgt derzeit 3.800 Zeichen. Der Wert ist konfigurierbar und liegt mit Sicherheitsabstand unter dem dokumentierten OpenAI-Limit von 4.096 Zeichen für das `input`-Feld. Die allgemeine Chunking-Komponente kennt keinen OpenAI-Provider und kann für andere Provider mit einer anderen Konfiguration verwendet werden.

Für den Prefill-Qualitätsmodus reserviert die Vorschau zusätzlich die Zeichen des Vorspanns und zeigt die tatsächliche Request-Größe:

```powershell
uv run markdown-tts preview 2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.md `
  --show-chunks --prefill
```

Mit der Standardkonfiguration beansprucht der Vorspann einschließlich Trenner 66 Zeichen. Der Referenzartikel bleibt bei zwei Requests mit 3.693 und 969 Zeichen.

## Prefill-Qualitätsmodus gegen hörbare Chunk-Anfänge

Ein Hörtest zeigte, dass der Anfang jedes TTS-Requests anders klingen kann als sein weiterer Verlauf und dadurch Chunk-Grenzen hörbar bleiben. Der Qualitätsmodus stellt deshalb jedem Chunk denselben neutralen Vorspannsatz voran und entfernt ihn nach der Synthese wieder. Die dafür nötige Kalibrierung wird automatisch verwaltet; im normalen Ablauf ist weder eine Kalibrierungsdatei noch ein separater Kalibrierungsbefehl nötig.

Der Qualitätsmodus erzeugt mit einem Aufruf eine fertige MP3:

```powershell
uv run markdown-tts synthesize-prefill `
  2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.md `
  output\ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.mp3 `
  --profile coaching
```

Für die Beurteilung der einzelnen Chunk-Klänge und Übergänge bleiben mit `--keep-chunks` zusätzlich alle Analyse-WAVs erhalten:

```powershell
uv run markdown-tts synthesize-prefill `
  2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden_prefill.md `
  output\ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.mp3 `
  --profile coaching `
  --keep-chunks
```

Nach erfolgreicher Verarbeitung gibt die CLI den eindeutigen Arbeitsordner aus. Darin liegen:

- `raw-001.wav`, `raw-002.wav`, …: originale Providerantworten einschließlich Vorspann
- `trimmed-001.wav`, `trimmed-002.wav`, …: tatsächlich zusammengefügte Chunks nach entferntem Vorspann
- `combined.wav`: vollständige Zusammenfügung vor der einmaligen MP3-Kodierung

Die finale MP3 liegt am angegebenen Zielpfad oder – wenn dieser weggelassen wurde –
gleichnamig neben der Eingabedatei. `synthesize-chunks` unterstützt ebenfalls
`--keep-chunks`; dort bleiben die nummerierten MP3-Quelldateien im benannten
Chunk-Verzeichnis erhalten.

Der zweite Pfad bezeichnet immer das vollständige fertige Hörstück. Das Wort `prefill` im Befehlsnamen kennzeichnet nur den verwendeten Qualitätsmodus; die kurze Kalibrierungsaufnahme wird intern verarbeitet und nicht unter diesem Zielpfad veröffentlicht.

Die Anwendung bildet einen kanonischen SHA-256-Fingerprint aus allen wirksamen Kalibrierungswerten: Vorspannsatz und Trenner, Profilname, Stimme, Geschwindigkeit, Instructions, Provider, Modell und WAV-Ausgabeformat. Unter `output\prefill-calibrations` wird eine dazu passende Kalibrierung automatisch wiederverwendet. Bei einem Cache-Miss wird der Vorspann vor den eigentlichen Chunks einmal als WAV synthetisiert. Gespeichert werden die Messwerte als `.json` und die normalisierte Kalibrierungsaufnahme mit demselben Basisnamen als `.wav`. Eine geänderte Einstellung erhält automatisch ein anderes Dateipaar; ältere Kalibrierungen werden dabei nicht gelöscht. Unterschiede in der bloßen JSON-Formatierung beeinflussen den Fingerprint nicht.

Eine vorhandene Kalibrierung lässt sich bewusst neu erzeugen:

```powershell
uv run markdown-tts synthesize-prefill `
  2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.md `
  output\ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.mp3 `
  --profile coaching `
  --refresh-calibration `
  --overwrite
```

`--calibration` und der separate Befehl `calibrate-prefill` bleiben für Diagnose- und Expertenfälle verfügbar. Quell- und Zielpfad werden vor einer automatischen Kalibrierung geprüft, damit ein ungültiger Syntheseauftrag keinen vermeidbaren kostenpflichtigen Kalibrierungsaufruf auslöst.

Pro Chunk erfolgt ein WAV-TTS-Aufruf. Der Trimmer durchsucht nur ein konfiguriertes Zeitfenster nahe der kalibrierten Vorspanndauer. Er sucht eine ausreichend lange Passage unterhalb der konfigurierten dBFS-Grenze; digitale Nullstille ist nicht erforderlich. Geschnitten wird in der Mitte dieser Passage. Wird keine sichere Stelle gefunden, wird keine finale Datei veröffentlicht. OpenAI-Streaming-WAVs mit einer Platzhalterlänge im Header werden anhand der tatsächlich lesbaren PCM-Frames vermessen und vor der weiteren Verarbeitung mit einem regulären Header normalisiert.

Die bereinigten PCM-WAV-Dateien werden ohne Qualitätsverlust zusammengefügt und anschließend genau einmal mit FFmpeg als MP3 kodiert. Bei Erfolg wird das Arbeitsverzeichnis standardmäßig automatisch entfernt; `--keep-chunks` bewahrt es ausdrücklich auf und gibt seinen Pfad aus. Bei einem Fehler bleiben Roh-Chunks, bereits getrimmte Chunks und weitere vorhandene Diagnoseartefakte unabhängig vom Schalter in einem Arbeitsordner neben der Zieldatei erhalten; dessen Pfad wird in der Fehlermeldung protokolliert. Vorspannsatz, Suchfenster und Energiegrenze stehen in `config/prefill.json`; die finale MP3-Kodierung steht in `config/audio_encoder.json`.

Der Vorspann erhöht den Inputverbrauch jedes Chunk-Aufrufs um derzeit 66 Zeichen. Nur bei einem Cache-Miss oder mit `--refresh-calibration` kommt ein Kalibrierungsaufruf hinzu. Die eigentlichen Chunk-Grenzen berücksichtigen die Reserve automatisch.

## Fortschritt, Tokenverbrauch, Kosten und Logging

Die OpenAI Speech-API gibt im SSE-Abschlussereignis `speech.audio.done` die tatsächlich verwendeten `input_tokens`, `output_tokens` und `total_tokens` zurück. Sie gibt dabei keinen fertigen Geldbetrag zurück. Markdown TTS verwendet deshalb die tatsächlichen Response-Tokenwerte und berechnet daraus transparent eine Kostensumme anhand der in der jeweiligen Provider-Konfiguration hinterlegten Preise. Der konfigurierte Preisstand und die offizielle Preisquelle werden mit ausgegeben. Maßgeblich für die spätere Abrechnung bleibt das OpenAI-Dashboard.

Die Standardausgabe eines längeren Laufs sieht sinngemäß so aus:

```text
[Prefill-Chunk 1/2] 3.693 Zeichen | 930 Input + 18.420 Audio-Output = 19.350 Tokens | berechnet 0,221598 USD
[Prefill-Chunk 2/2] 969 Zeichen | 255 Input + 4.810 Audio-Output = 5.065 Tokens | berechnet 0,057873 USD

=== API-VERBRAUCH DIESES LAUFS ===
Abgeschlossene TTS-Aufrufe: 2
Input-Tokens: 1.185
Audio-Output-Tokens: 23.230
Gesamttokens: 24.415
Berechnete Kosten: 0,000711 USD Input + 0,278760 USD Audio = 0,279471 USD
```

Die Zahlen im Beispiel dienen nur zur Erläuterung des Formats. Ein realer Lauf zeigt die Werte seiner eigenen API-Responses. Auch eine in demselben Lauf neu erzeugte Prefill-Kalibrierung wird als eigener kostenpflichtiger Aufruf erfasst. Bricht ein späterer Verarbeitungsschritt ab, wird die Summe der bis dahin erfolgreich abgeschlossenen API-Aufrufe trotzdem angezeigt.

Alle Befehle unterstützen ein konsistentes Logging. Standardmäßig wird `INFO` auf der Konsole ausgegeben. Ein zusätzliches UTF-8-Logfile lässt sich beispielsweise so schreiben:

```powershell
uv run markdown-tts synthesize-prefill `
  input.md output\audio.mp3 `
  --profile coaching `
  --keep-chunks `
  --log-level INFO `
  --log-file output\audio.log
```

`--log-level` akzeptiert `DEBUG`, `INFO`, `WARNING` oder `ERROR`. Fremdbibliotheken wie OpenAI und HTTPX bleiben auch bei detailliertem Projektlogging auf `WARNING`, damit insbesondere keine vertraulichen Requestdaten in das Log gelangen. `--no-progress` unterdrückt die formatierte Fortschritts- und Kostenausgabe; für eine ruhige Konsole kann es mit `--log-level WARNING` kombiniert werden.

Technische Grundlage: [OpenAI Speech API mit SSE-Streamformat](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create) und [GPT-4o Mini TTS Preise](https://developers.openai.com/api/docs/models/gpt-4o-mini-tts).

## Lange Dokumente über MP3-Chunks erzeugen

Zuerst immer die kostenfreie Chunk-Vorschau prüfen. Anschließend erzeugt der
folgende Befehl pro Chunk einen kostenpflichtigen TTS-Aufruf und fügt die Ergebnisse
ohne erneute Kodierung zur angegebenen MP3 zusammen:

```powershell
uv run markdown-tts synthesize-chunks `
  2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.md `
  output\ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.mp3
```

Während des Laufs heißen die Chunk-Dateien beispielsweise:

```text
2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.part-001.mp3
2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.part-002.mp3
```

Das Chunk-Verzeichnis hat denselben Stamm wie die Ausgabedatei, jedoch ohne
`.mp3`. Vor dem ersten API-Aufruf werden die Zielnamen auf bestehende Dateien
geprüft. Bei einem Provider- oder Mergefehler bleibt das Verzeichnis mitsamt den
bereits erzeugten Diagnoseartefakten bestehen. Nach einem vollständigen Erfolg wird
es entfernt, sofern nicht `--keep-chunks` angegeben wurde.

## Nummerierte MP3-Dateien zusammenführen

Für die Zusammenführung müssen `ffmpeg` und `ffprobe` installiert und über `PATH` erreichbar sein. Der folgende lokale Schritt verursacht keinen OpenAI-API-Aufruf:

```powershell
uv run markdown-tts merge output\2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.mp3 `
  output\chunks\2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.part-001.mp3 `
  output\chunks\2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.part-002.mp3
```

Die Reihenfolge der Eingabepfade bestimmt die Abspielreihenfolge. Der Audio Joiner prüft vorab Codec, Abtastrate und Kanalzahl aller Dateien. Er führt kompatible Streams mit FFmpeg `-c copy` zusammen, prüft anschließend Streamparameter und Gesamtdauer und veröffentlicht die Zieldatei erst danach atomar. Eine vorhandene Zieldatei wird nur mit dem ausdrücklich gesetzten Schalter `--overwrite` ersetzt. Die Einstellungen stehen in `config/audio_joiner.json`.

## Kurzes Markdown als MP3 erzeugen

Die Provider-Konfiguration erwartet standardmäßig deine Windows-Umgebungsvariable `GPT-4o-Mini-TTS-Key`. Der Schlüssel selbst wird weder in einer Datei gespeichert noch geloggt.

Zuerst immer die kostenfreie Sprachvorschau prüfen:

```powershell
uv run markdown-tts preview tests\corpus\tc_007_v1.md --show-cues
```

Danach kann bewusst ein kostenpflichtiger OpenAI-Aufruf gestartet werden:

```powershell
uv run markdown-tts synthesize tests\corpus\tc_007_v1.md output\tc_007.mp3
```

Der Zielpfad kann weggelassen werden. Dann entsteht
`tests\corpus\tc_007_v1.mp3`:

```powershell
uv run markdown-tts synthesize tests\corpus\tc_007_v1.md
```

Eine vorhandene Datei wird standardmäßig nicht überschrieben. Falls das ausdrücklich gewünscht ist:

```powershell
uv run markdown-tts synthesize tests\corpus\tc_007_v1.md output\tc_007.mp3 --overwrite
```

Der Befehl `synthesize` sendet weiterhin genau einen Request und eignet sich nur
für Dokumente, die laut Chunk-Vorschau einen Chunk ergeben. Für längere Dokumente
erzeugt `synthesize-chunks` automatisch alle Chunks und fügt sie zu einer fertigen
MP3 zusammen:

```powershell
uv run markdown-tts synthesize-chunks input.md
```

Vor einem `synthesize`-Provideraufruf wird der gerenderte Sprechtext gegen
`max_characters` aus `config/chunking.json` geprüft. Bei Überschreitung nennt die
CLI tatsächliche Zeichenzahl und Limit und verweist auf `synthesize-chunks` sowie
`synthesize-prefill`. OpenAI-API- und SSE-Fehler zeigen außerdem die konkrete kurze
Provider-Meldung an; vollständige Response-Bodies und Request-Inhalte werden nicht
ausgegeben.

Ohne expliziten Zielpfad entsteht `input.mp3`. Während des Laufs liegen die
nummerierten MP3-Chunks im Verzeichnis `input`. Erst nach einer erfolgreichen
Zusammenführung wird dieses Verzeichnis entfernt. Bei einem Fehler oder mit
`--keep-chunks` bleibt es für Diagnose beziehungsweise Hörtests erhalten. Auch
`--append-profile-name` wird unterstützt; beispielsweise entstehen dann
`input_podcast.mp3` und vorübergehend das Verzeichnis `input_podcast`.

## Tests

```powershell
uv run python -m unittest discover -s tests -v
```

Die Tests verwenden einen lokalen Fake-Provider und verursachen keinen API-Verbrauch.

---

# Qualitätsprinzipien

Das Projekt orientiert sich an folgenden Grundsätzen:

- Qualität vor Geschwindigkeit
- Lesbarkeit vor Komplexität
- Semantik vor Regex
- Konfiguration vor Hardcoding
- Wiederverwendbarkeit vor Speziallösungen
- Dokumentation ist Teil des Projekts

---

# Entwicklung

Neue Funktionen werden grundsätzlich in dieser Reihenfolge entwickelt:

1. Architektur prüfen
2. Implementieren
3. Testen
4. Dokumentation aktualisieren
5. Erkenntnisse dokumentieren

---

# Langfristige Roadmap

Geplante Erweiterungen:

- DOCX
- PDF
- HTML
- EPUB
- Notion Export
- Obsidian Vault
- REST API
- Docker
- Node.js-Portierung

---

# Ziel

Das langfristige Ziel des Projekts besteht darin, eine universelle Engine zur Umwandlung strukturierter Dokumente in hochwertige Sprachaufnahmen bereitzustellen.

Markdown ist lediglich das erste unterstützte Eingabeformat.

---

# Lizenz

Noch festzulegen.

---

# Status

🚧 In Entwicklung

Erste Version basiert auf Python.

Eine spätere Integration in einen bestehenden Node.js-Server ist ausdrücklich vorgesehen.
