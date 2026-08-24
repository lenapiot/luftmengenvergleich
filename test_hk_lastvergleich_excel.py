from pathlib import Path
from hk.lastvergleich import (
   extract_loads_from_pdfs_checked,
   extract_and_consolidate_schema,
   compare_loads_with_schema,
   determine_document_building,
)
from hk.lastvergleich_excel import (
   export_load_comparison_excel,
)

# ============================================================
# DATEIPFADE
# ============================================================
BASE = Path(
   r"C:\Users\PIOL\OneDrive - eicher+pauli\Python Codes\HLKS Code\Projekt Python Heizung"
)

SCHEMA_PDF = BASE / (
   "USZ_MIT2_52_HEK_150405-SH_00_001 - "
   "Strangschema Klimawärme_Kälte MIT2.pdf"
)

HEATING_PDFS = [
   BASE
   / "Heizlast"
   / (
       "USZ-MIT2-51-HEK01-PG-GR_H-O-150xxx-02 - "
       "Auslegung Verteilung EBENE H.pdf"
   ),
   BASE
   / "Heizlast"
   / (
       "USZ-MIT2-51-HEK01-PG-GR_J-O-150xxx-13 - "
       "Auslegung Verteilung EBENE J.pdf"
   ),
]

COOLING_PDFS = [
   BASE
   / "Kühllast"
   / (
       "USZ-MIT2-51-HEK01-PG-GR_H-O-150238-01 - "
       "Kühllast EBENE_H.pdf"
   ),
   BASE
   / "Kühllast"
   / (
       "USZ-MIT2-51-HEK01-PG-GR_J-O-150240-01 - "
       "Kühllast EBENE_J.pdf"
   ),
]

OUTPUT_PATH = (
   BASE
   / "Lastvergleich_Heizung_Kaelte_TEST.xlsx"
)

# ============================================================
# DATEIEN PRÜFEN
# ============================================================
def check_files() -> None:
   files = [
       SCHEMA_PDF,
       *HEATING_PDFS,
       *COOLING_PDFS,
   ]
   print()
   print("=" * 70)
   print("DATEIPRÜFUNG")
   print("=" * 70)
   missing = []
   for path in files:
       exists = path.exists()
       print(
           "OK     "
           if exists
           else "FEHLT  ",
           path,
       )
       if not exists:
           missing.append(
               path
           )
   if missing:
       print()
       print(
           "Mindestens eine Datei wurde "
           "nicht gefunden."
       )
       print(
           "Bitte Dateinamen/Pfade prüfen."
       )
       raise SystemExit

# ============================================================
# HAUPTPROGRAMM
# ============================================================
def main() -> None:
   check_files()
   # --------------------------------------------------------
   # STRANGSCHEMA
   # --------------------------------------------------------
   print()
   print("=" * 70)
   print("STRANGSCHEMA")
   print("=" * 70)
   schema = (
       extract_and_consolidate_schema(
           SCHEMA_PDF
       )
   )
   building = (
       determine_document_building(
           schema
       )
   )
   print(
       "Gebäude:",
       building,
   )
   print(
       "Schema-Räume:",
       len(schema),
   )
   if building not in {
       "MIT1",
       "MIT2",
   }:
       raise SystemExit(
           "Gebäude des Strangschemas "
           "konnte nicht eindeutig "
           "erkannt werden."
       )
   # --------------------------------------------------------
   # HEIZLAST
   # --------------------------------------------------------
   print()
   print("=" * 70)
   print("HEIZLAST")
   print("=" * 70)
   (
       heating,
       heating_check,
   ) = extract_loads_from_pdfs_checked(
       HEATING_PDFS,
       "Heizlast",
       expected_building=building,
   )
   print(
       "Räume:",
       heating[
           "raumnummer"
       ].nunique()
       if not heating.empty
       else 0,
   )
   # --------------------------------------------------------
   # KÜHLLAST
   # --------------------------------------------------------
   print()
   print("=" * 70)
   print("KÜHLLAST")
   print("=" * 70)
   (
       cooling,
       cooling_check,
   ) = extract_loads_from_pdfs_checked(
       COOLING_PDFS,
       "Kühllast",
       expected_building=building,
   )
   print(
       "Räume:",
       cooling[
           "raumnummer"
       ].nunique()
       if not cooling.empty
       else 0,
   )
   # --------------------------------------------------------
   # VERGLEICH
   # --------------------------------------------------------
   print()
   print("=" * 70)
   print("VERGLEICH")
   print("=" * 70)
   comparison = (
       compare_loads_with_schema(
           heating,
           cooling,
           schema,
       )
   )
   scope = comparison.attrs.get(
       "vergleichsumfang",
       {},
   )
   print(
       scope.get(
           "hinweis",
           "",
       )
   )
   print()
   print(
       "Berücksichtigte Ebenen:",
       ", ".join(
           scope.get(
               "beruecksichtigte_ebenen",
               [],
           )
       ),
   )
   print(
       "Nicht geprüfte Schema-Ebenen:",
       ", ".join(
           scope.get(
               "ausgeschlossene_schema_ebenen",
               [],
           )
       ),
   )
   print()
   print(
       "Status:"
   )
   print(
       comparison[
           "status_gesamt"
       ]
       .value_counts()
       .to_string()
   )
   # --------------------------------------------------------
   # EXCEL EXPORTIEREN
   # --------------------------------------------------------
   print()
   print("=" * 70)
   print("EXCEL-EXPORT")
   print("=" * 70)
   result_path = (
       export_load_comparison_excel(
           output_path=OUTPUT_PATH,
           comparison=comparison,
           schema_pdf=SCHEMA_PDF,
           heating_pdfs=HEATING_PDFS,
           cooling_pdfs=COOLING_PDFS,
           building=building,
           heating_check=heating_check,
           cooling_check=cooling_check,
       )
   )
   print()
   print(
       "FERTIG!"
   )
   print(
       "Excel erstellt unter:"
   )
   print(
       result_path
   )

if __name__ == "__main__":
   main()