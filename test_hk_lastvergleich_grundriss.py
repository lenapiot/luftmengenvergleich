from pathlib import Path
from tkinter import Tk, filedialog
from hk.lastvergleich import (
   extract_loads_from_pdf,
   determine_document_building,
)

def choose_pdf(title: str) -> Path:
   path = filedialog.askopenfilename(
       title=title,
       filetypes=[("PDF-Dateien", "*.pdf")],
   )
   if not path:
       raise SystemExit("Keine Datei ausgewählt.")
   return Path(path)

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
   ]
   print(
       f"{label}:",
       rows[columns].to_dict(
           orient="records"
       ),
   )

def main() -> None:
   root = Tk()
   root.withdraw()
   heating_pdf = choose_pdf(
       "Heizlast-Grundriss auswählen"
   )
   cooling_pdf = choose_pdf(
       "Kühllast-Grundriss auswählen"
   )
   heating = extract_loads_from_pdf(
       heating_pdf,
       "Heizlast",
   )
   cooling = extract_loads_from_pdf(
       cooling_pdf,
       "Kühllast",
   )
   print()
   print("=" * 40)
   print("HEIZLAST")
   print("=" * 40)
   print(
       "Dokument:",
       determine_document_building(
           heating
       ),
   )
   print(
       "Erkannte Räume:",
       len(heating),
   )
   print(
       heating[
           [
               "raumnummer",
               "raumname",
               "leistung_w",
               "vergleichswert_w",
               "ist_marker",
               "marker_typ",
           ]
       ].to_string(
           index=False
       )
   )
   print()
   print("=" * 40)
   print("KÜHLLAST")
   print("=" * 40)
   print(
       "Dokument:",
       determine_document_building(
           cooling
       ),
   )
   print(
       "Erkannte Räume:",
       len(cooling),
   )
   print(
       cooling[
           [
               "raumnummer",
               "raumname",
               "leistung_w",
               "vergleichswert_w",
               "ist_marker",
               "marker_typ",
           ]
       ].to_string(
           index=False
       )
   )
   print()
   print("=" * 40)
   print("KONTROLLWERTE")
   print("=" * 40)
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