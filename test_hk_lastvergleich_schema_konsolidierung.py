from pathlib import Path
from tkinter import Tk, filedialog
from hk.lastvergleich import (
   extract_schema_from_pdf,
   consolidate_schema,
   find_schema_conflicts,
)

def choose_pdf(title: str) -> Path:
   path = filedialog.askopenfilename(
       title=title,
       filetypes=[
           (
               "PDF-Dateien",
               "*.pdf",
           )
       ],
   )
   if not path:
       raise SystemExit(
           "Keine Datei ausgewählt."
       )
   return Path(path)

def print_room(
   dataframe,
   room_id: str,
) -> None:
   rows = dataframe[
       dataframe[
           "raumnummer"
       ]
       == room_id
   ]
   print()
   print(
       f"--- {room_id} ---"
   )
   if rows.empty:
       print(
           "nicht gefunden"
       )
       return
   print(
       rows[
           [
               "raumnummer",
               "raumname",
               "q_h_w",
               "q_k_w",
               "schema_status",
               "schema_eindeutig",
               "schema_werte",
               "anzahl_schema_eintraege",
               "anzahl_unterschiedliche_werte",
           ]
       ].to_string(
           index=False
       )
   )

def main() -> None:
   root = Tk()
   root.withdraw()
   pdf_path = choose_pdf(
       "Strangschema Klimawärme/Kälte auswählen"
   )
   raw_schema = (
       extract_schema_from_pdf(
           pdf_path
       )
   )
   schema = (
       consolidate_schema(
           raw_schema
       )
   )
   conflicts = (
       find_schema_conflicts(
           schema
       )
   )
   print()
   print("=" * 70)
   print("SCHEMA KONSOLIDIERUNG")
   print("=" * 70)
   print(
       "Rohe Schemaeinträge:",
       len(
           raw_schema
       ),
   )
   print(
       "Konsolidierte Räume:",
       len(
           schema
       ),
   )
   print(
       "Konflikte:",
       len(
           conflicts
       ),
   )
   print()
   print("=" * 70)
   print("KONTROLLRÄUME")
   print("=" * 70)
   test_rooms = [
       "MIT2H302",
       "MIT2H302e",
       "MIT2H314",
       "MIT2V3510",
   ]
   for room_id in test_rooms:
       print_room(
           schema,
           room_id,
       )
   print()
   print("=" * 70)
   print("ALLE KONFLIKTE")
   print("=" * 70)
   if conflicts.empty:
       print(
           "Keine Konflikte."
       )
   else:
       print(
           conflicts[
               [
                   "raumnummer",
                   "raumname",
                   "schema_status",
                   "schema_werte",
                   "anzahl_schema_eintraege",
               ]
           ].to_string(
               index=False
           )
       )

if __name__ == "__main__":
   main()