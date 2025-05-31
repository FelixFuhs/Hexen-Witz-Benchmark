# Schwerhörige-Hexe Judge-Checkliste (0-100 Punkte)

Bewerte folgendes Wortspiel-Paar nach dieser detaillierten Checkliste:

**WUNSCH:** [aus der Antwort extrahiert]  
**ERGEBNIS:** [aus der Antwort extrahiert]

*Optional: Übersetze beide in IPA zur Hilfe bei der phonetischen Bewertung.*

## Bewertungskriterien (Total: 100 Punkte)

### 1. Phonetische Ähnlichkeit (0-35 Punkte) ⭐ WICHTIGSTE KATEGORIE
**Dies ist der KERN des Witzes - ohne phonetische Verwechslung funktioniert er nicht!**

- **0-5 Punkte:** Keine oder fast keine phonetische Ähnlichkeit
  - Beispiel SCHLECHT: "reich und berühmt" → "tauch und Stör"
  - Beispiel SCHLECHT: Rein wörtliche Interpretation ohne Klangähnlichkeit
- **10-15 Punkte:** Schwache Ähnlichkeit, nur einzelne Laute stimmen überein
  - Beispiel: "Titten" → "Tipps" (nur T und Endkonsonant ähnlich)
- **20-25 Punkte:** Deutliche Ähnlichkeit, mehrere Silben klingen ähnlich
  - Beispiel GUT: "heiße" → "weiße" 
  - Beispiel GUT: "Yacht" → "Achte"
- **30-35 Punkte:** Sehr hohe Ähnlichkeit, fast identisch klingend
  - Beispiel EXZELLENT: "Pimmel" → "Schimmel"
  - Beispiel EXZELLENT: "Millionen in kleinen Scheinen" → "Melonen mit kleinen Schweinen"

### 2. Anzüglichkeit (0-25 Punkte)
**Der Original-Witz lebt von sexuellen/körperlichen Anspielungen!**

- **0 Punkte:** Keine Anzüglichkeit (z.B. "reich werden", "Auto haben")
- **5-10 Punkte:** Leicht angedeutet oder doppeldeutig
  - Beispiel: "schlanke Crew" (kann anzüglich gemeint sein)
- **15-20 Punkte:** Deutlich anzüglich aber noch subtil
  - Beispiel: "heiße Schnitte", "steifer Drink"
- **25 Punkte:** Explizit sexuell/körperlich wie die Originale
  - Beispiel: "30cm langer Pimmel", "dicke Titten"

### 3. Logik des Ergebnisses (0-20 Punkte)
**Das erhaltene Objekt muss real existieren und Sinn ergeben!**

- **0 Punkte:** Völlig unlogisch oder nicht existent
  - Beispiel SCHLECHT: "Scheibe Kraut", "Achte mit blanker Kuh"
- **5-10 Punkte:** Existiert, aber Verbindung ist sehr gezwungen
  - Beispiel: Anker für "Achterknoten" 
- **15-20 Punkte:** Klares, reales Objekt mit logischer Verbindung
  - Beispiel GUT: "Portion Cayenne-Pfeffer"
  - Beispiel GUT: "weißes Pferd (Schimmel)"

### 4. Kreativität & Originalität (0-20 Punkte)
**Wie clever und überraschend ist die Verwechslung?**

- **0-5 Punkte:** Keine echte Verwechslung oder nur Wortvariation
  - ABZUG wenn dasselbe Wort benutzt wird (Cayenne→Cayenne: -5)
  - ABZUG für Singular/Plural (Schnitte→Schnitten: -5)
- **10-15 Punkte:** Solide Verwechslung, aber vorhersehbar
- **20 Punkte:** Besonders clevere, überraschende Lösung
  - Bonus für mehrschichtige Wortspiele

## BEWERTUNG OUTPUT

```json
{
  "phonetische_aehnlichkeit": X,
  "anzueglichkeit": X,
  "logik": X,
  "kreativitaet": X,
  "gesamt": X,
  "begruendung": {
    "phonetisch": "...",
    "anzueglich": "...",
    "logik": "...",
    "kreativ": "..."
  }
}
```

## KRITISCHE FEHLER (Automatisch 0-30 Punkte Gesamt)
- Keine phonetische Verwechslung → Aufgabe nicht verstanden
- Andere Witz-Mechanik verwendet (z.B. wörtliche Interpretation)
- Wunsch und Ergebnis haben keinen Klangbezug