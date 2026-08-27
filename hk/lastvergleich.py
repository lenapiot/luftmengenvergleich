from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz
import pandas as pd

from hk.lastvergleich_excel_input import extract_loads_from_excel


# ============================================================
# REGEX
# ============================================================

ROOM_PATTERN = re.compile(
    r"\bMIT(?P<building>[12])(?P<level>[A-Z])(?P<number>\d+[A-Za-z]?)\b",
    flags=re.IGNORECASE,
)

SCHEMA_ROOM_PATTERN = re.compile(
    r"\bMIT\s*(?P<building>[12])\s*"
    r"(?P<level>[A-Z])\s*"
    r"(?P<number>\d+[A-Za-z]?)\b",
    flags=re.IGNORECASE,
)

LOAD_PATTERN = re.compile(
    r"^\s*(?P<value>[+-]?\d[\d'’`]*)\s*W\s*$",
    flags=re.IGNORECASE,
)

LOAD_PER_AREA_PATTERN = re.compile(
    r"W\s*/\s*m(?:²|2)",
    flags=re.IGNORECASE,
)

TEMPERATURE_PATTERN = re.compile(
    r"°\s*C",
    flags=re.IGNORECASE,
)

AREA_PATTERN = re.compile(
    r"\bm(?:²|2)\b",
    flags=re.IGNORECASE,
)


# ============================================================
# DATENMODELLE
# ============================================================

# Anteil des kleineren Gebäudeteils, ab dem ein Plan als echter MIT12-Plan gilt.
# Beispiel: 200 MIT1-Räume + 9 MIT2-Räume => MIT1 mit MIT2-Rest.
# Bei mindestens 10 % Minderheitsanteil => MIT12.
MIT12_MINORITY_THRESHOLD = 0.10


@dataclass(frozen=True)
class LoadRecord:
    raumnummer: str
    raumname: str | None
    leistung_w: int | None
    vergleichswert_w: int | None
    ist_marker: bool
    marker_typ: str | None
    lastart: str
    gebaeude: str
    ebene: str
    datei: str
    seite: int


@dataclass(frozen=True)
class FileBuildingCheck:
    datei: str
    pfad: str
    lastart: str
    erkanntes_gebaeude: str
    erwartetes_gebaeude: str | None
    akzeptiert: bool
    grund: str
    anzahl_datensaetze: int
    anzahl_raeume: int
    anzahl_raeume_verwendet: int
    anzahl_raeume_anderes_gebaeude: int


@dataclass(frozen=True)
class SchemaRecord:
    raumnummer: str
    raumname: str | None
    q_h_w: int | None
    q_k_w: int | None
    gebaeude: str
    ebene: str
    datei: str
    seite: int
    x: float
    y: float


# ============================================================
# ALLGEMEINE NORMALISIERUNG
# ============================================================

def normalize_line(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_watt_value(value: object) -> int | None:
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

    if not cleaned:
        return None

    try:
        return int(cleaned)
    except ValueError:
        return None


# ============================================================
# RAUMNUMMERN
# ============================================================

def normalize_room_id(room_id: str) -> str:
    match = ROOM_PATTERN.search(room_id or "")

    if not match:
        return room_id.strip()

    building = match.group("building")
    level = match.group("level").upper()
    number = match.group("number")

    number_match = re.fullmatch(r"(\d+)([A-Za-z]?)", number)

    if not number_match:
        return f"MIT{building}{level}{number}"

    digits = number_match.group(1)
    suffix = number_match.group(2).lower()

    return f"MIT{building}{level}{digits}{suffix}"


def normalize_schema_room_id(text: str) -> str | None:
    cleaned = normalize_line(text)
    match = SCHEMA_ROOM_PATTERN.search(cleaned)

    if not match:
        return None

    building = match.group("building")
    level = match.group("level").upper()
    number = match.group("number")

    number_match = re.fullmatch(r"(\d+)([A-Za-z]?)", number)

    if not number_match:
        return f"MIT{building}{level}{number}"

    digits = number_match.group(1)
    suffix = number_match.group(2).lower()

    return f"MIT{building}{level}{digits}{suffix}"


def extract_room_ids(text: str) -> list[str]:
    return [
        normalize_room_id(match.group(0))
        for match in ROOM_PATTERN.finditer(text or "")
    ]


def get_building_from_room(room_id: str) -> str:
    normal = normalize_schema_room_id(room_id) or normalize_room_id(room_id)
    match = ROOM_PATTERN.search(normal or "")

    if not match:
        return "Unbekannt"

    return f"MIT{match.group('building')}"


def get_level_from_room(room_id: str) -> str:
    normal = normalize_schema_room_id(room_id) or normalize_room_id(room_id)
    match = ROOM_PATTERN.search(normal or "")

    if not match:
        return "?"

    return match.group("level").upper()


# ============================================================
# GRUNDRISS: LASTEN
# ============================================================

def parse_single_load_line(text: str) -> int | None:
    cleaned = normalize_line(text)

    if LOAD_PER_AREA_PATTERN.search(cleaned):
        return None

    match = LOAD_PATTERN.fullmatch(cleaned)

    if not match:
        return None

    return normalize_watt_value(match.group("value"))


# ============================================================
# MARKERLOGIK
# ============================================================

def evaluate_marker(
    value: int | None,
    load_type: str,
) -> tuple[bool, str | None, int | None]:
    """
    Projektregel:

    Heizlast:
        -1 W = 0 W + geprüft

    Kühllast:
        +1 W = 0 W + geprüft
    """
    if value is None:
        return False, None, None

    normalized_type = load_type.strip().casefold()

    if normalized_type == "heizlast" and value == -1:
        return True, "0 W + geprüft", 0

    if normalized_type == "kühllast" and value == 1:
        return True, "0 W + geprüft", 0

    return False, None, value


def is_marker_value(
    value: int | None,
    load_type: str,
) -> tuple[bool, str | None]:
    marker, marker_type, _ = evaluate_marker(value, load_type)
    return marker, marker_type


def get_comparison_value(
    value: int | None,
    load_type: str,
) -> int | None:
    _, _, comparison_value = evaluate_marker(value, load_type)
    return comparison_value


# ============================================================
# GRUNDRISS: LEISTUNG IN RAUMNÄHE
# ============================================================

def find_load_near_room(
    lines: list[str],
    room_index: int,
    search_before: int = 7,
    search_after: int = 3,
) -> tuple[int | None, int | None]:
    start = max(0, room_index - search_before)

    for index in range(room_index - 1, start - 1, -1):
        value = parse_single_load_line(lines[index])

        if value is not None:
            return value, index

    end = min(len(lines), room_index + search_after + 1)

    for index in range(room_index + 1, end):
        value = parse_single_load_line(lines[index])

        if value is not None:
            return value, index

    return None, None


# ============================================================
# GRUNDRISS: RAUMNAME
# ============================================================

def clean_room_name_candidate(text: str) -> str | None:
    candidate = normalize_line(text)

    if not candidate:
        return None

    candidate = ROOM_PATTERN.sub(" ", candidate)
    candidate = normalize_line(candidate)

    if not candidate:
        return None

    if parse_single_load_line(candidate) is not None:
        return None

    if LOAD_PER_AREA_PATTERN.search(candidate):
        return None

    if TEMPERATURE_PATTERN.search(candidate):
        return None

    if AREA_PATTERN.search(candidate):
        return None

    if re.fullmatch(r"[\d.,+\-/'’` ]+", candidate):
        return None

    return candidate


def find_room_name(
    lines: list[str],
    room_index: int,
    load_index: int | None,
) -> str | None:
    current_line_name = clean_room_name_candidate(lines[room_index])

    if current_line_name:
        return current_line_name

    if load_index is not None:
        for index in range(
            load_index - 1,
            max(-1, load_index - 4),
            -1,
        ):
            if not (0 <= index < len(lines)):
                continue

            candidate = clean_room_name_candidate(lines[index])

            if candidate:
                return candidate

    candidate_indices = [
        room_index - 1,
        room_index - 2,
        room_index + 1,
        room_index + 2,
    ]

    for index in candidate_indices:
        if not (0 <= index < len(lines)):
            continue

        candidate = clean_room_name_candidate(lines[index])

        if candidate:
            return candidate

    return None


# ============================================================
# GRUNDRISS: PDF-TEXT
# ============================================================

def extract_page_lines(page: fitz.Page) -> list[str]:
    raw_text = page.get_text("text")

    return [
        normalize_line(line)
        for line in raw_text.splitlines()
        if normalize_line(line)
    ]


# ============================================================
# GRUNDRISS: EINZELNE PDF
# ============================================================

def extract_loads_from_pdf(
    pdf_path: str | Path,
    load_type: str,
) -> pd.DataFrame:
    pdf_path = Path(pdf_path)
    normalized_type = load_type.strip().casefold()

    if normalized_type not in {"heizlast", "kühllast"}:
        raise ValueError(
            "load_type muss 'Heizlast' oder 'Kühllast' sein."
        )

    display_type = (
        "Heizlast"
        if normalized_type == "heizlast"
        else "Kühllast"
    )

    records: list[LoadRecord] = []

    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(document):
            lines = extract_page_lines(page)

            for room_index, line in enumerate(lines):
                room_ids = extract_room_ids(line)

                if not room_ids:
                    continue

                load_value, load_index = find_load_near_room(
                    lines,
                    room_index,
                )

                room_name = find_room_name(
                    lines,
                    room_index,
                    load_index,
                )

                marker, marker_type, comparison_value = evaluate_marker(
                    load_value,
                    display_type,
                )

                for room_id in room_ids:
                    records.append(
                        LoadRecord(
                            raumnummer=room_id,
                            raumname=room_name,
                            leistung_w=load_value,
                            vergleichswert_w=comparison_value,
                            ist_marker=marker,
                            marker_typ=marker_type,
                            lastart=display_type,
                            gebaeude=get_building_from_room(room_id),
                            ebene=get_level_from_room(room_id),
                            datei=pdf_path.name,
                            seite=page_index + 1,
                        )
                    )

    columns = [
        "raumnummer",
        "raumname",
        "leistung_w",
        "vergleichswert_w",
        "ist_marker",
        "marker_typ",
        "lastart",
        "gebaeude",
        "ebene",
        "datei",
        "seite",
    ]

    if not records:
        return pd.DataFrame(columns=columns)

    dataframe = pd.DataFrame(
        [
            {
                "raumnummer": record.raumnummer,
                "raumname": record.raumname,
                "leistung_w": record.leistung_w,
                "vergleichswert_w": record.vergleichswert_w,
                "ist_marker": record.ist_marker,
                "marker_typ": record.marker_typ,
                "lastart": record.lastart,
                "gebaeude": record.gebaeude,
                "ebene": record.ebene,
                "datei": record.datei,
                "seite": record.seite,
            }
            for record in records
        ],
        columns=columns,
    )

    return (
        dataframe
        .drop_duplicates()
        .sort_values(
            [
                "gebaeude",
                "ebene",
                "raumnummer",
                "datei",
                "seite",
            ]
        )
        .reset_index(drop=True)
    )


# ============================================================
# GEBÄUDEERKENNUNG
# ============================================================

def determine_document_building(
    dataframe: pd.DataFrame,
) -> str:
    """
    Bestimmt den Gebäudeumfang eines STRANGSCHEMAS anhand seiner
    eindeutigen Raumnummern.

    Projektregel:
    - nur MIT1-Räume -> MIT1
    - nur MIT2-Räume -> MIT2
    - MIT1 + MIT2:
        Minderheitsanteil < 10 %  -> dominantes Gebäude
        Minderheitsanteil >= 10 % -> MIT12

    Das verhindert, dass einzelne stehengebliebene Räume des anderen
    Gebäudeteils ein eigentliches MIT1- oder MIT2-Strangschema fälschlich
    zu MIT12 machen.
    """
    if dataframe.empty:
        return "Unbekannt"

    if "gebaeude" not in dataframe.columns:
        return "Unbekannt"

    room_counts = {}

    for building_name in ("MIT1", "MIT2"):
        if "raumnummer" in dataframe.columns:
            count = int(
                dataframe.loc[
                    dataframe["gebaeude"] == building_name,
                    "raumnummer",
                ]
                .dropna()
                .astype(str)
                .nunique()
            )
        else:
            count = int(
                (
                    dataframe["gebaeude"]
                    .astype(str)
                    == building_name
                ).sum()
            )

        room_counts[building_name] = count

    mit1_count = room_counts["MIT1"]
    mit2_count = room_counts["MIT2"]
    total = mit1_count + mit2_count

    if total == 0:
        return "Unbekannt"

    if mit1_count > 0 and mit2_count == 0:
        return "MIT1"

    if mit2_count > 0 and mit1_count == 0:
        return "MIT2"

    if mit1_count >= mit2_count:
        dominant = "MIT1"
        minority_count = mit2_count
    else:
        dominant = "MIT2"
        minority_count = mit1_count

    minority_share = (
        minority_count / total
    )

    if (
        minority_share
        >= MIT12_MINORITY_THRESHOLD
    ):
        return "MIT12"

    return dominant


def _allowed_buildings_for_schema(
    expected_building: str | None,
) -> set[str]:
    """
    Gebäudeumfang des gewählten Strangschemas.

    MIT1  -> nur MIT1-Räume
    MIT2  -> nur MIT2-Räume
    MIT12 -> MIT1- und MIT2-Räume
    None  -> beide Gebäudeteile
    """
    if expected_building is None:
        return {"MIT1", "MIT2"}

    expected = expected_building.strip().upper()

    if expected == "MIT1":
        return {"MIT1"}

    if expected == "MIT2":
        return {"MIT2"}

    if expected == "MIT12":
        return {"MIT1", "MIT2"}

    raise ValueError(
        "expected_building muss None, 'MIT1', 'MIT2' oder 'MIT12' sein."
    )


def filter_schema_for_building(
    consolidated_schema: pd.DataFrame,
    building: str,
) -> pd.DataFrame:
    """
    Beschränkt ein konsolidiertes Strangschema auf den tatsächlich
    erkannten Gebäudeumfang.

    Fachregel:
    - MIT1  -> nur MIT1-Räume
    - MIT2  -> nur MIT2-Räume
    - MIT12 -> MIT1- und MIT2-Räume

    Dadurch werden einzelne stehengebliebene Räume des anderen
    Gebäudeteils nicht in den fachlichen Abgleich übernommen.
    """
    allowed_buildings = _allowed_buildings_for_schema(
        building
    )

    if consolidated_schema.empty:
        return consolidated_schema.copy()

    if "gebaeude" not in consolidated_schema.columns:
        raise ValueError(
            "Das konsolidierte Strangschema enthält keine Spalte 'gebaeude'."
        )

    filtered = (
        consolidated_schema.loc[
            consolidated_schema[
                "gebaeude"
            ].isin(
                allowed_buildings
            )
        ]
        .copy()
        .reset_index(drop=True)
    )

    return filtered


# ============================================================
# EINZELDATEI-GEBÄUDEPRÜFUNG
# ============================================================

def check_pdf_building(
    pdf_path: str | Path,
    load_type: str,
    expected_building: str | None = None,
) -> tuple[pd.DataFrame, FileBuildingCheck]:
    """
    Liest einen Heiz-/Kühllast-Grundriss und filtert ihn ausschliesslich
    nach dem Gebäudeumfang des Strangschemas.

    Fachregel:
    - MIT1-Schema  -> nur MIT1-Räume
    - MIT2-Schema  -> nur MIT2-Räume
    - MIT12-Schema -> MIT1- und MIT2-Räume

    Räume des anderen Gebäudeteils werden dokumentiert, aber nicht bewertet.
    Eine PDF wird NICHT abgelehnt, nur weil sie zusätzlich Räume des anderen
    Gebäudeteils enthält.
    """
    pdf_path = Path(pdf_path)

    raw_dataframe = extract_loads_from_pdf(
        pdf_path,
        load_type,
    )

    allowed_buildings = _allowed_buildings_for_schema(
        expected_building
    )

    detected_building = determine_document_building(
        raw_dataframe
    )

    expected = (
        expected_building.strip().upper()
        if expected_building
        else None
    )

    valid_building_mask = (
        raw_dataframe["gebaeude"].isin(
            allowed_buildings
        )
        if not raw_dataframe.empty
        else pd.Series(
            dtype=bool
        )
    )

    if raw_dataframe.empty:
        used_dataframe = raw_dataframe.copy()
        other_building_dataframe = raw_dataframe.copy()
    else:
        used_dataframe = (
            raw_dataframe.loc[
                valid_building_mask
            ]
            .copy()
        )

        other_building_dataframe = (
            raw_dataframe.loc[
                raw_dataframe["gebaeude"].isin(
                    {"MIT1", "MIT2"}
                )
                & ~valid_building_mask
            ]
            .copy()
        )

    # Die Datei ist akzeptiert, sobald sie mindestens einen für das
    # Strangschema relevanten Raum enthält. Bei leerer Extraktion oder
    # ausschliesslich falschem Gebäudeteil wird sie nicht verwendet.
    accepted = not used_dataframe.empty

    if raw_dataframe.empty:
        reason = (
            "Keine gültigen Lastdaten erkannt."
        )
    elif accepted and other_building_dataframe.empty:
        reason = "OK"
    elif accepted:
        reason = (
            f"Für {expected or 'MIT1/MIT2'} relevante Räume werden ausgewertet. "
            "Räume des anderen Gebäudeteils werden nicht in den Abgleich "
            "einbezogen."
        )
    else:
        reason = (
            f"Keine Räume passend zum Strangschema "
            f"{expected or 'MIT1/MIT2'} gefunden."
        )

    if not other_building_dataframe.empty:
        other_building_dataframe[
            "zielgebaeude"
        ] = expected

        other_building_dataframe[
            "nicht_geprueft_grund"
        ] = (
            "Anderer Gebäudeteil als im Strangschema – "
            "nicht in den Abgleich einbezogen"
        )

    used_dataframe.attrs[
        "nicht_gepruefte_raeume"
    ] = other_building_dataframe

    check = FileBuildingCheck(
        datei=pdf_path.name,
        pfad=str(pdf_path),
        lastart=load_type,
        erkanntes_gebaeude=detected_building,
        erwartetes_gebaeude=expected,
        akzeptiert=accepted,
        grund=reason,
        anzahl_datensaetze=len(raw_dataframe),
        anzahl_raeume=(
            raw_dataframe["raumnummer"].nunique()
            if not raw_dataframe.empty
            else 0
        ),
        anzahl_raeume_verwendet=(
            used_dataframe["raumnummer"].nunique()
            if not used_dataframe.empty
            else 0
        ),
        anzahl_raeume_anderes_gebaeude=(
            other_building_dataframe["raumnummer"].nunique()
            if not other_building_dataframe.empty
            else 0
        ),
    )

    return used_dataframe, check


# ============================================================
# MEHRERE GRUNDRISSE MIT PRÜFUNG
# ============================================================

def extract_loads_from_pdfs_checked(
    pdf_paths: Iterable[str | Path],
    load_type: str,
    expected_building: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    accepted_frames: list[pd.DataFrame] = []
    not_checked_frames: list[pd.DataFrame] = []
    checks: list[FileBuildingCheck] = []

    for pdf_path in pdf_paths:
        dataframe, check = check_pdf_building(
            pdf_path,
            load_type,
            expected_building,
        )

        checks.append(check)

        not_checked = dataframe.attrs.get(
            "nicht_gepruefte_raeume"
        )

        if (
            isinstance(not_checked, pd.DataFrame)
            and not not_checked.empty
        ):
            not_checked_frame = not_checked.copy()
            not_checked_frame.attrs = {}

            not_checked_frames.append(
                not_checked_frame
            )

        if check.akzeptiert and not dataframe.empty:
            # Wichtig:
            # check_pdf_building() speichert die nicht geprüften MIT12-Räume
            # temporär in dataframe.attrs. pandas vergleicht beim concat()
            # die attrs der einzelnen DataFrames. Da darin wiederum
            # DataFrames liegen können, würde das zu
            # "Can only compare identically-labeled DataFrame objects"
            # führen. Deshalb werden die attrs vor dem Zusammenführen
            # bewusst entfernt; die nicht geprüften Räume wurden oben
            # bereits separat übernommen.
            accepted_frame = dataframe.copy()
            accepted_frame.attrs = {}

            accepted_frames.append(
                accepted_frame
            )

    data_columns = [
        "raumnummer",
        "raumname",
        "leistung_w",
        "vergleichswert_w",
        "ist_marker",
        "marker_typ",
        "lastart",
        "gebaeude",
        "ebene",
        "datei",
        "seite",
    ]

    if accepted_frames:
        combined = (
            pd.concat(
                accepted_frames,
                ignore_index=True,
            )
            .drop_duplicates()
            .sort_values(
                [
                    "gebaeude",
                    "ebene",
                    "raumnummer",
                    "datei",
                    "seite",
                ]
            )
            .reset_index(drop=True)
        )
    else:
        combined = pd.DataFrame(
            columns=data_columns
        )

    if not_checked_frames:
        not_checked_combined = (
            pd.concat(
                not_checked_frames,
                ignore_index=True,
            )
            .drop_duplicates()
            .reset_index(drop=True)
        )

        not_checked_combined = _safe_sort_load_dataframe(
            not_checked_combined
        )
    else:
        not_checked_combined = pd.DataFrame(
            columns=[
                *data_columns,
                "zielgebaeude",
                "nicht_geprueft_grund",
            ]
        )

    combined.attrs["nicht_gepruefte_raeume"] = (
        not_checked_combined
    )

    check_columns = [
        "datei",
        "pfad",
        "lastart",
        "erkanntes_gebaeude",
        "erwartetes_gebaeude",
        "akzeptiert",
        "grund",
        "anzahl_datensaetze",
        "anzahl_raeume",
        "anzahl_raeume_verwendet",
        "anzahl_raeume_anderes_gebaeude",
    ]

    check_dataframe = pd.DataFrame(
        [
            {
                "datei": check.datei,
                "pfad": check.pfad,
                "lastart": check.lastart,
                "erkanntes_gebaeude": check.erkanntes_gebaeude,
                "erwartetes_gebaeude": check.erwartetes_gebaeude,
                "akzeptiert": check.akzeptiert,
                "grund": check.grund,
                "anzahl_datensaetze": check.anzahl_datensaetze,
                "anzahl_raeume": check.anzahl_raeume,
                "anzahl_raeume_verwendet":
                    check.anzahl_raeume_verwendet,
                "anzahl_raeume_anderes_gebaeude":
                    check.anzahl_raeume_anderes_gebaeude,
            }
            for check in checks
        ],
        columns=check_columns,
    )

    return combined, check_dataframe


# ============================================================
# ALTE MEHRFACHFUNKTION
# ============================================================

def extract_loads_from_pdfs(
    pdf_paths: Iterable[str | Path],
    load_type: str,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for pdf_path in pdf_paths:
        frame = extract_loads_from_pdf(
            pdf_path,
            load_type,
        )

        if not frame.empty:
            frames.append(frame)

    columns = [
        "raumnummer",
        "raumname",
        "leistung_w",
        "vergleichswert_w",
        "ist_marker",
        "marker_typ",
        "lastart",
        "gebaeude",
        "ebene",
        "datei",
        "seite",
    ]

    if not frames:
        return pd.DataFrame(columns=columns)

    return (
        pd.concat(
            frames,
            ignore_index=True,
        )
        .drop_duplicates()
        .sort_values(
            [
                "gebaeude",
                "ebene",
                "raumnummer",
                "datei",
                "seite",
            ]
        )
        .reset_index(drop=True)
    )



def _safe_sort_load_dataframe(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Sortiert Lastdaten robust, auch wenn einzelne Sortierspalten
    None/NaN enthalten. Die Originalspalten werden nicht verändert.
    """
    if dataframe.empty:
        return dataframe.copy()

    result = dataframe.copy()

    sort_columns = [
        column
        for column in (
            "gebaeude",
            "ebene",
            "raumnummer",
            "datei",
            "seite",
        )
        if column in result.columns
    ]

    if not sort_columns:
        return result.reset_index(drop=True)

    temp_columns: list[str] = []

    for column in sort_columns:
        temp_column = (
            f"__sort_{column}"
        )
        temp_columns.append(
            temp_column
        )

        if column == "seite":
            # Excel-Zeile / PDF-Seite:
            # fehlende Werte werden ans Ende sortiert.
            result[temp_column] = pd.to_numeric(
                result[column],
                errors="coerce",
            ).fillna(
                10**12
            )
        else:
            result[temp_column] = (
                result[column]
                .fillna("")
                .astype(str)
            )

    result = (
        result
        .sort_values(
            temp_columns,
            kind="stable",
        )
        .drop(
            columns=temp_columns,
        )
        .reset_index(drop=True)
    )

    return result


# ============================================================
# EXCEL: HEIZ-/KÜHLLASTEN IN BESTEHENDES DATENMODELL ÜBERFÜHREN
# ============================================================

def _empty_load_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "raumnummer",
            "raumname",
            "leistung_w",
            "vergleichswert_w",
            "ist_marker",
            "marker_typ",
            "lastart",
            "gebaeude",
            "ebene",
            "datei",
            "seite",
        ]
    )


def _filter_dataframe_for_expected_building(
    dataframe: pd.DataFrame,
    expected_building: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame, bool, str, str]:
    """
    Filtert Excel-Lastdaten ausschliesslich anhand des Strangschemas.

    Die gemeinsame Excel darf gleichzeitig MIT1- und MIT2-Räume enthalten.
    Sie wird deshalb selbst NICHT als falsches Gebäude abgelehnt.
    """
    allowed_buildings = _allowed_buildings_for_schema(
        expected_building
    )

    expected = (
        expected_building.strip().upper()
        if expected_building
        else None
    )

    detected = determine_document_building(
        dataframe
    )

    if dataframe.empty:
        return (
            dataframe.copy(),
            dataframe.copy(),
            False,
            detected,
            "Keine gültigen Lastdaten erkannt.",
        )

    valid_mask = dataframe["gebaeude"].isin(
        allowed_buildings
    )

    used = dataframe.loc[
        valid_mask
    ].copy()

    other = dataframe.loc[
        dataframe["gebaeude"].isin(
            {"MIT1", "MIT2"}
        )
        & ~valid_mask
    ].copy()

    accepted = not used.empty

    if accepted and other.empty:
        reason = "OK"
    elif accepted:
        reason = (
            f"Für {expected or 'MIT1/MIT2'} relevante Excel-Räume werden "
            "ausgewertet. Räume des anderen Gebäudeteils werden nicht "
            "in den Abgleich einbezogen."
        )
    else:
        reason = (
            f"Keine Excel-Räume passend zum Strangschema "
            f"{expected or 'MIT1/MIT2'} gefunden."
        )

    if not other.empty:
        other["zielgebaeude"] = expected
        other["nicht_geprueft_grund"] = (
            "Anderer Gebäudeteil als im Strangschema – "
            "nicht in den Abgleich einbezogen"
        )

    return (
        used,
        other,
        accepted,
        detected,
        reason,
    )


def extract_loads_from_excel_checked(
    excel_path: str | Path,
    mode: str = "beides",
    expected_building: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Liest eine Heiz-/Kühllast-Excel und liefert dieselben DataFrame-Strukturen
    wie die bestehende PDF-Extraktion.

    mode:
        "heizung"  -> nur Heizlast
        "kuehlung" -> nur Kühllast
        "beides"   -> Heiz- und Kühllast

    Rückgabe:
        heating_dataframe
        cooling_dataframe
        file_check_dataframe

    Wichtig:
    Excel-0-Werte sind echte 0-Werte und keine Marker.\n    Die Excel darf MIT1- und MIT2-Räume gleichzeitig enthalten.\n    Gefiltert wird ausschliesslich nach dem jeweiligen Strangschema.
    """
    normalized_mode = str(mode).strip().casefold()

    if normalized_mode not in {
        "heizung",
        "kuehlung",
        "beides",
    }:
        raise ValueError(
            "mode muss 'heizung', 'kuehlung' oder 'beides' sein."
        )

    excel_path = Path(excel_path)

    records = extract_loads_from_excel(
        excel_path,
        mode=normalized_mode,
    )

    heating_rows: list[dict] = []
    cooling_rows: list[dict] = []

    for record in records:
        room_id = normalize_room_id(
            record.raum_key
        )

        building = get_building_from_room(
            room_id
        )
        level = get_level_from_room(
            room_id
        )

        common = {
            "raumnummer": room_id,
            "raumname": None,
            "ist_marker": False,
            "marker_typ": None,
            "gebaeude": building,
            "ebene": level,
            "datei": excel_path.name,
            # Excel hat keine PDF-Seite. Die Excel-Zeile ist für die
            # Nachvollziehbarkeit nützlicher und passt in die bestehende
            # Integer-Spalte "seite".
            "seite": int(record.excel_zeile),
        }

        if record.heizlast_w is not None:
            heating_rows.append(
                {
                    **common,
                    # Originalwert aus Excel bleibt mit Vorzeichen sichtbar.
                    "leistung_w": int(
                        (
                            getattr(
                                record,
                                "heizlast_original_w",
                                None,
                            )
                            if getattr(
                                record,
                                "heizlast_original_w",
                                None,
                            )
                            is not None
                            else record.heizlast_w
                        )
                    ),
                    # Für den fachlichen Vergleich wird der Betrag verwendet.
                    "vergleichswert_w": abs(
                        int(
                            record.heizlast_w
                        )
                    ),
                    "lastart": "Heizlast",
                }
            )

        if record.kuehllast_w is not None:
            cooling_rows.append(
                {
                    **common,
                    # Originalwert aus Excel bleibt mit Vorzeichen sichtbar.
                    "leistung_w": int(
                        (
                            getattr(
                                record,
                                "kuehllast_original_w",
                                None,
                            )
                            if getattr(
                                record,
                                "kuehllast_original_w",
                                None,
                            )
                            is not None
                            else record.kuehllast_w
                        )
                    ),
                    # Für den fachlichen Vergleich wird der Betrag verwendet.
                    "vergleichswert_w": abs(
                        int(
                            record.kuehllast_w
                        )
                    ),
                    "lastart": "Kühllast",
                }
            )

    heating_raw = (
        pd.DataFrame(heating_rows)
        if heating_rows
        else _empty_load_dataframe()
    )

    cooling_raw = (
        pd.DataFrame(cooling_rows)
        if cooling_rows
        else _empty_load_dataframe()
    )

    checks: list[dict] = []
    not_checked_frames: list[pd.DataFrame] = []

    def process_one(
        raw: pd.DataFrame,
        load_type: str,
    ) -> pd.DataFrame:
        if raw.empty:
            return _empty_load_dataframe()

        (
            used,
            other,
            accepted,
            detected,
            reason,
        ) = _filter_dataframe_for_expected_building(
            raw,
            expected_building,
        )

        if not other.empty:
            other_copy = other.copy()
            other_copy.attrs = {}
            not_checked_frames.append(
                other_copy
            )

        checks.append(
            {
                "datei": excel_path.name,
                "pfad": str(excel_path),
                "lastart": load_type,
                "erkanntes_gebaeude": detected,
                "erwartetes_gebaeude": (
                    expected_building.upper()
                    if expected_building
                    else None
                ),
                "akzeptiert": accepted,
                "grund": reason,
                "anzahl_datensaetze": len(raw),
                "anzahl_raeume": (
                    raw["raumnummer"].nunique()
                    if not raw.empty
                    else 0
                ),
                "anzahl_raeume_verwendet": (
                    used["raumnummer"].nunique()
                    if not used.empty
                    else 0
                ),
                "anzahl_raeume_anderes_gebaeude": (
                    other["raumnummer"].nunique()
                    if not other.empty
                    else 0
                ),
            }
        )

        if not accepted:
            return _empty_load_dataframe()

        if used.empty:
            return _empty_load_dataframe()

        used = (
            used
            .drop_duplicates()
            .reset_index(drop=True)
        )

        used = _safe_sort_load_dataframe(
            used
        )

        used.attrs = {}
        return used

    heating = process_one(
        heating_raw,
        "Heizlast",
    )

    cooling = process_one(
        cooling_raw,
        "Kühllast",
    )

    if not_checked_frames:
        not_checked = (
            pd.concat(
                not_checked_frames,
                ignore_index=True,
            )
            .drop_duplicates()
            .reset_index(drop=True)
        )
    else:
        not_checked = pd.DataFrame()

    heating.attrs[
        "nicht_gepruefte_raeume"
    ] = not_checked

    cooling.attrs[
        "nicht_gepruefte_raeume"
    ] = not_checked

    check_columns = [
        "datei",
        "pfad",
        "lastart",
        "erkanntes_gebaeude",
        "erwartetes_gebaeude",
        "akzeptiert",
        "grund",
        "anzahl_datensaetze",
        "anzahl_raeume",
        "anzahl_raeume_verwendet",
        "anzahl_raeume_anderes_gebaeude",
    ]

    check_dataframe = pd.DataFrame(
        checks,
        columns=check_columns,
    )

    return (
        heating,
        cooling,
        check_dataframe,
    )


def extract_loads_from_excels_checked(
    excel_paths: Iterable[str | Path],
    mode: str = "beides",
    expected_building: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Liest mehrere Heiz-/Kühllast-Excel-Dateien ein und führt sie zu
    einer gemeinsamen Lastquelle zusammen.

    Jede Excel-Datei wird einzeln gelesen und für das aktuelle
    Strangschema nach MIT1 / MIT2 / MIT12 gefiltert.

    Wichtig:
    - Die Herkunftsdatei bleibt in der Spalte "datei" erhalten.
    - Derselbe Raum darf in mehreren Excel-Dateien vorkommen.
    - Gleiche Werte in mehreren Dateien bleiben fachlich eindeutig.
    - Unterschiedliche Werte für denselben Raum werden später im
      Vergleich als "mehrfach / prüfen" erkannt.
    """
    paths = [
        Path(path)
        for path in excel_paths
    ]

    if not paths:
        raise ValueError(
            "Mindestens eine Excel-Datei muss ausgewählt werden."
        )

    heating_frames: list[pd.DataFrame] = []
    cooling_frames: list[pd.DataFrame] = []
    check_frames: list[pd.DataFrame] = []
    not_checked_frames: list[pd.DataFrame] = []

    for excel_path in paths:
        (
            heating,
            cooling,
            checks,
        ) = extract_loads_from_excel_checked(
            excel_path=excel_path,
            mode=mode,
            expected_building=expected_building,
        )

        for dataframe, target in (
            (heating, heating_frames),
            (cooling, cooling_frames),
        ):
            not_checked = dataframe.attrs.get(
                "nicht_gepruefte_raeume"
            )

            if (
                isinstance(not_checked, pd.DataFrame)
                and not not_checked.empty
            ):
                frame = not_checked.copy()
                frame.attrs = {}
                not_checked_frames.append(
                    frame
                )

            if not dataframe.empty:
                frame = dataframe.copy()
                frame.attrs = {}
                target.append(
                    frame
                )

        if not checks.empty:
            check_frames.append(
                checks.copy()
            )

    def combine_load_frames(
        frames: list[pd.DataFrame],
    ) -> pd.DataFrame:
        if not frames:
            return _empty_load_dataframe()

        # KEIN Zusammenfassen nach Raumnummer:
        # Wir wollen bewusst sehen, wenn derselbe Raum in mehreren
        # Excel-Dateien vorkommt. Nur vollständig identische Zeilen
        # derselben Quelle werden entfernt.
        combined = (
            pd.concat(
                frames,
                ignore_index=True,
            )
            .drop_duplicates()
            .reset_index(drop=True)
        )

        return _safe_sort_load_dataframe(
            combined
        )

    heating_combined = combine_load_frames(
        heating_frames
    )
    cooling_combined = combine_load_frames(
        cooling_frames
    )

    if not_checked_frames:
        not_checked_combined = (
            pd.concat(
                not_checked_frames,
                ignore_index=True,
            )
            .drop_duplicates()
            .sort_values(
                [
                    "gebaeude",
                    "ebene",
                    "raumnummer",
                    "datei",
                    "seite",
                ]
            )
            .reset_index(drop=True)
        )
    else:
        not_checked_combined = pd.DataFrame()

    heating_combined.attrs[
        "nicht_gepruefte_raeume"
    ] = not_checked_combined

    cooling_combined.attrs[
        "nicht_gepruefte_raeume"
    ] = not_checked_combined

    if check_frames:
        check_dataframe = (
            pd.concat(
                check_frames,
                ignore_index=True,
            )
            .reset_index(drop=True)
        )
    else:
        check_dataframe = pd.DataFrame()

    return (
        heating_combined,
        cooling_combined,
        check_dataframe,
    )


# ============================================================
# DOPPELTE GRUNDRISS-RÄUME
# ============================================================

def find_duplicate_rooms(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()

    duplicate_mask = dataframe.duplicated(
        subset=["raumnummer", "lastart"],
        keep=False,
    )

    return (
        dataframe.loc[duplicate_mask]
        .sort_values(
            [
                "raumnummer",
                "datei",
                "seite",
            ]
        )
        .reset_index(drop=True)
    )


# ============================================================
# STRANGSCHEMA: SPANS
# ============================================================

def extract_schema_spans(
    page: fitz.Page,
) -> list[dict]:
    data = page.get_text("dict")
    spans: list[dict] = []

    for block in data.get("blocks", []):
        if "lines" not in block:
            continue

        for line in block["lines"]:
            for span in line.get("spans", []):
                text = normalize_line(
                    span.get("text", "")
                )

                if not text:
                    continue

                bbox = span.get("bbox")

                if not bbox:
                    continue

                x0, y0, x1, y1 = bbox

                spans.append(
                    {
                        "text": text,
                        "x0": float(x0),
                        "y0": float(y0),
                        "x1": float(x1),
                        "y1": float(y1),
                        "cx": (
                            float(x0)
                            + float(x1)
                        ) / 2,
                        "cy": (
                            float(y0)
                            + float(y1)
                        ) / 2,
                    }
                )

    return spans


# ============================================================
# STRANGSCHEMA: WATTWERTE
# ============================================================

def parse_schema_watt_span(
    text: str,
) -> int | None:
    cleaned = normalize_line(text)
    match = LOAD_PATTERN.fullmatch(cleaned)

    if not match:
        return None

    return normalize_watt_value(
        match.group("value")
    )


# ============================================================
# STRANGSCHEMA: QH / QK ZUORDNUNG
# ============================================================

def classify_schema_watt_value(
    watt_span: dict,
    spans: list[dict],
    room_cx: float,
) -> str | None:
    watt_y = watt_span["cy"]
    watt_x = watt_span["cx"]

    labels: list[tuple[float, str]] = []

    for span in spans:
        text = span["text"].strip().upper()

        if text not in {"H", "K"}:
            continue

        vertical_distance = abs(
            span["cy"] - watt_y
        )

        if vertical_distance > 2.5:
            continue

        if span["cx"] >= watt_x:
            continue

        if abs(
            span["cx"] - room_cx
        ) > 30:
            continue

        horizontal_distance = abs(
            watt_x - span["cx"]
        )

        if horizontal_distance > 30:
            continue

        labels.append(
            (
                horizontal_distance,
                text,
            )
        )

    if not labels:
        return None

    labels.sort(
        key=lambda item: item[0]
    )

    nearest_label = labels[0][1]

    if nearest_label == "H":
        return "Q_H"

    if nearest_label == "K":
        return "Q_K"

    return None


def find_schema_q_values(
    room_span: dict,
    spans: list[dict],
) -> tuple[int | None, int | None]:
    room_cx = room_span["cx"]
    room_cy = room_span["cy"]

    candidates: list[
        tuple[
            float,
            int,
            dict,
            str,
        ]
    ] = []

    for span in spans:
        value = parse_schema_watt_span(
            span["text"]
        )

        if value is None:
            continue

        dx = span["cx"] - room_cx
        dy = span["cy"] - room_cy

        if dy < 5:
            continue

        if dy > 45:
            continue

        if abs(dx) > 35:
            continue

        q_type = classify_schema_watt_value(
            span,
            spans,
            room_cx,
        )

        if q_type is None:
            continue

        distance = abs(dx) + abs(dy)

        candidates.append(
            (
                distance,
                value,
                span,
                q_type,
            )
        )

    q_h_candidates = [
        item
        for item in candidates
        if item[3] == "Q_H"
    ]

    q_k_candidates = [
        item
        for item in candidates
        if item[3] == "Q_K"
    ]

    q_h: int | None = None
    q_k: int | None = None

    if q_h_candidates:
        q_h_candidates.sort(
            key=lambda item: item[0]
        )
        q_h = q_h_candidates[0][1]

    if q_k_candidates:
        q_k_candidates.sort(
            key=lambda item: item[0]
        )
        q_k = q_k_candidates[0][1]

    return q_h, q_k


# ============================================================
# STRANGSCHEMA: RAUMNAME
# ============================================================

def is_schema_technical_text(
    text: str,
) -> bool:
    cleaned = normalize_line(text)
    upper = cleaned.upper()

    if not cleaned:
        return True

    if normalize_schema_room_id(cleaned):
        return True

    if parse_schema_watt_span(cleaned) is not None:
        return True

    if upper in {
        "Q",
        "H",
        "K",
        ":",
        "T",
        "ZU",
        "Z U",
    }:
        return True

    if re.fullmatch(
        r"[A-Z]\d+(?:\.\d+)+",
        upper,
    ):
        return True

    if re.fullmatch(
        r"[\d.,+\-/'’` ]+",
        cleaned,
    ):
        return True

    return False


def find_schema_room_name(
    room_span: dict,
    spans: list[dict],
) -> str | None:
    room_cx = room_span["cx"]
    room_cy = room_span["cy"]

    candidates: list[
        tuple[
            float,
            str,
        ]
    ] = []

    for span in spans:
        text = span["text"]

        if span is room_span:
            continue

        if is_schema_technical_text(text):
            continue

        dx = span["cx"] - room_cx
        dy = span["cy"] - room_cy

        if dx < -20:
            continue

        if dx > 180:
            continue

        if abs(dy) > 12:
            continue

        distance = abs(dx) + abs(dy)

        candidates.append(
            (
                distance,
                text,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0]
    )

    return candidates[0][1]


# ============================================================
# STRANGSCHEMA: ROHEXTRAKTION
# ============================================================

def extract_schema_from_pdf(
    pdf_path: str | Path,
) -> pd.DataFrame:
    pdf_path = Path(pdf_path)
    records: list[SchemaRecord] = []

    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(
            document,
            start=1,
        ):
            spans = extract_schema_spans(page)

            for span in spans:
                room_id = normalize_schema_room_id(
                    span["text"]
                )

                if not room_id:
                    continue

                q_h, q_k = find_schema_q_values(
                    span,
                    spans,
                )

                room_name = find_schema_room_name(
                    span,
                    spans,
                )

                records.append(
                    SchemaRecord(
                        raumnummer=room_id,
                        raumname=room_name,
                        q_h_w=q_h,
                        q_k_w=q_k,
                        gebaeude=get_building_from_room(
                            room_id
                        ),
                        ebene=get_level_from_room(
                            room_id
                        ),
                        datei=pdf_path.name,
                        seite=page_index,
                        x=span["cx"],
                        y=span["cy"],
                    )
                )

    columns = [
        "raumnummer",
        "raumname",
        "q_h_w",
        "q_k_w",
        "gebaeude",
        "ebene",
        "datei",
        "seite",
        "x",
        "y",
    ]

    if not records:
        return pd.DataFrame(
            columns=columns
        )

    dataframe = pd.DataFrame(
        [
            {
                "raumnummer": record.raumnummer,
                "raumname": record.raumname,
                "q_h_w": record.q_h_w,
                "q_k_w": record.q_k_w,
                "gebaeude": record.gebaeude,
                "ebene": record.ebene,
                "datei": record.datei,
                "seite": record.seite,
                "x": record.x,
                "y": record.y,
            }
            for record in records
        ],
        columns=columns,
    )

    return (
        dataframe
        .drop_duplicates()
        .sort_values(
            [
                "gebaeude",
                "ebene",
                "raumnummer",
                "seite",
                "y",
                "x",
            ]
        )
        .reset_index(drop=True)
    )


# ============================================================
# STRANGSCHEMA: DOPPELTE RÄUME
# ============================================================

def find_duplicate_schema_rooms(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()

    duplicate_mask = dataframe.duplicated(
        subset=["raumnummer"],
        keep=False,
    )

    return (
        dataframe.loc[duplicate_mask]
        .sort_values(
            [
                "raumnummer",
                "seite",
                "y",
                "x",
            ]
        )
        .reset_index(drop=True)
    )


# ============================================================
# STRANGSCHEMA: HILFSFUNKTIONEN FÜR KONSOLIDIERUNG
# ============================================================

def _value_or_none(
    value,
) -> int | None:
    if pd.isna(value):
        return None

    return int(value)


def _format_schema_pair(
    q_h: int | None,
    q_k: int | None,
) -> str:
    h_text = (
        "-"
        if q_h is None
        else str(q_h)
    )

    k_text = (
        "-"
        if q_k is None
        else str(q_k)
    )

    return (
        f"Q_H={h_text} W / "
        f"Q_K={k_text} W"
    )


def _choose_room_name(
    rows: pd.DataFrame,
) -> str | None:
    names = (
        rows["raumname"]
        .dropna()
        .astype(str)
    )

    names = [
        normalize_line(name)
        for name in names
        if normalize_line(name)
    ]

    if not names:
        return None

    counts = pd.Series(
        names
    ).value_counts()

    return str(counts.index[0])


# ============================================================
# STRANGSCHEMA: KONSOLIDIERUNG
# ============================================================

def consolidate_schema(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "raumnummer",
        "raumname",
        "q_h_w",
        "q_k_w",
        "schema_status",
        "schema_eindeutig",
        "schema_werte",
        "anzahl_schema_eintraege",
        "anzahl_unterschiedliche_werte",
        "gebaeude",
        "ebene",
        "datei",
        "seiten",
    ]

    if dataframe.empty:
        return pd.DataFrame(
            columns=columns
        )

    consolidated_rows = []

    for room_id, rows in dataframe.groupby(
        "raumnummer",
        sort=True,
    ):
        rows = rows.copy()

        room_name = _choose_room_name(rows)

        building = (
            rows["gebaeude"].dropna().iloc[0]
            if not rows["gebaeude"].dropna().empty
            else "Unbekannt"
        )

        level = (
            rows["ebene"].dropna().iloc[0]
            if not rows["ebene"].dropna().empty
            else "?"
        )

        filename = (
            rows["datei"].dropna().iloc[0]
            if not rows["datei"].dropna().empty
            else ""
        )

        pages = sorted(
            {
                int(page)
                for page in rows["seite"].dropna()
            }
        )

        pages_text = ", ".join(
            str(page)
            for page in pages
        )

        all_pairs: list[
            tuple[
                int | None,
                int | None,
            ]
        ] = []

        for _, row in rows.iterrows():
            q_h = _value_or_none(
                row["q_h_w"]
            )
            q_k = _value_or_none(
                row["q_k_w"]
            )

            all_pairs.append(
                (
                    q_h,
                    q_k,
                )
            )

        non_empty_pairs = [
            pair
            for pair in all_pairs
            if not (
                pair[0] is None
                and pair[1] is None
            )
        ]

        unique_non_empty_pairs = []

        for pair in non_empty_pairs:
            if pair not in unique_non_empty_pairs:
                unique_non_empty_pairs.append(
                    pair
                )

        number_entries = len(rows)
        number_unique_values = len(
            unique_non_empty_pairs
        )

        if number_unique_values == 0:
            q_h_final = None
            q_k_final = None
            schema_status = "Keine Leistung erkannt"
            schema_unique = True
            values_text = ""

        elif number_unique_values == 1:
            q_h_final, q_k_final = (
                unique_non_empty_pairs[0]
            )

            if number_entries == 1:
                schema_status = "Eindeutig"

            else:
                has_empty_rows = (
                    len(non_empty_pairs)
                    < number_entries
                )

                if has_empty_rows:
                    schema_status = (
                        "Eindeutig "
                        "(zusätzliche leere "
                        "Schemaeinträge)"
                    )
                else:
                    schema_status = (
                        "Eindeutig "
                        "(mehrfach identisch)"
                    )

            schema_unique = True
            values_text = _format_schema_pair(
                q_h_final,
                q_k_final,
            )

        else:
            q_h_final = None
            q_k_final = None
            schema_status = "Mehrfach / prüfen"
            schema_unique = False

            values_text = " | ".join(
                _format_schema_pair(
                    q_h,
                    q_k,
                )
                for q_h, q_k
                in unique_non_empty_pairs
            )

        consolidated_rows.append(
            {
                "raumnummer": room_id,
                "raumname": room_name,
                "q_h_w": q_h_final,
                "q_k_w": q_k_final,
                "schema_status": schema_status,
                "schema_eindeutig": schema_unique,
                "schema_werte": values_text,
                "anzahl_schema_eintraege": number_entries,
                "anzahl_unterschiedliche_werte": number_unique_values,
                "gebaeude": building,
                "ebene": level,
                "datei": filename,
                "seiten": pages_text,
            }
        )

    result = pd.DataFrame(
        consolidated_rows,
        columns=columns,
    )

    return (
        result
        .sort_values(
            [
                "gebaeude",
                "ebene",
                "raumnummer",
            ]
        )
        .reset_index(drop=True)
    )


def extract_and_consolidate_schema(
    pdf_path: str | Path,
) -> pd.DataFrame:
    raw_schema = extract_schema_from_pdf(
        pdf_path
    )

    return consolidate_schema(
        raw_schema
    )


def find_schema_conflicts(
    consolidated_schema: pd.DataFrame,
) -> pd.DataFrame:
    if consolidated_schema.empty:
        return consolidated_schema.copy()

    if (
        "schema_eindeutig"
        not in consolidated_schema.columns
    ):
        raise ValueError(
            "DataFrame muss zuerst mit "
            "consolidate_schema() "
            "konsolidiert werden."
        )

    return (
        consolidated_schema.loc[
            consolidated_schema[
                "schema_eindeutig"
            ]
            == False
        ]
        .sort_values(
            [
                "gebaeude",
                "ebene",
                "raumnummer",
            ]
        )
        .reset_index(drop=True)
    )


# ============================================================
# FINALER LASTVERGLEICH: HILFSFUNKTIONEN
# ============================================================

def _consolidate_ground_load(
    dataframe: pd.DataFrame,
    room_id: str,
) -> dict:
    """
    Konsolidiert Heizlast- oder Kühllast-Einträge
    für genau einen Raum.
    """
    empty_result = {
        "vorhanden": False,
        "eindeutig": True,
        "vergleichswert_w": None,
        "originalwerte": "",
        "ist_marker": False,
        "marker_typ": None,
        "raumname": None,
        "dateien": "",
        "anzahl_dateien": 0,
        "mehrere_dateien": False,
    }

    if dataframe.empty:
        return empty_result.copy()

    rows = dataframe[
        dataframe["raumnummer"] == room_id
    ].copy()

    if rows.empty:
        return empty_result.copy()

    comparison_values = []

    for value in rows["vergleichswert_w"]:
        normalized = (
            None
            if pd.isna(value)
            else int(value)
        )

        if normalized not in comparison_values:
            comparison_values.append(normalized)

    original_values = []

    for value in rows["leistung_w"]:
        normalized = (
            None
            if pd.isna(value)
            else int(value)
        )

        if normalized not in original_values:
            original_values.append(normalized)

    non_empty_comparison_values = [
        value
        for value in comparison_values
        if value is not None
    ]

    eindeutig = (
        len(non_empty_comparison_values) <= 1
    )

    vergleichswert = (
        non_empty_comparison_values[0]
        if len(non_empty_comparison_values) == 1
        else None
    )

    marker_rows = rows[
        rows["ist_marker"] == True
    ]

    ist_marker = not marker_rows.empty

    marker_types = (
        marker_rows["marker_typ"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    marker_typ = (
        " | ".join(marker_types)
        if marker_types
        else None
    )

    names = (
        rows["raumname"]
        .dropna()
        .astype(str)
    )

    room_name = (
        names.value_counts().index[0]
        if not names.empty
        else None
    )

    files = (
        rows["datei"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    original_text = " | ".join(
        "-" if value is None else str(value)
        for value in original_values
    )

    return {
        "vorhanden": True,
        "eindeutig": eindeutig,
        "vergleichswert_w": vergleichswert,
        "originalwerte": original_text,
        "ist_marker": ist_marker,
        "marker_typ": marker_typ,
        "raumname": room_name,
        "dateien": " | ".join(files),
        "anzahl_dateien": len(files),
        "mehrere_dateien": len(files) > 1,
    }


def _normalize_optional_int(
    value,
) -> int | None:
    if value is None:
        return None

    if pd.isna(value):
        return None

    return int(value)


def _compare_single_load(
    grundriss_info: dict,
    schema_value: int | float | None,
    schema_eindeutig: bool,
) -> tuple[str, int | None]:
    """
    Fachliche Vergleichslogik:

    - 0 W im Grundriss + kein Schemawert = Keine Leistung
    - kein Grundriss + 0 W im Schema = Keine Leistung
    - beide 0 W = OK
    - echte Last nur auf einer Seite = Nur im ...
    - beide echte Werte vorhanden, aber verschieden = Abweichung
    - Mehrfachwerte werden nicht automatisch verglichen
    """

    if not schema_eindeutig:
        return "Schema mehrfach / prüfen", None

    if not grundriss_info["eindeutig"]:
        return "Grundriss mehrfach / prüfen", None

    grundriss_present = grundriss_info["vorhanden"]
    grundriss_value = grundriss_info["vergleichswert_w"]
    schema_value_normalized = _normalize_optional_int(schema_value)

    # --------------------------------------------------------
    # Grundriss ist NICHT vorhanden
    # --------------------------------------------------------

    if not grundriss_present:
        if schema_value_normalized is None:
            return "Nicht vorhanden", None

        if schema_value_normalized == 0:
            return "Keine Leistung", 0

        return "Nur im Schema", None

    # --------------------------------------------------------
    # Grundriss ist vorhanden, aber Wert konnte nicht gelesen werden
    # --------------------------------------------------------

    if grundriss_value is None:
        return "Grundrisswert fehlt", None

    grundriss_value = int(grundriss_value)

    # --------------------------------------------------------
    # Schemawert fehlt
    # --------------------------------------------------------

    if schema_value_normalized is None:
        if grundriss_value == 0:
            return "Keine Leistung", 0

        return "Nur im Grundriss", None

    # --------------------------------------------------------
    # Beide Seiten haben Werte
    # --------------------------------------------------------

    difference = (
        grundriss_value
        - schema_value_normalized
    )

    if difference == 0:
        return "OK", 0

    return "Abweichung", difference


def _overall_comparison_status(
    heating_status: str,
    cooling_status: str,
) -> str:
    statuses = {
        heating_status,
        cooling_status,
    }

    if any(
        "mehrfach" in status.casefold()
        for status in statuses
    ):
        return "Mehrfach / prüfen"

    if "Grundrisswert fehlt" in statuses:
        return "Prüfen"

    if "Abweichung" in statuses:
        return "Abweichung"

    if (
        "Nur im Schema" in statuses
        or "Nur im Grundriss" in statuses
    ):
        return "Unvollständig"

    meaningful = {
        status
        for status in statuses
        if status not in {
            "Nicht vorhanden",
            "Nicht geprüft",
        }
    }

    # Ein Raum kann z. B. Heizung = OK und Kühlung = Keine Leistung haben.
    if meaningful and meaningful <= {
        "OK",
        "Keine Leistung",
    }:
        if "OK" in meaningful:
            return "OK"

        return "Keine Leistung"

    if not meaningful:
        return "Keine Leistung"

    return "Prüfen"


# ============================================================
# FINALER LASTVERGLEICH
# ============================================================

def get_selected_comparison_levels(
    heating: pd.DataFrame,
    cooling: pd.DataFrame,
) -> list[str]:
    """
    Nur noch Informationsfunktion für den Export.

    Die Ebenen beschränken den Vergleich NICHT mehr.
    """
    levels: set[str] = set()

    for dataframe in (
        heating,
        cooling,
    ):
        if dataframe.empty:
            continue

        if "ebene" not in dataframe.columns:
            continue

        for value in (
            dataframe["ebene"]
            .dropna()
            .astype(str)
        ):
            level = value.strip().upper()

            if level and level != "?":
                levels.add(level)

    return sorted(levels)


def get_comparison_scope(
    heating: pd.DataFrame,
    cooling: pd.DataFrame,
    consolidated_schema: pd.DataFrame,
) -> dict:
    """
    Der Vergleich wird NICHT mehr anhand ausgewählter Ebenen begrenzt.

    Für jedes Strangschema werden alle Räume dieses Schemas mit den
    vorhandenen Lastdaten abgeglichen. Der einzige fachliche Ausschluss
    erfolgt vorher anhand des Gebäudeumfangs MIT1 / MIT2 / MIT12.
    """
    source_levels = get_selected_comparison_levels(
        heating,
        cooling,
    )

    schema_levels: list[str] = []

    if (
        not consolidated_schema.empty
        and "ebene" in consolidated_schema.columns
    ):
        schema_levels = sorted(
            {
                str(value).strip().upper()
                for value
                in consolidated_schema[
                    "ebene"
                ].dropna()
                if (
                    str(value).strip()
                    and str(value).strip() != "?"
                )
            }
        )

    note = (
        "Verglichen werden alle Räume des jeweiligen Strangschemas. "
        "Die Ebene ist kein Ausschlusskriterium. Aus Lastquellen werden "
        "nur Räume ausgeschlossen, die zu einem anderen Gebäudeteil als "
        "das Strangschema gehören."
    )

    return {
        "beruecksichtigte_ebenen": schema_levels,
        "lastdaten_ebenen": source_levels,
        "schema_ebenen_gesamt": schema_levels,
        "ausgeschlossene_schema_ebenen": [],
        "hinweis": note,
    }


def compare_loads_with_schema(
    heating: pd.DataFrame,
    cooling: pd.DataFrame,
    consolidated_schema: pd.DataFrame,
    compare_heating: bool = True,
    compare_cooling: bool = True,
) -> pd.DataFrame:
    """
    Führt Heizlast-Grundrisse, Kühllast-Grundrisse
    und konsolidiertes Strangschema zusammen.

    VERGLEICHSUMFANG:
    Es werden alle Räume des jeweiligen Strangschemas berücksichtigt.
    Die Ebene ist kein Ausschlusskriterium.

    Lastdaten des anderen Gebäudeteils werden bereits beim Einlesen
    ausgeschlossen:
        MIT1-Schema  -> MIT1
        MIT2-Schema  -> MIT2
        MIT12-Schema -> MIT1 + MIT2

    Fachliche Regeln:

    Heizlast -1 W -> Vergleichswert 0 W + geprüft
    Kühllast +1 W -> Vergleichswert 0 W + geprüft

    Ein 0-W-Grundrisswert braucht keinen Schemaeintrag.
    Ein 0-W-Schemawert braucht keinen Grundrisseintrag.
    """

    if not compare_heating and not compare_cooling:
        raise ValueError(
            "Mindestens Heizlast oder Kühllast muss für den Vergleich aktiviert sein."
        )

    # --------------------------------------------------------
    # STRANGSCHEMA SELBST AUF SEINEN ERKANNTEN GEBÄUDEUMFANG FILTERN
    # --------------------------------------------------------
    #
    # Beispiel:
    # Ein MIT1-Strangschema kann einzelne alte MIT2-Räume enthalten.
    # Diese dürfen den fachlichen Vergleich nicht beeinflussen.
    #
    # Ein echtes MIT12-Strangschema behält dagegen MIT1 + MIT2.

    schema_building = determine_document_building(
        consolidated_schema
    )

    if schema_building not in {
        "MIT1",
        "MIT2",
        "MIT12",
    }:
        raise ValueError(
            "Gebäudeumfang des Strangschemas konnte nicht eindeutig erkannt werden."
        )

    consolidated_schema = filter_schema_for_building(
        consolidated_schema,
        schema_building,
    )

    required_schema_columns = {
        "raumnummer",
        "q_h_w",
        "q_k_w",
        "schema_status",
        "schema_eindeutig",
        "schema_werte",
        "ebene",
    }

    missing_columns = (
        required_schema_columns
        - set(
            consolidated_schema.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "Das Strangschema muss zuerst mit "
            "consolidate_schema() konsolidiert werden. "
            f"Fehlende Spalten: {sorted(missing_columns)}"
        )

    scope = get_comparison_scope(
        heating,
        cooling,
        consolidated_schema,
    )

    not_checked_frames: list[pd.DataFrame] = []

    for source_dataframe in (
        heating,
        cooling,
    ):
        not_checked = source_dataframe.attrs.get(
            "nicht_gepruefte_raeume"
        )

        if (
            isinstance(not_checked, pd.DataFrame)
            and not not_checked.empty
        ):
            not_checked_frames.append(
                not_checked.copy()
            )

    if not_checked_frames:
        not_checked_rooms = (
            pd.concat(
                not_checked_frames,
                ignore_index=True,
            )
            .drop_duplicates()
            .reset_index(drop=True)
        )
    else:
        not_checked_rooms = pd.DataFrame()

    selected_levels = scope[
        "beruecksichtigte_ebenen"
    ]

    # --------------------------------------------------------
    # KEIN EBENENFILTER MEHR
    # --------------------------------------------------------
    # Das vollständige Strangschema wird verglichen.
    # Räume ohne passenden Lastdatensatz erscheinen entsprechend
    # als "Nur im Schema". Ausschlüsse aufgrund eines anderen
    # Gebäudeteils erfolgen bereits beim Einlesen der Lastquelle.

    schema_for_comparison = (
        consolidated_schema
        .copy()
        .reset_index(drop=True)
    )

    room_ids = set()

    if not heating.empty:
        room_ids.update(
            heating[
                "raumnummer"
            ]
            .dropna()
            .astype(str)
            .tolist()
        )

    if not cooling.empty:
        room_ids.update(
            cooling[
                "raumnummer"
            ]
            .dropna()
            .astype(str)
            .tolist()
        )

    if not schema_for_comparison.empty:
        room_ids.update(
            schema_for_comparison[
                "raumnummer"
            ]
            .dropna()
            .astype(str)
            .tolist()
        )

    result_rows = []

    for room_id in sorted(
        room_ids
    ):
        heating_info = (
            _consolidate_ground_load(
                heating,
                room_id,
            )
        )

        cooling_info = (
            _consolidate_ground_load(
                cooling,
                room_id,
            )
        )

        schema_rows = (
            schema_for_comparison[
                schema_for_comparison[
                    "raumnummer"
                ]
                == room_id
            ]
        )

        if schema_rows.empty:
            schema_present = False
            schema_q_h = None
            schema_q_k = None
            schema_status = (
                "Nicht im Schema"
            )
            schema_unique = True
            schema_values = ""
            schema_room_name = None
            schema_file = ""

        else:
            schema_present = True
            schema_row = (
                schema_rows.iloc[0]
            )

            schema_q_h = (
                schema_row[
                    "q_h_w"
                ]
            )

            schema_q_k = (
                schema_row[
                    "q_k_w"
                ]
            )

            schema_status = str(
                schema_row[
                    "schema_status"
                ]
            )

            schema_unique = bool(
                schema_row[
                    "schema_eindeutig"
                ]
            )

            schema_values = (
                ""
                if pd.isna(
                    schema_row[
                        "schema_werte"
                    ]
                )
                else str(
                    schema_row[
                        "schema_werte"
                    ]
                )
            )

            raw_schema_room_name = (
                schema_row.get(
                    "raumname"
                )
            )

            schema_room_name = (
                None
                if pd.isna(
                    raw_schema_room_name
                )
                else str(
                    raw_schema_room_name
                )
            )

            raw_schema_file = (
                schema_row.get(
                    "datei",
                    "",
                )
            )

            schema_file = (
                ""
                if pd.isna(
                    raw_schema_file
                )
                else str(
                    raw_schema_file
                )
            )

        if compare_heating:
            (
                heating_status,
                heating_difference,
            ) = _compare_single_load(
                heating_info,
                schema_q_h,
                schema_unique,
            )
        else:
            heating_status = "Nicht geprüft"
            heating_difference = None

        if compare_cooling:
            # Kühllasten können je nach Quelle mit unterschiedlichem
            # Vorzeichen vorliegen:
            # - PDF-Grundriss typischerweise negativ
            # - Excel-Import als Betrag positiv
            # - Strangschema typischerweise negativ
            #
            # Fachlich wird deshalb für den Kühllastvergleich auf BEIDEN
            # Seiten nur der Betrag verwendet. Die Originalwerte bleiben
            # im Export unverändert sichtbar.

            cooling_info_for_comparison = (
                cooling_info.copy()
            )

            if (
                cooling_info_for_comparison[
                    "vergleichswert_w"
                ]
                is not None
            ):
                cooling_info_for_comparison[
                    "vergleichswert_w"
                ] = abs(
                    int(
                        cooling_info_for_comparison[
                            "vergleichswert_w"
                        ]
                    )
                )

            normalized_schema_q_k = (
                _normalize_optional_int(
                    schema_q_k
                )
            )

            schema_q_k_for_comparison = (
                None
                if normalized_schema_q_k is None
                else abs(
                    normalized_schema_q_k
                )
            )

            (
                cooling_status,
                cooling_difference,
            ) = _compare_single_load(
                cooling_info_for_comparison,
                schema_q_k_for_comparison,
                schema_unique,
            )
        else:
            cooling_status = "Nicht geprüft"
            cooling_difference = None

        overall_status = (
            _overall_comparison_status(
                heating_status,
                cooling_status,
            )
        )

        room_name = (
            heating_info[
                "raumname"
            ]
            or cooling_info[
                "raumname"
            ]
            or schema_room_name
        )

        result_rows.append(
            {
                "raumnummer":
                    room_id,

                "raumname":
                    room_name,

                # HEIZLAST
                "heizlast_original_w":
                    heating_info[
                        "originalwerte"
                    ],

                "heizlast_vergleich_w":
                    heating_info[
                        "vergleichswert_w"
                    ],

                "heizlast_marker":
                    heating_info[
                        "ist_marker"
                    ],

                "heizlast_marker_typ":
                    heating_info[
                        "marker_typ"
                    ],

                "q_h_schema_w":
                    _normalize_optional_int(
                        schema_q_h
                    ),

                "differenz_heizung_w":
                    heating_difference,

                "status_heizung":
                    heating_status,

                # KÜHLLAST
                "kuehllast_original_w":
                    cooling_info[
                        "originalwerte"
                    ],

                "kuehllast_vergleich_w":
                    cooling_info[
                        "vergleichswert_w"
                    ],

                "kuehllast_marker":
                    cooling_info[
                        "ist_marker"
                    ],

                "kuehllast_marker_typ":
                    cooling_info[
                        "marker_typ"
                    ],

                "q_k_schema_w":
                    _normalize_optional_int(
                        schema_q_k
                    ),

                "differenz_kuehlung_w":
                    cooling_difference,

                "status_kuehlung":
                    cooling_status,

                # SCHEMA / GESAMT
                "schema_status":
                    schema_status,

                "schema_eindeutig":
                    schema_unique,

                "schema_werte":
                    schema_values,

                "status_gesamt":
                    overall_status,

                # QUELLEN
                "datei_heizlast":
                    heating_info[
                        "dateien"
                    ],

                "anzahl_dateien_heizlast":
                    heating_info[
                        "anzahl_dateien"
                    ],

                "mehrere_dateien_heizlast":
                    (
                        "Ja"
                        if heating_info[
                            "mehrere_dateien"
                        ]
                        else "Nein"
                    ),

                "datei_kuehllast":
                    cooling_info[
                        "dateien"
                    ],

                "anzahl_dateien_kuehllast":
                    cooling_info[
                        "anzahl_dateien"
                    ],

                "mehrere_dateien_kuehllast":
                    (
                        "Ja"
                        if cooling_info[
                            "mehrere_dateien"
                        ]
                        else "Nein"
                    ),

                "datei_schema":
                    schema_file,

                "im_schema":
                    schema_present,

                "im_heizlastgrundriss":
                    heating_info[
                        "vorhanden"
                    ],

                "im_kuehllastgrundriss":
                    cooling_info[
                        "vorhanden"
                    ],
            }
        )

    columns = [
        "raumnummer",
        "raumname",

        "heizlast_original_w",
        "heizlast_vergleich_w",
        "heizlast_marker",
        "heizlast_marker_typ",
        "q_h_schema_w",
        "differenz_heizung_w",
        "status_heizung",

        "kuehllast_original_w",
        "kuehllast_vergleich_w",
        "kuehllast_marker",
        "kuehllast_marker_typ",
        "q_k_schema_w",
        "differenz_kuehlung_w",
        "status_kuehlung",

        "schema_status",
        "schema_eindeutig",
        "schema_werte",
        "status_gesamt",

        "datei_heizlast",
        "datei_kuehllast",
        "datei_schema",

        "im_schema",
        "im_heizlastgrundriss",
        "im_kuehllastgrundriss",
    ]

    if not result_rows:
        result = pd.DataFrame(
            columns=columns
        )

        result.attrs[
            "vergleichsumfang"
        ] = scope

        result.attrs[
            "nicht_gepruefte_raeume"
        ] = not_checked_rooms

        return result

    result = pd.DataFrame(
        result_rows,
        columns=columns,
    )

    status_order = {
        "Mehrfach / prüfen": 0,
        "Prüfen": 1,
        "Abweichung": 2,
        "Unvollständig": 3,
        "OK": 4,
        "Keine Leistung": 5,
    }

    result[
        "_status_sort"
    ] = (
        result[
            "status_gesamt"
        ]
        .map(
            status_order
        )
        .fillna(
            99
        )
    )

    result = (
        result
        .sort_values(
            [
                "_status_sort",
                "raumnummer",
            ]
        )
        .drop(
            columns=[
                "_status_sort",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # Transparenter Vergleichsumfang wird direkt
    # am DataFrame gespeichert und kann später von
    # GUI und Excel-Export ausgelesen werden.
    result.attrs[
        "vergleichsumfang"
    ] = scope

    result.attrs[
        "beruecksichtigte_ebenen"
    ] = selected_levels

    result.attrs[
        "ausgeschlossene_schema_ebenen"
    ] = scope[
        "ausgeschlossene_schema_ebenen"
    ]

    result.attrs[
        "hinweis_vergleichsumfang"
    ] = scope[
        "hinweis"
    ]

    result.attrs[
        "nicht_gepruefte_raeume"
    ] = not_checked_rooms

    result.attrs[
        "heizlast_geprueft"
    ] = bool(compare_heating)

    result.attrs[
        "kuehllast_geprueft"
    ] = bool(compare_cooling)

    return result

# ============================================================
# MEHRERE STRANGSCHEMATA
# ============================================================

def prepare_comparisons_for_schemas(
    schema_paths: Iterable[str | Path],
    heating: pd.DataFrame,
    cooling: pd.DataFrame,
    compare_heating: bool = True,
    compare_cooling: bool = True,
) -> list[dict]:
    """
    Bereitet für jedes ausgewählte Strangschema einen eigenen Vergleich vor.

    Diese Funktion führt bewusst noch keinen Excel-Export aus.
    Die GUI kann dadurch für jedes Ergebnis separat eine Ausgabedatei erzeugen.

    Rückgabe je Schema:
        schema_path
        building
        schema
        comparison

    Hinweis:
    heating/cooling müssen für das jeweilige Schema bereits passend nach
    MIT1/MIT2/MIT12 gefiltert sein. Für PDF- oder Excel-Quellen geschieht
    das über check_pdf_building()/extract_loads_from_pdfs_checked() bzw.
    extract_loads_from_excel_checked().
    """
    results: list[dict] = []

    for schema_path in schema_paths:
        schema_path = Path(schema_path)

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
                f"Gebäudeumfang des Strangschemas konnte nicht erkannt werden: "
                f"{schema_path.name}"
            )

        schema = filter_schema_for_building(
            schema,
            building,
        )

        comparison = compare_loads_with_schema(
            heating=heating,
            cooling=cooling,
            consolidated_schema=schema,
            compare_heating=compare_heating,
            compare_cooling=compare_cooling,
        )

        results.append(
            {
                "schema_path": schema_path,
                "building": building,
                "schema": schema,
                "comparison": comparison,
            }
        )

    return results

