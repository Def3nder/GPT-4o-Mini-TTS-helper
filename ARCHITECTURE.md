# Systemarchitektur

```text
Markdown-Datei

↓

UTF-8 Loader

↓

Markdown Parser

↓

sprachneutrales Dokument-AST

↓

Semantic Renderer

↓

Semantic Chunker

↓

Speech Renderer / globales Sprachprofil

↓

TTS Provider

↓

optionaler WAV Prefill Trimmer

↓

WAV Joiner oder MP3 Stream-Copy

↓

optionaler finaler FFmpeg Encoder

↓

MP3
```

## Implementierte Komponenten

- `loader.py`: Liest Eingaben strikt als UTF-8 und liefert verständliche Ladefehler.
- `parser.py`: Übersetzt Markdown semantisch in das AST und wendet konfigurierbare Nicht-Sprach-Filter an.
- `ast.py`: Provider- und renderunabhängiges Dokumentmodell aus Dataclasses.
- `config.py`: Lädt und validiert Parser-, Renderer-, Chunking-, Profil-, Provider-, Prefill-, Audio-Joiner- und Encoder-Konfigurationen aus JSON; die Provider-Konfiguration enthält außerdem datierte Tokenpreise und deren Quelle.
- `semantic_renderer.py`: Erzeugt sprechbare Blöcke und bewahrt Fett-/Kursiv-Spannen als providerunabhängige Metadaten.
- `chunker.py`: Teilt sprechbare Blöcke providerunabhängig an Struktur-, Satz- und Wortgrenzen und erhält dabei Blockarten sowie Semantik-Cues.
- `profiles.py`: Entdeckt JSON-Sprachprofile, prüft eindeutige Namen und löst Profilnamen oder explizite Dateipfade auf.
- `prefill.py`: Dekoriert Requests mit dem festen Vorspann und verwaltet per kanonischem Konfigurations-Fingerprint adressierte Kalibrierungspaare aus JSON-Metadaten und normalisierter WAV-Aufnahme.
- `speech_renderer.py`: Kombiniert den Sprechtext mit Stimme, Geschwindigkeit und globalen Profilanweisungen zu einer providerunabhängigen TTS-Anfrage. Lokale Semantik-Cues werden nicht als vermeintlich passagengenaue Provider-Anweisungen ausgegeben.
- `tts/base.py`: Definiert den austauschbaren TTS-Provider-Vertrag einschließlich optionaler, vom Provider gemeldeter Usage-Daten.
- `tts/openai_provider.py`: Kapselt OpenAI-SDK, API-Key, Retry, Speech-SSE-Decodierung, Usage-Extraktion sowie Profilparameter und atomare Audiodateiausgabe.
- `progress.py`: Definiert providerunabhängige Fortschrittsereignisse für abgeschlossene Syntheseschritte.
- `usage.py`: Aggregiert tatsächliche Speech-Usage und berechnet daraus Kosten anhand der geladenen Provider-Konfiguration.
- `audio/base.py`: Definiert den providerunabhängigen Vertrag und die Fehlerklassen für Audio-Zusammenführung.
- `audio/ffmpeg_joiner.py`: Prüft Audiodateien mit FFprobe, fügt kompatible Streams per FFmpeg Stream-Copy zusammen und validiert das Ergebnis vor der atomaren Veröffentlichung.
- `audio/prefill_trimmer.py`: Analysiert PCM-WAV-Fenster in dBFS und entfernt den Vorspann in der Mitte einer ausreichend langen energiearmen Passage nahe der kalibrierten Dauer.
- `audio/wav_joiner.py`: Fügt kompatible PCM-WAV-Dateien sampleerhaltend zusammen.
- `audio/encoder.py`: Kodiert das zusammengeführte WAV genau einmal mit FFmpeg und prüft Codec sowie Dauer vor der Veröffentlichung.
- `audio/wav_support.py`: Stellt gemeinsame validierte WAV-Parameter bereit, zählt bei Streaming-Platzhalterheadern tatsächlich lesbare PCM-Frames und konfiguriert WAV-Writer ohne ungeprüfte Framezahl.
- `audio/factory.py`: Erzeugt den konfigurierten Audio Joiner, ohne die CLI an FFmpeg zu koppeln.
- `application.py`: Orchestriert Single-Chunk-Konvertierung sowie die transaktionale Erzeugung nummerierter Multi-Chunk-Audiodateien und emittiert Fortschrittsereignisse nach erfolgreich abgeschlossenen Provideraufrufen.
- `cli.py`: Dünne Oberfläche für Vorschau, Synthese und Audio-Zusammenführung; formatiert Fortschritt, Usage, berechnete Kosten und Logging, enthält aber keine Synthese- oder Preisberechnungslogik.

Die CLI kann Sprachprofile auflisten und anzeigen, Chunk-Grenzen kostenfrei visualisieren, nummerierte Chunk-Audiodateien erzeugen und diese anschließend lokal zusammenführen. Die Batch-Ausgabe wird erst veröffentlicht, nachdem alle Provideraufrufe erfolgreich waren. Der getrennte Audio Joiner arbeitet ausschließlich auf fertigen Dateien und kennt weder Markdown noch TTS-Provider.

Der Prefill-Qualitätsmodus ist ein eigener Anwendungspfad. Der Semantic Chunker reserviert providerunabhängig die exakte Länge des später ergänzten Vorspanns. Ein kanonischer SHA-256-Fingerprint umfasst Vorspann und Trenner, Profilname, Stimme, Geschwindigkeit, bereinigte Instructions, Provider, Modell und WAV-Format. Die Anwendung lädt das dazugehörige Paar aus JSON-Messwerten und normalisierter Kalibrierungs-WAV aus dem Cache oder erzeugt es bei einem Cache-Miss automatisch; `--refresh-calibration` erzwingt die Neuerzeugung. Andere Fingerprints und damit ältere Kalibrierungen bleiben bestehen. Quell- und Zielpfad sowie die sprechbaren Chunks werden vor einem möglichen Kalibrierungsaufruf validiert. Erst die validierte, einmalig kodierte MP3 wird als Endergebnis veröffentlicht. Arbeitsartefakte werden nach Erfolg standardmäßig entfernt. Für Hörtests kann die Anwendungsschicht sie mit `--keep-chunks` bewusst erhalten und ihren eindeutigen Pfad zurückgeben. Bei einem Fehler bleiben sie unabhängig davon in einem protokollierten Diagnoseordner neben dem Ziel bestehen.

Beim MP3-Merge werden keine Audiodaten neu kodiert. FFprobe muss für alle Eingaben denselben Codec, dieselbe Abtastrate und dieselbe Kanalzahl melden. FFmpeg verarbeitet danach eine geordnete Concat-Liste mit `-c copy`. Die temporäre Ausgabe wird erneut geprüft; nur bei passenden Streamparametern und einer Gesamtdauer innerhalb der konfigurierten Toleranz wird sie an den endgültigen Zielpfad verschoben.

OpenAI TTS erhält pro Request Stimme, Geschwindigkeit und ein globales `instructions`-Feld aus dem ausgewählten Profil. Die Kernarchitektur setzt deshalb keine passagengenaue Stimmsteuerung voraus. Für die Verständlichkeit werden vor allem Dokumentbereinigung, sprachliche Listenmarker, sinnvolle Blockgrenzen und globale Sprechweise verwendet.

Für `gpt-4o-mini-tts` verwendet der OpenAI-Provider das dokumentierte SSE-Streamformat. `speech.audio.delta` wird Base64-dekodiert und wie zuvor zunächst atomar in eine Arbeitsdatei geschrieben. Erst ein gültiges `speech.audio.done` mit Usage-Daten schließt den Provideraufruf erfolgreich ab. Die Anwendungsschicht erhält danach ein providerunabhängiges Fortschrittsereignis. Tokenaggregation und Kostenrechnung bleiben getrennt: Tokens stammen aus der Response, Preise aus der datierten JSON-Konfiguration, und der Geldbetrag wird ausdrücklich nur berechnet.
