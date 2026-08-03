import re

# =============================================================================
# 1. EINSTELLUNGEN
# =============================================================================

# Erkennt beispielsweise:
# MIT2X1
# MIT1X407
# MIT2X5300a
#
# Falls die Raumnummern später anders aufgebaut sind, muss nur dieses Muster
# angepasst werden.
ROOM_RE = re.compile(r"\bMIT\d+[A-Z]\d+[a-z]?\b")

# Wie viele Zeilen zwischen einer Zuluft- und Abluftzeile liegen dürfen.
MAX_AIRFLOW_DISTANCE = 3

# Wie viele Zeilen vor und nach einer Luftmengenangabe nach einer Raumnummer
# gesucht werden.
ROOM_SEARCH_RADIUS = 4

EXCEL_STATUS_COLORS = {
    "OK": "D9E1F2",
    "Abweichung Luftmenge": "F4CCCC",
    "Abweichung Raumname": "FCE5CD",
    "Nur im Grundriss": "D9EAD3",
    "Nur im Schema": "D9D2E9",
    "Mehrfach / uneindeutig": "FFF2CC",
}

PDF_STATUS_COLORS = {
    "OK": (0.50, 0.50, 0.50),
    "Abweichung Luftmenge": (1.00, 0.00, 0.00),
    "Abweichung Raumname": (1.00, 0.50, 0.00),
    "Nur im Grundriss": (0.00, 0.65, 0.00),
    "Nur im Schema": (0.60, 0.20, 0.80),
    "Mehrfach / uneindeutig": (0.85, 0.65, 0.00),
}
