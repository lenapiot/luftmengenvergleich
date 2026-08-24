from pathlib import Path
from tkinter import Tk, filedialog
from hk.lastvergleich import (
   extract_loads_from_pdfs_checked,
   extract_and_consolidate_schema,
   compare_loads_with_schema,
   determine_document_building,
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

def choose_pdfs(title: str) -> list[Path]:
   paths = filedialog.askopenfilenames(
       title=title,
       filetypes=[("PDF-Dateien", "*.pdf")],
   )
   if not paths:
       raise SystemExit(
           "Keine Dateien ausgewählt."
       )
   return [
       Path(path)
       for path in paths
   ]

def print_examples(
   dataframe,
   mask,
   title: str,
   max_rows: int = 15,
) -> None:
   rows = dataframe.loc[
       mask
   ].copy()
   print()
   print("=" * 80)
   print(title)
   print("=" * 80)
   print(
       "Anzahl:",
       len(rows),
   )
   if rows.empty:
       return
   columns = [
       "raumnummer",
       "raumname",
       "status_heizung",
       "status_kuehlung",
       "status_gesamt",
       "heizlast_vergleich_w",
       "q_h_schema_w",
       "kuehllast_vergleich_w",
       "q_k_schema_w",
       "im_schema",
       "im_heizlastgrundriss",
       "im_kuehllastgrundriss",
   ]
   print(
       rows[
           columns
       ]
       .head(
           max_rows
       )
       .to_string(
           index=False
       )
   )

def main() -> None:
   root = Tk()
   root.withdraw()
   # --------------------------------------------------------
   # 1. DATEIEN AUSWÄHLEN
   # --------------------------------------------------------
   schema_pdf = choose_pdf(
       "Strangschema Klimawärme/Kälte auswählen"
   )
   heating_pdfs = choose_pdfs(
       "Heizlast-Grundrisse auswählen"
   )
   cooling_pdfs = choose_pdfs(
       "Kühllast-Grundrisse auswählen"
   )
   # --------------------------------------------------------
   # 2. STRANGSCHEMA
   # --------------------------------------------------------
   schema = (
       extract_and_consolidate_schema(
           schema_pdf
       )
   )
   building = (
       determine_document_building(
           schema
       )
   )
   print()
   print("=" * 80)
   print("SCHEMA")
   print("=" * 80)
   print(
       "Datei:",
       schema_pdf.name,
   )
   print(
       "Erkanntes Gebäude:",
       building,
   )
   if building not in {
       "MIT1",
       "MIT2",
   }:
       print()
       print(
           "WARNUNG: Das Gebäude des "
           "Strangschemas konnte nicht "
           "eindeutig erkannt werden."
       )
       raise SystemExit

   # --------------------------------------------------------
   # 3. HEIZLAST
   # --------------------------------------------------------
   (
       heating,
       heating_check,
   ) = extract_loads_from_pdfs_checked(
       heating_pdfs,
       "Heizlast",
       expected_building=building,
   )
   # --------------------------------------------------------
   # 4. KÜHLLAST
   # --------------------------------------------------------
   (
       cooling,
       cooling_check,
   ) = extract_loads_from_pdfs_checked(
       cooling_pdfs,
       "Kühllast",
       expected_building=building,
   )
   # --------------------------------------------------------
   # 5. DATEIPRÜFUNG AUSGEBEN
   # --------------------------------------------------------
   print()
   print("=" * 80)
   print("DATEIPRÜFUNG HEIZLAST")
   print("=" * 80)
   if heating_check.empty:
       print(
           "Keine Heizlast-Dateien geprüft."
       )
   else:
       print(
           heating_check[
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
   print("=" * 80)
   print("DATEIPRÜFUNG KÜHLLAST")
   print("=" * 80)
   if cooling_check.empty:
       print(
           "Keine Kühllast-Dateien geprüft."
       )
   else:
       print(
           cooling_check[
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
   # --------------------------------------------------------
   # 6. VERGLEICH
   # --------------------------------------------------------
   comparison = (
       compare_loads_with_schema(
           heating,
           cooling,
           schema,
       )
   )
   # --------------------------------------------------------
   # 7. ALLGEMEINE DIAGNOSE
   # --------------------------------------------------------
   print()
   print("=" * 80)
   print("DIAGNOSE")
   print("=" * 80)
   print(
       "Gebäude:",
       building,
   )
   print(
       "Schema-Räume:",
       schema[
           "raumnummer"
       ].nunique()
       if not schema.empty
       else 0,
   )
   print(
       "Heizlast-Räume:",
       heating[
           "raumnummer"
       ].nunique()
       if not heating.empty
       else 0,
   )
   print(
       "Kühllast-Räume:",
       cooling[
           "raumnummer"
       ].nunique()
       if not cooling.empty
       else 0,
   )
   print(
       "Vergleichs-Räume:",
       comparison[
           "raumnummer"
       ].nunique()
       if not comparison.empty
       else 0,
   )
   # --------------------------------------------------------
   # 8. STATUS
   # --------------------------------------------------------
   print()
   print("=" * 80)
   print("GESAMTSTATUS")
   print("=" * 80)
   print(
       comparison[
           "status_gesamt"
       ]
       .value_counts(
           dropna=False
       )
       .to_string()
   )
   print()
   print("=" * 80)
   print("STATUS HEIZUNG")
   print("=" * 80)
   print(
       comparison[
           "status_heizung"
       ]
       .value_counts(
           dropna=False
       )
       .to_string()
   )
   print()
   print("=" * 80)
   print("STATUS KÜHLUNG")
   print("=" * 80)
   print(
       comparison[
           "status_kuehlung"
       ]
       .value_counts(
           dropna=False
       )
       .to_string()
   )
   # --------------------------------------------------------
   # 9. DIAGNOSE DER UNVOLLSTÄNDIGEN FÄLLE
   # --------------------------------------------------------
   print_examples(
       comparison,
       (
           comparison[
               "im_schema"
           ]
& ~comparison[
               "im_heizlastgrundriss"
           ]
       ),
       (
           "IM SCHEMA, ABER NICHT "
           "IM HEIZLAST-GRUNDRISS"
       ),
   )
   print_examples(
       comparison,
       (
           comparison[
               "im_schema"
           ]
& ~comparison[
               "im_kuehllastgrundriss"
           ]
       ),
       (
           "IM SCHEMA, ABER NICHT "
           "IM KÜHLLAST-GRUNDRISS"
       ),
   )
   print_examples(
       comparison,
       (
           ~comparison[
               "im_schema"
           ]
& comparison[
               "im_heizlastgrundriss"
           ]
       ),
       (
           "IM HEIZLAST-GRUNDRISS, "
           "ABER NICHT IM SCHEMA"
       ),
   )
   print_examples(
       comparison,
       (
           ~comparison[
               "im_schema"
           ]
& comparison[
               "im_kuehllastgrundriss"
           ]
       ),
       (
           "IM KÜHLLAST-GRUNDRISS, "
           "ABER NICHT IM SCHEMA"
       ),
   )
   print_examples(
       comparison,
       (
           comparison[
               "status_heizung"
           ]
           == "Grundrisswert fehlt"
       ),
       "HEIZLAST-GRUNDRISSWERT FEHLT",
   )
   print_examples(
       comparison,
       (
           comparison[
               "status_kuehlung"
           ]
           == "Grundrisswert fehlt"
       ),
       "KÜHLLAST-GRUNDRISSWERT FEHLT",
   )
   print_examples(
       comparison,
       (
           comparison[
               "status_heizung"
           ]
           == "Nur im Grundriss"
       ),
       "HEIZLAST NUR IM GRUNDRISS",
   )
   print_examples(
       comparison,
       (
           comparison[
               "status_kuehlung"
           ]
           == "Nur im Grundriss"
       ),
       "KÜHLLAST NUR IM GRUNDRISS",
   )
   print_examples(
       comparison,
       (
           comparison[
               "status_heizung"
           ]
           == "Nur im Schema"
       ),
       "HEIZLAST NUR IM SCHEMA",
   )
   print_examples(
       comparison,
       (
           comparison[
               "status_kuehlung"
           ]
           == "Nur im Schema"
       ),
       "KÜHLLAST NUR IM SCHEMA",
   )
   print_examples(
       comparison,
       (
           comparison[
               "status_gesamt"
           ]
           == "Unvollständig"
       ),
       (
           "BEISPIELE: "
           "GESAMTSTATUS UNVOLLSTÄNDIG"
       ),
       max_rows=25,
   )

if __name__ == "__main__":
   main()