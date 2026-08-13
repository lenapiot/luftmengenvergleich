from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz
import pandas as pd


# ------------------------------------------------------------
# REGEX
# ------------------------------------------------------------

ROOM_PATTERN = re.compile(
    r"\bMIT(?P<building>[12])(?P<level>[A-Z])(?P<number>\d+[A-Za-z]?)\b",
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


# ------------------------------------------------------------
# DATENMODELLE
# ------------------------------------------------------------

@dataclass(frozen=True)
class LoadRecord:
    raumnummer: str
    raumname: str | None

    # Originalwert aus dem PDF
    leistung_w: int | None

    # Wert für den späteren Vergleich
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


# ------------------------------------------------------------
# NORMALISIERUNG
# ------------------------------------------------------------

def normalize_line(
    text: object,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(text or ""),
    ).strip()


def normalize_watt_value(
    value: object,
) -> int | None:
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


def normalize_room_id(
    room_id: str,
) -> str:
    match = ROOM_PATTERN.search(
        room_id or ""
    )

    if not match:
        return room_id.strip()

    building = match.group(
        "building"
    )

    level = match.group(
        "level"
    ).upper()

    number = match.group(
        "number"
    )

    number_match = re.fullmatch(
        r"(\d+)([A-Za-z]?)",
        number,
    )

    if not number_match:
        return (
            f"MIT{building}"
            f"{level}"
            f"{number}"
        )

    digits = number_match.group(1)
    suffix = number_match.group(2).lower()

    return (
        f"MIT{building}"
        f"{level}"
        f"{digits}"
        f"{suffix}"
    )


# ------------------------------------------------------------
# RAUMERKENNUNG
# ------------------------------------------------------------

def extract_room_ids(
    text: str,
) -> list[str]:
    return [
        normalize_room_id(
            match.group(0)
        )
        for match in ROOM_PATTERN.finditer(
            text or ""
        )
    ]


def get_building_from_room(
    room_id: str,
) -> str:
    match = ROOM_PATTERN.search(
        room_id or ""
    )

    if not match:
        return "Unbekannt"

    return (
        f"MIT{match.group('building')}"
    )


def get_level_from_room(
    room_id: str,
) -> str:
    match = ROOM_PATTERN.search(
        room_id or ""
    )

    if not match:
        return "?"

    return match.group(
        "level"
    ).upper()


# ------------------------------------------------------------
# LASTEN
# ------------------------------------------------------------

def parse_single_load_line(
    text: str,
) -> int | None:
    cleaned = normalize_line(
        text
    )

    if LOAD_PER_AREA_PATTERN.search(
        cleaned
    ):
        return None

    match = LOAD_PATTERN.fullmatch(
        cleaned
    )

    if not match:
        return None

    return normalize_watt_value(
        match.group(
            "value"
        )
    )


# ------------------------------------------------------------
# MARKERLOGIK
# ------------------------------------------------------------

def evaluate_marker(
    value: int | None,
    load_type: str,
) -> tuple[
    bool,
    str | None,
    int | None,
]:
    """
    Projektregel:

    Heizlast:
        -1 W = 0 W + geprüft

    Kühllast:
        +1 W = 0 W + geprüft
    """

    if value is None:
        return (
            False,
            None,
            None,
        )

    normalized_type = (
        load_type
        .strip()
        .casefold()
    )

    if (
        normalized_type == "heizlast"
        and value == -1
    ):
        return (
            True,
            "0 W + geprüft",
            0,
        )

    if (
        normalized_type == "kühllast"
        and value == 1
    ):
        return (
            True,
            "0 W + geprüft",
            0,
        )

    return (
        False,
        None,
        value,
    )


def is_marker_value(
    value: int | None,
    load_type: str,
) -> tuple[
    bool,
    str | None,
]:
    (
        marker,
        marker_type,
        _,
    ) = evaluate_marker(
        value,
        load_type,
    )

    return (
        marker,
        marker_type,
    )


def get_comparison_value(
    value: int | None,
    load_type: str,
) -> int | None:
    (
        _,
        _,
        comparison_value,
    ) = evaluate_marker(
        value,
        load_type,
    )

    return comparison_value


# ------------------------------------------------------------
# LEISTUNG IN RAUMNÄHE
# ------------------------------------------------------------

def find_load_near_room(
    lines: list[str],
    room_index: int,
    search_before: int = 7,
    search_after: int = 3,
) -> tuple[
    int | None,
    int | None,
]:
    start = max(
        0,
        room_index - search_before,
    )

    # zuerst rückwärts suchen
    for index in range(
        room_index - 1,
        start - 1,
        -1,
    ):
        value = parse_single_load_line(
            lines[index]
        )

        if value is not None:
            return (
                value,
                index,
            )

    # danach kurz vorwärts
    end = min(
        len(lines),
        room_index
        + search_after
        + 1,
    )

    for index in range(
        room_index + 1,
        end,
    ):
        value = parse_single_load_line(
            lines[index]
        )

        if value is not None:
            return (
                value,
                index,
            )

    return (
        None,
        None,
    )


# ------------------------------------------------------------
# RAUMNAME
# ------------------------------------------------------------

def clean_room_name_candidate(
    text: str,
) -> str | None:
    candidate = normalize_line(
        text
    )

    if not candidate:
        return None

    candidate = ROOM_PATTERN.sub(
        " ",
        candidate,
    )

    candidate = normalize_line(
        candidate
    )

    if not candidate:
        return None

    if parse_single_load_line(
        candidate
    ) is not None:
        return None

    if LOAD_PER_AREA_PATTERN.search(
        candidate
    ):
        return None

    if TEMPERATURE_PATTERN.search(
        candidate
    ):
        return None

    if AREA_PATTERN.search(
        candidate
    ):
        return None

    if re.fullmatch(
        r"[\d.,+\-/'’` ]+",
        candidate,
    ):
        return None

    return candidate


def find_room_name(
    lines: list[str],
    room_index: int,
    load_index: int | None,
) -> str | None:

    current_line_name = (
        clean_room_name_candidate(
            lines[room_index]
        )
    )

    if current_line_name:
        return current_line_name

    if load_index is not None:

        for index in range(
            load_index - 1,
            max(
                -1,
                load_index - 4,
            ),
            -1,
        ):
            if not (
                0
                <= index
                < len(lines)
            ):
                continue

            candidate = (
                clean_room_name_candidate(
                    lines[index]
                )
            )

            if candidate:
                return candidate

    candidate_indices = [
        room_index - 1,
        room_index - 2,
        room_index + 1,
        room_index + 2,
    ]

    for index in candidate_indices:

        if not (
            0
            <= index
            < len(lines)
        ):
            continue

        candidate = (
            clean_room_name_candidate(
                lines[index]
            )
        )

        if candidate:
            return candidate

    return None


# ------------------------------------------------------------
# PDF-TEXT
# ------------------------------------------------------------

def extract_page_lines(
    page: fitz.Page,
) -> list[str]:

    raw_text = page.get_text(
        "text"
    )

    return [
        normalize_line(
            line
        )
        for line in raw_text.splitlines()
        if normalize_line(
            line
        )
    ]


# ------------------------------------------------------------
# EINZELNE PDF EXTRAHIEREN
# ------------------------------------------------------------

def extract_loads_from_pdf(
    pdf_path: str | Path,
    load_type: str,
) -> pd.DataFrame:

    pdf_path = Path(
        pdf_path
    )

    normalized_type = (
        load_type
        .strip()
        .casefold()
    )

    if normalized_type not in {
        "heizlast",
        "kühllast",
    }:
        raise ValueError(
            "load_type muss "
            "'Heizlast' oder "
            "'Kühllast' sein."
        )

    display_type = (
        "Heizlast"
        if normalized_type
        == "heizlast"
        else "Kühllast"
    )

    records: list[
        LoadRecord
    ] = []

    with fitz.open(
        pdf_path
    ) as document:

        for page_index, page in enumerate(
            document
        ):
            lines = extract_page_lines(
                page
            )

            for room_index, line in enumerate(
                lines
            ):
                room_ids = extract_room_ids(
                    line
                )

                if not room_ids:
                    continue

                (
                    load_value,
                    load_index,
                ) = find_load_near_room(
                    lines,
                    room_index,
                )

                room_name = find_room_name(
                    lines,
                    room_index,
                    load_index,
                )

                (
                    marker,
                    marker_type,
                    comparison_value,
                ) = evaluate_marker(
                    load_value,
                    display_type,
                )

                for room_id in room_ids:

                    records.append(
                        LoadRecord(
                            raumnummer=room_id,
                            raumname=room_name,

                            leistung_w=load_value,

                            vergleichswert_w=(
                                comparison_value
                            ),

                            ist_marker=marker,
                            marker_typ=marker_type,

                            lastart=display_type,

                            gebaeude=(
                                get_building_from_room(
                                    room_id
                                )
                            ),

                            ebene=(
                                get_level_from_room(
                                    room_id
                                )
                            ),

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
        return pd.DataFrame(
            columns=columns
        )

    dataframe = pd.DataFrame(
        [
            {
                "raumnummer":
                    record.raumnummer,

                "raumname":
                    record.raumname,

                "leistung_w":
                    record.leistung_w,

                "vergleichswert_w":
                    record.vergleichswert_w,

                "ist_marker":
                    record.ist_marker,

                "marker_typ":
                    record.marker_typ,

                "lastart":
                    record.lastart,

                "gebaeude":
                    record.gebaeude,

                "ebene":
                    record.ebene,

                "datei":
                    record.datei,

                "seite":
                    record.seite,
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
        .reset_index(
            drop=True
        )
    )


# ------------------------------------------------------------
# GEBÄUDEERKENNUNG
# ------------------------------------------------------------

def determine_document_building(
    dataframe: pd.DataFrame,
) -> str:
    """
    Rückgabe:

    MIT1
    MIT2
    Gemischt
    Unbekannt
    """

    if dataframe.empty:
        return "Unbekannt"

    buildings = (
        dataframe[
            "gebaeude"
        ]
        .dropna()
        .astype(str)
    )

    buildings = buildings[
        buildings.isin(
            [
                "MIT1",
                "MIT2",
            ]
        )
    ]

    if buildings.empty:
        return "Unbekannt"

    counts = (
        buildings
        .value_counts()
    )

    if len(counts) == 1:
        return counts.index[0]

    total = int(
        counts.sum()
    )

    strongest = (
        counts.index[0]
    )

    strongest_count = int(
        counts.iloc[0]
    )

    # 90-%-Regel innerhalb EINER PDF
    if (
        total > 0
        and strongest_count
        / total
        >= 0.90
    ):
        return strongest

    return "Gemischt"


# ------------------------------------------------------------
# EINZELDATEI PRÜFEN
# ------------------------------------------------------------

def check_pdf_building(
    pdf_path: str | Path,
    load_type: str,
    expected_building: str | None = None,
) -> tuple[
    pd.DataFrame,
    FileBuildingCheck,
]:
    """
    Extrahiert eine PDF und prüft sie einzeln.

    expected_building:
        None
        MIT1
        MIT2
    """

    pdf_path = Path(
        pdf_path
    )

    dataframe = (
        extract_loads_from_pdf(
            pdf_path,
            load_type,
        )
    )

    detected_building = (
        determine_document_building(
            dataframe
        )
    )

    expected = (
        expected_building.upper()
        if expected_building
        else None
    )

    if expected not in {
        None,
        "MIT1",
        "MIT2",
    }:
        raise ValueError(
            "expected_building muss "
            "None, 'MIT1' oder 'MIT2' sein."
        )

    accepted = True
    reason = "OK"

    if detected_building == "Unbekannt":

        accepted = False
        reason = (
            "Gebäude konnte nicht "
            "bestimmt werden."
        )

    elif detected_building == "Gemischt":

        accepted = False
        reason = (
            "PDF enthält eine "
            "uneindeutige Mischung "
            "aus MIT1 und MIT2."
        )

    elif (
        expected is not None
        and detected_building
        != expected
    ):

        accepted = False
        reason = (
            f"Erkannt: {detected_building}; "
            f"erwartet: {expected}."
        )

    check = FileBuildingCheck(
        datei=pdf_path.name,
        pfad=str(pdf_path),
        lastart=load_type,

        erkanntes_gebaeude=(
            detected_building
        ),

        erwartetes_gebaeude=expected,

        akzeptiert=accepted,
        grund=reason,

        anzahl_datensaetze=len(
            dataframe
        ),

        anzahl_raeume=(
            dataframe[
                "raumnummer"
            ].nunique()
            if not dataframe.empty
            else 0
        ),
    )

    return (
        dataframe,
        check,
    )


# ------------------------------------------------------------
# MEHRERE PDFs MIT EINZELDATEIPRÜFUNG
# ------------------------------------------------------------

def extract_loads_from_pdfs_checked(
    pdf_paths: Iterable[
        str | Path
    ],
    load_type: str,
    expected_building: str | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Extrahiert mehrere PDFs.

    Jede Datei wird EINZELN geprüft.

    Falsche / uneindeutige Dateien
    werden automatisch ausgeschlossen.

    Rückgabe:

    1. kombinierter DataFrame
       nur aus akzeptierten PDFs

    2. Prüfprotokoll
       mit allen PDFs
    """

    accepted_frames: list[
        pd.DataFrame
    ] = []

    checks: list[
        FileBuildingCheck
    ] = []

    for pdf_path in pdf_paths:

        (
            dataframe,
            check,
        ) = check_pdf_building(
            pdf_path,
            load_type,
            expected_building,
        )

        checks.append(
            check
        )

        if (
            check.akzeptiert
            and not dataframe.empty
        ):
            accepted_frames.append(
                dataframe
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
            .reset_index(
                drop=True
            )
        )

    else:

        combined = pd.DataFrame(
            columns=data_columns
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
    ]

    if checks:

        check_dataframe = pd.DataFrame(
            [
                {
                    "datei":
                        check.datei,

                    "pfad":
                        check.pfad,

                    "lastart":
                        check.lastart,

                    "erkanntes_gebaeude":
                        check.erkanntes_gebaeude,

                    "erwartetes_gebaeude":
                        check.erwartetes_gebaeude,

                    "akzeptiert":
                        check.akzeptiert,

                    "grund":
                        check.grund,

                    "anzahl_datensaetze":
                        check.anzahl_datensaetze,

                    "anzahl_raeume":
                        check.anzahl_raeume,
                }

                for check in checks
            ],

            columns=check_columns,
        )

    else:

        check_dataframe = pd.DataFrame(
            columns=check_columns
        )

    return (
        combined,
        check_dataframe,
    )


# ------------------------------------------------------------
# BISHERIGE MEHRFACHFUNKTION
# ------------------------------------------------------------

def extract_loads_from_pdfs(
    pdf_paths: Iterable[
        str | Path
    ],
    load_type: str,
) -> pd.DataFrame:
    """
    Alte Funktion bleibt bestehen,
    damit bisheriger Code weiterläuft.

    Keine Gebäudeprüfung.
    """

    frames: list[
        pd.DataFrame
    ] = []

    for pdf_path in pdf_paths:

        frame = (
            extract_loads_from_pdf(
                pdf_path,
                load_type,
            )
        )

        if not frame.empty:
            frames.append(
                frame
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

    if not frames:
        return pd.DataFrame(
            columns=columns
        )

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
        .reset_index(
            drop=True
        )
    )


# ------------------------------------------------------------
# DOPPELTE RÄUME
# ------------------------------------------------------------

def find_duplicate_rooms(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    if dataframe.empty:
        return dataframe.copy()

    duplicate_mask = (
        dataframe
        .duplicated(
            subset=[
                "raumnummer",
                "lastart",
            ],
            keep=False,
        )
    )

    return (
        dataframe.loc[
            duplicate_mask
        ]
        .sort_values(
            [
                "raumnummer",
                "datei",
                "seite",
            ]
        )
        .reset_index(
            drop=True
        )
    )
