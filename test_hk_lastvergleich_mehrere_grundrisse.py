from pathlib import Path
from tkinter import Tk, filedialog
from hk.lastvergleich import (
   extract_loads_from_pdfs,
   determine_document_building,
   find_duplicate_rooms,
)

def choose_pdfs(title: str) -> list[Path]:
   paths = filedialog.askopenfilenames(
       title=title,
       filetypes=[("PDF-Dateien", "*.pdf")],
   )
   if not paths:
       raise SystemExit("Keine Dateien ausgewählt.")
   return [
       Path(path)
       for path in paths
   ]

def print_room(
   df,
   room_id: str,
   label: str,
) -> None:
   rows = df[
       df["raumnummer"] == room_id
   ]
   if rows.empty:
       print(
           f"{label}: nicht gefunden"
       )
       return
   columns = [
       "leistung_w",
       "vergleichswert_w",
       "ist_marker",
       "marker_typ",
       "raumname",
       "datei",
       "seite",
   ]
   print(
       f"{label}:",
       rows[columns].to_dict(
           orient="records"
       ),
   )

def print_summary(
   title: str,
   df,
) -> None:
   print()
   print("=" * 60)
   print(title)
   print("=" * 60)
   print(
       "Dokument:",
       determine_document_building(
           df
       ),
   )
   print(
       "Erkannte Datensätze:",
       len(df),
   )
   print(
       "Eindeutige Räume:",
       df["raumnummer"].nunique()
       if not df.empty
       else 0,
   )
   if df.empty:
       print("Keine Räume erkannt.")
       return
   print()
   print(
       df[
           [
               "raumnummer",
               "raumname",
               "leistung_w",
               "vergleichswert_w",
               "ist_marker",
               "marker_typ",
               "datei",
           ]
       ].to_string(
           index=False
       )
   )

def main() -> None:
   root = Tk()
   root.withdraw()
   print()
   print(
       "=== Heizlast-Grundrisse auswählen ==="
   )
   heating_pdfs = choose_pdfs(
       "Heizlast-Grundrisse auswählen"
   )
   print()
   print(
       "=== Kühllast-Grundrisse auswählen ==="
   )
   cooling_pdfs = choose_pdfs(
       "Kühllast-Grundrisse auswählen"
   )
   heating = extract_loads_from_pdfs(
       heating_pdfs,
       "Heizlast",
   )
   cooling = extract_loads_from_pdfs(
       cooling_pdfs,
       "Kühllast",
   )
   print_summary(
       "HEIZLAST",
       heating,
   )
   print_summary(
       "KÜHLLAST",
       cooling,
   )
   print()
   print("=" * 60)
   print("GEBÄUDEKONTROLLE")
   print("=" * 60)
   heating_building = (
       determine_document_building(
           heating
       )
   )
   cooling_building = (
       determine_document_building(
           cooling
       )
   )
   print(
       "Heizlast:",
       heating_building,
   )
   print(
       "Kühllast:",
       cooling_building,
   )
   if (
       heating_building
       in {"MIT1", "MIT2"}
       and cooling_building
       in {"MIT1", "MIT2"}
   ):
       if (
           heating_building
           == cooling_building
       ):
           print(
               "OK: Heizlast und Kühllast "
               "gehören zum gleichen Gebäude."
           )
       else:
           print(
               "WARNUNG: Heizlast und Kühllast "
               "gehören nicht zum gleichen Gebäude!"
           )
   else:
       print(
           "WARNUNG: Gebäude konnte nicht "
           "eindeutig bestimmt werden."
       )
   print()
   print("=" * 60)
   print("DOPPELTE RÄUME")
   print("=" * 60)
   heating_duplicates = (
       find_duplicate_rooms(
           heating
       )
   )
   cooling_duplicates = (
       find_duplicate_rooms(
           cooling
       )
   )
   print()
   print(
       "Heizlast - doppelte Räume:",
       heating_duplicates[
           "raumnummer"
       ].nunique()
       if not heating_duplicates.empty
       else 0,
   )
   if not heating_duplicates.empty:
       print(
           heating_duplicates[
               [
                   "raumnummer",
                   "leistung_w",
                   "datei",
                   "seite",
               ]
           ].to_string(
               index=False
           )
       )
   print()
   print(
       "Kühllast - doppelte Räume:",
       cooling_duplicates[
           "raumnummer"
       ].nunique()
       if not cooling_duplicates.empty
       else 0,
   )
   if not cooling_duplicates.empty:
       print(
           cooling_duplicates[
               [
                   "raumnummer",
                   "leistung_w",
                   "datei",
                   "seite",
               ]
           ].to_string(
               index=False
           )
       )
   print()
   print("=" * 60)
   print("KONTROLLWERTE")
   print("=" * 60)
   test_rooms = [
       "MIT2H302",
       "MIT2H4205",
       "MIT2J204",
   ]
   for room_id in test_rooms:
       print()
       print(
           f"--- {room_id} ---"
       )
       print_room(
           heating,
           room_id,
           "Heizlast",
       )
       print_room(
           cooling,
           room_id,
           "Kühllast",
       )

if __name__ == "__main__":
   main()