# Luftmengenvergleich
## Zweck
Dieses Python-Programm vergleicht automatisch die Luftmengenangaben eines Grundrissplans mit einem oder mehreren Lüftungs-Prinzipschemata.
Dabei werden aus allen ausgewählten PDFs automatisch
- Raumnummer
- Raumname
- Zuluft
- Abluft
extrahiert, zusammengeführt und miteinander verglichen.
Das Programm erstellt anschließend
- eine formatierte Excel-Auswertung,
- einen markierten Grundriss als PDF,
- Übersichten aller Abweichungen,
- Listen der Räume, die nur in einem Dokument vorkommen,
- ein Protokoll aller PDF-Markierungen.
---
# Funktionen
Version 0.2 unterstützt unter anderem:
- Vergleich eines Grundrisses mit beliebig vielen Prinzipschemata
- Zusammenführung aller ausgewählten Schemata zu einer gemeinsamen Vergleichsbasis
- Vergleich von
 - Raumnummer
 - Raumname
 - Zuluft
 - Abluft
- farbige Excel-Auswertung
- automatische PDF-Markierung
- Übersicht aller verwendeten Prinzipschemata
- Rohdatenexport aller gefundenen Räume
---
# Voraussetzungen
- Windows 10 oder Windows 11
- Python 3.10 oder neuer
- digital erzeugte PDFs mit vorhandener Textebene
- ähnlich aufgebaute Grundriss- und Lüftungspläne
---
# Installation
Projektordner öffnen und anschließend:
```powershell
python -m pip install -r requirements.txt
```
---
# Programm starten
```powershell
python luftmengen_vergleich.py
```
Anschließend erscheinen nacheinander drei Auswahlfenster.
## 1. Grundriss auswählen
Den Grundriss bzw. Flächenplan auswählen.
Der Grundriss enthält typischerweise Einträge wie
```
MIT2X1
ZUL: 4'000 m³/h
ABL: 4'450 m³/h
```
---
## 2. Prinzipschemata auswählen
Nun können **beliebig viele Lüftungs-Prinzipschemata gleichzeitig ausgewählt werden.**
Alle ausgewählten PDFs werden automatisch eingelesen und gemeinsam mit dem Grundriss verglichen.
Ein Prinzipschema enthält typischerweise
```
Parkplätze gedeckt
MIT2X1
Zuluft 4'000 m³/h
Abluft 4'450 m³/h
```
---
## 3. Ausgabeordner auswählen
Hier wird der Ordner gewählt, in dem sämtliche Ergebnisse gespeichert werden.
---
# Ausgabedateien
Das Programm erzeugt automatisch
```
<Name>_Luftmengenvergleich.xlsx
<Name>_markiert.pdf
```
---
# Aufbau der Excel-Datei
Die Excel-Datei enthält folgende Tabellen:
- Legende
- Grundriss_Rohdaten
- Schema_Rohdaten
- Vergleich
- Abweichungen
- Nur_im_Grundriss
- Nur_im_Schema
- PDF_Markierungen
---
# Statuswerte
## OK
Raum wurde in Grundriss und Schema gefunden.
Raumname sowie Luftmengen stimmen überein.
---
## Abweichung Luftmenge
Zuluft und/oder Abluft unterscheiden sich.
---
## Abweichung Raumname
Luftmengen stimmen überein, der Raumname jedoch nicht.
---
## Nur im Grundriss
Der Raum wurde ausschließlich im Grundriss gefunden.
---
## Nur im Schema
Der Raum wurde ausschließlich in den ausgewählten Prinzipschemata gefunden.
---
## Mehrfach / uneindeutig
Für dieselbe Raumnummer wurden widersprüchliche Angaben gefunden.
---
# Unterstützte Dokumentstruktur
## Grundriss
```
MIT2X1
ZUL: 4'000 m³/h
ABL: 4'450 m³/h
```
## Prinzipschema
```
Parkplätze gedeckt
MIT2X1
Zuluft 4'000 m³/h
Abluft 4'450 m³/h
```
---
# Hinweise
Das Programm arbeitet zuverlässig bei
- digital erzeugten PDFs
- ähnlicher Dokumentstruktur
- vorhandener Textebene
Die Ergebnisse müssen anschließend fachlich kontrolliert werden.
---
# Bekannte Einschränkungen
- Eingescannte PDFs ohne Textebene werden nicht unterstützt.
- Die Raumnummern müssen dem hinterlegten Muster entsprechen.
- Sehr stark abweichende Planlayouts können Anpassungen der Extraktionslogik erfordern.
- Das Programm ersetzt keine technische Endkontrolle.
---
# Fehlerbehebung
## ModuleNotFoundError
```powershell
python -m pip install -r requirements.txt
```
---
## Keine Räume im Grundriss erkannt
Prüfen:
- wurde der richtige Grundriss gewählt?
- besitzt das PDF eine Textebene?
- enthält der Plan Einträge wie `ZUL:` und `ABL:`?
---
## Keine Räume im Schema erkannt
Prüfen:
- wurden die richtigen Prinzipschemata ausgewählt?
- besitzen die PDFs eine Textebene?
- enthalten sie Einträge wie `Zuluft` und `Abluft`?
---
## PDF-Markierung nicht eindeutig
Die betreffende Raumnummer kommt mehrfach im Grundriss vor.
Dieser Fall wird automatisch im Tabellenblatt
```
PDF_Markierungen
```
protokolliert.
---
# Projektstatus
**Version 0.2**
Der aktuelle Stand unterstützt den automatischen Vergleich eines Grundrisses mit beliebig vielen Lüftungs-Prinzipschemata.
Alle ausgewählten Schemata werden automatisch zusammengeführt und gemeinsam ausgewertet.
