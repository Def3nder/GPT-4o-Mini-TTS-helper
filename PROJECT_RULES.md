# PROJECT_RULES.md

Dieses Dokument definiert die verbindlichen Entwicklungsregeln des Projekts.

Alle Implementierungen sollen diesen Regeln folgen.

---

# Projektziel

Ziel ist nicht die schnellstmögliche Entwicklung.

Ziel ist eine hochwertige, wartbare und reproduzierbare TTS-Engine zur Erzeugung natürlicher Hörbücher, Podcasts und Coaching-Audios.

Qualität hat Vorrang vor Geschwindigkeit.

---

# Architektur

- Parser, Renderer und TTS sind strikt voneinander getrennt.
- Keine Geschäftslogik in der GUI.
- Keine Geschäftslogik im CLI.
- Jede Komponente besitzt genau eine Verantwortung.
- Provider (OpenAI, ElevenLabs usw.) müssen austauschbar sein.

---

# Konfiguration

Es werden keine Parameter im Code hart codiert.

Alle Einstellungen erfolgen über Konfigurationsdateien.

Beispiele:

- Stimmen
- Geschwindigkeit
- Chunkgrößen
- Sprachprofile
- Parser-Regeln

---

# Dokumentation

Neue Komponenten erhalten eine kurze Dokumentation.

Architekturentscheidungen werden in DECISIONS.md dokumentiert.

Neue Erkenntnisse kommen nach erfolgreicher Validierung in LESSONS-LEARNED.md.

Experimente werden ausschließlich in EXPERIMENTS.md dokumentiert.

---

# Codequalität

- Python 3.12+
- Type Hints für alle öffentlichen Funktionen
- Dataclasses verwenden, wenn sinnvoll
- Aussagekräftige Funktionsnamen
- Kleine, klar abgegrenzte Funktionen
- Keine doppelten Implementierungen

---

# Logging

Alle relevanten Verarbeitungsschritte werden geloggt.

Mindestens:

- Parser
- Chunking
- API-Aufrufe
- Audio-Zusammenführung
- Fehler

---

# Fehlerbehandlung

Das Programm soll niemals kommentarlos abbrechen.

Fehler müssen verständlich erklärt werden.

Möglichst konkrete Lösungsvorschläge anzeigen.

---

# Tests

Neue Parserfunktionen erhalten Unit-Tests.

Neue Renderer erhalten Referenztests.

Alle Änderungen werden gegen den definierten Testkorpus geprüft.

---

# Audioqualität

Die Audioqualität besitzt höchste Priorität.

Wenn zwei Lösungen möglich sind, wird die gewählt, die die bessere Hörqualität liefert.

---

# Erweiterbarkeit

Neue Eingabeformate sollen ohne Änderungen an der Kernarchitektur ergänzt werden können.

Geplante Formate:

- Markdown
- DOCX
- PDF
- HTML
- EPUB
- Notion Export
- Obsidian Vault

---

# Kompatibilität

Alle Kernkomponenten sollen später ohne grundlegende Änderungen nach Node.js portierbar sein.

Die Architektur ist daher möglichst sprachunabhängig zu halten.

---

# Entwicklung

Neue Features werden in kleinen, abgeschlossenen Schritten entwickelt.

Nach jedem Schritt:

1. Funktion testen
2. Dokumentation aktualisieren
3. Erkenntnisse dokumentieren
4. Erst danach folgt das nächste Feature

---

# Grundsatz

Der Quellcode soll auch nach einem Jahr ohne große Einarbeitung verständlich und wartbar sein.

Lesbarkeit ist wichtiger als möglichst kompakter Code.
