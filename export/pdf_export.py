
from pathlib import Path

import fitz 
import pandas as pd

from config.settings import PDF_STATUS_COLORS

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