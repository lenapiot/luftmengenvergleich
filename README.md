# Planvergleich
Internes Prüf- und Vergleichstool für HLKS-Planunterlagen.
Das Programm fasst mehrere automatisierte Prüfungen für Lüftungs-, Heizungs- und Kältepläne in einer gemeinsamen grafischen Oberfläche zusammen.
Aktuell stehen drei Module zur Verfügung:
1. Lüftung – Luftmengenvergleich
2. Heizung/Kälte – Betriebsnummernkontrolle
3. Heizung/Kälte – Strangschema-Lastvergleich
---
# 1. Lüftung – Luftmengenvergleich
Der Luftmengenvergleich vergleicht Angaben aus Lüftungsgrundrissen mit den zugehörigen Prinzipschemata.
## Geprüfte Angaben
Je nach Planformat werden unter anderem verglichen:
- Raumnummer
- Raumname
- Zuluft
- Abluft
- Betriebsart
- Vorkommen im Grundriss
- Vorkommen im Schema
Es können mehrere Grundriss-PDFs und mehrere Schema-PDFs gleichzeitig verarbeitet werden.
## Betriebsarten
Das Programm unterstützt auch Pläne mit mehreren Betriebsarten, beispielsweise:
```text
ZUL: Nominal 400 / Havarie 2300 m3/h
ABL: Nominal 400 / Havarie 2400 m3/h
