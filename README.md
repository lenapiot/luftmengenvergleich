# Planvergleich
Internes Prüf- und Vergleichstool für HLKS-Planunterlagen.
Das Programm bündelt drei Module in einer gemeinsamen Benutzeroberfläche:
1. **Lüftung – Luftmengenvergleich**
2. **Heizung/Kälte – Betriebsnummernkontrolle**
3. **Heizung/Kälte – Strangschema-Lastvergleich**
Ziel ist es, wiederkehrende Planprüfungen zu automatisieren, Abweichungen schneller sichtbar zu machen und die Ergebnisse strukturiert auszugeben.
---
## 1. Lüftung – Luftmengenvergleich
### Zweck
Vergleicht Luftmengen aus Lüftungsgrundrissen mit den Angaben aus den zugehörigen Prinzipschemata.
Geprüft werden insbesondere:
- Raumnummer
- Raumname
- Zuluft
- Abluft
- Betriebsart
- Vorkommen im Grundriss und im Schema
Mehrere Grundrisse und mehrere Schemata können gemeinsam verarbeitet werden.
### Besondere Funktionen
Das Modul unterstützt unterschiedliche Raumnummernformate sowie projektspezifische Suchmuster.
Für numerische Raumnummern steht der Modus:
```text
Numerisch - Geschoss.Raum
```
zur Verfügung, zum Beispiel:
```text
-01.227
00.302
01.514
```
Bei Projekten mit e+p-Luftmengenblöcken wird die ep-Nummer intern als eindeutiger Vergleichsschlüssel verwendet. Dadurch können auch mehrere Blöcke mit derselben verkürzten Raumnummer korrekt getrennt werden.
Beispiel:
```text
Raum: -1.21
ep: 228
```
und
```text
Raum: -1.21
ep: 229
```
werden als zwei unterschiedliche Einträge behandelt.
Die ursprünglichen architektonischen Raumbeschriftungen werden dabei nicht als zusätzliche Vergleichsräume gewertet.
Auch mehrere Betriebsarten innerhalb eines Blocks werden unterstützt, zum Beispiel:
```text
ZUL: Nominal 400 / Havarie 2300 m3/h
ABL: Nominal 400 / Havarie 2400 m3/h
```
Nominal- und Havariewerte werden separat verglichen.
### Ausgabe
Das Modul erstellt:
- eine Excel-Gesamtauswertung
- Grundriss- und Schema-Rohdaten
- eine Übersicht aller Vergleiche und Abweichungen
- Listen für «Nur im Grundriss» und «Nur im Schema»
- ein PDF-Markierungsprotokoll
- markierte Grundriss-PDFs
Mögliche Status sind unter anderem:
```text
OK
Abweichung Luftmenge
Abweichung Raumname
Mehrfach / uneindeutig
Nur im Grundriss
Nur im Schema
```
---
## 2. Heizung/Kälte – Betriebsnummernkontrolle
### Zweck
Vergleicht Betriebs- und Komponentenkennzeichnungen zwischen technischen Planunterlagen.
Das Modul hilft insbesondere dabei, fehlende oder zusätzliche Betriebsnummern sowie Unterschiede zwischen zwei Unterlagen schnell zu erkennen.
### Erkennung
Unterstützt werden verschiedene Nummerierungsformen, unter anderem:
```text
D12.3
AB12.3
AB12.3.1
STA12.4
ZV70.01
```
Die Erkennung unterstützt:
- Präfixe mit einem oder zwei Buchstaben
- `STA`
- ein- bis dreistellige Nummernteile
- einen oder zwei Punkte
- mehrere Betriebsnummern innerhalb einer Zeile
Für bestimmte Nummernserien werden führende Nullen berücksichtigt.
Beispiel:
```text
ZV70.01
ZV70.02
...
ZV70.12
```
Diese Nummern werden nicht fälschlicherweise zu `ZV70.1`, `ZV70.2` usw. gekürzt.
### Vergleich und Ausgabe
Nach der Extraktion werden die Nummern der ausgewählten Unterlagen gegenübergestellt.
Dabei wird sichtbar, welche Betriebsnummern:
- in beiden Unterlagen vorhanden sind
- nur in der ersten Unterlage vorhanden sind
- nur in der zweiten Unterlage vorhanden sind
- nicht eindeutig erkannt wurden
Die Auswertung dient als Grundlage für die gezielte manuelle Kontrolle der auffälligen Nummern.
---
## 3. Heizung/Kälte – Strangschema-Lastvergleich
### Zweck
Vergleicht Heiz- und Kühllasten aus Projektunterlagen mit den entsprechenden Angaben im Strangschema.
Das Modul ist insbesondere für Projekte mit mehreren Ebenen und mehreren Lastdateien ausgelegt.
### Eingaben
Verarbeitet werden:
- ein Strangschema
- eine oder mehrere Heizlastdateien
- eine oder mehrere Kühllastdateien
Für grössere Projekte kann auch ein kompletter Ordner mit Lastdateien ausgewählt werden.
### Vergleichslogik
Die erkannten Heiz- und Kühllasten werden den passenden Einträgen im Strangschema zugeordnet und miteinander verglichen.
Unterstützt werden:
- Heizlasten
- Kühllasten
- MIT1
- MIT2
- gemischte MIT1/MIT2-Fälle
- mehrere Dateien
- Ebenenfilter
Nur die ausgewählten Ebenen werden geprüft. Einträge anderer Ebenen werden nicht automatisch als Fehler gewertet.
### 0-W-Sonderfälle
Bestimmte Angaben werden als bewusst geprüfte Nullwerte interpretiert:
```text
Heizlast -1 -> 0 W
Kühllast +1 -> 0 W
```
Diese Werte gelten damit nicht als fehlende Last.
### Ausgabe
Die Excel-Auswertung enthält unter anderem:
- Übersicht
- Lastvergleich
- Dateiprüfung
- Nicht geprüft
Dadurch bleibt nachvollziehbar, welche Dateien verarbeitet wurden, welche Lasten übereinstimmen und welche Einträge noch manuell kontrolliert werden müssen.
---
## Start
Abhängigkeiten installieren:
```powershell
pip install -r requirements.txt
```
Programm starten:
```powershell
python luftmengen_vergleich.py
```
## Hinweis
Das Tool unterstützt die technische Planprüfung und soll repetitive manuelle Kontrollen reduzieren.
Automatisch erkannte Abweichungen und nicht eindeutige Fälle sollten weiterhin anhand der Originalunterlagen fachlich kontrolliert werden.
