from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import fitz
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill 
from openpyxl.utils import get_column_letter


POSITION_PATTERN = re.compile(
    r"\b(?:STA|SF|AK|DP|ZV|[AFMPRSV])\s*\d+\s*\.\s*\d+\b",
    re.IGNORECASE,
)


@dataclass
class PositionRecord:
    positionsnummer: str
    quelle: str
    datei: str
    seite: int | None = None


def normalize_position_number(value: object) -> str | None:
    """Normalisiert Positionsnummern wie 'F8 0 . 2 1' zu 'F80.21'."""
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    text = (
        text.replace("\u00a0", " ")
        .replace("\n", " ")
        .replace("\t", " ")
        .upper()
    )

    match = POSITION_PATTERN.search(text)

    if not match:
        return None

    number = match.group(0)

    number = re.sub(
        r"\s+",
        "",
        number,
    )

    return number


def find_position_numbers(text: str) -> list[str]:
    """Findet alle Positionsnummern in einem Text."""
    numbers: list[str] = []

    for match in POSITION_PATTERN.finditer(text):
        number = normalize_position_number(
            match.group(0)
        )

        if number is not None:
            numbers.append(number)

    return numbers


def color_int_to_rgb(color: int) -> tuple[int, int, int]:
    """Wandelt eine PyMuPDF-Farbe in RGB um."""
    red = (color >> 16) & 255
    green = (color >> 8) & 255
    blue = color & 255

    return red, green, blue


def is_blueish(color: int) -> bool:
    """
    Prüft, ob eine Textfarbe blau/türkis ist.

    In den Schemata sind die relevanten Nummern meist türkis/blau.
    Beispiel PyMuPDF-Farbe: 65535 = RGB(0, 255, 255).
    """
    red, green, blue = color_int_to_rgb(
        color
    )

    return (
        blue >= 120
        and green >= 80
        and red <= 120
    )


def extract_schema_positions(
    pdf_path: str | Path,
    only_blue: bool = True,
) -> pd.DataFrame:
    """Extrahiert Positionsnummern aus einem Schema-PDF."""
    pdf_path = Path(
        pdf_path
    )

    records: list[PositionRecord] = []

    document = fitz.open(
        pdf_path
    )

    try:
        for page_index, page in enumerate(
            document,
            start=1,
        ):
            page_dict = page.get_text(
                "dict"
            )

            for block in page_dict.get(
                "blocks",
                [],
            ):
                for line in block.get(
                    "lines",
                    [],
                ):
                    for span in line.get(
                        "spans",
                        [],
                    ):
                        text = span.get(
                            "text",
                            "",
                        )

                        color = int(
                            span.get(
                                "color",
                                0,
                            )
                        )

                        if only_blue and not is_blueish(
                            color
                        ):
                            continue

                        positions = find_position_numbers(
                            text
                        )

                        for position in positions:
                            records.append(
                                PositionRecord(
                                    positionsnummer=position,
                                    quelle="Schema",
                                    datei=pdf_path.name,
                                    seite=page_index,
                                )
                            )

    finally:
        document.close()

    return pd.DataFrame(
        [
            record.__dict__
            for record in records
        ]
    )


def find_header_row_and_position_column(
    excel_path: str | Path,
    sheet_name: str = "Tabelle1",
) -> tuple[int, int]:
    """
    Findet die Header-Zeile und die Spalte 'Pos. Nr.'.

    Rückgabe:
    - header_row: 1-basierte Excel-Zeilennummer
    - position_column: 1-basierte Excel-Spaltennummer
    """
    workbook = load_workbook(
        excel_path,
        read_only=True,
        data_only=True,
    )

    worksheet = workbook[
        sheet_name
    ]

    try:
        for row in range(
            1,
            min(
                worksheet.max_row,
                30,
            )
            + 1,
        ):
            for column in range(
                1,
                worksheet.max_column + 1,
            ):
                value = worksheet.cell(
                    row=row,
                    column=column,
                ).value

                if value is None:
                    continue

                normalized = (
                    str(value)
                    .strip()
                    .lower()
                    .replace(" ", "")
                )

                if normalized in {
                    "pos.nr.",
                    "pos.nr",
                    "posnr.",
                    "posnr",
                }:
                    return row, column

    finally:
        workbook.close()

    raise ValueError(
        "Die Spalte 'Pos. Nr.' wurde in der Excel-Datei nicht gefunden."
    )


def extract_excel_positions(
    excel_path: str | Path,
    sheet_name: str = "Tabelle1",
) -> pd.DataFrame:
    """Extrahiert Positionsnummern aus der BML-Exceldatei."""
    excel_path = Path(
        excel_path
    )

    header_row, position_column = find_header_row_and_position_column(
        excel_path=excel_path,
        sheet_name=sheet_name,
    )

    dataframe = pd.read_excel(
        excel_path,
        sheet_name=sheet_name,
        header=header_row - 1,
    )

    position_column_name = dataframe.columns[
        position_column - 1
    ]

    records: list[PositionRecord] = []

    for value in dataframe[
        position_column_name
    ].dropna():
        position = normalize_position_number(
            value
        )

        if position is None:
            continue

        records.append(
            PositionRecord(
                positionsnummer=position,
                quelle="Excel",
                datei=excel_path.name,
                seite=None,
            )
        )

    return pd.DataFrame(
        [
            record.__dict__
            for record in records
        ]
    )


def determine_status(
    schema_count: int,
    excel_count: int,
) -> str:
    """Bestimmt den Vergleichsstatus."""
    if schema_count > 1 and excel_count > 1:
        return "Mehrfach in beiden"

    if schema_count > 1:
        return "Mehrfach im Schema"

    if excel_count > 1:
        return "Mehrfach in Excel"

    if schema_count == 1 and excel_count == 1:
        return "OK"

    if schema_count == 1 and excel_count == 0:
        return "Nur im Schema"

    if schema_count == 0 and excel_count == 1:
        return "Nur in Excel"

    return "Unklar"


def compare_positions(
    schema_df: pd.DataFrame,
    excel_df: pd.DataFrame,
) -> pd.DataFrame:
    """Vergleicht Positionsnummern aus Schema und Excel."""
    schema_numbers = (
        schema_df["positionsnummer"].tolist()
        if not schema_df.empty
        else []
    )

    excel_numbers = (
        excel_df["positionsnummer"].tolist()
        if not excel_df.empty
        else []
    )

    schema_counter = Counter(
        schema_numbers
    )

    excel_counter = Counter(
        excel_numbers
    )

    all_numbers = sorted(
        set(schema_counter)
        | set(excel_counter)
    )

    rows: list[dict[str, object]] = []

    for number in all_numbers:
        schema_count = schema_counter.get(
            number,
            0,
        )

        excel_count = excel_counter.get(
            number,
            0,
        )

        rows.append(
            {
                "Positionsnummer": number,
                "Status": determine_status(
                    schema_count,
                    excel_count,
                ),
                "Anzahl Schema": schema_count,
                "Anzahl Excel": excel_count,
            }
        )

    result = pd.DataFrame(
        rows
    )

    if result.empty:
        return result

    status_order = {
        "Nur im Schema": 0,
        "Nur in Excel": 1,
        "Mehrfach im Schema": 2,
        "Mehrfach in Excel": 3,
        "Mehrfach in beiden": 4,
        "Unklar": 5,
        "OK": 6,
    }

    result["_sort"] = result["Status"].map(
        status_order
    )

    result = result.sort_values(
        by=[
            "_sort",
            "Positionsnummer",
        ]
    ).drop(
        columns=[
            "_sort",
        ]
    )

    return result


def export_result(
    comparison_df: pd.DataFrame,
    schema_df: pd.DataFrame,
    excel_df: pd.DataFrame,
    output_path: str | Path,
) -> None:
    """Exportiert den Vergleich als Excel-Datei."""
    output_path = Path(
        output_path
    )

    with pd.ExcelWriter(
        output_path,
        engine="openpyxl",
    ) as writer:
        comparison_df.to_excel(
            writer,
            sheet_name="Vergleich",
            index=False,
        )

        schema_df.to_excel(
            writer,
            sheet_name="Nummern_Schema",
            index=False,
        )

        excel_df.to_excel(
            writer,
            sheet_name="Nummern_Excel",
            index=False,
        )

    format_excel_output(
        output_path
    )


def format_excel_output(
    output_path: str | Path,
) -> None:
    """Formatiert die Excel-Auswertung."""
    workbook = load_workbook(
        output_path
    )

    status_colors = {
        "OK": "C6EFCE",
        "Nur im Schema": "FFF2CC",
        "Nur in Excel": "F4CCCC",
        "Mehrfach im Schema": "FCE4D6",
        "Mehrfach in Excel": "FCE4D6",
        "Mehrfach in beiden": "EADCF8",
        "Unklar": "D9EAD3",
    }

    for worksheet in workbook.worksheets:
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

        for cell in worksheet[1]:
            cell.font = Font(
                bold=True
            )
            cell.fill = PatternFill(
                fill_type="solid",
                fgColor="D9EAF7",
            )

        for column_cells in worksheet.columns:
            max_length = 0
            column_letter = get_column_letter(
                column_cells[0].column
            )

            for cell in column_cells:
                if cell.value is not None:
                    max_length = max(
                        max_length,
                        len(str(cell.value)),
                    )

            worksheet.column_dimensions[
                column_letter
            ].width = min(
                max_length + 2,
                45,
            )

    comparison_sheet = workbook[
        "Vergleich"
    ]

    status_column = None

    for cell in comparison_sheet[1]:
        if cell.value == "Status":
            status_column = cell.column
            break

    if status_column is not None:
        for row in range(
            2,
            comparison_sheet.max_row + 1,
        ):
            status = comparison_sheet.cell(
                row=row,
                column=status_column,
            ).value

            color = status_colors.get(
                status
            )

            if color:
                for column in range(
                    1,
                    comparison_sheet.max_column + 1,
                ):
                    comparison_sheet.cell(
                        row=row,
                        column=column,
                    ).fill = PatternFill(
                        fill_type="solid",
                        fgColor=color,
                    )

    workbook.save(
        output_path
    )


def run_hk_number_check(
    schema_pdf: str | Path,
    bml_excel: str | Path,
    output_dir: str | Path,
    name: str = "HK_Nummernkontrolle",
) -> Path:
    """Führt die komplette Nummernkontrolle für ein PDF-Excel-Paar aus."""
    schema_pdf = Path(
        schema_pdf
    )

    bml_excel = Path(
        bml_excel
    )

    output_dir = Path(
        output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    schema_df = extract_schema_positions(
        schema_pdf,
        only_blue=True,
    )

    excel_df = extract_excel_positions(
        bml_excel,
    )

    comparison_df = compare_positions(
        schema_df,
        excel_df,
    )

    safe_name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        name,
    ).strip("_")

    output_path = output_dir / f"{safe_name}.xlsx"

    export_result(
        comparison_df=comparison_df,
        schema_df=schema_df,
        excel_df=excel_df,
        output_path=output_path,
    )

    return output_path
