# TEST_CORPUS.md

Dieses Dokument definiert den offiziellen Testkorpus des Projekts.

Alle Änderungen am Parser, Renderer oder an den Sprachprofilen werden ausschließlich anhand dieses Korpus bewertet.

Dadurch bleiben Testergebnisse über Monate vergleichbar.

---

# Grundregeln

- Testtexte werden niemals verändert.
- Jeder Test erhält eine eindeutige ID.
- Änderungen an einem Testtext erzeugen eine neue Version.
- Alle Audiovergleiche erfolgen mit identischen Testtexten.

---

# Bewertungskriterien

## Natürlichkeit

Wie menschlich klingt die Ausgabe?

Bewertung:

1–10

---

## Verständlichkeit

Sind alle Sätze leicht verständlich?

Bewertung:

1–10

---

## Hörfluss

Wirken Übergänge angenehm?

Bewertung:

1–10

---

## Betonung

Werden wichtige Aussagen sinnvoll hervorgehoben?

Bewertung:

1–10

---

## Emotion

Passt die emotionale Wirkung zum Text?

Bewertung:

1–10

---

# TC-001

## Name

Kurzer Coachingartikel

## Zweck

Standardtest

## Eigenschaften

- ca. 500 Wörter
- Überschriften
- Absätze
- Fett
- Kursiv

Prüft:

- Parser
- Renderer
- Standardprofil

---

# TC-002

## Name

Langer Coachingartikel

## Zweck

Chunking

## Eigenschaften

- 2500–5000 Wörter
- mehrere Kapitel
- lange Sätze

Prüft:

- Chunking
- MP3-Zusammenführung
- Übergänge
- Prefill-Kalibrierung und Vorspannschnitt

---

# TC-003

## Name

Sehr lange Sätze

## Zweck

Prosodie

Eigenschaften

- Nebensätze
- Gedankenstriche
- Semikolon
- Doppelpunkt

Prüft

- Satztrennung
- Sprachfluss

---

# TC-004

## Name

Viele Listen

## Zweck

Listenverarbeitung

Eigenschaften

- Bullet Lists
- Nummerierungen
- Mehrere Ebenen

Prüft

- Pausen
- Rhythmus

---

# TC-005

## Name

Dialog

## Zweck

Wörtliche Rede

Eigenschaften

- viele Zitate
- Sprecherwechsel

Prüft

- Natürlichkeit
- Betonung

---

# TC-006

## Name

Technischer Text

## Zweck

Neutralität

Eigenschaften

- Fachbegriffe
- Zahlen
- Abkürzungen
- URLs

Prüft

- Aussprache
- Bereinigung
- Lesbarkeit

---

# TC-007

## Name

Markdown-Stresstest

## Zweck

Parser

Enthält

- Überschriften
- Fett
- Kursiv
- Tabellen
- Inline-Code
- Codeblöcke
- Blockquotes
- HTML
- YAML Frontmatter
- Bilder
- Links
- Fußnoten

Prüft

- Vollständigkeit des Parsers

Referenzdatei:

- `tests/corpus/tc_007_v1.md`

Version:

- 1 (unveränderlich; Änderungen erfordern `tc_007_v2.md`)

---

# TC-008

## Name

Joe-Turan-Referenz

## Zweck

Hauptreferenz

Eigenschaften

- typische Coachingtexte
- lange Absätze
- emotionale Sprache
- viele Gedankenstriche
- Hervorhebungen
- Überschriften

Diese Referenz dient als primärer Qualitätstest des gesamten Systems.

Alle Änderungen werden zuerst an diesem Text bewertet.

Referenzdatei:

- `2026-08-29_ein-mann-muss-lernen-sexuell-gefaehrlich-zu-werden.md`

---

# Testprotokoll

Für jede neue Version wird dokumentiert:

Version:

Datum:

OpenAI-Modell:

Stimme:

Profil:

Geschwindigkeit:

Chunkgröße:

Renderer-Version:

Parser-Version:

Gesamtbewertung:

Natürlichkeit:

Verständlichkeit:

Hörfluss:

Bemerkungen:

---

# Ziel

Das Projekt gilt langfristig als erfolgreich, wenn unabhängige Hörer die erzeugten Sprachaufnahmen überwiegend als professionell produziert und angenehm hörbar bewerten.

Nicht maximale Geschwindigkeit, sondern reproduzierbare Qualität ist das oberste Entwicklungsziel.
