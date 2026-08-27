from __future__ import annotations

import csv
from pathlib import Path
from tkinter import Tk, filedialog, messagebox, simpledialog

from hk.lastvergleich_excel_input import (
    extract_loads_from_excel,
    summarize_excel_records,
)


def main() -> None:
    root = Tk()
    root.withdraw()

    excel_path = filedialog.askopenfilename(
        title="Heiz-/Kühllast-Excel auswählen",
        filetypes=[
            ("Excel-Dateien", "*.xlsx *.xlsm"),
            ("Alle Dateien", "*.*"),
        ],
    )

    if not excel_path:
        return

    mode_choice = simpledialog.askinteger(
        "Prüfumfang",
        (
            "Welche Lasten sollen extrahiert werden?\n\n"
            "1 = nur Heizlast\n"
            "2 = nur Kühllast\n"
            "3 = Heiz- und Kühllast"
        ),
        minvalue=1,
        maxvalue=3,
    )

    if mode_choice is None:
        return

    mode_map = {
        1: "heizung",
        2: "kuehlung",
        3: "beides",
    }

    mode = mode_map[
        mode_choice
    ]

    try:
        records = extract_loads_from_excel(
            excel_path=excel_path,
            mode=mode,
        )

        summary = summarize_excel_records(
            records
        )

        output_path = (
            Path(excel_path).parent
            / "TEST_Excel_Lastdaten.csv"
        )

        with output_path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            writer = csv.writer(
                file,
                delimiter=";",
            )

            writer.writerow(
                [
                    "Raum Original",
                    "Raum Vergleich",
                    "Heizlast W",
                    "Kühllast W",
                    "Excel-Zeile",
                ]
            )

            for record in records:
                writer.writerow(
                    [
                        record.raum,
                        record.raum_key,
                        (
                            ""
                            if record.heizlast_w is None
                            else record.heizlast_w
                        ),
                        (
                            ""
                            if record.kuehllast_w is None
                            else record.kuehllast_w
                        ),
                        record.excel_zeile,
                    ]
                )

        messagebox.showinfo(
            "Test erfolgreich",
            (
                "Excel-Extraktion erfolgreich.\n\n"
                f"Räume: {summary['anzahl_raeume']}\n"
                f"Mit Heizlast: {summary['mit_heizlast']}\n"
                f"Mit Kühllast: {summary['mit_kuehllast']}\n"
                f"Heizlast = 0 W: {summary['heizlast_0w']}\n"
                f"Kühllast = 0 W: {summary['kuehllast_0w']}\n\n"
                "Testdatei:\n"
                f"{output_path}"
            ),
        )

    except Exception as error:
        messagebox.showerror(
            "Fehler",
            str(error),
        )
        raise


if __name__ == "__main__":
    main()
