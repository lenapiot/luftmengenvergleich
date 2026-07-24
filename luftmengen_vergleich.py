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


# =============================================================================
# 1. EINSTELLUNGEN
# =============================================================================

import re

from config.settings import(
    ROOM_RE,
    MAX_AIRFLOW_DISTANCE,
    ROOM_SEARCH_RADIUS,
    EXCEL_STATUS_COLORS,
    PDF_STATUS_COLORS,
)


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


def normalize_name(value: object) -> str | None:
    """Normalisiert einen Raumnamen für den Vergleich."""
    if value is None or pd.isna(value):
        return None

    text = re.sub(r"\s+", " ", str(value)).strip().casefold()
    return text or None


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


def unique_non_null_values(series: pd.Series) -> list[object]:
    """Gibt eindeutige, nichtleere Werte einer Spalte zurück."""
    values: list[object] = []

    for value in series:
        if value is None or pd.isna(value):
            continue

        if value not in values:
            values.append(value)

    return values


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

def consolidate_rooms(
    raw_df: pd.DataFrame,
    source_label: str,
) -> pd.DataFrame:
    """
    Erstellt pro Raumnummer eine Vergleichszeile.

    Mehrere identische Funde sind erlaubt.
    Mehrere widersprüchliche Werte werden als uneindeutig gekennzeichnet.
    """
    columns = [
        "raumnummer",
        f"raumname_{source_label}",
        f"zul_{source_label}",
        f"abl_{source_label}",
        f"seiten_{source_label}",
        f"anzahl_funde_{source_label}",
        f"uneindeutig_{source_label}",
    ]

    if raw_df.empty:
        return pd.DataFrame(
            columns=columns
        )

    rows: list[dict[str, object]] = []

    for room_id, group in raw_df.groupby(
        "raumnummer",
        sort=True,
    ):
        names = unique_non_null_values(
            group["raumname"]
        )
        zul_values = unique_non_null_values(
            group["zul"]
        )
        abl_values = unique_non_null_values(
            group["abl"]
        )

        pages = sorted(
            {
                int(page)
                for page in group["seite"]
                if page is not None
                and not pd.isna(page)
            }
        )

        ambiguous = (
            len(names) > 1
            or len(zul_values) > 1
            or len(abl_values) > 1
        )

        rows.append(
            {
                "raumnummer": room_id,
                f"raumname_{source_label}": (
                    names[0]
                    if len(names) == 1
                    else " | ".join(
                        map(str, names)
                    )
                ),
                f"zul_{source_label}": (
                    zul_values[0]
                    if len(zul_values) == 1
                    else None
                ),
                f"abl_{source_label}": (
                    abl_values[0]
                    if len(abl_values) == 1
                    else None
                ),
                f"seiten_{source_label}": ", ".join(
                    map(str, pages)
                ),
                f"anzahl_funde_{source_label}": len(
                    group
                ),
                f"uneindeutig_{source_label}": ambiguous,
            }
        )

    return pd.DataFrame(
        rows,
        columns=columns,
    )


# =============================================================================
# 7. GRUNDRISS UND SCHEMA VERGLEICHEN
# =============================================================================

def determine_status(
    row: pd.Series,
) -> str:
    """Bestimmt den Status einer Vergleichszeile."""
    if row["_merge"] == "left_only":
        return "Nur im Grundriss"

    if row["_merge"] == "right_only":
        return "Nur im Schema"

    if (
        bool(row.get(
            "uneindeutig_grundriss",
            False,
        ))
        or bool(row.get(
            "uneindeutig_schema",
            False,
        ))
    ):
        return "Mehrfach / uneindeutig"

    if (
        not row["zul_stimmt"]
        or not row["abl_stimmt"]
    ):
        return "Abweichung Luftmenge"

    if not row["raumname_stimmt"]:
        return "Abweichung Raumname"

    return "OK"


def build_comparison(
    floorplan_raw_df: pd.DataFrame,
    schema_raw_df: pd.DataFrame,
) -> pd.DataFrame:
    """Erstellt die vollständige Vergleichstabelle."""
    floorplan_df = consolidate_rooms(
        floorplan_raw_df,
        "grundriss",
    )

    schema_df = consolidate_rooms(
        schema_raw_df,
        "schema",
    )

    comparison_df = pd.merge(
        floorplan_df,
        schema_df,
        on="raumnummer",
        how="outer",
        indicator=True,
    )

    comparison_df["vorkommen"] = (
        comparison_df["_merge"]
        .astype(str)
        .replace(
            {
                "both": "Grundriss und Schema",
                "left_only": "Nur Grundriss",
                "right_only": "Nur Schema",
            }
        )
    )

    both_mask = (
        comparison_df["_merge"] == "both"
    )

    comparison_df["zul_stimmt"] = False
    comparison_df["abl_stimmt"] = False
    comparison_df["raumname_stimmt"] = False

    comparison_df.loc[
        both_mask,
        "zul_stimmt",
    ] = (
        comparison_df.loc[
            both_mask,
            "zul_grundriss",
        ]
        ==
        comparison_df.loc[
            both_mask,
            "zul_schema",
        ]
    )

    comparison_df.loc[
        both_mask,
        "abl_stimmt",
    ] = (
        comparison_df.loc[
            both_mask,
            "abl_grundriss",
        ]
        ==
        comparison_df.loc[
            both_mask,
            "abl_schema",
        ]
    )

    comparison_df.loc[
        both_mask,
        "raumname_stimmt",
    ] = [
        normalize_name(left)
        == normalize_name(right)
        for left, right in zip(
            comparison_df.loc[
                both_mask,
                "raumname_grundriss",
            ],
            comparison_df.loc[
                both_mask,
                "raumname_schema",
            ],
        )
    ]

    comparison_df["status"] = (
        comparison_df.apply(
            determine_status,
            axis=1,
        )
    )

    comparison_df = comparison_df.drop(
        columns=["_merge"]
    )

    status_order = pd.CategoricalDtype(
        categories=[
            "Abweichung Luftmenge",
            "Abweichung Raumname",
            "Mehrfach / uneindeutig",
            "Nur im Grundriss",
            "Nur im Schema",
            "OK",
        ],
        ordered=True,
    )

    comparison_df["status"] = (
        comparison_df["status"]
        .astype(status_order)
    )

    return (
        comparison_df
        .sort_values(
            ["status", "raumnummer"]
        )
        .reset_index(drop=True)
    )


# =============================================================================
# 8. PDF-MARKIERUNG
# =============================================================================

def find_exact_word_rectangles_in_document(
    document: fitz.Document,
    search_text: str,
) -> list[tuple[int, fitz.Rect]]:
    """
    Sucht eine Raumnummer exakt auf allen PDF-Seiten.

    Rückgabe:
        Liste mit:
        (Seitenindex, Rechteck)
    """
    matches: list[
        tuple[int, fitz.Rect]
    ] = []

    for page_index, page in enumerate(
        document
    ):
        for word in page.get_text("words"):
            x0, y0, x1, y1, text, *_ = word

            if text.strip() == search_text:
                matches.append(
                    (
                        page_index,
                        fitz.Rect(
                            x0,
                            y0,
                            x1,
                            y1,
                        ),
                    )
                )

    return matches


def draw_number_label(
    page: fitz.Page,
    room_rect: fitz.Rect,
    label: str,
    color: tuple[float, float, float],
) -> fitz.Rect:
    """Zeichnet eine kleine Kennzeichnung neben die Raumnummer."""
    label_width = max(
        18,
        7 * len(str(label)),
    )
    label_height = 14

    label_rect = fitz.Rect(
        room_rect.x1 + 4,
        room_rect.y0 - 1,
        room_rect.x1 + 4 + label_width,
        room_rect.y0 - 1 + label_height,
    )

    page.draw_rect(
        label_rect,
        color=color,
        fill=(1, 1, 1),
        width=1.5,
    )

    page.insert_textbox(
        label_rect,
        str(label),
        fontsize=8,
        fontname="helv",
        color=color,
        align=fitz.TEXT_ALIGN_CENTER,
    )

    return label_rect


def draw_pdf_legend(
    page: fitz.Page,
) -> None:
    """Zeichnet eine Legende auf die erste Seite."""
    x = 20
    y = 20
    legend_width = 285
    title_height = 24
    row_height = 22

    legend_entries = [
        (
            "Grau",
            "Geprüft, keine Abweichung",
            PDF_STATUS_COLORS["OK"],
        ),
        (
            "Rot",
            "Abweichung Luftmenge",
            PDF_STATUS_COLORS[
                "Abweichung Luftmenge"
            ],
        ),
        (
            "Orange",
            "Abweichung Raumname",
            PDF_STATUS_COLORS[
                "Abweichung Raumname"
            ],
        ),
        (
            "Grün / V",
            "Nur im Grundriss",
            PDF_STATUS_COLORS[
                "Nur im Grundriss"
            ],
        ),
        (
            "Gelb",
            "Mehrfach oder uneindeutig",
            PDF_STATUS_COLORS[
                "Mehrfach / uneindeutig"
            ],
        ),
        (
            "Violett",
            "Nur im Schema; nicht markierbar",
            PDF_STATUS_COLORS[
                "Nur im Schema"
            ],
        ),
    ]

    legend_height = (
        title_height
        + len(legend_entries) * row_height
        + 10
    )

    background_rect = fitz.Rect(
        x,
        y,
        x + legend_width,
        y + legend_height,
    )

    page.draw_rect(
        background_rect,
        color=(0, 0, 0),
        fill=(1, 1, 1),
        width=1.2,
    )

    page.insert_textbox(
        fitz.Rect(
            x + 8,
            y + 4,
            x + legend_width - 8,
            y + title_height,
        ),
        "Legende Luftmengen-Kontrolle",
        fontsize=11,
        fontname="helv",
        color=(0, 0, 0),
        align=fitz.TEXT_ALIGN_LEFT,
    )

    current_y = y + title_height

    for short_name, description, color in (
        legend_entries
    ):
        color_box = fitz.Rect(
            x + 8,
            current_y + 4,
            x + 28,
            current_y + 18,
        )

        page.draw_rect(
            color_box,
            color=color,
            fill=(1, 1, 1),
            width=2,
        )

        page.insert_textbox(
            fitz.Rect(
                x + 34,
                current_y + 2,
                x + 100,
                current_y + row_height,
            ),
            short_name,
            fontsize=8,
            fontname="helv",
            color=(0, 0, 0),
            align=fitz.TEXT_ALIGN_LEFT,
        )

        page.insert_textbox(
            fitz.Rect(
                x + 102,
                current_y + 2,
                x + legend_width - 6,
                current_y + row_height,
            ),
            description,
            fontsize=7,
            fontname="helv",
            color=(0, 0, 0),
            align=fitz.TEXT_ALIGN_LEFT,
        )

        current_y += row_height


def create_marked_pdf(
    floorplan_pdf: Path,
    output_pdf: Path,
    comparison_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Erstellt eine markierte Kopie des Grundrisses und ein Protokoll.
    """
    document = fitz.open(
        floorplan_pdf
    )

    deviation_number = 1
    only_floorplan_number = 1

    results: list[
        dict[str, object]
    ] = []

    for _, row in comparison_df.iterrows():
        room_id = str(row["raumnummer"])
        status = str(row["status"])

        if status == "Nur im Schema":
            results.append(
                {
                    "kennzeichnung": None,
                    "raumnummer": room_id,
                    "status": status,
                    "seite": None,
                    "anzahl_treffer": 0,
                    "ergebnis": (
                        "Nicht markierbar – "
                        "Raum fehlt im Grundriss"
                    ),
                }
            )
            continue

        color = PDF_STATUS_COLORS.get(
            status
        )

        if color is None:
            results.append(
                {
                    "kennzeichnung": None,
                    "raumnummer": room_id,
                    "status": status,
                    "seite": None,
                    "anzahl_treffer": 0,
                    "ergebnis": "Unbekannter Status",
                }
            )
            continue

        matches = (
            find_exact_word_rectangles_in_document(
                document,
                room_id,
            )
        )

        if len(matches) != 1:
            results.append(
                {
                    "kennzeichnung": None,
                    "raumnummer": room_id,
                    "status": status,
                    "seite": None,
                    "anzahl_treffer": len(matches),
                    "ergebnis": (
                        "Nicht eindeutig gefunden"
                        if matches
                        else "Raumnummer nicht gefunden"
                    ),
                }
            )
            continue

        page_index, room_rect = matches[0]
        page = document[page_index]

        marking_rect = fitz.Rect(
            room_rect.x0 - 2,
            room_rect.y0 - 2,
            room_rect.x1 + 2,
            room_rect.y1 + 2,
        )

        page.draw_rect(
            marking_rect,
            color=color,
            width=2,
        )

        label: str | None = None

        if status in {
            "Abweichung Luftmenge",
            "Abweichung Raumname",
            "Mehrfach / uneindeutig",
        }:
            label = str(
                deviation_number
            )
            deviation_number += 1

        elif status == "Nur im Grundriss":
            label = (
                f"V{only_floorplan_number}"
            )
            only_floorplan_number += 1

        if label:
            draw_number_label(
                page,
                marking_rect,
                label,
                color,
            )

        results.append(
            {
                "kennzeichnung": label,
                "raumnummer": room_id,
                "status": status,
                "seite": page_index + 1,
                "anzahl_treffer": 1,
                "ergebnis": "Markiert",
            }
        )

    if len(document) > 0:
        draw_pdf_legend(
            document[0]
        )

    document.save(
        output_pdf,
        garbage=4,
        deflate=True,
    )
    document.close()

    return pd.DataFrame(
        results
    )


# =============================================================================
# 9. EXCEL-DATEI ERSTELLEN UND FORMATIEREN
# =============================================================================

def find_column_number(
    worksheet,
    column_name: str,
) -> int | None:
    """Sucht eine Spalte anhand ihrer Überschrift."""
    for cell in worksheet[1]:
        if cell.value == column_name:
            return cell.column

    return None


def adjust_column_widths(
    worksheet,
) -> None:
    """Passt die Spaltenbreiten automatisch an."""
    for column_cells in worksheet.columns:
        max_length = 0

        column_number = (
            column_cells[0].column
        )
        column_letter = get_column_letter(
            column_number
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


def format_data_sheet(
    worksheet,
) -> None:
    """Formatiert ein normales Datenblatt."""
    header_fill = PatternFill(
        fill_type="solid",
        fgColor="D9E1F2",
    )

    thin_border = Border(
        left=Side(
            style="thin",
            color="D9D9D9",
        ),
        right=Side(
            style="thin",
            color="D9D9D9",
        ),
        top=Side(
            style="thin",
            color="D9D9D9",
        ),
        bottom=Side(
            style="thin",
            color="D9D9D9",
        ),
    )

    for cell in worksheet[1]:
        cell.font = Font(
            bold=True
        )
        cell.fill = header_fill
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )
        cell.border = thin_border

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = (
        worksheet.dimensions
    )

    for row in worksheet.iter_rows(
        min_row=2,
        max_row=worksheet.max_row,
    ):
        for cell in row:
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )
            cell.border = thin_border

    adjust_column_widths(
        worksheet
    )


def color_rows_by_status(
    worksheet,
) -> None:
    """Färbt Zeilen anhand der Statusspalte."""
    status_column = find_column_number(
        worksheet,
        "status",
    )

    if status_column is None:
        return

    for row_number in range(
        2,
        worksheet.max_row + 1,
    ):
        status_cell = worksheet.cell(
            row=row_number,
            column=status_column,
        )

        status = status_cell.value
        color = EXCEL_STATUS_COLORS.get(
            status
        )

        if color is None:
            continue

        fill = PatternFill(
            fill_type="solid",
            fgColor=color,
        )

        for cell in worksheet[row_number]:
            cell.fill = fill

        status_cell.font = Font(
            bold=True
        )


def create_legend_sheet(
    workbook,
    floorplan_pdf: Path,
    schema_pdf: Path,
    comparison_df: pd.DataFrame,
) -> None:
    """Erstellt Legende und Statuszusammenfassung."""
    if "Legende" in workbook.sheetnames:
        del workbook["Legende"]

    worksheet = workbook.create_sheet(
        "Legende",
        0,
    )

    worksheet["A1"] = (
        "Luftmengen-Vergleich"
    )
    worksheet["A1"].font = Font(
        bold=True,
        size=16,
    )

    worksheet["A2"] = (
        "Automatischer Vergleich zwischen "
        "Luftmengen-Grundriss und "
        "Lüftungs-Prinzipschema"
    )

    worksheet["A4"] = "Status"
    worksheet["B4"] = "Bedeutung"
    worksheet["C4"] = "Anzahl"

    meanings = {
        "OK": (
            "Raum ist in beiden Dokumenten "
            "vorhanden; Raumname und "
            "Luftmengen stimmen überein."
        ),
        "Abweichung Luftmenge": (
            "Zuluft und/oder Abluft "
            "unterscheiden sich."
        ),
        "Abweichung Raumname": (
            "Die Luftmengen stimmen, aber "
            "die Raumbezeichnung weicht ab."
        ),
        "Nur im Grundriss": (
            "Der Raum wurde nur im "
            "Grundriss gefunden."
        ),
        "Nur im Schema": (
            "Der Raum wurde nur im "
            "Schema gefunden."
        ),
        "Mehrfach / uneindeutig": (
            "Eine Raumnummer wurde mehrfach "
            "mit widersprüchlichen Angaben "
            "gefunden."
        ),
    }

    counts = (
        comparison_df["status"]
        .astype(str)
        .value_counts()
        .to_dict()
    )

    row_number = 5

    for status, meaning in (
        meanings.items()
    ):
        worksheet.cell(
            row=row_number,
            column=1,
            value=status,
        )

        worksheet.cell(
            row=row_number,
            column=2,
            value=meaning,
        )

        worksheet.cell(
            row=row_number,
            column=3,
            value=counts.get(
                status,
                0,
            ),
        )

        worksheet.cell(
            row=row_number,
            column=1,
        ).fill = PatternFill(
            fill_type="solid",
            fgColor=EXCEL_STATUS_COLORS[
                status
            ],
        )

        row_number += 1

    worksheet["A13"] = (
        "Verwendeter Grundriss:"
    )
    worksheet["B13"] = (
        floorplan_pdf.name
    )

    worksheet["A14"] = (
        "Verwendetes Schema:"
    )
    worksheet["B14"] = schema_pdf.name

    worksheet["A16"] = "Hinweis:"
    worksheet["B16"] = (
        "Die Auswertung ist für ähnlich "
        "strukturierte, digital erzeugte "
        "PDFs ausgelegt. Die Ergebnisse "
        "müssen fachlich kontrolliert werden."
    )

    for reference in [
        "A13",
        "A14",
        "A16",
    ]:
        worksheet[
            reference
        ].font = Font(
            bold=True
        )

    thin_border = Border(
        left=Side(
            style="thin",
            color="B7B7B7",
        ),
        right=Side(
            style="thin",
            color="B7B7B7",
        ),
        top=Side(
            style="thin",
            color="B7B7B7",
        ),
        bottom=Side(
            style="thin",
            color="B7B7B7",
        ),
    )

    for row in worksheet.iter_rows(
        min_row=4,
        max_row=10,
        min_col=1,
        max_col=3,
    ):
        for cell in row:
            cell.border = thin_border
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

    for cell in worksheet[4]:
        cell.font = Font(
            bold=True
        )
        cell.fill = PatternFill(
            fill_type="solid",
            fgColor="D9E1F2",
        )

    worksheet.column_dimensions[
        "A"
    ].width = 28

    worksheet.column_dimensions[
        "B"
    ].width = 80

    worksheet.column_dimensions[
        "C"
    ].width = 12

    worksheet.freeze_panes = "A5"


def export_excel(
    output_path: Path,
    floorplan_raw_df: pd.DataFrame,
    schema_raw_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    marking_df: pd.DataFrame,
    floorplan_pdf: Path,
    schema_pdf: Path,
) -> None:
    """Exportiert und formatiert die Excel-Auswertung."""
    deviations_df = comparison_df[
        comparison_df[
            "status"
        ].astype(str) != "OK"
    ].copy()

    only_floorplan_df = comparison_df[
        comparison_df[
            "status"
        ].astype(str) == "Nur im Grundriss"
    ].copy()

    only_schema_df = comparison_df[
        comparison_df[
            "status"
        ].astype(str) == "Nur im Schema"
    ].copy()

    with pd.ExcelWriter(
        output_path,
        engine="openpyxl",
    ) as writer:
        floorplan_raw_df.to_excel(
            writer,
            sheet_name="Grundriss_Rohdaten",
            index=False,
        )

        schema_raw_df.to_excel(
            writer,
            sheet_name="Schema_Rohdaten",
            index=False,
        )

        comparison_df.to_excel(
            writer,
            sheet_name="Vergleich",
            index=False,
        )

        deviations_df.to_excel(
            writer,
            sheet_name="Abweichungen",
            index=False,
        )

        only_floorplan_df.to_excel(
            writer,
            sheet_name="Nur_im_Grundriss",
            index=False,
        )

        only_schema_df.to_excel(
            writer,
            sheet_name="Nur_im_Schema",
            index=False,
        )

        marking_df.to_excel(
            writer,
            sheet_name="PDF_Markierungen",
            index=False,
        )

    workbook = load_workbook(
        output_path
    )

    create_legend_sheet(
        workbook,
        floorplan_pdf,
        schema_pdf,
        comparison_df,
    )

    for worksheet in (
        workbook.worksheets
    ):
        if worksheet.title == "Legende":
            continue

        format_data_sheet(
            worksheet
        )

        if worksheet.title in {
            "Vergleich",
            "Abweichungen",
            "Nur_im_Grundriss",
            "Nur_im_Schema",
        }:
            color_rows_by_status(
                worksheet
            )

    workbook.save(
        output_path
    )


# =============================================================================
# 10. DATEIEN AUSWÄHLEN
# =============================================================================

def choose_pdf(
    title: str,
) -> Path:
    """Öffnet einen Dateidialog zur Auswahl einer PDF-Datei."""
    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    root.attributes(
        "-topmost",
        True,
    )

    selected = filedialog.askopenfilename(
        title=title,
        filetypes=[
            (
                "PDF-Dateien",
                "*.pdf",
            )
        ],
    )

    root.destroy()

    if not selected:
        raise SystemExit(
            "Keine PDF-Datei ausgewählt."
        )

    return Path(selected)


def choose_output_folder(
    initial_folder: Path,
) -> Path:
    """Öffnet einen Dialog zur Auswahl des Ausgabeordners."""
    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    root.attributes(
        "-topmost",
        True,
    )

    selected = filedialog.askdirectory(
        title="Ausgabeordner auswählen",
        initialdir=str(initial_folder),
    )

    root.destroy()

    if not selected:
        return initial_folder

    return Path(selected)


def validate_pdf(
    path: Path,
    description: str,
) -> None:
    """Prüft, ob die ausgewählte Datei existiert und ein PDF ist."""
    if not path.exists():
        raise FileNotFoundError(
            f"{description} wurde nicht gefunden: "
            f"{path}"
        )

    if path.suffix.lower() != ".pdf":
        raise ValueError(
            f"{description} ist keine PDF-Datei: "
            f"{path}"
        )


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
