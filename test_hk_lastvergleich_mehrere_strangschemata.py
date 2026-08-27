from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import Tk, filedialog, messagebox, simpledialog

import pandas as pd

from hk.lastvergleich import (
    compare_loads_with_schema,
    determine_document_building,
    extract_and_consolidate_schema,
    extract_loads_from_excel_checked,
    extract_loads_from_pdfs_checked,
)
from hk.lastvergleich_excel import export_load_comparison_excel


def _choose_schema_pdfs() -> list[Path]:
    paths = filedialog.askopenfilenames(
        title="Ein oder mehrere Strangschemata auswählen",
        filetypes=[
            ("PDF-Dateien", "*.pdf"),
            ("Alle Dateien", "*.*"),
        ],
    )

    return [
        Path(path)
        for path in paths
    ]


def _choose_source_type() -> str | None:
    choice = simpledialog.askinteger(
        "Lastquelle",
        (
            "Welche Lastquelle soll getestet werden?\n\n"
            "1 = Excel\n"
            "2 = PDF-Grundrisse"
        ),
        minvalue=1,
        maxvalue=2,
    )

    if choice is None:
        return None

    return {
        1: "excel",
        2: "pdf",
    }[choice]


def _choose_mode() -> str | None:
    choice = simpledialog.askinteger(
        "Prüfumfang",
        (
            "Welche Lasten sollen verglichen werden?\n\n"
            "1 = nur Heizlast\n"
            "2 = nur Kühllast\n"
            "3 = Heiz- und Kühllast"
        ),
        minvalue=1,
        maxvalue=3,
    )

    if choice is None:
        return None

    return {
        1: "heizung",
        2: "kuehlung",
        3: "beides",
    }[choice]


def _choose_excel() -> Path | None:
    path = filedialog.askopenfilename(
        title="Gemeinsame Heiz-/Kühllast-Excel auswählen",
        filetypes=[
            ("Excel-Dateien", "*.xlsx *.xlsm"),
            ("Alle Dateien", "*.*"),
        ],
    )

    return Path(path) if path else None


def _choose_heating_pdfs() -> list[Path]:
    paths = filedialog.askopenfilenames(
        title="Heizlast-Grundrisse auswählen",
        filetypes=[
            ("PDF-Dateien", "*.pdf"),
            ("Alle Dateien", "*.*"),
        ],
    )

    return [
        Path(path)
        for path in paths
    ]


def _choose_cooling_pdfs() -> list[Path]:
    paths = filedialog.askopenfilenames(
        title="Kühllast-Grundrisse auswählen",
        filetypes=[
            ("PDF-Dateien", "*.pdf"),
            ("Alle Dateien", "*.*"),
        ],
    )

    return [
        Path(path)
        for path in paths
    ]


def _choose_output_dir() -> Path | None:
    path = filedialog.askdirectory(
        title="Ausgabeordner auswählen",
    )

    return Path(path) if path else None


def _split_checks(
    check_dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if check_dataframe.empty:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
        )

    heating_check = (
        check_dataframe.loc[
            check_dataframe[
                "lastart"
            ].astype(str)
            == "Heizlast"
        ]
        .copy()
        .reset_index(drop=True)
    )

    cooling_check = (
        check_dataframe.loc[
            check_dataframe[
                "lastart"
            ].astype(str)
            == "Kühllast"
        ]
        .copy()
        .reset_index(drop=True)
    )

    return (
        heating_check,
        cooling_check,
    )


def main() -> None:
    root = Tk()
    root.withdraw()

    schema_paths = _choose_schema_pdfs()

    if not schema_paths:
        return

    source_type = _choose_source_type()

    if source_type is None:
        return

    mode = _choose_mode()

    if mode is None:
        return

    compare_heating = mode in {
        "heizung",
        "beides",
    }

    compare_cooling = mode in {
        "kuehlung",
        "beides",
    }

    excel_path: Path | None = None
    heating_pdfs: list[Path] = []
    cooling_pdfs: list[Path] = []

    if source_type == "excel":
        excel_path = _choose_excel()

        if excel_path is None:
            return

    else:
        if compare_heating:
            heating_pdfs = _choose_heating_pdfs()

            if not heating_pdfs:
                messagebox.showerror(
                    "Fehler",
                    "Für Heizlast wurden keine PDFs ausgewählt.",
                )
                return

        if compare_cooling:
            cooling_pdfs = _choose_cooling_pdfs()

            if not cooling_pdfs:
                messagebox.showerror(
                    "Fehler",
                    "Für Kühllast wurden keine PDFs ausgewählt.",
                )
                return

    output_dir = _choose_output_dir()

    if output_dir is None:
        return

    created_files: list[Path] = []
    summary_lines: list[str] = []

    try:
        for schema_path in schema_paths:
            # ------------------------------------------------
            # 1. STRANGSCHEMA EINZELN AUSWERTEN
            # ------------------------------------------------

            schema = extract_and_consolidate_schema(
                schema_path
            )

            building = determine_document_building(
                schema
            )

            if building not in {
                "MIT1",
                "MIT2",
                "MIT12",
            }:
                raise ValueError(
                    "Gebäudeumfang des Strangschemas konnte "
                    f"nicht erkannt werden:\n{schema_path.name}"
                )

            # ------------------------------------------------
            # 2. LASTQUELLE FÜR DIESES SCHEMA NEU FILTERN
            # ------------------------------------------------

            if source_type == "excel":
                assert excel_path is not None

                (
                    heating,
                    cooling,
                    check_dataframe,
                ) = extract_loads_from_excel_checked(
                    excel_path=excel_path,
                    mode=mode,
                    expected_building=building,
                )

                (
                    heating_check,
                    cooling_check,
                ) = _split_checks(
                    check_dataframe
                )

                heating_sources = (
                    [excel_path]
                    if compare_heating
                    else []
                )

                cooling_sources = (
                    [excel_path]
                    if compare_cooling
                    else []
                )

            else:
                if compare_heating:
                    (
                        heating,
                        heating_check,
                    ) = extract_loads_from_pdfs_checked(
                        pdf_paths=heating_pdfs,
                        load_type="Heizlast",
                        expected_building=building,
                    )
                else:
                    heating = pd.DataFrame()
                    heating_check = pd.DataFrame()

                if compare_cooling:
                    (
                        cooling,
                        cooling_check,
                    ) = extract_loads_from_pdfs_checked(
                        pdf_paths=cooling_pdfs,
                        load_type="Kühllast",
                        expected_building=building,
                    )
                else:
                    cooling = pd.DataFrame()
                    cooling_check = pd.DataFrame()

                heating_sources = (
                    heating_pdfs
                    if compare_heating
                    else []
                )

                cooling_sources = (
                    cooling_pdfs
                    if compare_cooling
                    else []
                )

            # ------------------------------------------------
            # 3. VERGLEICH
            # ------------------------------------------------

            comparison = compare_loads_with_schema(
                heating=heating,
                cooling=cooling,
                consolidated_schema=schema,
                compare_heating=compare_heating,
                compare_cooling=compare_cooling,
            )

            # ------------------------------------------------
            # 4. EIGENE ERGEBNISDATEI FÜR DIESES SCHEMA
            # ------------------------------------------------

            timestamp = datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )

            safe_schema_stem = (
                schema_path.stem
                .replace(" ", "_")
                .replace("/", "_")
                .replace("\\", "_")
            )

            output_path = (
                output_dir
                / (
                    f"TEST_Lastvergleich_"
                    f"{building}_"
                    f"{safe_schema_stem}_"
                    f"{timestamp}.xlsx"
                )
            )

            export_load_comparison_excel(
                output_path=output_path,
                comparison=comparison,
                schema_pdf=schema_path,
                heating_pdfs=heating_sources,
                cooling_pdfs=cooling_sources,
                building=building,
                heating_check=heating_check,
                cooling_check=cooling_check,
            )

            created_files.append(
                output_path
            )

            counts = (
                comparison[
                    "status_gesamt"
                ]
                .value_counts()
                .to_dict()
            )

            status_text = ", ".join(
                f"{status}: {count}"
                for status, count
                in counts.items()
            )

            summary_lines.append(
                (
                    f"{schema_path.name}\n"
                    f"  Gebäude: {building}\n"
                    f"  Räume im Vergleich: {len(comparison)}\n"
                    f"  {status_text}"
                )
            )

        messagebox.showinfo(
            "Test erfolgreich",
            (
                f"{len(created_files)} Ergebnisdatei(en) wurden erstellt.\n\n"
                + "\n\n".join(
                    summary_lines
                )
                + "\n\nAusgabeordner:\n"
                + str(output_dir)
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
