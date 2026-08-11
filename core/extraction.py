from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz
import pandas as pd

from config.settings import (
    ROOM_RE,
    MAX_AIRFLOW_DISTANCE,
    ROOM_SEARCH_RADIUS,
)


OPERATING_MODES = {
    "nominal": "Nominal",
    "havarie": "Havarie",
}


@dataclass(frozen=True)
class TextLine:
    """Eine bereinigte Textzeile mit Seiteninformation."""

    page_number: int
    line_number: int
    text: str


def normalize_number(value: object) -> int | None:
    """Wandelt eine Luftmenge als Text in eine ganze Zahl um."""
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
    room_pattern: re.Pattern[str] = ROOM_RE,
) -> tuple[str | None, str | None]:
    """Sucht eine Raumnummer und möglichen Resttext in einer Zeile."""
    match = room_pattern.search(line or "")

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


def detect_operating_mode(text: str) -> str | None:
    """Erkennt bekannte Betriebsarten: Nominal und Havarie."""
    normalized = re.sub(r"\s+", " ", str(text)).strip().casefold()

    for keyword, display_name in OPERATING_MODES.items():
        if re.search(
            rf"\b{re.escape(keyword)}\b",
            normalized,
            flags=re.IGNORECASE,
        ):
            return display_name

    return None


def remove_operating_mode_from_text(text: str | None) -> str | None:
    """Entfernt Nominal/Havarie aus einem möglichen Raumnamen."""
    if not text:
        return None

    cleaned = str(text)

    for keyword in OPERATING_MODES:
        cleaned = re.sub(
            rf"\b{re.escape(keyword)}\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—:/")

    return cleaned or None


def extract_clean_lines(pdf_path: Path) -> list[TextLine]:
    """Liest alle nichtleeren Textzeilen eines PDFs aus."""
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


def split_lines_by_page(records: list[TextLine]) -> dict[int, list[str]]:
    """Gruppiert Textzeilen nach PDF-Seite."""
    pages: dict[int, list[str]] = {}

    for record in records:
        pages.setdefault(record.page_number, []).append(record.text)

    return pages


def find_matching_airflow_pair(
    lines: list[str],
    start_index: int,
    zul_re: re.Pattern[str],
    abl_re: re.Pattern[str],
) -> tuple[re.Match[str], re.Match[str], int] | None:
    """Sucht zu einer Zuluftzeile eine nahe Abluftzeile."""
    zul_match = zul_re.search(lines[start_index])

    if not zul_match:
        return None

    last_index = min(
        len(lines),
        start_index + MAX_AIRFLOW_DISTANCE + 1,
    )

    for abl_index in range(start_index + 1, last_index):
        abl_match = abl_re.search(lines[abl_index])

        if abl_match:
            return zul_match, abl_match, abl_index

    return None


def choose_room_candidate(
    lines: list[str],
    zul_index: int,
    abl_index: int,
    preferred_offsets: list[int],
    room_pattern: re.Pattern[str] = ROOM_RE,
) -> tuple[str | None, str | None, int | None]:
    """Sucht nahe einer Luftmengenangabe nach einer Raumnummer."""
    candidate_indices = [
        zul_index + offset
        for offset in preferred_offsets
    ]

    for distance in range(1, ROOM_SEARCH_RADIUS + 1):
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
            lines[candidate_index],
            room_pattern,
        )

        if room_id:
            return room_id, rest, candidate_index

    return None, None, None


def find_operating_mode_near_block(
    lines: list[str],
    room_index: int,
    zul_index: int,
    abl_index: int,
) -> str | None:
    """
    Sucht Nominal oder Havarie in unmittelbarer Nähe eines Luftmengenblocks.

    Diese Funktion bleibt wichtig für Fälle, bei denen Nominal/Havarie
    auf einer eigenen Zeile steht. Fälle wie
    "ZUL: Nominal 400 / Havarie 2300 m3/h" werden zusätzlich direkt aus
    der ZUL-/ABL-Zeile ausgewertet.
    """
    candidate_indices: list[int] = []

    start_index = min(room_index, zul_index, abl_index)
    end_index = max(room_index, zul_index, abl_index)

    candidate_indices.extend(range(start_index, end_index + 1))

    candidate_indices.extend(
        [
            room_index - 3,
            room_index - 2,
            room_index - 1,
            room_index + 1,
            room_index + 2,
            zul_index - 2,
            zul_index - 1,
            zul_index,
            zul_index + 1,
            abl_index - 1,
            abl_index,
            abl_index + 1,
            abl_index + 2,
        ]
    )

    already_tested: set[int] = set()

    for index in candidate_indices:
        if index in already_tested:
            continue

        already_tested.add(index)

        if not 0 <= index < len(lines):
            continue

        operating_mode = detect_operating_mode(lines[index])

        if operating_mode:
            return operating_mode

    return None


def infer_room_name(
    lines: list[str],
    room_index: int,
    zul_index: int,
    rest: str | None,
    room_pattern: re.Pattern[str] = ROOM_RE,
) -> str | None:
    """Sucht den wahrscheinlichsten Raumnamen."""
    cleaned_rest = remove_operating_mode_from_text(rest)

    if cleaned_rest:
        return cleaned_rest

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

        if detect_operating_mode(candidate):
            continue

        candidate_room_id, _ = find_room_in_line(candidate, room_pattern)

        if candidate_room_id:
            continue

        if re.fullmatch(r"[\d\s'’`.,:/+\-]+", candidate):
            continue

        candidate = remove_operating_mode_from_text(candidate)

        if candidate:
            return candidate

    return None


def extract_mode_values_from_airflow_line(text: str) -> dict[str, int | None]:
    """
    Extrahiert Luftmengen pro Betriebsart aus einer einzelnen ZUL-/ABL-Zeile.

    Beispiel:
        "ZUL: Nominal 400 / Havarie 2300 m3/h"

    Ergebnis:
        {
            "Nominal": 400,
            "Havarie": 2300,
        }
    """
    values: dict[str, int | None] = {}

    cleaned = re.sub(r"\s+", " ", str(text)).strip()

    for keyword, display_name in OPERATING_MODES.items():
        match = re.search(
            rf"\b{re.escape(keyword)}\b\s*[:=]?\s*([0-9][0-9'’` ]*|\?)",
            cleaned,
            flags=re.IGNORECASE,
        )

        if match:
            values[display_name] = normalize_number(match.group(1))

    return values


def build_airflow_records_from_pair(
    zul_line: str,
    abl_line: str,
    zul_match: re.Match[str],
    abl_match: re.Match[str],
    fallback_operating_mode: str | None,
) -> list[dict[str, int | str | None]]:
    """
    Baut einen oder mehrere Luftmengen-Datensätze aus einer ZUL-/ABL-Zeile.

    Neu unterstützter Fall:
        ZUL: Nominal 400 / Havarie 2300 m3/h
        ABL: Nominal 400 / Havarie 2400 m3/h

    Daraus entstehen zwei Datensätze:
        Nominal: ZUL 400, ABL 400
        Havarie: ZUL 2300, ABL 2400
    """
    zul_mode_values = extract_mode_values_from_airflow_line(zul_line)
    abl_mode_values = extract_mode_values_from_airflow_line(abl_line)

    has_inline_modes = bool(zul_mode_values or abl_mode_values)

    if has_inline_modes:
        records: list[dict[str, int | str | None]] = []

        for display_name in OPERATING_MODES.values():
            if display_name not in zul_mode_values and display_name not in abl_mode_values:
                continue

            records.append(
                {
                    "betriebsart": display_name,
                    "zul": zul_mode_values.get(display_name),
                    "abl": abl_mode_values.get(display_name),
                }
            )

        return records

    return [
        {
            "betriebsart": fallback_operating_mode,
            "zul": normalize_number(zul_match.group(1)),
            "abl": normalize_number(abl_match.group(1)),
        }
    ]


def extract_rooms_from_pages(
    page_lines: dict[int, list[str]],
    source_type: str,
    room_pattern: re.Pattern[str] = ROOM_RE,
) -> pd.DataFrame:
    """
    Extrahiert Raumnummer, Raumname, Zuluft, Abluft und Betriebsart.

    Jeder vollständige ZUL-/ABL-Block wird als eigener Datensatz gespeichert.
    Wenn in einer ZUL-/ABL-Zeile mehrere Betriebsarten stehen, z.B.
    Nominal und Havarie, werden daraus mehrere Datensätze erzeugt.
    """
    if source_type == "grundriss":
        zul_re = re.compile(
            r"^ZUL\s*:.*?\b([0-9][0-9'’` ]*|\?)\s*(?:m|$)",
            re.IGNORECASE,
        )
        abl_re = re.compile(
            r"^ABL\s*:.*?\b([0-9][0-9'’` ]*|\?)\s*(?:m|$)",
            re.IGNORECASE,
        )
        preferred_offsets = [-1, 2, -2, 3]

    elif source_type == "schema":
        zul_re = re.compile(
            r"^Zuluft\s*:?.*?\b([0-9][0-9'’` ]*|\?)\s*(?:m|$)",
            re.IGNORECASE,
        )
        abl_re = re.compile(
            r"^Abluft\s*:?.*?\b([0-9][0-9'’` ]*|\?)\s*(?:m|$)",
            re.IGNORECASE,
        )
        preferred_offsets = [-1, -2, 2, 3]

    else:
        raise ValueError("source_type muss 'grundriss' oder 'schema' sein.")

    rooms: list[dict[str, object]] = []

    for page_number, lines in page_lines.items():
        block_index = 0

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
                room_pattern,
            )

            if room_id is None or room_index is None:
                continue

            block_index += 1

            room_name = infer_room_name(
                lines,
                room_index,
                zul_index,
                rest,
                room_pattern,
            )

            fallback_operating_mode = find_operating_mode_near_block(
                lines,
                room_index,
                zul_index,
                abl_index,
            )

            airflow_records = build_airflow_records_from_pair(
                zul_line=lines[zul_index],
                abl_line=lines[abl_index],
                zul_match=zul_match,
                abl_match=abl_match,
                fallback_operating_mode=fallback_operating_mode,
            )

            for airflow_record in airflow_records:
                rooms.append(
                    {
                        "raumnummer": room_id,
                        "raumname": room_name,
                        "betriebsart": airflow_record["betriebsart"],
                        "zul": airflow_record["zul"],
                        "abl": airflow_record["abl"],
                        "seite": page_number,
                        "block_index": block_index,
                        "quelle": source_type,
                    }
                )

    columns = [
        "raumnummer",
        "raumname",
        "betriebsart",
        "zul",
        "abl",
        "seite",
        "block_index",
        "quelle",
    ]

    if not rooms:
        return pd.DataFrame(columns=columns)

    return (
        pd.DataFrame(rooms, columns=columns)
        .drop_duplicates()
        .sort_values(
            [
                "raumnummer",
                "seite",
                "block_index",
                "betriebsart",
            ]
        )
        .reset_index(drop=True)
    )
