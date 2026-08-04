from __future__ import annotations
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from luftmengen_vergleich import run_comparison

class LuftmengenGUI:
   def __init__(self) -> None:
       self.root = tk.Tk()
       self.root.title("Luftmengenvergleich")
       self.root.geometry("700x520")
       self.root.resizable(False, False)
       self.floorplan_pdfs: list[Path] = []
       self.schema_pdfs: list[Path] = []
       self.output_dir: Path | None = None
       self.create_widgets()
   def create_widgets(self) -> None:
       title = tk.Label(
           self.root,
           text="Luftmengenvergleich",
           font=("Segoe UI", 18, "bold"),
       )
       title.pack(pady=15)
       tk.Button(
           self.root,
           text="Grundrisse auswählen",
           width=30,
           command=self.choose_floorplans,
       ).pack(pady=5)
       self.floorplan_label = tk.Label(
           self.root,
           text="Keine Grundrisse ausgewählt",
       )
       self.floorplan_label.pack()
       tk.Button(
           self.root,
           text="Grundriss-Auswahl leeren",
           width=30,
           command=self.clear_floorplans,
       ).pack(pady=5)
       tk.Button(
           self.root,
           text="Prinzipschemata auswählen",
           width=30,
           command=self.choose_schemas,
       ).pack(pady=10)
       self.schema_label = tk.Label(
           self.root,
           text="Keine Prinzipschemata ausgewählt",
       )
       self.schema_label.pack()
       tk.Button(
           self.root,
           text="Schema-Auswahl leeren",
           width=30,
           command=self.clear_schemas,
       ).pack(pady=5)
       tk.Button(
           self.root,
           text="Ausgabeordner auswählen",
           width=30,
           command=self.choose_output,
       ).pack(pady=10)
       self.output_label = tk.Label(
           self.root,
           text="Kein Ausgabeordner ausgewählt",
           wraplength=620,
       )
       self.output_label.pack()
       tk.Button(
           self.root,
           text="Vergleich starten",
           width=30,
           height=2,
           command=self.start,
       ).pack(pady=25)
       self.status = tk.Label(
           self.root,
           text="Bereit",
           fg="blue",
           wraplength=620,
       )
       self.status.pack()
   def choose_floorplans(self) -> None:
       selected = filedialog.askopenfilenames(
           title="Grundrisse auswählen",
           filetypes=[("PDF-Dateien", "*.pdf")],
       )
       new_files = [
           Path(path)
           for path in selected
       ]
       for path in new_files:
           if path not in self.floorplan_pdfs:
               self.floorplan_pdfs.append(path)
       self.update_floorplan_label()
   def choose_schemas(self) -> None:
       selected = filedialog.askopenfilenames(
           title="Prinzipschemata auswählen",
           filetypes=[("PDF-Dateien", "*.pdf")],
       )
       new_files = [
           Path(path)
           for path in selected
       ]
       for path in new_files:
           if path not in self.schema_pdfs:
               self.schema_pdfs.append(path)
       self.update_schema_label()
   def clear_floorplans(self) -> None:
       self.floorplan_pdfs.clear()
       self.update_floorplan_label()
   def clear_schemas(self) -> None:
       self.schema_pdfs.clear()
       self.update_schema_label()
   def update_floorplan_label(self) -> None:
       count = len(self.floorplan_pdfs)
       if count == 0:
           text = "Keine Grundrisse ausgewählt"
       elif count == 1:
           text = "1 Grundriss ausgewählt"
       else:
           text = f"{count} Grundrisse ausgewählt"
       self.floorplan_label.config(
           text=text
       )
   def update_schema_label(self) -> None:
       count = len(self.schema_pdfs)
       if count == 0:
           text = "Keine Prinzipschemata ausgewählt"
       elif count == 1:
           text = "1 Prinzipschema ausgewählt"
       else:
           text = f"{count} Prinzipschemata ausgewählt"
       self.schema_label.config(
           text=text
       )
   def choose_output(self) -> None:
       folder = filedialog.askdirectory(
           title="Ausgabeordner auswählen",
       )
       if folder:
           self.output_dir = Path(folder)
           self.output_label.config(
               text=str(self.output_dir)
           )
   def set_status(
       self,
       text: str,
   ) -> None:
       self.status.config(
           text=text
       )
       self.root.update_idletasks()
   def start(self) -> None:
       if not self.floorplan_pdfs:
           messagebox.showerror(
               "Fehler",
               "Bitte mindestens einen Grundriss auswählen.",
           )
           return
       if not self.schema_pdfs:
           messagebox.showerror(
               "Fehler",
               "Bitte mindestens ein Prinzipschema auswählen.",
           )
           return
       if self.output_dir is None:
           messagebox.showerror(
               "Fehler",
               "Bitte einen Ausgabeordner auswählen.",
           )
           return
       try:
           self.set_status(
               "Vergleich wird gestartet ..."
           )
           run_comparison(
               floorplan_pdfs=self.floorplan_pdfs,
               schema_pdfs=self.schema_pdfs,
               output_dir=self.output_dir,
               status_callback=self.set_status,
           )
           self.set_status(
               "Fertig"
           )
           messagebox.showinfo(
               "Fertig",
               "Der Vergleich wurde erfolgreich abgeschlossen.",
           )
       except Exception as error:
           self.set_status(
               "Fehler"
           )
           messagebox.showerror(
               "Fehler",
               str(error),
           )
   def run(self) -> None:
       self.root.mainloop()

def start_gui() -> None:
   app = LuftmengenGUI()
   app.run()