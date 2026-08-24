from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz
import pandas as pd


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
    if dataframe.empty:
        return "Unbekannt"

    if "gebaeude" not in dataframe.columns:
        return "Unbekannt"

    buildings = dataframe["gebaeude"].dropna().astype(str)
    buildings = buildings[buildings.isin(["MIT1", "MIT2"])]

    if buildings.empty:
        return "Unbekannt"

    counts = buildings.value_counts()

    if len(counts) == 1:
        return counts.index[0]

    total = int(counts.sum())
    strongest = counts.index[0]
    strongest_count = int(counts.iloc[0])

    if total > 0 and strongest_count / total >= 0.90:
        return strongest

    return "Gemischt"


# ============================================================
# EINZELDATEI-GEBÄUDEPRÜFUNG
# ============================================================

def check_pdf_building(
    pdf_path: str | Path,
    load_type: str,
    expected_building: str | None = None,
) -> tuple[pd.DataFrame, FileBuildingCheck]:
    """
    Prüft einen Heiz-/Kühllast-Grundriss gegen das erwartete Gebäude.

    Gebäudeklassifikation:
    - nur MIT1-Räume -> MIT1
    - nur MIT2-Räume -> MIT2
    - beide Gebäudeteile mit mindestens 10 % Minderheitsanteil -> MIT12
    - kleiner Gebäudeteil < 10 % -> dominantes Gebäude mit Restbestand

    Beispiele:
    - 200 MIT1 + 9 MIT2  -> "MIT1 mit MIT2-Rest"
    - 120 MIT1 + 80 MIT2 -> "MIT12"

    Für ein MIT2-Strangschema gilt:
    - MIT2: akzeptieren
    - MIT12: akzeptieren und nur MIT2-Räume vergleichen
    - MIT1 mit MIT2-Rest: ablehnen; die wenigen MIT2-Räume gelten nur als
      stehengebliebener Rest und machen den Plan nicht zu einem MIT2-Plan.

    Räume des jeweils anderen Gebäudeteils werden separat dokumentiert und
    niemals als fachlicher Vergleichsfehler gewertet.
    """
    pdf_path = Path(pdf_path)

    raw_dataframe = extract_loads_from_pdf(
        pdf_path,
        load_type,
    )

    expected = (
        expected_building.upper()
        if expected_building
        else None
    )

    if expected not in {None, "MIT1", "MIT2"}:
        raise ValueError(
            "expected_building muss None, 'MIT1' oder 'MIT2' sein."
        )

    # --------------------------------------------------------
    # GEBÄUDEANTEILE ÜBER EINDEUTIGE RAUMNUMMERN BESTIMMEN
    # --------------------------------------------------------

    room_counts = {
        "MIT1": 0,
        "MIT2": 0,
    }

    if not raw_dataframe.empty:
        for building_name in (
            "MIT1",
            "MIT2",
        ):
            room_counts[
                building_name
            ] = int(
                raw_dataframe.loc[
                    raw_dataframe[
                        "gebaeude"
                    ]
                    == building_name,
                    "raumnummer",
                ]
                .dropna()
                .nunique()
            )

    mit1_count = room_counts[
        "MIT1"
    ]
    mit2_count = room_counts[
        "MIT2"
    ]

    total_building_rooms = (
        mit1_count
        + mit2_count
    )

    present_buildings = {
        building_name
        for building_name, count
        in room_counts.items()
        if count > 0
    }

    dominant_building: str | None = None
    minority_building: str | None = None
    minority_share = 0.0
    is_true_mit12 = False
    is_dominant_with_rest = False

    if total_building_rooms == 0:
        detected_building = (
            "Unbekannt"
        )

    elif mit1_count > 0 and mit2_count == 0:
        detected_building = (
            "MIT1"
        )
        dominant_building = (
            "MIT1"
        )

    elif mit2_count > 0 and mit1_count == 0:
        detected_building = (
            "MIT2"
        )
        dominant_building = (
            "MIT2"
        )

    else:
        if mit1_count >= mit2_count:
            dominant_building = (
                "MIT1"
            )
            minority_building = (
                "MIT2"
            )
            minority_count = (
                mit2_count
            )
        else:
            dominant_building = (
                "MIT2"
            )
            minority_building = (
                "MIT1"
            )
            minority_count = (
                mit1_count
            )

        minority_share = (
            minority_count
            / total_building_rooms
        )

        if (
            minority_share
            >= MIT12_MINORITY_THRESHOLD
        ):
            detected_building = (
                "MIT12"
            )
            is_true_mit12 = True

        else:
            detected_building = (
                f"{dominant_building} mit "
                f"{minority_building}-Rest"
            )
            is_dominant_with_rest = True

    # --------------------------------------------------------
    # AKZEPTANZ GEGEN DAS STRANGSCHEMA
    # --------------------------------------------------------

    accepted = True
    reason = "OK"

    used_dataframe = (
        raw_dataframe.copy()
    )

    other_building_dataframe = (
        raw_dataframe.iloc[
            0:0
        ].copy()
    )

    if detected_building == "Unbekannt":
        accepted = False

        reason = (
            "Gebäude konnte nicht bestimmt werden."
        )

        used_dataframe = (
            raw_dataframe.iloc[
                0:0
            ].copy()
        )

    elif expected is None:
        # Ohne Zielgebäude bleibt die vollständige Datei erhalten.
        reason = "OK"

    elif is_true_mit12:
        # Echter gemischter Plan:
        # Zielgebäude wird ausgewertet, anderer Teil nur dokumentiert.
        if expected not in present_buildings:
            accepted = False

            reason = (
                f"MIT12 erkannt, aber keine {expected}-Räume gefunden."
            )

            used_dataframe = (
                raw_dataframe.iloc[
                    0:0
                ].copy()
            )

        else:
            used_dataframe = (
                raw_dataframe.loc[
                    raw_dataframe[
                        "gebaeude"
                    ]
                    == expected
                ].copy()
            )

            other_building_dataframe = (
                raw_dataframe.loc[
                    raw_dataframe[
                        "gebaeude"
                    ].isin(
                        {
                            "MIT1",
                            "MIT2",
                        }
                    )
                    & (
                        raw_dataframe[
                            "gebaeude"
                        ]
                        != expected
                    )
                ].copy()
            )

            other_building = (
                "MIT1"
                if expected
                == "MIT2"
                else "MIT2"
            )

            reason = (
                "Echter MIT12-Grundriss: "
                f"{expected}-Räume werden ausgewertet. "
                f"{other_building}-Räume werden dokumentiert, "
                "aber nicht bewertet und nicht als Fehler gewertet. "
                f"Anteile: MIT1={mit1_count}, MIT2={mit2_count}."
            )

    elif is_dominant_with_rest:
        assert dominant_building is not None
        assert minority_building is not None

        if expected == dominant_building:
            # Passender Hauptplan; kleiner Rest wird ignoriert/dokumentiert.
            accepted = True

            used_dataframe = (
                raw_dataframe.loc[
                    raw_dataframe[
                        "gebaeude"
                    ]
                    == expected
                ].copy()
            )

            other_building_dataframe = (
                raw_dataframe.loc[
                    raw_dataframe[
                        "gebaeude"
                    ]
                    == minority_building
                ].copy()
            )

            reason = (
                f"{dominant_building}-Plan mit kleinem "
                f"{minority_building}-Rest "
                f"({minority_share:.1%}, Grenzwert "
                f"{MIT12_MINORITY_THRESHOLD:.0%}). "
                f"{dominant_building}-Räume werden ausgewertet; "
                f"{minority_building}-Räume nur dokumentiert."
            )

        else:
            # Der erwartete Gebäudeteil ist nur der kleine Rest.
            # Das darf den Plan NICHT passend machen.
            accepted = False

            used_dataframe = (
                raw_dataframe.iloc[
                    0:0
                ].copy()
            )

            reason = (
                f"Abgelehnt: überwiegend {dominant_building}. "
                f"{minority_building} ist nur ein kleiner Rest "
                f"({minority_share:.1%}, unter "
                f"{MIT12_MINORITY_THRESHOLD:.0%}). "
                f"Erwartet wird {expected}. "
                f"Raumanzahl: MIT1={mit1_count}, MIT2={mit2_count}."
            )

    else:
        # Reiner MIT1- oder MIT2-Plan.
        if dominant_building == expected:
            accepted = True

            used_dataframe = (
                raw_dataframe.loc[
                    raw_dataframe[
                        "gebaeude"
                    ]
                    == expected
                ].copy()
            )

            reason = "OK"

        else:
            accepted = False

            used_dataframe = (
                raw_dataframe.iloc[
                    0:0
                ].copy()
            )

            reason = (
                f"Erkannt: {dominant_building}; erwartet: {expected}."
            )

    # --------------------------------------------------------
    # NICHT GEPRÜFTE RÄUME DOKUMENTIEREN
    # --------------------------------------------------------

    if not other_building_dataframe.empty:
        other_building_dataframe = (
            other_building_dataframe.copy()
        )

        other_building_dataframe[
            "zielgebaeude"
        ] = expected

        other_building_dataframe[
            "nicht_geprueft_grund"
        ] = (
            "Anderer Gebäudeteil im Grundriss – "
            "nicht Teil des gewählten Strangschemas"
        )

    used_dataframe.attrs[
        "nicht_gepruefte_raeume"
    ] = (
        other_building_dataframe
    )

    check = FileBuildingCheck(
        datei=pdf_path.name,
        pfad=str(
            pdf_path
        ),
        lastart=load_type,
        erkanntes_gebaeude=detected_building,
        erwartetes_gebaeude=expected,
        akzeptiert=accepted,
        grund=reason,
        anzahl_datensaetze=len(
            raw_dataframe
        ),
        anzahl_raeume=(
            raw_dataframe[
                "raumnummer"
            ].nunique()
            if not raw_dataframe.empty
            else 0
        ),
        anzahl_raeume_verwendet=(
            used_dataframe[
                "raumnummer"
            ].nunique()
            if not used_dataframe.empty
            else 0
        ),
        anzahl_raeume_anderes_gebaeude=(
            other_building_dataframe[
                "raumnummer"
            ].nunique()
            if not other_building_dataframe.empty
            else 0
        ),
    )

    return (
        used_dataframe,
        check,
    )


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
        if status != "Nicht vorhanden"
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
    Ermittelt die Ebenen, für die tatsächlich
    Heizlast- oder Kühllast-Grundrisse ausgewählt wurden.

    Beispiel:
        Heizlast H + J
        Kühllast H + J
        -> ["H", "J"]
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

            if (
                level
                and level != "?"
            ):
                levels.add(level)

    return sorted(levels)


def get_comparison_scope(
    heating: pd.DataFrame,
    cooling: pd.DataFrame,
    consolidated_schema: pd.DataFrame,
) -> dict:
    """
    Gibt den Umfang des Lastvergleichs transparent zurück.

    Wichtig:
    Es werden nur Schema-Räume der Ebenen berücksichtigt,
    für die mindestens ein Heizlast- oder Kühllast-Grundriss
    ausgewählt wurde.
    """

    selected_levels = (
        get_selected_comparison_levels(
            heating,
            cooling,
        )
    )

    schema_levels: list[str] = []

    if (
        not consolidated_schema.empty
        and "ebene"
        in consolidated_schema.columns
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
                    and str(value).strip()
                    != "?"
                )
            }
        )

    ignored_schema_levels = sorted(
        set(schema_levels)
        - set(selected_levels)
    )

    note = (
        "Hinweis: Verglichen werden nur die Ebenen, "
        "für die Heizlast- oder Kühllast-Grundrisse "
        "ausgewählt wurden. Räume anderer Ebenen aus "
        "dem Strangschema werden in diesem Vergleich "
        "nicht berücksichtigt."
    )

    return {
        "beruecksichtigte_ebenen":
            selected_levels,

        "schema_ebenen_gesamt":
            schema_levels,

        "ausgeschlossene_schema_ebenen":
            ignored_schema_levels,

        "hinweis":
            note,
    }


def compare_loads_with_schema(
    heating: pd.DataFrame,
    cooling: pd.DataFrame,
    consolidated_schema: pd.DataFrame,
) -> pd.DataFrame:
    """
    Führt Heizlast-Grundrisse, Kühllast-Grundrisse
    und konsolidiertes Strangschema zusammen.

    SEHR WICHTIGER VERGLEICHSUMFANG:
    Es werden nur diejenigen Ebenen des Strangschemas
    berücksichtigt, für die mindestens ein Heizlast-
    oder Kühllast-Grundriss ausgewählt wurde.

    Beispiel:
        Grundrisse H + J ausgewählt
        -> Schema wird nur für H + J verglichen.

    Andere Ebenen des Strangschemas gelten in diesem
    Lauf ausdrücklich als NICHT geprüft.

    Fachliche Regeln:

    Heizlast -1 W -> Vergleichswert 0 W + geprüft
    Kühllast +1 W -> Vergleichswert 0 W + geprüft

    Ein 0-W-Grundrisswert braucht keinen Schemaeintrag.
    Ein 0-W-Schemawert braucht keinen Grundrisseintrag.
    """

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

    if not selected_levels:
        raise ValueError(
            "Es wurden keine gültigen Ebenen aus "
            "Heizlast- oder Kühllast-Grundrissen erkannt. "
            "Ohne ausgewählte Grundriss-Ebene kann kein "
            "Lastvergleich durchgeführt werden."
        )

    # --------------------------------------------------------
    # STRANGSCHEMA AUF TATSÄCHLICH GEPRÜFTE EBENEN BESCHRÄNKEN
    # --------------------------------------------------------

    schema_for_comparison = (
        consolidated_schema.loc[
            consolidated_schema[
                "ebene"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(
                selected_levels
            )
        ]
        .copy()
        .reset_index(
            drop=True
        )
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

        (
            heating_status,
            heating_difference,
        ) = _compare_single_load(
            heating_info,
            schema_q_h,
            schema_unique,
        )

        (
            cooling_status,
            cooling_difference,
        ) = _compare_single_load(
            cooling_info,
            schema_q_k,
            schema_unique,
        )

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

                "datei_kuehllast":
                    cooling_info[
                        "dateien"
                    ],

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

    return result
