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
    NUMERIC_ROOM_SEARCH_RADIUS,
    NUMERIC_FLOOR_ROOM_PATTERN,
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


def is_numeric_floor_room_pattern(
    room_pattern: re.Pattern[str],
) -> bool:
    """
    Erkennt die feste Option «Numerisch - Geschoss.Raum».

    Der Vergleich über den Pattern-Text hält die Schnittstelle zu den
    bestehenden Modulen unverändert: run_comparison kann weiterhin einfach
    das kompilierte Regex an diese Datei übergeben.
    """
    return (
        room_pattern.pattern
        == NUMERIC_FLOOR_ROOM_PATTERN
    )


def normalize_numeric_room_id(
    room_id: str,
) -> str:
    """
    Vereinheitlicht numerische Geschoss-/Raumnummern.

    Wichtig:
    Nur der Geschossteil VOR dem Punkt wird numerisch normalisiert.
    Der Raumteil NACH dem Punkt bleibt exakt erhalten.

    Beispiele:
        -01.503 -> -1.503
        -01.230 -> -1.230
        -01.200 -> -1.200
        -01.010 -> -1.010
        00.302  -> 0.302
        01.514  -> 1.514
        02.004  -> 2.004
        2.4     -> 2.4

    Dadurch bleiben unterschiedliche Räume wie -1.230 und -1.23
    eindeutig voneinander getrennt.
    """
    cleaned = re.sub(
        r"\s+",
        "",
        str(room_id),
    )

    floor_text, room_text = cleaned.split(
        ".",
        1,
    )

    floor_value = int(
        floor_text
    )

    return (
        f"{floor_value}."
        f"{room_text}"
    )


def is_plausible_numeric_room_match(
    line: str,
    match: re.Match[str],
) -> bool:
    """
    Filtert typische Dezimalzahlen heraus, die keine Raumnummern sind.

    Auf Flächenplänen stehen neben echten Raumnummern viele Werte wie:
        BF: 41.56 m2
        RH: 2.885 m
        OK FB: 3.50
        OK RB: 3.53

    Diese dürfen nicht als Räume interpretiert werden.
    """
    text = re.sub(
        r"\s+",
        " ",
        str(line),
    ).strip()

    before = text[
        :match.start()
    ].strip()

    after = text[
        match.end():
    ].strip()

    before_upper = before.upper()
    after_upper = after.upper()

    # Positive Koten wie +3.88 oder ±0.00 sind keine Raumnummern.
    if (
        match.start() > 0
        and text[
            match.start() - 1
        ] in {
            "+",
            "±",
        }
    ):
        return False

    # Typische Planattribute direkt vor einer Dezimalzahl.
    measurement_prefixes = (
        "BF:",
        "BF ",
        "RH:",
        "RH ",
        "OK FB:",
        "OK FB ",
        "OK RB:",
        "OK RB ",
        "UK FB:",
        "UK RB:",
        "H:",
        "B:",
        "L:",
        "D:",
        "R:",
        "T:",
    )

    if any(
        before_upper.endswith(
            prefix
        )
        for prefix in measurement_prefixes
    ):
        return False

    # Einheiten direkt hinter einer Dezimalzahl.
    if re.match(
        r"^(?:M²|M2|M3|M³|M\\b|MM\\b|CM\\b|°C|%|L/MIN\\b|1/H\\b)",
        after_upper,
    ):
        return False

    # Zusätzliche typische technische Schreibweisen.
    if re.search(
        r"(?:^|\\s)(?:BF|RH|OK\\s*FB|OK\\s*RB|UK\\s*FB|UK\\s*RB)\\s*:\\s*$",
        before_upper,
    ):
        return False

    return True


def find_room_in_line(
    line: str,
    room_pattern: re.Pattern[str] = ROOM_RE,
) -> tuple[str | None, str | None]:
    """
    Sucht eine Raumnummer und möglichen Resttext in einer Zeile.

    Bei «Numerisch - Geschoss.Raum» werden nicht einfach alle
    Dezimalzahlen akzeptiert. Typische Flächen-, Höhen- und Kotenwerte
    werden vorher ausgeschlossen.
    """
    text = line or ""

    numeric_mode = is_numeric_floor_room_pattern(
        room_pattern
    )

    for match in room_pattern.finditer(
        text
    ):
        if (
            numeric_mode
            and not is_plausible_numeric_room_match(
                text,
                match,
            )
        ):
            continue

        room_id = match.group(
            0
        )

        if numeric_mode:
            room_id = normalize_numeric_room_id(
                room_id
            )

        rest = (
            text[
                :match.start()
            ]
            + " "
            + text[
                match.end():
            ]
        ).strip()

        rest = re.sub(
            r"\s+",
            " ",
            rest,
        )

        return (
            room_id,
            rest or None,
        )

    return None, None


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

    search_radius = (
        NUMERIC_ROOM_SEARCH_RADIUS
        if is_numeric_floor_room_pattern(
            room_pattern
        )
        else ROOM_SEARCH_RADIUS
    )

    for distance in range(
        1,
        search_radius + 1,
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



def extract_ep_number_near_block(
    lines: list[str],
    abl_index: int,
) -> str | None:
    """
    Sucht die ep-Nummer direkt nach einem ZUL/ABL-Block.

    Beispiel Grundriss:
        -1.227
        ZUL: 9100m3/h
        ABL: 9500m3/h
        ep: 219
    """
    ep_re = re.compile(
        r"^\s*ep\s*:\s*(\d{1,5})\s*$",
        re.IGNORECASE,
    )

    search_end = min(
        len(lines),
        abl_index + 5,
    )

    for index in range(
        abl_index + 1,
        search_end,
    ):
        match = ep_re.fullmatch(
            lines[index].strip()
        )

        if match:
            return match.group(1)

    return None



def is_ep_primary_numeric_mode() -> bool:
    """
    Dokumentiert die Regel für «Numerisch - Geschoss.Raum»:

    Vergleichsrelevant sind ausschließlich die von e+p ergänzten
    Luftmengenblöcke mit ZUL / ABL / ep.

    Die ursprünglichen architektonischen Raumbeschriftungen im Grundriss
    werden NICHT als zusätzliche Räume in die Rohdaten aufgenommen.
    Dadurch entstehen keine künstlichen Doppelungen.
    """
    return True

def extract_numeric_floorplan_rooms(
    pdf_path: Path,
    room_pattern: re.Pattern[str],
) -> pd.DataFrame:
    """
    Extrahiert numerische Grundrissräume inklusive ep-Nummer.

    Für diesen Gebäudetyp ist die ep-Nummer der robuste gemeinsame
    Schlüssel zwischen Grundriss und Prinzipschema.
    """
    records = extract_clean_lines(
        pdf_path
    )

    page_lines = split_lines_by_page(
        records
    )

    zul_re = re.compile(
        r"^ZUL\s*:.*?\b([0-9][0-9'’` ]*|\?)\s*(?:m|$)",
        re.IGNORECASE,
    )

    abl_re = re.compile(
        r"^ABL\s*:.*?\b([0-9][0-9'’` ]*|\?)\s*(?:m|$)",
        re.IGNORECASE,
    )

    preferred_offsets = [
        -1,
        2,
        -2,
        3,
    ]

    rows: list[dict[str, object]] = []

    for page_number, lines in page_lines.items():
        block_index = 0

        for zul_index in range(
            len(lines)
        ):
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

            ep_number = extract_ep_number_near_block(
                lines,
                abl_index,
            )

            fallback_operating_mode = (
                find_operating_mode_near_block(
                    lines,
                    room_index,
                    zul_index,
                    abl_index,
                )
            )

            airflow_records = build_airflow_records_from_pair(
                zul_line=lines[zul_index],
                abl_line=lines[abl_index],
                zul_match=zul_match,
                abl_match=abl_match,
                fallback_operating_mode=fallback_operating_mode,
            )

            for airflow_record in airflow_records:
                rows.append(
                    {
                        "raumnummer": room_id,
                        "raumname": room_name,
                        "betriebsart": airflow_record["betriebsart"],
                        "zul": airflow_record["zul"],
                        "abl": airflow_record["abl"],
                        "seite": page_number,
                        "block_index": block_index,
                        "quelle": "grundriss",
                        "ep_nummer": ep_number,
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
        "ep_nummer",
    ]

    if not rows:
        return pd.DataFrame(
            columns=columns
        )

    return (
        pd.DataFrame(
            rows,
            columns=columns,
        )
        .drop_duplicates()
        .reset_index(
            drop=True
        )
    )


def extract_numeric_schema_blocks(
    page_lines: dict[int, list[str]],
) -> pd.DataFrame:
    """
    Extrahiert Blöcke aus dem Prinzipschema.

    Im Schema stehen die Überschriften und Werte getrennt, z.B.:

        Zuluft
        Abluft
        Anlage
        Raumfläche
        ep:
        9100 m³/h
        9500 m³/h
        Küche
        69.1 m²
        219

    Daher kann die normale Extraktion, die eine Zahl direkt auf der
    Zuluft-/Abluftzeile erwartet, diese Blöcke nicht lesen.
    """
    airflow_value_re = re.compile(
        r"^\s*([0-9][0-9'’` ]*|\?)\s*m(?:³|3)/h\s*$",
        re.IGNORECASE,
    )

    area_re = re.compile(
        r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*m(?:²|2)\s*$",
        re.IGNORECASE,
    )

    pure_int_re = re.compile(
        r"^\s*(\d{1,5})\s*$"
    )

    rows: list[dict[str, object]] = []

    for page_number, lines in page_lines.items():
        block_index = 0

        for start_index, line in enumerate(
            lines
        ):
            if not re.fullmatch(
                r"\s*Zuluft\s*",
                line,
                flags=re.IGNORECASE,
            ):
                continue

            # Nur typische Raumblock-Kopfzeilen berücksichtigen.
            window_head = [
                value.strip().casefold()
                for value in lines[
                    start_index:
                    min(
                        len(lines),
                        start_index + 6,
                    )
                ]
            ]

            if (
                "abluft" not in window_head
                or "raumfläche" not in window_head
                or "ep:" not in window_head
            ):
                continue

            search_end = min(
                len(lines),
                start_index + 14,
            )

            airflow_values: list[int | None] = []
            room_name: str | None = None
            area_m2: float | None = None
            ep_number: str | None = None

            # Nach dem Kopf folgen zwei Luftmengen, Raumname, Fläche, ep.
            for index in range(
                start_index + 1,
                search_end,
            ):
                candidate = lines[
                    index
                ].strip()

                airflow_match = airflow_value_re.fullmatch(
                    candidate
                )

                if airflow_match and len(
                    airflow_values
                ) < 2:
                    airflow_values.append(
                        normalize_number(
                            airflow_match.group(1)
                        )
                    )
                    continue

                area_match = area_re.fullmatch(
                    candidate
                )

                if (
                    area_match
                    and len(
                        airflow_values
                    ) >= 2
                ):
                    try:
                        area_m2 = float(
                            area_match.group(1).replace(
                                ",",
                                ".",
                            )
                        )
                    except ValueError:
                        area_m2 = None

                    # Die nächste reine Ganzzahl ist die ep-Nummer.
                    for ep_index in range(
                        index + 1,
                        min(
                            len(lines),
                            index + 4,
                        ),
                    ):
                        ep_match = pure_int_re.fullmatch(
                            lines[
                                ep_index
                            ].strip()
                        )

                        if ep_match:
                            ep_number = ep_match.group(
                                1
                            )
                            break

                    break

                if (
                    len(
                        airflow_values
                    ) >= 2
                    and room_name is None
                    and candidate
                    and candidate.casefold()
                    not in {
                        "zuluft",
                        "abluft",
                        "anlage",
                        "raumfläche",
                        "ep:",
                    }
                    and not airflow_value_re.fullmatch(
                        candidate
                    )
                    and not area_re.fullmatch(
                        candidate
                    )
                    and not pure_int_re.fullmatch(
                        candidate
                    )
                ):
                    room_name = candidate

            if (
                len(
                    airflow_values
                ) < 2
                or ep_number is None
            ):
                continue

            block_index += 1

            rows.append(
                {
                    "raumnummer": None,
                    "raumname": room_name,
                    "betriebsart": None,
                    "zul": airflow_values[0],
                    "abl": airflow_values[1],
                    "seite": page_number,
                    "block_index": block_index,
                    "quelle": "schema",
                    "ep_nummer": ep_number,
                    "raumflaeche_m2": area_m2,
                }
            )

    return pd.DataFrame(
        rows,
        columns=[
            "raumnummer",
            "raumname",
            "betriebsart",
            "zul",
            "abl",
            "seite",
            "block_index",
            "quelle",
            "ep_nummer",
            "raumflaeche_m2",
        ],
    )


def map_numeric_schema_by_ep(
    floorplan_df: pd.DataFrame,
    schema_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Ordnet Schema-Blöcke über die ep-Nummer dem echten Grundrissraum zu.

    Das ist deutlich robuster als eine Zuordnung über Raumflächen:
    Grundriss -1.227 hat ep 219 und das Schema ebenfalls ep 219.
    """
    if floorplan_df.empty or schema_df.empty:
        return schema_df.iloc[0:0].copy()

    if (
        "ep_nummer" not in floorplan_df.columns
        or "ep_nummer" not in schema_df.columns
    ):
        return schema_df.iloc[0:0].copy()

    mapping_source = (
        floorplan_df[
            [
                "raumnummer",
                "ep_nummer",
            ]
        ]
        .dropna(
            subset=[
                "raumnummer",
                "ep_nummer",
            ]
        )
        .drop_duplicates()
    )

    # Nur eindeutige ep -> Raumnummer-Zuordnungen verwenden.
    ep_counts = (
        mapping_source.groupby(
            "ep_nummer"
        )[
            "raumnummer"
        ]
        .nunique()
    )

    unique_eps = set(
        ep_counts[
            ep_counts == 1
        ].index.astype(
            str
        )
    )

    mapping_source = mapping_source.loc[
        mapping_source[
            "ep_nummer"
        ].astype(
            str
        ).isin(
            unique_eps
        )
    ].copy()

    ep_to_room = {
        str(
            row.ep_nummer
        ): row.raumnummer
        for row in mapping_source.itertuples(
            index=False
        )
    }

    result = schema_df.copy()

    result[
        "raumnummer"
    ] = result[
        "ep_nummer"
    ].astype(
        str
    ).map(
        ep_to_room
    )

    return (
        result.dropna(
            subset=[
                "raumnummer"
            ]
        )
        .reset_index(
            drop=True
        )
    )

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
