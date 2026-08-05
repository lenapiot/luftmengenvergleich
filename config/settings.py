from __future__ import annotations
import re

# =============================================================================
# 1. RAUMNUMMERNFORMATE
# =============================================================================
ROOM_PATTERN_PRESETS = {
   "usz_standard": {
       "label": "USZ-Standard",
       "description": (
           "Beispiele: MIT2X1, MIT1X407, MIT2X5300a"
       ),
       "pattern": r"\bMIT\d+[A-Z]\d+[a-z]?\b",
   },
   "letters_numbers": {
       "label": "Buchstaben + Nummer",
       "description": (
           "Beispiele: R203, LAB104, OP12"
       ),
       "pattern": r"\b[A-ZÄÖÜ]{1,6}\d+[a-z]?\b",
   },
   "letters_dash_numbers": {
       "label": "Buchstaben – Nummer",
       "description": (
           "Beispiele: A-101, LAB-204, OP-12a"
       ),
       "pattern": r"\b[A-ZÄÖÜ]{1,6}-\d+[a-z]?\b",
   },
   "letters_dot_numbers": {
       "label": "Buchstaben / Punkte / Nummern",
       "description": (
           "Beispiele: LAB.04.12, A.1.203"
       ),
       "pattern": (
           r"\b[A-ZÄÖÜ]{1,6}(?:\.\d+){1,3}[a-z]?\b"
       ),
   },
   "general_room_code": {
       "label": "Allgemeines Raumformat",
       "description": (
           "Erkennt viele häufige Formen wie "
           "R203, A-101, LAB.04.12"
       ),
       "pattern": (
           r"\b(?:"
           r"[A-ZÄÖÜ]{1,8}\d+[a-z]?"
           r"|"
           r"[A-ZÄÖÜ]{1,8}-\d+[a-z]?"
           r"|"
           r"[A-ZÄÖÜ]{1,8}(?:\.\d+){1,3}[a-z]?"
           r")\b"
       ),
   },
}

DEFAULT_ROOM_PATTERN_KEY = "usz_standard"

def get_room_pattern(
   preset_key: str = DEFAULT_ROOM_PATTERN_KEY,
   custom_pattern: str | None = None,
) -> re.Pattern[str]:
   """
   Erstellt das reguläre Ausdrucksmuster für Raumnummern.
   Bei custom_pattern wird das benutzerdefinierte Muster verwendet.
   Andernfalls wird ein vordefiniertes Format aus ROOM_PATTERN_PRESETS
   geladen.
   """
   if custom_pattern:
       try:
           return re.compile(
               custom_pattern,
               flags=re.IGNORECASE,
           )
       except re.error as error:
           raise ValueError(
               "Das benutzerdefinierte "
               "Raumnummernmuster ist ungültig: "
               f"{error}"
           ) from error
   if preset_key not in ROOM_PATTERN_PRESETS:
       raise ValueError(
           "Unbekanntes Raumnummernformat: "
           f"{preset_key}"
       )
   pattern = ROOM_PATTERN_PRESETS[
       preset_key
   ]["pattern"]
   return re.compile(
       pattern,
       flags=re.IGNORECASE,
   )

# Abwärtskompatibilität:
# Solange noch nicht alle Programmteile umgestellt sind,
# verwendet der bestehende Code weiterhin das USZ-Standardmuster.
ROOM_RE = get_room_pattern(
   DEFAULT_ROOM_PATTERN_KEY
)

# =============================================================================
# 2. EXTRAKTIONSEINSTELLUNGEN
# =============================================================================
# Wie viele Zeilen zwischen einer Zuluft- und Abluftzeile liegen dürfen.
MAX_AIRFLOW_DISTANCE = 3
# Wie viele Zeilen vor und nach einer Luftmengenangabe nach einer Raumnummer
# gesucht werden.
ROOM_SEARCH_RADIUS = 4

# =============================================================================
# 3. EXCEL-FARBEN
# =============================================================================
EXCEL_STATUS_COLORS = {
   "OK": "D9E1F2",
   "Abweichung Luftmenge": "F4CCCC",
   "Abweichung Raumname": "FCE5CD",
   "Nur im Grundriss": "D9EAD3",
   "Nur im Schema": "D9D2E9",
   "Mehrfach / uneindeutig": "FFF2CC",
}

# =============================================================================
# 4. PDF-FARBEN
# =============================================================================
PDF_STATUS_COLORS = {
   "OK": (0.50, 0.50, 0.50),
   "Abweichung Luftmenge": (1.00, 0.00, 0.00),
   "Abweichung Raumname": (1.00, 0.50, 0.00),
   "Nur im Grundriss": (0.00, 0.65, 0.00),
   "Nur im Schema": (0.60, 0.20, 0.80),
   "Mehrfach / uneindeutig": (0.85, 0.65, 0.00),
}
