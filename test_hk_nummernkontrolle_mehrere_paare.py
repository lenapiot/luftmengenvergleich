from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from hk.nummernkontrolle import run_hk_number_check


def ask_yes_no(title: str, message: str) -> bool:
    return messagebox.askyesno(
        title,
        message,
    )


def choose_schema_pdf(pair_number: int) -> str | None:
    return filedialog.askopenfilename(
        title=f"Paar {pair_number}: Prinzipschema-PDF auswählen",
        filetypes=[
            ("PDF-Dateien", "*.pdf"),
        ],
    )


def choose_bml_excel(pair_number: int) -> str | None:
    return filedialog.askopenfilename(
        title=f"Paar {pair_number}: Passende BML-Excel auswählen",
        filetypes=[
            ("Excel-Dateien", "*.xlsx"),
        ],
    )


def choose_pair_name(
    pair_number: int,
    schema_pdf: str,
) -> str:
    default_name = Path(schema_pdf).stem

    pair_name = simpledialog.askstring(
        title=f"Paar {pair_number}: Name der Auswertung",
        prompt=(
            "Wie soll diese Auswertung heissen?\n\n"
            "Beispiele:\n"
            "- Heizung_Kaelte\n"
            "- Verteilung_MIT1\n"
            "- Verteilung_MIT2"
        ),
        initialvalue=default_name,
    )

    if pair_name is None or not pair_name.strip():
        return default_name

    return pair_name.strip()


def collect_pairs() -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []

    pair_number = 1

    while True:
        schema_pdf = choose_schema_pdf(
            pair_number
        )

        if not schema_pdf:
            if not pairs:
                messagebox.showinfo(
                    "Abgebrochen",
                    "Es wurde kein Schema ausgewählt.",
                )
            break

        bml_excel = choose_bml_excel(
            pair_number
        )

        if not bml_excel:
            messagebox.showinfo(
                "Abgebrochen",
                (
                    "Es wurde keine BML ausgewählt. "
                    "Dieses Paar wird nicht hinzugefügt."
                ),
            )
            break

        pair_name = choose_pair_name(
            pair_number=pair_number,
            schema_pdf=schema_pdf,
        )

        pairs.append(
            {
                "name": pair_name,
                "schema_pdf": schema_pdf,
                "bml_excel": bml_excel,
            }
        )

        add_another = ask_yes_no(
            "Weiteres Paar?",
            (
                "Dieses Paar wurde hinzugefügt.\n\n"
                "Möchtest du noch ein weiteres Schema/BML-Paar "
                "auswählen?"
            ),
        )

        if not add_another:
            break

        pair_number += 1

    return pairs


def run_all_pairs(
    pairs: list[dict[str, str]],
    output_dir: str,
) -> list[Path]:
    output_paths: list[Path] = []

    for index, pair in enumerate(
        pairs,
        start=1,
    ):
        output_path = run_hk_number_check(
            schema_pdf=pair["schema_pdf"],
            bml_excel=pair["bml_excel"],
            output_dir=output_dir,
            name=f"HK_Nummernkontrolle_{index}_{pair['name']}",
        )

        output_paths.append(
            output_path
        )

    return output_paths


def main() -> None:
    root = tk.Tk()
    root.withdraw()

    messagebox.showinfo(
        "HK-Nummernkontrolle",
        (
            "Du kannst jetzt mehrere Schema/BML-Paare auswählen.\n\n"
            "Für jedes Paar gilt:\n"
            "1. Prinzipschema-PDF auswählen\n"
            "2. passende BML-Excel auswählen\n"
            "3. Namen für die Auswertung eingeben\n\n"
            "Danach wird pro Paar eine eigene Excel-Auswertung erstellt."
        ),
    )

    pairs = collect_pairs()

    if not pairs:
        return

    output_dir = filedialog.askdirectory(
        title="Ausgabeordner für alle Auswertungen auswählen",
    )

    if not output_dir:
        return

    try:
        output_paths = run_all_pairs(
            pairs=pairs,
            output_dir=output_dir,
        )

    except Exception as error:
        messagebox.showerror(
            "Fehler",
            str(error),
        )
        return

    result_text = "\n".join(
        str(path)
        for path in output_paths
    )

    messagebox.showinfo(
        "Fertig",
        (
            "Die HK-Nummernkontrolle wurde abgeschlossen.\n\n"
            f"Erstellte Dateien: {len(output_paths)}\n\n"
            f"{result_text}"
        ),
    )


if __name__ == "__main__":
    main()
