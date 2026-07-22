# Luftmengenvergleich – Prototyp

## Zweck

Dieses Python-Programm vergleicht die Luftmengenangaben aus zwei ähnlich aufgebauten PDF-Dokumenten:

1. einem Grundriss- bzw. Flächenplan mit Angaben wie `ZUL:` und `ABL:`
2. einem Lüftungsplan bzw. Prinzipschema mit Angaben wie `Zuluft` und `Abluft`

Das Programm extrahiert Raumnummern, Raumnamen sowie Zu- und Abluftmengen, vergleicht beide Dokumente und erstellt:

- eine Excel-Auswertung,
- eine markierte Kopie des Grundrissplans,
- eine Übersicht der Abweichungen,
- Listen der Räume, die nur in einem Dokument vorkommen,
- ein Protokoll nicht eindeutig gefundener PDF-Markierungen.

## Voraussetzungen

- Windows 10 oder Windows 11
- Python 3.10 oder neuer
- digital erzeugte PDFs mit auslesbarer Textebene
- ähnlich aufgebaute Raumstempel wie beim getesteten Dokumentpaar

## Installation

1. Den gesamten Projektordner auf den Computer kopieren.
2. PowerShell oder die Eingabeaufforderung öffnen.
3. In den Projektordner wechseln:

```powershell
cd "C:\Pfad\zum\Luftmengenvergleich_Prototyp"
```

4. Benötigte Bibliotheken installieren:

```powershell
python -m pip install -r requirements.txt
```

## Programm starten

```powershell
python luftmengen_vergleich.py
```

Danach erscheinen drei Auswahlfenster:

1. **Grundriss-PDF auswählen**  
   Hier den Grundriss bzw. Flächenplan mit Angaben wie `ZUL:` und `ABL:` auswählen.

2. **Lüftungsplan / Prinzipschema auswählen**  
   Hier das zugehörige Schema mit Angaben wie `Zuluft` und `Abluft` auswählen.

3. **Ausgabeordner auswählen**  
   Hier den Ordner auswählen, in dem die Ergebnisse gespeichert werden sollen.

## Ausgabedateien

Das Programm erstellt im gewählten Ausgabeordner:

- `<Name_des_Grundrisses>_Luftmengenvergleich.xlsx`
- `<Name_des_Grundrisses>_markiert.pdf`

Die Excel-Datei enthält folgende Tabellenblätter:

- `Legende`
- `Grundriss_Rohdaten`
- `Schema_Rohdaten`
- `Vergleich`
- `Abweichungen`
- `Nur_im_Grundriss`
- `Nur_im_Schema`
- `PDF_Markierungen`

## Statuswerte

- **OK**: Raumname und Luftmengen stimmen überein.
- **Abweichung Luftmenge**: Zuluft und/oder Abluft unterscheiden sich.
- **Abweichung Raumname**: Luftmengen stimmen, Raumname weicht ab.
- **Nur im Grundriss**: Raum wurde nur im Grundriss gefunden.
- **Nur im Schema**: Raum wurde nur im Schema gefunden.
- **Mehrfach / uneindeutig**: Eine Raumnummer wurde mehrfach mit widersprüchlichen Angaben gefunden.

## Unterstützte Dokumentstruktur

Beispiel Grundriss:

```text
MIT2X1
ZUL: 4'000 m³/h
ABL: 4'450 m³/h
```

Beispiel Lüftungsschema:

```text
Parkplätze gedeckt
MIT2X1
Zuluft 4'000 m³/h
Abluft 4'450 m³/h
```

## Wichtige Einschränkungen

- Der Prototyp funktioniert nur zuverlässig bei PDFs mit vorhandener Textebene.
- Eingescannte Pläne ohne auslesbaren Text werden nicht automatisch erkannt.
- Die Raumnummern müssen dem aktuell hinterlegten Muster entsprechen, zum Beispiel `MIT2X1`, `MIT1X407` oder `MIT2X5300a`.
- Abweichende Planstrukturen können Anpassungen an den regulären Ausdrücken oder der Suchlogik erfordern.
- Die Resultate müssen fachlich kontrolliert werden.
- Der Prototyp ersetzt keine abschliessende technische Prüfung.

## Fehlerbehebung

### `ModuleNotFoundError`

```powershell
python -m pip install -r requirements.txt
```

### Keine Räume im Grundriss erkannt

Prüfen:

- Ist wirklich der Grundriss mit `ZUL:` und `ABL:` ausgewählt?
- Ist der Text im PDF markierbar?
- Entsprechen die Raumnummern ungefähr dem Muster `MIT2X1`?

### Keine Räume im Schema erkannt

Prüfen:

- Ist das richtige Lüftungsschema ausgewählt?
- Enthält es Angaben wie `Zuluft` und `Abluft`?
- Besitzt das PDF eine Textebene?

### Markierung nicht eindeutig

Die Raumnummer kommt im Grundriss mehrfach vor. Der Fall wird im Tabellenblatt `PDF_Markierungen` protokolliert und nicht automatisch markiert.

## Projektstatus

Version: **0.1 – Prototyp**

Der Prototyp ist für erste Tests mit ähnlich aufgebauten Grundriss- und Lüftungsplänen vorgesehen.
