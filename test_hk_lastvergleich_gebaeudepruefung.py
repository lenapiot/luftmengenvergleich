from pathlib import Path
from tkinter import Tk, filedialog
from hk.lastvergleich import (
   extract_loads_from_pdfs_checked,
)

def choose_pdfs(title: str) -> list[Path]:
   paths = filedialog.askopenfilenames(
       title=title,
       filetypes=[("PDF-Dateien", "*.pdf")],
   )
   if not paths:
       raise SystemExit("Keine Dateien ausgewählt.")
   return [Path(path) for path in paths]

def main() -> None:
   root = Tk()
   root.withdraw()
   print()
   print("=== TEST GEBÄUDEPRÜFUNG ===")
   print()
   pdfs = choose_pdfs(
       "Mehrere Heizlast-Grundrisse auswählen"
   )
   data, check = extract_loads_from_pdfs_checked(
       pdfs,
       "Heizlast",
       expected_building="MIT2",
   )
   print()
   print("=" * 60)
   print("PRÜFPROTOKOLL")
   print("=" * 60)
   print(
       check[
           [
               "datei",
               "erkanntes_gebaeude",
               "erwartetes_gebaeude",
               "akzeptiert",
               "grund",
               "anzahl_raeume",
           ]
       ].to_string(
           index=False
       )
   )
   print()
   print("=" * 60)
   print("AKZEPTIERTE DATEN")
   print("=" * 60)
   print(
       "Erkannte Räume:",
       data["raumnummer"].nunique()
       if not data.empty
       else 0,
   )
   print()
   if not data.empty:
       print(
           data[
               [
                   "raumnummer",
                   "raumname",
                   "leistung_w",
                   "datei",
               ]
           ].head(30).to_string(
               index=False
           )
       )
   print()
   print("=" * 60)
   print("KONTROLLE")
   print("=" * 60)
   if check.empty:
       print("Keine Dateien geprüft.")
       return
   accepted = check[
       check["akzeptiert"] == True
   ]
   rejected = check[
       check["akzeptiert"] == False
   ]
   print(
       "Akzeptierte Dateien:",
       len(accepted),
   )
   print(
       "Abgelehnte Dateien:",
       len(rejected),
   )

if __name__ == "__main__":
   main()