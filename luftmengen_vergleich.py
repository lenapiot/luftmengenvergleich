from __future__ import annotations
"""
Automatischer Luftmengenvergleich für ähnlich aufgebaute Grundriss- und
Lüftungsplan-PDFs.
Das Programm kann mehrere Grundrisse und mehrere Prinzipschemata gleichzeitig
einlesen, die gefundenen Raumdaten zusammenführen und vergleichen.
Installation:
   python -m pip install pymupdf pandas openpyxl
Start:
   python luftmengen_vergleich.py
"""
import pandas as pd
from core.comparison import build_comparison
from core.extraction import (
   extract_clean_lines,
   extract_rooms_from_pages,
   split_lines_by_page,
)
from export.excel_export import export_excel
from export.pdf_export import create_marked_pdf
from ui.dialogs import (
   choose_multiple_pdfs,
   choose_output_folder,
   validate_pdf,
)

def main() -> None:
   """Führt den vollständigen Luftmengenvergleich aus."""
   print()
   print("Luftmengen-Vergleich")
   print("====================")
   print()
   floorplan_pdfs = choose_multiple_pdfs(
       "Grundrisse auswählen"
   )
   schema_pdfs = choose_multiple_pdfs(
       "Lüftungspläne / Prinzipschemata auswählen"
   )
   for floorplan_pdf in floorplan_pdfs:
       validate_pdf(
           floorplan_pdf,
           "Grundriss",
       )
   for schema_pdf in schema_pdfs:
       validate_pdf(
           schema_pdf,
           "Schema",
       )
   output_dir = choose_output_folder(
       floorplan_pdfs[0].parent
   )
   output_excel = (
       output_dir
       / "Luftmengenvergleich_Gesamt.xlsx"
   )
   print("1/6 PDFs werden eingelesen ...")
   print(
       f"   {len(floorplan_pdfs)} Grundriss-PDF(s)"
   )
   print(
       f"   {len(schema_pdfs)} Schema-PDF(s)"
   )
   print("2/6 Räume werden extrahiert ...")
   floorplan_dataframes = []
   for floorplan_pdf in floorplan_pdfs:
       floorplan_records = extract_clean_lines(
           floorplan_pdf
       )
       floorplan_df = extract_rooms_from_pages(
           split_lines_by_page(
               floorplan_records
           ),
           "grundriss",
       )
       if not floorplan_df.empty:
           floorplan_df["quelldatei"] = (
               floorplan_pdf.name
           )
           floorplan_dataframes.append(
               floorplan_df
           )
   if floorplan_dataframes:
       floorplan_raw_df = pd.concat(
           floorplan_dataframes,
           ignore_index=True,
       )
   else:
       floorplan_raw_df = pd.DataFrame()
   schema_dataframes = []
   for schema_pdf in schema_pdfs:
       schema_records = extract_clean_lines(
           schema_pdf
       )
       schema_df = extract_rooms_from_pages(
           split_lines_by_page(
               schema_records
           ),
           "schema",
       )
       if not schema_df.empty:
           schema_df["quelldatei"] = (
               schema_pdf.name
           )
           schema_dataframes.append(
               schema_df
           )
   if schema_dataframes:
       schema_raw_df = pd.concat(
           schema_dataframes,
           ignore_index=True,
       )
   else:
       schema_raw_df = pd.DataFrame()
   print(
       "   Grundrisse:",
       len(floorplan_raw_df),
       "gefundene Datensätze",
   )
   print(
       "   Schemata:",
       len(schema_raw_df),
       "gefundene Datensätze",
   )
   if floorplan_raw_df.empty:
       raise RuntimeError(
           "In den ausgewählten Grundrissen wurden "
           "keine Räume mit ZUL/ABL erkannt."
       )
   if schema_raw_df.empty:
       raise RuntimeError(
           "In den ausgewählten Schemata wurden "
           "keine Räume mit Zuluft/Abluft erkannt."
       )
   print("3/6 Daten werden verglichen ...")
   comparison_df = build_comparison(
       floorplan_raw_df,
       schema_raw_df,
   )
   print("4/6 Grundrisse werden markiert ...")
   marking_dataframes = []
   for floorplan_pdf in floorplan_pdfs:
       output_pdf = (
           output_dir
           / (
               f"{floorplan_pdf.stem}"
               "_markiert.pdf"
           )
       )
       floorplan_name = floorplan_pdf.name
       # Nur Räume auswählen, die tatsächlich
       # in diesem Grundriss gefunden wurden.
       floorplan_mask = (
           comparison_df[
               "quelldateien_grundriss"
           ]
           .fillna("")
           .apply(
               lambda value: floorplan_name
               in {
                   filename.strip()
                   for filename in str(value).split("|")
                   if filename.strip()
               }
           )
       )
       floorplan_comparison_df = (
           comparison_df[
               floorplan_mask
           ].copy()
       )
       marking_df = create_marked_pdf(
           floorplan_pdf,
           output_pdf,
           floorplan_comparison_df,
       )
       marking_df.insert(
           0,
           "grundrissdatei",
           floorplan_pdf.name,
       )
       marking_df.insert(
           1,
           "ausgabedatei",
           output_pdf.name,
       )
       marking_dataframes.append(
           marking_df
       )
       print(
           "   Erstellt:",
           output_pdf.name,
       )
   if marking_dataframes:
       combined_marking_df = pd.concat(
           marking_dataframes,
           ignore_index=True,
       )
   else:
       combined_marking_df = pd.DataFrame()
   print(
       "5/6 Excel-Auswertung wird erstellt ..."
   )
   export_excel(
       output_excel,
       floorplan_raw_df,
       schema_raw_df,
       comparison_df,
       combined_marking_df,
       floorplan_pdfs,
       schema_pdfs,
   )
   print("6/6 Fertig.")
   print()
   print("Excel-Auswertung:")
   print(output_excel)
   print()
   print("Markierte Grundrisse:")
   for floorplan_pdf in floorplan_pdfs:
       print(
           output_dir
           / (
               f"{floorplan_pdf.stem}"
               "_markiert.pdf"
           )
       )
   print()
   print("Statusübersicht:")
   print(
       comparison_df["status"]
       .astype(str)
       .value_counts()
       .to_string()
   )

if __name__ == "__main__":
   main()