from __future__ import annotations

from pathlib import Path
from tkinter import Tk, filedialog, messagebox

from luft.nummernkontrolle import run_luft_number_check


def main() -> None:
    root = Tk()
    root.withdraw()

    schema_pdf = filedialog.askopenfilename(
        title="Lüftungs-Prinzipschema auswählen",
        filetypes=[
            ("PDF-Dateien", "*.pdf"),
            ("Alle Dateien", "*.*"),
        ],
    )

    if not schema_pdf:
        return

    bml_excel = filedialog.askopenfilename(
        title="Lüftungs-BML auswählen",
        filetypes=[
            ("Excel-Dateien", "*.xlsx *.xlsm"),
            ("Alle Dateien", "*.*"),
        ],
    )

    if not bml_excel:
        return

    output_dir = filedialog.askdirectory(
        title="Ausgabeordner auswählen",
    )

    if not output_dir:
        return

    try:
        output_path = run_luft_number_check(
            schema_pdf=Path(schema_pdf),
            bml_excel=Path(bml_excel),
            output_dir=Path(output_dir),
            name="TEST_Lueftung_Schemanummernkontrolle",
        )

    except Exception as error:
        messagebox.showerror(
            "Fehler",
            str(error),
        )
        raise

    messagebox.showinfo(
        "Fertig",
        (
            "Die Lüftungs-Schemanummernkontrolle "
            "wurde erfolgreich erstellt:\n\n"
            f"{output_path}"
        ),
    )


if __name__ == "__main__":
    main()
