from __future__ import annotations

"""
Automatischer Luftmengenvergleich für ähnlich aufgebaute Grundriss- und
Lüftungsplan-PDFs.

Das Programm kann mehrere Grundrisse und mehrere Prinzipschemata gleichzeitig
einlesen, die gefundenen Raumdaten zusammenführen und vergleichen.

Start:
    python luftmengen_vergleich.py
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd

from config.settings import (
    DEFAULT_ROOM_PATTERN_KEY,
    get_room_pattern,
)

from core.comparison import build_comparison

from core.extraction import (
    extract_clean_lines,
    extract_rooms_from_pages,
    split_lines_by_page,
    extract_numeric_schema_blocks,
    extract_numeric_floorplan_rooms,
    map_numeric_schema_by_ep,
)

from export.excel_export import export_excel
from export.pdf_export import create_marked_pdf
from ui.dialogs import validate_pdf


StatusCallback = Callable[[str], None]


def run_comparison(
    floorplan_pdfs: Sequence[Path],
    schema_pdfs: Sequence[Path],
    output_dir: Path,
    status_callback: StatusCallback | None = None,
    room_pattern_key: str = DEFAULT_ROOM_PATTERN_KEY,
    custom_room_pattern: str | None = None,
) -> dict[str, object]:
    """
    Führt den vollständigen Luftmengenvergleich aus.

    Spezialfall «Numerisch - Geschoss.Raum»:
    - Grundriss: echte Raumnummern wie -01.227 / 00.302 / 01.514.
    - Schema: falls keine solchen Nummern vorhanden sind, werden
      Raumname + Raumfläche + ZUL/ABL aus dem Schema gelesen.
    - Die Schema-Blöcke werden über die gemeinsame ep-Nummer
      dem echten Grundrissraum zugeordnet.
    """

    def report(message: str) -> None:
        print(message)

        if status_callback is not None:
            status_callback(message)

    floorplan_pdfs = [
        Path(path)
        for path in floorplan_pdfs
    ]

    schema_pdfs = [
        Path(path)
        for path in schema_pdfs
    ]

    output_dir = Path(output_dir)

    if not floorplan_pdfs:
        raise ValueError(
            "Es wurden keine Grundrisse ausgewählt."
        )

    if not schema_pdfs:
        raise ValueError(
            "Es wurden keine Prinzipschemata ausgewählt."
        )

    room_pattern = get_room_pattern(
        preset_key=room_pattern_key,
        custom_pattern=custom_room_pattern,
    )

    numeric_floor_room_mode = (
        room_pattern_key == "numeric_floor_room"
        and custom_room_pattern is None
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

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_excel = (
        output_dir
        / "Luftmengenvergleich_Gesamt.xlsx"
    )

    report("1/6 PDFs werden eingelesen ...")
    report(
        f"   {len(floorplan_pdfs)} Grundriss-PDF(s)"
    )
    report(
        f"   {len(schema_pdfs)} Schema-PDF(s)"
    )

    report("2/6 Räume werden extrahiert ...")

    # ========================================================
    # GRUNDRISSE
    # ========================================================

    floorplan_dataframes: list[pd.DataFrame] = []

    for floorplan_pdf in floorplan_pdfs:
        report(
            f"   Grundriss wird eingelesen: "
            f"{floorplan_pdf.name}"
        )

        if numeric_floor_room_mode:
            floorplan_df = (
                extract_numeric_floorplan_rooms(
                    floorplan_pdf,
                    room_pattern,
                )
            )

        else:
            floorplan_records = extract_clean_lines(
                floorplan_pdf
            )

            floorplan_df = extract_rooms_from_pages(
                split_lines_by_page(
                    floorplan_records
                ),
                "grundriss",
                room_pattern,
            )

        if not floorplan_df.empty:
            floorplan_df = floorplan_df.copy()

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

    # ========================================================
    # SCHEMATA
    # ========================================================

    schema_dataframes: list[pd.DataFrame] = []

    for schema_pdf in schema_pdfs:
        report(
            f"   Schema wird eingelesen: "
            f"{schema_pdf.name}"
        )

        schema_records = extract_clean_lines(
            schema_pdf
        )

        schema_pages = split_lines_by_page(
            schema_records
        )

        if numeric_floor_room_mode:
            # 1. Versuch: echte numerische Raumnummern stehen
            # direkt im Schema.
            direct_schema_df = extract_rooms_from_pages(
                schema_pages,
                "schema",
                room_pattern,
            )

            if not direct_schema_df.empty:
                schema_df = direct_schema_df

            else:
                # 2. Versuch: Schema enthält keine echte Raumnummer.
                # Dann über die gemeinsame ep-Nummer zuordnen.
                schema_blocks_df = (
                    extract_numeric_schema_blocks(
                        schema_pages
                    )
                )

                schema_df = (
                    map_numeric_schema_by_ep(
                        floorplan_raw_df,
                        schema_blocks_df,
                    )
                )

        else:
            schema_df = extract_rooms_from_pages(
                schema_pages,
                "schema",
                room_pattern,
            )

        if not schema_df.empty:
            schema_df = schema_df.copy()

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

    report(
        f"   Grundrisse: {len(floorplan_raw_df)} "
        "gefundene Datensätze"
    )

    report(
        f"   Schemata: {len(schema_raw_df)} "
        "gefundene Datensätze"
    )

    if floorplan_raw_df.empty:
        raise RuntimeError(
            "In den ausgewählten Grundrissen wurden "
            "keine Räume mit ZUL/ABL erkannt."
        )

    if schema_raw_df.empty:
        if numeric_floor_room_mode:
            raise RuntimeError(
                "In den ausgewählten Schemata konnten keine "
                "Luftmengenblöcke über die ep-Nummern den numerischen "
                "Grundrissräumen zugeordnet werden. "
                "Bitte prüfen, ob Grundriss und Schema zusammengehören."
            )

        raise RuntimeError(
            "In den ausgewählten Schemata wurden "
            "keine Räume mit Zuluft/Abluft erkannt."
        )

    report("3/6 Daten werden verglichen ...")

    if numeric_floor_room_mode:
        comparison_df = build_comparison(
            floorplan_raw_df,
            schema_raw_df,
            key_column="ep_nummer",
        )
    else:
        comparison_df = build_comparison(
            floorplan_raw_df,
            schema_raw_df,
        )

    report("4/6 Grundrisse werden markiert ...")

    marking_dataframes: list[pd.DataFrame] = []
    output_pdfs: list[Path] = []

    for floorplan_pdf in floorplan_pdfs:
        output_pdf = (
            output_dir
            / (
                f"{floorplan_pdf.stem}"
                "_markiert.pdf"
            )
        )

        floorplan_name = floorplan_pdf.name

        floorplan_mask = (
            comparison_df[
                "quelldateien_grundriss"
            ]
            .fillna("")
            .apply(
                lambda value: floorplan_name
                in {
                    filename.strip()
                    for filename
                    in str(value).split("|")
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

        output_pdfs.append(
            output_pdf
        )

        report(
            f"   Erstellt: {output_pdf.name}"
        )

    if marking_dataframes:
        combined_marking_df = pd.concat(
            marking_dataframes,
            ignore_index=True,
        )
    else:
        combined_marking_df = pd.DataFrame()

    report(
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

    report("6/6 Fertig.")

    return {
        "output_excel": output_excel,
        "output_pdfs": output_pdfs,
        "comparison_df": comparison_df,
        "marking_df": combined_marking_df,
        "room_pattern": room_pattern.pattern,
    }


def main() -> None:
    """Startet die grafische Benutzeroberfläche."""
    from ui.gui import start_gui

    start_gui()


if __name__ == "__main__":
    main()
