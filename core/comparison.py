import re
import pandas as pd


def normalize_name(
    value: object,
) -> str | None:
    """Normalisiert einen Raumnamen für den Vergleich."""
    if value is None or pd.isna(value):
        return None

    text = re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip().casefold()

    return text or None


def unique_non_null_values(
    series: pd.Series,
) -> list[object]:
    """Gibt eindeutige, nichtleere Werte einer Spalte zurück."""
    values: list[object] = []

    for value in series:
        if value is None or pd.isna(value):
            continue

        if value not in values:
            values.append(value)

    return values


def has_multiple_blocks_in_same_file(
    group: pd.DataFrame,
) -> bool:
    """
    Prüft, ob derselbe Vergleichsschlüssel innerhalb derselben PDF
    mehrfach als eigener Luftmengenblock gefunden wurde.

    Mehrere identische Funde in unterschiedlichen PDFs sind erlaubt.
    """
    if len(group) <= 1:
        return False

    if "quelldatei" not in group.columns:
        return len(group) > 1

    counts_per_file = (
        group.groupby(
            "quelldatei",
            dropna=False,
        )
        .size()
    )

    return bool(
        (counts_per_file > 1).any()
    )


def consolidate_rooms(
    raw_df: pd.DataFrame,
    source_label: str,
    key_column: str = "raumnummer",
) -> pd.DataFrame:
    """
    Erstellt pro Vergleichsschlüssel eine Vergleichszeile.

    Standard:
        key_column = "raumnummer"

    Numerischer Modus:
        key_column = "ep_nummer"

    Dadurch können bei numerischen Plänen auch verkürzte bzw. mehrfach
    vorkommende Raumnummern wie -1.21 sauber getrennt werden, solange die
    ep-Nummern eindeutig sind.
    """
    columns = [
        "_vergleichsschluessel",
        f"raumnummer_{source_label}",
        f"raumname_{source_label}",
        f"betriebsarten_{source_label}",
        f"zul_{source_label}",
        f"abl_{source_label}",
        f"seiten_{source_label}",
        f"anzahl_funde_{source_label}",
        f"quelldateien_{source_label}",
        f"mehrfachblock_{source_label}",
        f"uneindeutig_{source_label}",
    ]

    if raw_df.empty:
        return pd.DataFrame(
            columns=columns
        )

    if key_column not in raw_df.columns:
        raise KeyError(
            f"Vergleichsschlüssel '{key_column}' "
            "ist in den Rohdaten nicht vorhanden."
        )

    working_df = raw_df.copy()

    # Datensätze ohne Schlüssel können nicht sicher verglichen werden.
    working_df = working_df.dropna(
        subset=[key_column]
    )

    if working_df.empty:
        return pd.DataFrame(
            columns=columns
        )

    rows: list[dict[str, object]] = []

    for compare_key, group in working_df.groupby(
        key_column,
        sort=True,
    ):
        room_ids = unique_non_null_values(
            group["raumnummer"]
        )

        names = unique_non_null_values(
            group["raumname"]
        )

        zul_values = unique_non_null_values(
            group["zul"]
        )

        abl_values = unique_non_null_values(
            group["abl"]
        )

        if "betriebsart" in group.columns:
            operating_modes = unique_non_null_values(
                group["betriebsart"]
            )
        else:
            operating_modes = []

        pages = sorted(
            {
                int(page)
                for page in group["seite"]
                if page is not None
                and not pd.isna(page)
            }
        )

        if "quelldatei" in group.columns:
            source_files = unique_non_null_values(
                group["quelldatei"]
            )
        else:
            source_files = []

        multiple_blocks = (
            has_multiple_blocks_in_same_file(
                group
            )
        )

        conflicting_values = (
            len(room_ids) > 1
            or len(names) > 1
            or len(zul_values) > 1
            or len(abl_values) > 1
        )

        ambiguous = (
            multiple_blocks
            or conflicting_values
        )

        rows.append(
            {
                "_vergleichsschluessel": str(compare_key),

                f"raumnummer_{source_label}": (
                    room_ids[0]
                    if len(room_ids) == 1
                    else " | ".join(
                        map(str, room_ids)
                    )
                ),

                f"raumname_{source_label}": (
                    names[0]
                    if len(names) == 1
                    else " | ".join(
                        map(str, names)
                    )
                ),

                f"betriebsarten_{source_label}": (
                    " | ".join(
                        map(str, operating_modes)
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

                f"quelldateien_{source_label}": " | ".join(
                    map(str, source_files)
                ),

                f"mehrfachblock_{source_label}": (
                    multiple_blocks
                ),

                f"uneindeutig_{source_label}": ambiguous,
            }
        )

    return pd.DataFrame(
        rows,
        columns=columns,
    )


def determine_status(
    row: pd.Series,
) -> str:
    """Bestimmt den Status einer Vergleichszeile."""
    if row["_merge"] == "left_only":
        return "Nur im Grundriss"

    if row["_merge"] == "right_only":
        return "Nur im Schema"

    if (
        bool(
            row.get(
                "uneindeutig_grundriss",
                False,
            )
        )
        or bool(
            row.get(
                "uneindeutig_schema",
                False,
            )
        )
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
    key_column: str = "raumnummer",
) -> pd.DataFrame:
    """
    Erstellt die vollständige Vergleichstabelle.

    Standardmäßig wird über die Raumnummer verglichen.

    Für «Numerisch - Geschoss.Raum» kann stattdessen
    key_column="ep_nummer" übergeben werden. Dann ist ep der interne
    eindeutige Schlüssel; die Raumnummer bleibt nur die angezeigte
    Raumbezeichnung.
    """
    floorplan_df = consolidate_rooms(
        floorplan_raw_df,
        "grundriss",
        key_column=key_column,
    )

    schema_df = consolidate_rooms(
        schema_raw_df,
        "schema",
        key_column=key_column,
    )

    comparison_df = pd.merge(
        floorplan_df,
        schema_df,
        on="_vergleichsschluessel",
        how="outer",
        indicator=True,
    )

    # Angezeigte Raumnummer:
    # Grundriss hat Vorrang, Schema dient als Fallback.
    comparison_df["raumnummer"] = (
        comparison_df[
            "raumnummer_grundriss"
        ].combine_first(
            comparison_df[
                "raumnummer_schema"
            ]
        )
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

    if both_mask.any():
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
        columns=[
            "_merge",
            "raumnummer_grundriss",
            "raumnummer_schema",
        ]
    )

    # Raumnummer wieder an den Anfang stellen, damit Excel/PDF-Export
    # weiterhin dieselbe Struktur wie bisher erhalten.
    remaining_columns = [
        column
        for column in comparison_df.columns
        if column != "raumnummer"
    ]

    comparison_df = comparison_df[
        [
            "raumnummer",
            *remaining_columns,
        ]
    ]

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

    comparison_df = (
        comparison_df
        .sort_values(
            [
                "status",
                "raumnummer",
                "_vergleichsschluessel",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # Der interne Schlüssel wird für den Vergleich benötigt,
    # soll aber nicht als zusätzliche technische Spalte im normalen
    # Vergleich/Excel-Export erscheinen.
    comparison_df = comparison_df.drop(
        columns=[
            "_vergleichsschluessel"
        ]
    )

    return comparison_df
