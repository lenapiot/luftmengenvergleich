from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from hk.nummernkontrolle import run_hk_number_check

def main() -> None:
   root = tk.Tk()
   root.withdraw()
   schema_pdf = filedialog.askopenfilename(
       title="Prinzipschema-PDF auswählen",
       filetypes=[
           ("PDF-Dateien", "*.pdf"),
       ],
   )
   if not schema_pdf:
       return
   bml_excel = filedialog.askopenfilename(
       title="Passende BML-Excel auswählen",
       filetypes=[
           ("Excel-Dateien", "*.xlsx"),
       ],
   )
   if not bml_excel:
       return
   output_dir = filedialog.askdirectory(
       title="Ausgabeordner auswählen",
   )
   if not output_dir:
       return
   schema_name = Path(
       schema_pdf
   ).stem
   try:
       output_path = run_hk_number_check(
           schema_pdf=schema_pdf,
           bml_excel=bml_excel,
           output_dir=output_dir,
           name=f"HK_Nummernkontrolle_{schema_name}",
       )
   except Exception as error:
       messagebox.showerror(
           "Fehler",
           str(error),
       )
       return
   messagebox.showinfo(
       "Fertig",
       (
           "Die HK-Nummernkontrolle wurde abgeschlossen.\n\n"
           f"Ergebnis:\n{output_path}"
       ),
   )

if __name__ == "__main__":
   main()


