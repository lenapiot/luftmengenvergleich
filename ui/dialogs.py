from pathlib import Path

def choose_pdf(title: str) -> Path:
   """Öffnet einen Dateidialog zur Auswahl einer PDF-Datei."""
   from tkinter import Tk, filedialog
   root = Tk()
   root.withdraw()
   root.attributes("-topmost", True)
   selected = filedialog.askopenfilename(
       title=title,
       filetypes=[("PDF-Dateien", "*.pdf")],
   )
   root.destroy()
   if not selected:
       raise SystemExit("Keine PDF-Datei ausgewählt.")
   return Path(selected)

def choose_output_folder(initial_folder: Path) -> Path:
   """Öffnet einen Dialog zur Auswahl des Ausgabeordners."""
   from tkinter import Tk, filedialog
   root = Tk()
   root.withdraw()
   root.attributes("-topmost", True)
   selected = filedialog.askdirectory(
       title="Ausgabeordner auswählen",
       initialdir=str(initial_folder),
   )
   root.destroy()
   if not selected:
       return initial_folder
   return Path(selected)

def validate_pdf(path: Path, description: str) -> None:
   """Prüft, ob die ausgewählte Datei existiert und ein PDF ist."""
   if not path.exists():
       raise FileNotFoundError(
           f"{description} wurde nicht gefunden: {path}"
       )
   if path.suffix.lower() != ".pdf":
       raise ValueError(
           f"{description} ist keine PDF-Datei: {path}"
       )


def choose_multiple_pdfs(title: str) -> list[Path]:
   """Öffnet einen Dateidialog zur Auswahl mehrerer PDF-Dateien."""
   from tkinter import Tk, filedialog
   root = Tk()
   root.withdraw()
   root.attributes("-topmost", True)
   selected = filedialog.askopenfilenames(
       title=title,
       filetypes=[("PDF-Dateien", "*.pdf")],
   )
   root.destroy()
   if not selected:
       raise SystemExit("Keine PDF-Dateien ausgewählt.")
   return [Path(path) for path in selected]