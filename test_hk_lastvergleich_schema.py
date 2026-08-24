from pathlib import Path
from tkinter import Tk, filedialog
from hk.lastvergleich import (
   extract_schema_from_pdf,
   determine_document_building,
   find_duplicate_schema_rooms,
)

def choose_pdf(
   title: str,
) -> Path:
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
   return Path(
       path
   )

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
   columns = [
       "raumnummer",
       "raumname",
       "q_h_w",
       "q_k_w",
       "seite",
       "x",
       "y",
   ]
   print(
       rows[
           columns
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
   dataframe = (
       extract_schema_from_pdf(
           pdf_path
       )
   )
   print()
   print("=" * 60)
   print("STRANGSCHEMA")
   print("=" * 60)
   print(
       "Gebäude:",
       determine_document_building(
           dataframe
       ),
   )
   print(
       "Erkannte Datensätze:",
       len(
           dataframe
       ),
   )
   print(
       "Eindeutige Räume:",
       dataframe[
           "raumnummer"
       ].nunique()
       if not dataframe.empty
       else 0,
   )
   print()
   print(
       dataframe[
           [
               "raumnummer",
               "raumname",
               "q_h_w",
               "q_k_w",
           ]
       ]
       .head(
           50
       )
       .to_string(
           index=False
       )
   )
   duplicates = (
       find_duplicate_schema_rooms(
           dataframe
       )
   )
   print()
   print("=" * 60)
   print("DOPPELTE RÄUME")
   print("=" * 60)
   print(
       "Anzahl:",
       duplicates[
           "raumnummer"
       ].nunique()
       if not duplicates.empty
       else 0,
   )
   print()
   print("=" * 60)
   print("KONTROLLWERTE")
   print("=" * 60)
   test_rooms = [
       "MIT2H302",
       "MIT2H302e",
       "MIT2H314",
   ]
   for room_id in test_rooms:
       print_room(
           dataframe,
           room_id,
       )

if __name__ == "__main__":
   main()


