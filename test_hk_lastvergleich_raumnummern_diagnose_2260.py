from pathlib import Path
from tkinter import Tk, filedialog
from difflib import get_close_matches

from hk.lastvergleich import (
    extract_loads_from_pdfs_checked,
    extract_and_consolidate_schema,
    compare_loads_with_schema,
    determine_document_building,
)


def choose_pdf(title: str) -> Path:
    path = filedialog.askopenfilename(
        title=title,
        filetypes=[("PDF-Dateien", "*.pdf")],
    )
    if not path:
        raise SystemExit("Keine Datei ausgewählt.")
    return Path(path)


def choose_pdfs(title: str) -> list[Path]:
    paths = filedialog.askopenfilenames(
        title=title,
        filetypes=[("PDF-Dateien", "*.pdf")],
    )
    if not paths:
        raise SystemExit("Keine Dateien ausgewählt.")
    return [Path(path) for path in paths]


def print_room_list(title: str, rooms: list[str], max_rows: int = 20) -> None:
    print()
    print("=" * 90)
    print(title)
    print("=" * 90)
    print("Anzahl:", len(rooms))
    for room in rooms[:max_rows]:
        print(room)


def print_similar_matches(
    source_rooms: list[str],
    target_rooms: list[str],
    title: str,
    max_rows: int = 20,
) -> None:
    print()
    print("=" * 90)
    print(title)
    print("=" * 90)

    if not source_rooms:
        print("Keine Räume.")
        return

    for room in source_rooms[:max_rows]:
        matches = get_close_matches(
            room,
            target_rooms,
            n=5,
            cutoff=0.55,
        )
        if matches:
            print(f"{room:20s} -> " + " | ".join(matches))
        else:
            print(f"{room:20s} -> keine ähnliche Raumnummer")


def main() -> None:
    root = Tk()
    root.withdraw()

    schema_pdf = choose_pdf(
        "Strangschema Klimawärme/Kälte auswählen"
    )
    heating_pdfs = choose_pdfs(
        "Heizlast-Grundrisse auswählen"
    )
    cooling_pdfs = choose_pdfs(
        "Kühllast-Grundrisse auswählen"
    )

    schema = extract_and_consolidate_schema(
        schema_pdf
    )
    building = determine_document_building(
        schema
    )

    if building not in {"MIT1", "MIT2"}:
        raise SystemExit(
            "Gebäude des Strangschemas konnte nicht eindeutig erkannt werden."
        )

    heating, _ = extract_loads_from_pdfs_checked(
        heating_pdfs,
        "Heizlast",
        expected_building=building,
    )

    cooling, _ = extract_loads_from_pdfs_checked(
        cooling_pdfs,
        "Kühllast",
        expected_building=building,
    )

    comparison = compare_loads_with_schema(
        heating,
        cooling,
        schema,
    )

    schema_rooms = sorted(set(schema["raumnummer"].dropna().astype(str)))
    heating_rooms = sorted(set(heating["raumnummer"].dropna().astype(str)))
    cooling_rooms = sorted(set(cooling["raumnummer"].dropna().astype(str)))
    floorplan_rooms = sorted(set(heating_rooms) | set(cooling_rooms))

    only_schema = sorted(set(schema_rooms) - set(floorplan_rooms))
    only_heating = sorted(set(heating_rooms) - set(schema_rooms))
    only_cooling = sorted(set(cooling_rooms) - set(schema_rooms))

    in_both_heating_schema = sorted(set(heating_rooms) & set(schema_rooms))
    in_both_cooling_schema = sorted(set(cooling_rooms) & set(schema_rooms))

    print()
    print("=" * 90)
    print("RAUMNUMMERN-DIAGNOSE")
    print("=" * 90)

    print("Gebäude:", building)
    print("Schema-Räume:", len(schema_rooms))
    print("Heizlast-Räume:", len(heating_rooms))
    print("Kühllast-Räume:", len(cooling_rooms))
    print("Grundriss-Räume gesamt:", len(floorplan_rooms))

    print()
    print("Schnittmenge Schema/Heizlast:", len(in_both_heating_schema))
    print("Schnittmenge Schema/Kühllast:", len(in_both_cooling_schema))
    print("Nur im Schema:", len(only_schema))
    print("Nur im Heizlast-Grundriss:", len(only_heating))
    print("Nur im Kühllast-Grundriss:", len(only_cooling))

    print_room_list(
        "BEISPIELE: NUR IM SCHEMA",
        only_schema,
    )
    print_room_list(
        "BEISPIELE: NUR IM HEIZLAST-GRUNDRISS",
        only_heating,
    )
    print_room_list(
        "BEISPIELE: NUR IM KÜHLLAST-GRUNDRISS",
        only_cooling,
    )

    print_similar_matches(
        only_heating,
        schema_rooms,
        "ÄHNLICHE SCHEMA-RAUMNUMMERN ZU HEIZLAST-RÄUMEN",
    )
    print_similar_matches(
        only_cooling,
        schema_rooms,
        "ÄHNLICHE SCHEMA-RAUMNUMMERN ZU KÜHLLAST-RÄUMEN",
    )
    print_similar_matches(
        only_schema,
        floorplan_rooms,
        "ÄHNLICHE GRUNDRISS-RAUMNUMMERN ZU SCHEMA-RÄUMEN",
    )

    print()
    print("=" * 90)
    print("EBENENVERTEILUNG")
    print("=" * 90)

    print()
    print("SCHEMA:")
    print(
        schema["ebene"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print("HEIZLAST:")
    if heating.empty:
        print("keine Daten")
    else:
        print(
            heating["ebene"]
            .value_counts()
            .sort_index()
            .to_string()
        )

    print()
    print("KÜHLLAST:")
    if cooling.empty:
        print("keine Daten")
    else:
        print(
            cooling["ebene"]
            .value_counts()
            .sort_index()
            .to_string()
        )

    print()
    print("=" * 90)
    print("GESAMTSTATUS")
    print("=" * 90)
    print(
        comparison["status_gesamt"]
        .value_counts(dropna=False)
        .to_string()
    )


if __name__ == "__main__":
    main()
