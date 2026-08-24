
from pathlib import Path
import re

import fitz
import pandas as pd

from config.settings import PDF_STATUS_COLORS


def clean_source_value(value: object) -> str:
    """
    Bereinigt die Angabe der Quelldateien.
    Leere Werte und NaN werden als leerer Text zurückgegeben.
    """
    if value is None or pd.isna(value):
        return ""

    return str(value).strip()


def normalize_numeric_room_for_search(
    value: str,
) -> str | None:
    """
    Normalisiert nur das Geschoss einer numerischen Raumnummer.

    Beispiele:
        -01.512 -> -1.512
        -1.512  -> -1.512
        00.302  -> 0.302
        01.514  -> 1.514
    """
    text = re.sub(
        r"\s+",
        "",
        str(value),
    )

    match = re.fullmatch(
        r"(-?\d{1,2})\.(\d{1,3})",
        text,
    )

    if not match:
        return None

    try:
        floor = int(
            match.group(1)
        )
    except ValueError:
        return None

    return (
        f"{floor}."
        f"{match.group(2)}"
    )


def room_search_variants(
    room_id: str,
) -> set[str]:
    """
    Erzeugt gleichwertige Schreibweisen für die PDF-Suche.

    Beispiel:
        -1.512 -> {-1.512, -01.512}
        0.302  -> {0.302, 00.302}
        1.514  -> {1.514, 01.514}
    """
    variants = {
        str(
            room_id
        ).strip()
    }

    normalized = normalize_numeric_room_for_search(
        room_id
    )

    if normalized is None:
        return variants

    floor_text, room_text = normalized.split(
        ".",
        1,
    )

    floor = int(
        floor_text
    )

    variants.add(
        normalized
    )

    if floor < 0:
        variants.add(
            f"-{abs(floor):02d}."
            f"{room_text}"
        )
    else:
        variants.add(
            f"{floor:02d}."
            f"{room_text}"
        )

    return variants


def find_exact_word_rectangles_in_document(
    document: fitz.Document,
    search_text: str,
) -> list[tuple[int, fitz.Rect]]:
    """
    Sucht eine Raumnummer exakt auf allen PDF-Seiten.
    """
    matches: list[
        tuple[int, fitz.Rect]
    ] = []

    variants = room_search_variants(
        search_text
    )

    normalized_target = (
        normalize_numeric_room_for_search(
            search_text
        )
    )

    for page_index, page in enumerate(
        document
    ):
        for word in page.get_text(
            "words"
        ):
            x0, y0, x1, y1, text, *_ = word
            candidate = text.strip()

            exact_match = (
                candidate in variants
            )

            normalized_candidate = (
                normalize_numeric_room_for_search(
                    candidate
                )
            )

            equivalent_numeric_match = (
                normalized_target is not None
                and normalized_candidate
                == normalized_target
            )

            if (
                exact_match
                or equivalent_numeric_match
            ):
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


def find_room_rectangle_by_ep(
    document: fitz.Document,
    ep_number: str,
    room_id: str,
) -> tuple[int, fitz.Rect] | None:
    """
    Findet bei numerischen Plänen genau den Raumnummern-Text,
    der zu einer bestimmten ep-Nummer gehört.

    Das löst Fälle wie:
        ep 228 -> -1.21
        ep 229 -> -1.21

    Obwohl die dargestellte Raumnummer mehrfach identisch ist,
    ist die ep-Nummer eindeutig und identifiziert den richtigen Block.
    """
    ep_text = str(
        ep_number
    ).strip()

    if not ep_text:
        return None

    normalized_room = (
        normalize_numeric_room_for_search(
            room_id
        )
    )

    best_match: tuple[
        float,
        int,
        fitz.Rect,
    ] | None = None

    for page_index, page in enumerate(
        document
    ):
        words = page.get_text(
            "words"
        )

        # Alle ep-Werte suchen, die unmittelbar neben "ep:" stehen.
        ep_value_words: list[
            tuple[float, float, float, float, str]
        ] = []

        for index, word in enumerate(
            words
        ):
            x0, y0, x1, y1, text, *_ = word

            if text.strip() != ep_text:
                continue

            cy = (
                y0 + y1
            ) / 2

            has_ep_label = False

            for other in words:
                ox0, oy0, ox1, oy1, otext, *_ = other

                if otext.strip().casefold() not in {
                    "ep:",
                    "ep",
                }:
                    continue

                ocy = (
                    oy0 + oy1
                ) / 2

                if (
                    abs(
                        ocy - cy
                    ) <= 4
                    and 0
                    <= x0 - ox1
                    <= 25
                ):
                    has_ep_label = True
                    break

            if has_ep_label:
                ep_value_words.append(
                    (
                        x0,
                        y0,
                        x1,
                        y1,
                        text,
                    )
                )

        for ep_word in ep_value_words:
            ex0, ey0, ex1, ey1, _ = (
                ep_word
            )

            ecx = (
                ex0 + ex1
            ) / 2
            ecy = (
                ey0 + ey1
            ) / 2

            for word in words:
                x0, y0, x1, y1, text, *_ = word
                candidate = text.strip()

                normalized_candidate = (
                    normalize_numeric_room_for_search(
                        candidate
                    )
                )

                if normalized_candidate is None:
                    continue

                # Normalerweise steht die Raumnummer direkt unter ep.
                cx = (
                    x0 + x1
                ) / 2
                cy = (
                    y0 + y1
                ) / 2

                dx = abs(
                    cx - ecx
                )
                dy = (
                    cy - ecy
                )

                if (
                    dx > 35
                    or not 3 <= dy <= 35
                ):
                    continue

                room_matches = (
                    normalized_room is None
                    or normalized_candidate
                    == normalized_room
                )

                # Bei verkürzten Nummern darf zusätzlich eine
                # Präfix-Beziehung gelten.
                prefix_matches = False

                if (
                    normalized_room is not None
                    and normalized_candidate is not None
                ):
                    prefix_matches = (
                        normalized_candidate.startswith(
                            normalized_room
                        )
                        or normalized_room.startswith(
                            normalized_candidate
                        )
                    )

                if not (
                    room_matches
                    or prefix_matches
                ):
                    continue

                distance = (
                    dx
                    + abs(
                        dy
                    )
                )

                rect = fitz.Rect(
                    x0,
                    y0,
                    x1,
                    y1,
                )

                if (
                    best_match is None
                    or distance
                    < best_match[0]
                ):
                    best_match = (
                        distance,
                        page_index,
                        rect,
                    )

    if best_match is None:
        return None

    return (
        best_match[1],
        best_match[2],
    )


def draw_number_label(
    page: fitz.Page,
    room_rect: fitz.Rect,
    label: str,
    color: tuple[
        float,
        float,
        float,
    ],
) -> fitz.Rect:
    """Zeichnet eine kleine Kennzeichnung neben die Raumnummer."""
    label_width = max(
        18,
        7 * len(
            str(
                label
            )
        ),
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
        str(
            label
        ),
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
        + len(
            legend_entries
        ) * row_height
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

    current_y = (
        y + title_height
    )

    for (
        short_name,
        description,
        color,
    ) in legend_entries:
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

        current_y += (
            row_height
        )


def create_marked_pdf(
    floorplan_pdf: Path,
    output_pdf: Path,
    comparison_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Erstellt eine markierte Kopie des Grundrisses und ein Protokoll.

    Verbesserungen für numerische Pläne:
    - ep wird als eindeutiger Anker verwendet, wenn vorhanden.
    - -1.512 und -01.512 werden als gleichwertige Schreibweisen erkannt.
    - Wenn dieselbe architektonische Raumnummer mehrfach im Plan steht,
      werden alle Treffer markiert statt den Raum komplett abzulehnen.
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
        room_id = str(
            row["raumnummer"]
        )

        status = str(
            row["status"]
        )

        ep_value = row.get(
            "ep_nummer",
            None,
        )

        ep_number = (
            None
            if ep_value is None
            or pd.isna(
                ep_value
            )
            else str(
                ep_value
            ).strip()
        )

        floorplan_sources = clean_source_value(
            row.get(
                "quelldateien_grundriss",
                "",
            )
        )

        schema_sources = clean_source_value(
            row.get(
                "quelldateien_schema",
                "",
            )
        )

        if status == "Nur im Schema":
            results.append(
                {
                    "kennzeichnung": None,
                    "raumnummer": room_id,
                    "ep_nummer": ep_number,
                    "status": status,
                    "grundriss_quellen":
                        floorplan_sources,
                    "schema_quellen":
                        schema_sources,
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
                    "ep_nummer": ep_number,
                    "status": status,
                    "grundriss_quellen":
                        floorplan_sources,
                    "schema_quellen":
                        schema_sources,
                    "seite": None,
                    "anzahl_treffer": 0,
                    "ergebnis":
                        "Unbekannter Status",
                }
            )
            continue

        matches: list[
            tuple[int, fitz.Rect]
        ] = []

        # Bei vorhandenem ep zuerst den exakt zugehörigen Luftmengenblock
        # suchen. So sind z.B. ep 228 und ep 229 trotz gleicher
        # dargestellter Raumnummer -1.21 eindeutig.
        if ep_number:
            ep_match = (
                find_room_rectangle_by_ep(
                    document,
                    ep_number,
                    room_id,
                )
            )

            if ep_match is not None:
                matches = [
                    ep_match
                ]

        # Fallback bzw. Räume ohne ep:
        # Raumnummer direkt in allen gleichwertigen Schreibweisen suchen.
        if not matches:
            matches = (
                find_exact_word_rectangles_in_document(
                    document,
                    room_id,
                )
            )

        if not matches:
            results.append(
                {
                    "kennzeichnung": None,
                    "raumnummer": room_id,
                    "ep_nummer": ep_number,
                    "status": status,
                    "grundriss_quellen":
                        floorplan_sources,
                    "schema_quellen":
                        schema_sources,
                    "seite": None,
                    "anzahl_treffer": 0,
                    "ergebnis":
                        "Raumnummer nicht gefunden",
                }
            )
            continue

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

        marked_pages: list[int] = []

        for (
            page_index,
            room_rect,
        ) in matches:
            page = document[
                page_index
            ]

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

            if label:
                draw_number_label(
                    page,
                    marking_rect,
                    label,
                    color,
                )

            marked_pages.append(
                page_index + 1
            )

        results.append(
            {
                "kennzeichnung": label,
                "raumnummer": room_id,
                "ep_nummer": ep_number,
                "status": status,
                "grundriss_quellen":
                    floorplan_sources,
                "schema_quellen":
                    schema_sources,
                "seite": (
                    ", ".join(
                        map(
                            str,
                            sorted(
                                set(
                                    marked_pages
                                )
                            ),
                        )
                    )
                ),
                "anzahl_treffer":
                    len(
                        matches
                    ),
                "ergebnis": (
                    "Markiert"
                    if len(
                        matches
                    ) == 1
                    else (
                        f"Markiert "
                        f"({len(matches)} Treffer)"
                    )
                ),
            }
        )

    if len(
        document
    ) > 0:
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
