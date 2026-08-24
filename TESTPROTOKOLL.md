# Testprotokoll – Planvergleich
Dieses Testprotokoll dient zur Kontrolle vor einer neuen Version bzw. vor dem Erstellen einer neuen EXE.
Ziel ist sicherzustellen, dass Änderungen an einem Modul keine bereits funktionierenden Bereiche beschädigt haben.
Status:
- [ ] Nicht getestet
- [x] Erfolgreich getestet
---
# 1. Lüftung – Luftmengenvergleich
## 1.1 Standardvergleich
- [ ] Grundriss-PDF kann ausgewählt werden
- [ ] Schema-PDF kann ausgewählt werden
- [ ] Räume werden im Grundriss erkannt
- [ ] Räume werden im Schema erkannt
- [ ] Zuluft wird korrekt ausgelesen
- [ ] Abluft wird korrekt ausgelesen
- [ ] Raumname wird korrekt zugeordnet
- [ ] Vergleich wird ohne Fehler abgeschlossen
### Erwartetes Ergebnis
Bei gleichen Angaben:
```text
Status = OK
```
Bei unterschiedlichen Luftmengen:
```text
Status = Abweichung Luftmenge
```
Bei unterschiedlichen Raumnamen:
```text
Status = Abweichung Raumname
```
---
## 1.2 Mehrere Grundrisse und Schemata
- [ ] Mehrere Grundriss-PDFs gleichzeitig auswählbar
- [ ] Mehrere Schema-PDFs gleichzeitig auswählbar
- [ ] Daten aller Dateien werden eingelesen
- [ ] Keine Datei überschreibt die vorherige
- [ ] Gesamtauswertung enthält Daten aus allen ausgewählten Dateien
---
## 1.3 Nominal / Havarie
Test mit Angaben wie:
```text
ZUL: Nominal 400 / Havarie 2300 m3/h
ABL: Nominal 400 / Havarie 2400 m3/h
```
Prüfen:
- [ ] Nominal-Zuluft wird als 400 erkannt
- [ ] Nominal-Abluft wird als 400 erkannt
- [ ] Havarie-Zuluft wird als 2300 erkannt
- [ ] Havarie-Abluft wird als 2400 erkannt
- [ ] Nominal und Havarie werden getrennt verglichen
---
## 1.4 Numerisch – Geschoss.Raum
Test mit einem Projekt mit numerischen Raumnummern.
Beispiele:
```text
-01.227
00.302
01.514
```
Prüfen:
- [ ] Modus «Numerisch - Geschoss.Raum» kann ausgewählt werden
- [ ] numerische Raumnummern werden erkannt
- [ ] Geschossnummern werden korrekt normalisiert
- [ ] Raumteil nach dem Punkt bleibt unverändert
- [ ] keine offensichtlichen Masse oder Höhen werden als Räume erkannt
Beispiele:
```text
-01.230 -> -1.230
00.302  -> 0.302
01.514  -> 1.514
```
---
## 1.5 e+p-Blöcke und ep-Nummern
Test mit einem Grundriss, der sowohl originale architektonische Raumbeschriftungen als auch e+p-Luftmengenblöcke enthält.
Prüfen:
- [ ] e+p-Luftmengenblöcke werden als Vergleichsgrundlage verwendet
- [ ] originale Raumbeschriftungen werden nicht zusätzlich als eigene Vergleichsräume aufgenommen
- [ ] ep-Nummern werden erkannt
- [ ] ep-Nummern dienen im numerischen Modus als eindeutiger Schlüssel
Spezialfall:
```text
Raum: -1.21
ep: 228
```
und
```text
Raum: -1.21
ep: 229
```
Prüfen:
- [ ] ep 228 und ep 229 werden als zwei getrennte Einträge behandelt
- [ ] beide Einträge werden im PDF an der richtigen Stelle markiert
---
## 1.6 Excel-Ausgabe
Prüfen, ob folgende Tabellenblätter vorhanden und plausibel sind:
- [ ] Legende
- [ ] Grundriss_Rohdaten
- [ ] Schema_Rohdaten
- [ ] Vergleich
- [ ] Abweichungen
- [ ] Nur_im_Grundriss
- [ ] Nur_im_Schema
- [ ] PDF_Markierungen
Zusätzlich:
- [ ] keine offensichtlich doppelten Datensätze
- [ ] Quelldateien sind nachvollziehbar
- [ ] Statuswerte stimmen mit den Originalunterlagen überein
---
## 1.7 Markierte PDFs
- [ ] markierte PDF wird erstellt
- [ ] richtige Raumnummer wird markiert
- [ ] OK-Einträge werden korrekt markiert
- [ ] Abweichungen werden korrekt markiert
- [ ] «Nur im Grundriss»-Einträge werden korrekt markiert
- [ ] Markierungen überdecken die relevanten Texte nicht unbrauchbar
- [ ] Legende wird dargestellt
- [ ] mehrfach vorkommende verkürzte Raumnummern werden über ep korrekt lokalisiert
---
# 2. Heizung/Kälte – Betriebsnummernkontrolle
## 2.1 Grundfunktion
- [ ] beide Vergleichsunterlagen können ausgewählt werden
- [ ] Betriebsnummern werden aus beiden PDFs extrahiert
- [ ] Vergleich wird ohne Fehler abgeschlossen
- [ ] gleiche Betriebsnummern werden als vorhanden erkannt
- [ ] fehlende Betriebsnummern werden angezeigt
- [ ] zusätzliche Betriebsnummern werden angezeigt
---
## 2.2 Unterstützte Nummernformate
Mit Testunterlagen prüfen, dass folgende Formen erkannt werden:
```text
D12.3
AB12.3
STA12.4
AB12.3.1
ZV70.01
```
Prüfen:
- [ ] Präfix mit einem Buchstaben
- [ ] Präfix mit zwei Buchstaben
- [ ] STA
- [ ] 1–3 Ziffern vor dem ersten Punkt
- [ ] 1–3 Ziffern nach dem ersten Punkt
- [ ] optionaler zweiter Punkt
- [ ] mehrere Betriebsnummern innerhalb derselben Zeile
---
## 2.3 ZV-Nummern
Spezialtest mit:
```text
ZV70.01
ZV70.02
ZV70.03
...
ZV70.12
```
Prüfen:
- [ ] führende Null bleibt erhalten
- [ ] ZV70.01 wird nicht als ZV70.1 ausgegeben
- [ ] ZV70.10 bis ZV70.12 werden korrekt erkannt
- [ ] vollständige Nummernserie erscheint in der Auswertung
---
## 2.4 Vergleichsergebnis
Kontrollieren:
- [ ] Nummer in beiden Unterlagen -> korrekt erkannt
- [ ] Nummer nur in Unterlage 1 -> korrekt angezeigt
- [ ] Nummer nur in Unterlage 2 -> korrekt angezeigt
- [ ] keine offensichtlich falschen Teilnummern werden erzeugt
- [ ] keine relevante Betriebsnummer fehlt
---
# 3. Heizung/Kälte – Strangschema-Lastvergleich
## 3.1 Grundfunktion
- [ ] Strangschema kann ausgewählt werden
- [ ] Heizlastdateien können ausgewählt werden
- [ ] Kühllastdateien können ausgewählt werden
- [ ] Ordnerauswahl funktioniert
- [ ] mehrere Dateien werden gemeinsam verarbeitet
- [ ] Vergleich wird ohne Fehler abgeschlossen
---
## 3.2 Heizlast
Test mit einem bekannten Heizlastfall.
Prüfen:
- [ ] Heizlast wird korrekt erkannt
- [ ] passender Eintrag im Strangschema wird gefunden
- [ ] gleiche Leistung -> OK
- [ ] unterschiedliche Leistung -> Abweichung
---
## 3.3 Kühllast
Test mit einem bekannten Kühllastfall.
Prüfen:
- [ ] Kühllast wird korrekt erkannt
- [ ] passender Eintrag im Strangschema wird gefunden
- [ ] gleiche Leistung -> OK
- [ ] unterschiedliche Leistung -> Abweichung
---
## 3.4 0-W-Sonderfälle
### Heizlast
```text
-1
```
muss interpretiert werden als:
```text
0 W
```
Prüfen:
- [ ] Heizlast -1 wird als 0 W behandelt
- [ ] der Eintrag gilt als geprüft
### Kühllast
```text
+1
```
muss interpretiert werden als:
```text
0 W
```
Prüfen:
- [ ] Kühllast +1 wird als 0 W behandelt
- [ ] der Eintrag gilt als geprüft
---
## 3.5 Ebenenfilter
Test mit einem Strangschema mit mehreren Ebenen.
Prüfen:
- [ ] relevante Ebenen können ausgewählt werden
- [ ] ausgewählte Ebenen werden geprüft
- [ ] nicht ausgewählte Ebenen werden nicht als Fehler angezeigt
- [ ] Einträge aus anderen Ebenen verfälschen die Auswertung nicht
---
## 3.6 MIT1
Test mit bekanntem MIT1-Projekt.
- [ ] MIT1-Struktur wird korrekt verarbeitet
- [ ] Lasten werden richtig zugeordnet
- [ ] Vergleichsergebnisse stimmen mit manueller Kontrolle überein
---
## 3.7 MIT2
Test mit bekanntem MIT2-Projekt.
- [ ] MIT2-Struktur wird korrekt verarbeitet
- [ ] Lasten werden richtig zugeordnet
- [ ] Vergleichsergebnisse stimmen mit manueller Kontrolle überein
---
## 3.8 Gemischte MIT1/MIT2-Fälle
Test mit einer Datei, die beide Strukturen enthält.
- [ ] gemischte Struktur wird erkannt
- [ ] einzelne Minderheitseinträge führen nicht zu einer falschen Gesamtklassifizierung
- [ ] MIT1- und MIT2-Werte werden korrekt zugeordnet
- [ ] Ergebnis stimmt mit manueller Kontrolle überein
---
## 3.9 Excel-Ausgabe
Prüfen, ob folgende Tabellenblätter vorhanden und plausibel sind:
- [ ] Übersicht
- [ ] Lastvergleich
- [ ] Dateiprüfung
- [ ] Nicht geprüft
Zusätzlich:
- [ ] verarbeitete Dateien sind vollständig aufgeführt
- [ ] Heiz- und Kühllasten sind nachvollziehbar
- [ ] Abweichungen stimmen mit den Originalunterlagen überein
- [ ] nicht prüfbare Einträge werden separat aufgeführt
---
# 4. Gemeinsame Benutzeroberfläche
- [ ] Programm startet ohne Fehlermeldung
- [ ] e+p-Logo wird angezeigt
- [ ] Lüftung – Luftmengenvergleich öffnet korrekt
- [ ] Heizung/Kälte – Betriebsnummernkontrolle öffnet korrekt
- [ ] Heizung/Kälte – Strangschema-Lastvergleich öffnet korrekt
- [ ] Wechsel zwischen den Modulen funktioniert
- [ ] Dateiauswahl funktioniert
- [ ] Ordnerauswahl funktioniert
- [ ] Fortschrittsanzeige funktioniert
- [ ] Programm reagiert während längerer Auswertungen weiterhin sinnvoll
- [ ] Ausgabedateien werden am erwarteten Ort gespeichert
---
# 5. Finaler Test vor EXE-Erstellung
Vor dem Erstellen einer neuen EXE müssen mindestens folgende Referenztests erfolgreich sein:
| Test | Status |
|---|---|
| Lüftung Standardvergleich | [ ] |
| Lüftung Nominal/Havarie | [ ] |
| Lüftung Numerisch / ep | [ ] |
| Lüftung PDF-Markierung | [ ] |
| Betriebsnummern Standard | [ ] |
| Betriebsnummern ZV / führende Null | [ ] |
| Strangschema Heizlast | [ ] |
| Strangschema Kühllast | [ ] |
| Strangschema MIT1 | [ ] |
| Strangschema MIT2 | [ ] |
| Strangschema gemischtes MIT1/MIT2 | [ ] |
| Strangschema Ebenenfilter | [ ] |
| 0-W-Sonderfälle | [ ] |
---
# 6. Freigabe
Datum:
```text
____________________
```
Version:
```text
____________________
```
Getestet durch:
```text
____________________
```
Ergebnis:
- [ ] Freigegeben
- [ ] Fehler vorhanden – keine EXE erstellen
Bemerkungen:
```text

```
hat Kontextmenü
