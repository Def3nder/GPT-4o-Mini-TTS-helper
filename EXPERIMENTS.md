# EXPERIMENTS.md

Dieses Dokument enthält alle Experimente rund um Sprachqualität, Performance und Architektur.

Ziel ist es, Entscheidungen datenbasiert zu treffen und erfolgreiche Ergebnisse reproduzierbar zu machen.

---

# Status

| ID | Thema | Status |
|----|--------|--------|
| EXP-001 | Optimale Chunkgröße | geplant |
| EXP-002 | Beste Stimme | geplant |
| EXP-003 | Wirkung von Instructions | geplant |
| EXP-004 | Einfluss von Markdown | geplant |
| EXP-010 | Audio Joining / Übergangshörtest | hörbare Grenze beobachtet, Prefill-Variante implementiert |

---

# Vorlage

## Experiment-ID

EXP-000

### Ziel

Welche Frage soll beantwortet werden?

### Hypothese

Was erwarten wir?

### Testaufbau

Welche Parameter werden verändert?

Welche bleiben gleich?

### Testdaten

Welcher Artikel?

Wie viele Wörter?

Wie viele Zeichen?

### Bewertungsmethode

Subjektiv

1–10

oder

AB-Vergleich

### Ergebnis

...

### Erkenntnis

...

### Entscheidung

...

---

# EXP-001

## Optimale Chunkgröße

Status

Geplant

### Fragestellung

Welche Chunkgröße erzeugt die natürlichste Prosodie?

### Zu testen

- 1500 Zeichen
- 2500 Zeichen
- 3200 Zeichen
- 3800 Zeichen

### Bewertung

- Natürlichkeit
- Satzfluss
- Betonung
- Übergänge

Die Zeichenwerte bleiben unter dem technischen Request-Limit. Sie sind Qualitätsvarianten und noch keine bestätigte optimale Chunkgröße.

---

# EXP-002

## Beste Stimme

Status

Geplant

### Stimmen

- cedar
- marin
- ash
- sage
- coral
- verse

### Bewertung

- Wärme
- Natürlichkeit
- Coaching-Eindruck
- Hörbuch-Eindruck
- Langzeithören

---

# EXP-003

## Wirkung von Instructions

Fragestellung

Wie stark beeinflussen Instructions die Prosodie?

### Varianten

A

keine Instructions

B

nur

"Speak slowly."

C

vollständiges Coaching-Profil

D

Podcast-Profil

### Bewertung

- Natürlichkeit
- Betonung
- Emotion
- Pausen

### Beobachtung 2026-09-01

Das aktuelle globale Coaching-Profil erzeugte in einem ersten Hörtest einen verständlichen, aber recht monotonen Sprechstil. Diese Einzelbeobachtung wird später durch einen reproduzierbaren AB-Vergleich mit unterschiedlichen globalen Profilformulierungen geprüft.

### Konfigurierte Hörtestprofile

- `coaching-level1-m`: `echo`; `coaching-level1-w`: `nova`; Geschwindigkeit 1,00; tiefenentspannt und sanft
- `coaching-level2-m`: `cedar`; `coaching-level2-w`: `marin`; Geschwindigkeit 1,00; klar und empathisch
- `coaching-level3-m`: `onyx`; `coaching-level3-w`: `marin`; Geschwindigkeit 1,00; motivierend und aktivierend
- `coaching-level4-m`: `onyx`; `coaching-level4-w`: `shimmer`; Geschwindigkeit 1,00; enthusiastisch und inspirierend

Die Profile sind technisch konfiguriert. Ihre subjektive Wirkung und insbesondere die in den Instructions gewünschten Pausen werden erst durch einen reproduzierbaren Hörvergleich bewertet.

---

# EXP-004

## Fett

Status

Keine passagengenaue TTS-Steuerung vorgesehen

Fragestellung

Ist die intern erhaltene `strong`-Semantik später für Chunking oder andere Provider nützlich?

Varianten

A

Semantik nur im AST erhalten

B

Semantik zusätzlich für Chunking verwenden

Bewertung

AB-Vergleich

---

# EXP-005

## Kursiv

Status

Keine passagengenaue TTS-Steuerung vorgesehen

Fragestellung

Ist die intern erhaltene `emphasis`-Semantik später für Chunking oder andere Provider nützlich?

Varianten

- Semantik nur im AST erhalten
- Semantik zusätzlich für Chunking verwenden

---

# EXP-006

## Überschriften

Fragestellung

Welche Pause wirkt natürlich?

Test

250 ms

500 ms

750 ms

1000 ms

1500 ms

---

# EXP-007

## Absatzpausen

Welche Pause klingt angenehm?

- 300 ms
- 500 ms
- 700 ms
- 900 ms

---

# EXP-008

## Kapitelpausen

Test

- 1 s
- 1,5 s
- 2 s
- 3 s

---

# EXP-009

## Geschwindigkeit

Welche Geschwindigkeit wirkt für Coaching-Texte am angenehmsten?

Test

0.75

0.80

0.85

0.90

0.95

1.00

---

# EXP-010

## Audio Joining

Status

Hörbare Request-Anfänge beobachtet; kalibrierter WAV-Prefill technisch implementiert, AB-Hörvergleich ausstehend

Fragestellung

Sind Übergänge zwischen zwei Chunks hörbar?

Varianten

A

hart schneiden

B

50 ms Fade

C

100 ms Fade

D

200 ms Fade

E

Identischer Vorspannsatz pro Chunk, Schnitt in der Mitte einer energiearmen WAV-Passage nahe der kalibrierten Vorspanndauer, danach einmalige finale MP3-Kodierung

### Beobachtung 2026-09-01

Der Anfang jeder einzelnen Synthese klingt im Hörtest etwas anders als ihr restlicher Verlauf. Bei hart zusammengefügten Dateien macht diese kurze Einschwingphase die Chunk-Grenzen hörbar. Dasselbe Verhalten wurde bereits in einem anderen TTS-Projekt beobachtet.

Der erste reale Kalibrierungsversuch legte einen OpenAI-Streaming-WAV-Header mit der Platzhalterlänge `0xFFFFFFFF` offen. Dadurch wurde zuvor fälschlich eine Dauer von rund 24,9 Stunden berechnet und das Suchfenster verfehlt. Die Implementierung bestimmt bei solchen Headern nun die tatsächlich lesbare PCM-Länge, normalisiert die Kalibrierungs-WAV und bewahrt sie neben den JSON-Messwerten auf. Dieser Fehlerpfad ist synthetisch regressionstestet. Zu prüfen bleibt, ob reale OpenAI-WAV-Chunks nach dem Entfernen des identischen Vorspanns subjektiv unauffälliger ineinander übergehen.

Für diesen Hörvergleich kann `synthesize-prefill --keep-chunks` die originalen `raw-*.wav`, die geschnittenen `trimmed-*.wav` und die daraus erzeugte `combined.wav` desselben Laufs gemeinsam aufbewahren. Dadurch lassen sich Einschwingphase, Schnittwirkung und Übergang ohne erneuten API-Aufruf direkt vergleichen.

---

# EXP-011

## Satztrennung

Fragestellung

Wo dürfen lange Sätze getrennt werden?

Test

- Punkt
- Semikolon
- Doppelpunkt
- Gedankenstrich
- Komma

---

# EXP-012

## Hörtest

Ziel

Nicht technische Qualität bewerten.

Sondern:

"Vergisst der Hörer nach wenigen Minuten, dass er einer KI zuhört?"

Bewertung

1

Roboter

↓

10

Professionelles Hörbuch

---

# Erkenntnisse

Hier werden später ausschließlich bestätigte Ergebnisse eingetragen.

Beispiel:

✓ Chunkgröße 900–1200 Wörter liefert die beste Prosodie.

✓ Geschwindigkeit 0.85 eignet sich besonders für Coaching-Texte.

✓ Überschriften wirken mit ca. 1 Sekunde Pause natürlicher.

✓ Kapitel niemals mitten im Absatz beginnen.

Nur Erkenntnisse, die mehrfach reproduziert wurden, werden hier übernommen.
