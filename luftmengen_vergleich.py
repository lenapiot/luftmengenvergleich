"""
Automatischer Luftmengenvergleich für ähnlich aufgebaute Grundriss- und
Lüftungsplan-PDFs.

Das Programm:
1. lässt Grundriss und Schema auswählen,
2. liest alle PDF-Seiten aus,
3. extrahiert Raumnummer, Raumname, Zuluft und Abluft,
4. vergleicht beide Dokumente,
5. erstellt eine formatierte Excel-Datei,
6. markiert die Räume im Grundriss-PDF,
7. erstellt ein Protokoll nicht eindeutiger Markierungen.

Geeignet für digital erzeugte PDFs mit ähnlicher Textstruktur wie das Testpaar:
    Grundriss:
        Raumname / Raumnummer
        ZUL: 4'000 m³/h
        ABL: 4'450 m³/h

    Schema:
        Raumname
        Raumnummer
        Zuluft 4'000 m³/h
        Abluft 4'450 m³/h

Installation:
    python -m pip install pymupdf pandas openpyxl

Start:
    python luftmengen_vergleich.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


import re

from config.settings import(
    ROOM_RE,
    MAX_AIRFLOW_DISTANCE,
    ROOM_SEARCH_RADIUS,
    EXCEL_STATUS_COLORS,
    PDF_STATUS_COLORS,
)


from ui.dialogs import(
    choose_pdf,
    choose_output_folder,
    validate_pdf,
)

from export.pdf_export import create_marked_pdf

from export.excel_export import export_excel

from core.comparison import build_comparison

# =============================================================================
# 1. EINSTELLUNGEN (settings.py)
# =============================================================================

# =============================================================================
# 2. DATENSTRUKTUR
# =============================================================================

@dataclass(frozen=True)
class TextLine:
    """Eine bereinigte Textzeile mit Seiteninformation."""

    page_number: int
    line_number: int
    text: str


# =============================================================================
# 3. ALLGEMEINE HILFSFUNKTIONEN
# =============================================================================

def normalize_number(value: object) -> int | None:
    """
    Wandelt eine Luftmenge in eine ganze Zahl um.

    Beispiele:
        "4000"   -> 4000
        "4'450"  -> 4450
        "4’450"  -> 4450
        "?"      -> None
    """
    if value is None:
        return None

    cleaned = (
        str(value)
        .strip()
        .replace("'", "")
        .replace("’", "")
        .replace("`", "")
        .replace(" ", "")
    )

    if cleaned in {"", "?", "-", "–"}:
        return None

    try:
        return int(cleaned)
    except ValueError:
        return None



def find_room_in_line(
    line: str,
) -> tuple[str | None, str | None]:
    """
    Sucht eine Raumnummer in einer Textzeile.

    Beispiele:
        "MIT1X409 Elektro" -> ("MIT1X409", "Elektro")
        "MIT2X1"           -> ("MIT2X1", None)
    """
    match = ROOM_RE.search(line or "")

    if not match:
        return None, None

    room_id = match.group(0)

    rest = (
        line[:match.start()]
        + " "
        + line[match.end():]
    ).strip()

    rest = re.sub(r"\s+", " ", rest)

    return room_id, rest or None


def is_airflow_line(text: str) -> bool:
    """Prüft, ob eine Zeile eine Luftmengenangabe enthält."""
    return bool(
        re.search(
            r"^(?:ZUL|ABL)\s*:|^(?:Zuluft|Abluft)\b",
            text,
            flags=re.IGNORECASE,
        )
    )





# =============================================================================
# 4. PDF EINLESEN
# =============================================================================

def extract_clean_lines(pdf_path: Path) -> list[TextLine]:
    """
    Liest alle Seiten eines PDFs und gibt alle nichtleeren Textzeilen zurück.
    """
    records: list[TextLine] = []

    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(document):
            raw_text = page.get_text("text")

            clean_lines = [
                re.sub(r"\s+", " ", line).strip()
                for line in raw_text.splitlines()
                if line.strip()
            ]

            for line_index, text in enumerate(clean_lines):
                records.append(
                    TextLine(
                        page_number=page_index + 1,
                        line_number=line_index,
                        text=text,
                    )
                )

    return records


def split_lines_by_page(
    records: list[TextLine],
) -> dict[int, list[str]]:
    """Gruppiert die ausgelesenen Textzeilen nach PDF-Seite."""
    pages: dict[int, list[str]] = {}

    for record in records:
        pages.setdefault(
            record.page_number,
            [],
        ).append(record.text)

    return pages


# =============================================================================
# 5. RÄUME UND LUFTMENGEN EXTRAHIEREN
# =============================================================================

def find_matching_airflow_pair(
    lines: list[str],
    start_index: int,
    zul_re: re.Pattern[str],
    abl_re: re.Pattern[str],
) -> tuple[re.Match[str], re.Match[str], int] | None:
    """
    Sucht zu einer Zuluftzeile eine nahe folgende Abluftzeile.
    """
    zul_match = zul_re.search(lines[start_index])

    if not zul_match:
        return None

    last_index = min(
        len(lines),
        start_index + MAX_AIRFLOW_DISTANCE + 1,
    )

    for abl_index in range(
        start_index + 1,
        last_index,
    ):
        abl_match = abl_re.search(lines[abl_index])

        if abl_match:
            return zul_match, abl_match, abl_index

    return None


def choose_room_candidate(
    lines: list[str],
    zul_index: int,
    abl_index: int,
    preferred_offsets: list[int],
) -> tuple[str | None, str | None, int | None]:
    """
    Sucht in der Umgebung einer Luftmengenangabe nach einer Raumnummer.
    """
    candidate_indices: list[int] = [
        zul_index + offset
        for offset in preferred_offsets
    ]

    for distance in range(
        1,
        ROOM_SEARCH_RADIUS + 1,
    ):
        candidate_indices.extend(
            [
                zul_index - distance,
                abl_index + distance,
            ]
        )

    already_tested: set[int] = set()

    for candidate_index in candidate_indices:
        if candidate_index in already_tested:
            continue

        already_tested.add(candidate_index)

        if not 0 <= candidate_index < len(lines):
            continue

        room_id, rest = find_room_in_line(
            lines[candidate_index]
        )

        if room_id:
            return room_id, rest, candidate_index

    return None, None, None


def infer_room_name(
    lines: list[str],
    room_index: int,
    zul_index: int,
    rest: str | None,
) -> str | None:
    """
    Sucht den wahrscheinlichsten Raumnamen.

    Priorität:
    1. Resttext in derselben Zeile wie die Raumnummer
    2. Zeile vor der Raumnummer
    3. Zeile vor Zuluft
    4. weitere nahe Zeilen
    """
    if rest:
        return rest

    candidate_indices = [
        room_index - 1,
        zul_index - 1,
        room_index + 1,
        zul_index - 2,
    ]

    for index in candidate_indices:
        if not 0 <= index < len(lines):
            continue

        candidate = lines[index].strip()

        if not candidate:
            continue

        if is_airflow_line(candidate):
            continue

        candidate_room_id, _ = find_room_in_line(
            candidate
        )

        if candidate_room_id:
            continue

        if re.fullmatch(
            r"[\d\s'’`.,:/+\-]+",
            candidate,
        ):
            continue

        return candidate

    return None


def extract_rooms_from_pages(
    page_lines: dict[int, list[str]],
    source_type: str,
) -> pd.DataFrame:
    """
    Extrahiert Raumnummer, Raumname, Zuluft und Abluft.

    source_type:
        "grundriss"
        "schema"
    """
    if source_type == "grundriss":
        zul_re = re.compile(
            r"^ZUL\s*:\s*([0-9'’` ]+|\?)\s*m",
            re.IGNORECASE,
        )

        abl_re = re.compile(
            r"^ABL\s*:\s*([0-9'’` ]+|\?)\s*m",
            re.IGNORECASE,
        )

        preferred_offsets = [-1, 2, -2, 3]

    elif source_type == "schema":
        zul_re = re.compile(
            r"^Zuluft\s*:?\s*([0-9'’` ]+|\?)\s*m",
            re.IGNORECASE,
        )

        abl_re = re.compile(
            r"^Abluft\s*:?\s*([0-9'’` ]+|\?)\s*m",
            re.IGNORECASE,
        )

        preferred_offsets = [-1, -2, 2, 3]

    else:
        raise ValueError(
            "source_type muss 'grundriss' oder 'schema' sein."
        )

    rooms: list[dict[str, object]] = []

    for page_number, lines in page_lines.items():
        for zul_index in range(len(lines)):
            airflow_pair = find_matching_airflow_pair(
                lines,
                zul_index,
                zul_re,
                abl_re,
            )

            if airflow_pair is None:
                continue

            zul_match, abl_match, abl_index = airflow_pair

            room_id, rest, room_index = choose_room_candidate(
                lines,
                zul_index,
                abl_index,
                preferred_offsets,
            )

            if room_id is None or room_index is None:
                continue

            room_name = infer_room_name(
                lines,
                room_index,
                zul_index,
                rest,
            )

            rooms.append(
                {
                    "raumnummer": room_id,
                    "raumname": room_name,
                    "zul": normalize_number(
                        zul_match.group(1)
                    ),
                    "abl": normalize_number(
                        abl_match.group(1)
                    ),
                    "seite": page_number,
                    "quelle": source_type,
                }
            )

    columns = [
        "raumnummer",
        "raumname",
        "zul",
        "abl",
        "seite",
        "quelle",
    ]

    if not rooms:
        return pd.DataFrame(
            columns=columns
        )

    return (
        pd.DataFrame(
            rooms,
            columns=columns,
        )
        .drop_duplicates()
        .sort_values(
            ["raumnummer", "seite"]
        )
        .reset_index(drop=True)
    )


# =============================================================================
# 6. DOPPELTE ODER UNEINDEUTIGE RÄUME KONSOLIDIEREN
# =============================================================================



# =============================================================================
# 7. GRUNDRISS UND SCHEMA VERGLEICHEN
# =============================================================================



# =============================================================================
# 8. PDF-MARKIERUNG (pdf_export.py)
# =============================================================================


# =============================================================================
# 9. EXCEL-DATEI ERSTELLEN UND FORMATIEREN (excel_export.py)
# =============================================================================

# =============================================================================
# 10. DATEIEN AUSWÄHLEN (dialogs.py)
# =============================================================================


# =============================================================================
# 11. HAUPTPROGRAMM
# =============================================================================

def main() -> None:
    """Führt den vollständigen Luftmengenvergleich aus."""
    print()
    print("Luftmengen-Vergleich")
    print("====================")
    print()

    floorplan_pdf = choose_pdf(
        "Grundriss-PDF auswählen"
    )

    schema_pdf = choose_pdf(
        "Lüftungsplan / Prinzipschema auswählen"
    )

    validate_pdf(
        floorplan_pdf,
        "Grundriss",
    )

    validate_pdf(
        schema_pdf,
        "Schema",
    )

    output_dir = choose_output_folder(
        floorplan_pdf.parent
    )

    output_excel = (
        output_dir
        / (
            f"{floorplan_pdf.stem}"
            "_Luftmengenvergleich.xlsx"
        )
    )

    output_pdf = (
        output_dir
        / (
            f"{floorplan_pdf.stem}"
            "_markiert.pdf"
        )
    )

    print("1/6 PDFs werden eingelesen ...")

    floorplan_records = (
        extract_clean_lines(
            floorplan_pdf
        )
    )

    schema_records = (
        extract_clean_lines(
            schema_pdf
        )
    )

    print("2/6 Räume werden extrahiert ...")

    floorplan_raw_df = (
        extract_rooms_from_pages(
            split_lines_by_page(
                floorplan_records
            ),
            "grundriss",
        )
    )

    schema_raw_df = (
        extract_rooms_from_pages(
            split_lines_by_page(
                schema_records
            ),
            "schema",
        )
    )

    print(
        "   Grundriss:",
        len(floorplan_raw_df),
        "gefundene Datensätze",
    )

    print(
        "   Schema:",
        len(schema_raw_df),
        "gefundene Datensätze",
    )

    if floorplan_raw_df.empty:
        raise RuntimeError(
            "Im Grundriss wurden keine Räume "
            "mit ZUL/ABL erkannt."
        )

    if schema_raw_df.empty:
        raise RuntimeError(
            "Im Schema wurden keine Räume "
            "mit Zuluft/Abluft erkannt."
        )

    print("3/6 Daten werden verglichen ...")

    comparison_df = build_comparison(
        floorplan_raw_df,
        schema_raw_df,
    )

    print("4/6 Grundriss wird markiert ...")

    marking_df = create_marked_pdf(
        floorplan_pdf,
        output_pdf,
        comparison_df,
    )

    print(
        "5/6 Excel-Auswertung "
        "wird erstellt ..."
    )

    export_excel(
        output_excel,
        floorplan_raw_df,
        schema_raw_df,
        comparison_df,
        marking_df,
        floorplan_pdf,
        schema_pdf,
    )

    print("6/6 Fertig.")
    print()

    print("Excel-Auswertung:")
    print(output_excel)
    print()

    print("Markierter Grundriss:")
    print(output_pdf)
    print()

    print("Statusübersicht:")
    print(
        comparison_df[
            "status"
        ]
        .astype(str)
        .value_counts()
        .to_string()
    )


if __name__ == "__main__":
    main()
