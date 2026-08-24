from pathlib import Path
from tkinter import Tk, filedialog
from hk.lastvergleich import (
   extract_schema_from_pdf,
   find_duplicate_schema_rooms,
)

def choose_pdf(title: str) -> Path:
   path = filedialog.askopenfilename(
       title=title,
       filetypes=[("PDF-Dateien", "*.pdf")],
   )
   if not path:
       raise SystemExit(
           "Keine Datei ausgewählt."
       )
   return Path(path)

def main() -> None:
   root = Tk()
   root.withdraw()
   pdf_path = choose_pdf(
       "Strangschema Klimawärme/Kälte auswählen"
   )
   schema = extract_schema_from_pdf(
       pdf_path
   )
   duplicates = find_duplicate_schema_rooms(
       schema
   )
   print()
   print("=" * 70)
   print("DOPPELTE RÄUME IM STRANGSCHEMA")
   print("=" * 70)
   if duplicates.empty:
       print("Keine doppelten Räume gefunden.")
       return
   room_ids = sorted(
       duplicates[
           "raumnummer"
       ].unique()
   )
   print(
       "Anzahl doppelte Raumnummern:",
       len(room_ids),
   )
   for room_id in room_ids:
       rows = duplicates[
           duplicates[
               "raumnummer"
           ] == room_id
       ]
       print()
       print(
           "-" * 70
       )
       print(
           room_id
       )
       print(
           "-" * 70
       )
       print(
           rows[
               [
                   "raumnummer",
                   "raumname",
                   "q_h_w",
                   "q_k_w",
                   "seite",
                   "x",
                   "y",
               ]
           ].to_string(
               index=False
           )
       )
       combinations = (
           rows[
               [
                   "q_h_w",
                   "q_k_w",
               ]
           ]
           .drop_duplicates()
       )
       if len(combinations) == 1:
           print(
               "→ Gleiche Q_H/Q_K-Werte: vermutlich unkritisches Duplikat."
           )
       else:
           print(
               "→ ACHTUNG: unterschiedliche Q_H/Q_K-Werte!"
           )

if __name__ == "__main__":
   main()