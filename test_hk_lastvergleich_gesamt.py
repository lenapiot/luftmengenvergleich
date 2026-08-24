from pathlib import Path
from tkinter import Tk, filedialog
from hk.lastvergleich import (
   extract_loads_from_pdfs_checked,
   extract_and_consolidate_schema,
   compare_loads_with_schema,
)

def choose_pdf(title: str) -> Path:
   path = filedialog.askopenfilename(
       title=title,
       filetypes=[("PDF-Dateien", "*.pdf")],
   )
   if not path:
       raise SystemExit("Keine Datei ausgewählt.")
   return Path(path)

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
   dataframe,
   room_id: str,
) -> None:
   rows = dataframe[
       dataframe["raumnummer"] == room_id
   ]
   print()
   print(f"--- {room_id} ---")
   if rows.empty:
       print("nicht gefunden")
       return
   columns = [
       "raumnummer",
       "raumname",
       "heizlast_original_w",
       "heizlast_vergleich_w",
       "q_h_schema_w",
       "differenz_heizung_w",
       "status_heizung",
       "kuehllast_original_w",
       "kuehllast_vergleich_w",
       "q_k_schema_w",
       "differenz_kuehlung_w",
       "status_kuehlung",
       "schema_status",
       "schema_werte",
       "status_gesamt",
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
   # --------------------------------------------------------
   # 1. STRANGSCHEMA
   # --------------------------------------------------------
   schema_pdf = choose_pdf(
       "MIT2 Strangschema Klimawärme/Kälte auswählen"
   )
   schema = extract_and_consolidate_schema(
       schema_pdf
   )
   # --------------------------------------------------------
   # 2. HEIZLAST-GRUNDRISSE
   # --------------------------------------------------------
   heating_pdfs = choose_pdfs(
       "MIT2 Heizlast-Grundrisse auswählen"
   )
   heating, heating_check = (
       extract_loads_from_pdfs_checked(
           heating_pdfs,
           "Heizlast",
           expected_building="MIT2",
       )
   )
   # --------------------------------------------------------
   # 3. KÜHLLAST-GRUNDRISSE
   # --------------------------------------------------------
   cooling_pdfs = choose_pdfs(
       "MIT2 Kühllast-Grundrisse auswählen"
   )
   cooling, cooling_check = (
       extract_loads_from_pdfs_checked(
           cooling_pdfs,
           "Kühllast",
           expected_building="MIT2",
       )
   )
   # --------------------------------------------------------
   # 4. VERGLEICH
   # --------------------------------------------------------
   comparison = compare_loads_with_schema(
       heating,
       cooling,
       schema,
   )
   # --------------------------------------------------------
   # AUSGABE
   # --------------------------------------------------------
   print()
   print("=" * 80)
   print("GESAMTVERGLEICH")
   print("=" * 80)
   print(
       "Schema-Räume:",
       len(schema),
   )
   print(
       "Heizlast-Räume:",
       heating["raumnummer"].nunique()
       if not heating.empty
       else 0,
   )
   print(
       "Kühllast-Räume:",
       cooling["raumnummer"].nunique()
       if not cooling.empty
       else 0,
   )
   print(
       "Vergleichs-Räume:",
       len(comparison),
   )
   print()
   print("=" * 80)
   print("STATUS")
   print("=" * 80)
   print(
       comparison[
           "status_gesamt"
       ].value_counts()
   )
   print()
   print("=" * 80)
   print("KONTROLLRÄUME")
   print("=" * 80)
   test_rooms = [
       "MIT2H302",
       "MIT2H314",
       "MIT2H4205",
       "MIT2J204",
   ]
   for room_id in test_rooms:
       print_room(
           comparison,
           room_id,
       )

if __name__ == "__main__":
   main()