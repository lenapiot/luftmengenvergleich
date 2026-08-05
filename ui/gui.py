from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config.settings import (
    DEFAULT_ROOM_PATTERN_KEY,
    ROOM_PATTERN_PRESETS,
)
from luftmengen_vergleich import run_comparison


CUSTOM_PATTERN_LABEL = "Benutzerdefiniertes Muster"


class LuftmengenGUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Luftmengenvergleich")
        self.root.geometry("760x720")
        self.root.resizable(False, False)

        self.floorplan_pdfs: list[Path] = []
        self.schema_pdfs: list[Path] = []
        self.output_dir: Path | None = None

        self.pattern_labels_to_keys = {
            settings["label"]: key
            for key, settings in ROOM_PATTERN_PRESETS.items()
        }

        default_label = ROOM_PATTERN_PRESETS[
            DEFAULT_ROOM_PATTERN_KEY
        ]["label"]

        self.room_pattern_var = tk.StringVar(
            value=default_label
        )

        self.custom_pattern_var = tk.StringVar()

        self.create_widgets()
        self.update_pattern_description()

    def create_widgets(self) -> None:
        title = tk.Label(
            self.root,
            text="Luftmengenvergleich",
            font=("Segoe UI", 20, "bold"),
        )
        title.pack(pady=(18, 5))

        subtitle = tk.Label(
            self.root,
            text=(
                "Grundrisse und Prinzipschemata automatisch "
                "vergleichen"
            ),
            font=("Segoe UI", 10),
        )
        subtitle.pack(pady=(0, 15))

        files_frame = tk.LabelFrame(
            self.root,
            text="1. Dateien auswählen",
            font=("Segoe UI", 10, "bold"),
            padx=15,
            pady=12,
        )
        files_frame.pack(
            fill="x",
            padx=25,
            pady=5,
        )

        tk.Button(
            files_frame,
            text="Grundrisse hinzufügen",
            width=28,
            command=self.choose_floorplans,
        ).grid(
            row=0,
            column=0,
            padx=8,
            pady=5,
        )

        tk.Button(
            files_frame,
            text="Grundriss-Auswahl leeren",
            width=28,
            command=self.clear_floorplans,
        ).grid(
            row=0,
            column=1,
            padx=8,
            pady=5,
        )

        self.floorplan_label = tk.Label(
            files_frame,
            text="Keine Grundrisse ausgewählt",
        )
        self.floorplan_label.grid(
            row=1,
            column=0,
            columnspan=2,
            pady=(0, 8),
        )

        tk.Button(
            files_frame,
            text="Prinzipschemata hinzufügen",
            width=28,
            command=self.choose_schemas,
        ).grid(
            row=2,
            column=0,
            padx=8,
            pady=5,
        )

        tk.Button(
            files_frame,
            text="Schema-Auswahl leeren",
            width=28,
            command=self.clear_schemas,
        ).grid(
            row=2,
            column=1,
            padx=8,
            pady=5,
        )

        self.schema_label = tk.Label(
            files_frame,
            text="Keine Prinzipschemata ausgewählt",
        )
        self.schema_label.grid(
            row=3,
            column=0,
            columnspan=2,
            pady=(0, 5),
        )

        pattern_frame = tk.LabelFrame(
            self.root,
            text="2. Raumnummernformat",
            font=("Segoe UI", 10, "bold"),
            padx=15,
            pady=12,
        )
        pattern_frame.pack(
            fill="x",
            padx=25,
            pady=10,
        )

        tk.Label(
            pattern_frame,
            text="Format auswählen:",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=5,
            pady=5,
        )

        pattern_options = [
            settings["label"]
            for settings in ROOM_PATTERN_PRESETS.values()
        ]
        pattern_options.append(
            CUSTOM_PATTERN_LABEL
        )

        self.pattern_combobox = ttk.Combobox(
            pattern_frame,
            textvariable=self.room_pattern_var,
            values=pattern_options,
            state="readonly",
            width=38,
        )
        self.pattern_combobox.grid(
            row=0,
            column=1,
            sticky="w",
            padx=5,
            pady=5,
        )
        self.pattern_combobox.bind(
            "<<ComboboxSelected>>",
            self.on_pattern_changed,
        )

        self.pattern_description_label = tk.Label(
            pattern_frame,
            text="",
            justify="left",
            wraplength=600,
        )
        self.pattern_description_label.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            padx=5,
            pady=(3, 8),
        )

        self.custom_pattern_label = tk.Label(
            pattern_frame,
            text="Eigenes Muster:",
        )
        self.custom_pattern_label.grid(
            row=2,
            column=0,
            sticky="w",
            padx=5,
            pady=5,
        )

        self.custom_pattern_entry = tk.Entry(
            pattern_frame,
            textvariable=self.custom_pattern_var,
            width=42,
            state="disabled",
        )
        self.custom_pattern_entry.grid(
            row=2,
            column=1,
            sticky="w",
            padx=5,
            pady=5,
        )

        self.custom_help_label = tk.Label(
            pattern_frame,
            text=(
                "Nur für fortgeschrittene Benutzer. "
                "Beispiel: \\bRAUM-\\d+[a-z]?\\b"
            ),
            justify="left",
            wraplength=600,
            fg="gray",
        )
        self.custom_help_label.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="w",
            padx=5,
            pady=(0, 5),
        )

        output_frame = tk.LabelFrame(
            self.root,
            text="3. Ausgabe",
            font=("Segoe UI", 10, "bold"),
            padx=15,
            pady=12,
        )
        output_frame.pack(
            fill="x",
            padx=25,
            pady=5,
        )

        tk.Button(
            output_frame,
            text="Ausgabeordner auswählen",
            width=30,
            command=self.choose_output,
        ).pack(pady=5)

        self.output_label = tk.Label(
            output_frame,
            text="Kein Ausgabeordner ausgewählt",
            wraplength=650,
        )
        self.output_label.pack(pady=5)

        self.start_button = tk.Button(
            self.root,
            text="Vergleich starten",
            width=32,
            height=2,
            font=("Segoe UI", 11, "bold"),
            command=self.start,
        )
        self.start_button.pack(pady=(18, 10))

        self.status = tk.Label(
            self.root,
            text="Bereit",
            fg="blue",
            wraplength=680,
            font=("Segoe UI", 10),
        )
        self.status.pack(pady=5)

    def choose_floorplans(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Grundrisse auswählen",
            filetypes=[
                ("PDF-Dateien", "*.pdf"),
            ],
        )

        new_files = [
            Path(path)
            for path in selected
        ]

        for path in new_files:
            if path not in self.floorplan_pdfs:
                self.floorplan_pdfs.append(path)

        self.update_floorplan_label()

    def choose_schemas(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Prinzipschemata auswählen",
            filetypes=[
                ("PDF-Dateien", "*.pdf"),
            ],
        )

        new_files = [
            Path(path)
            for path in selected
        ]

        for path in new_files:
            if path not in self.schema_pdfs:
                self.schema_pdfs.append(path)

        self.update_schema_label()

    def clear_floorplans(self) -> None:
        self.floorplan_pdfs.clear()
        self.update_floorplan_label()

    def clear_schemas(self) -> None:
        self.schema_pdfs.clear()
        self.update_schema_label()

    def update_floorplan_label(self) -> None:
        count = len(self.floorplan_pdfs)

        if count == 0:
            text = "Keine Grundrisse ausgewählt"
        elif count == 1:
            text = "1 Grundriss ausgewählt"
        else:
            text = f"{count} Grundrisse ausgewählt"

        self.floorplan_label.config(
            text=text
        )

    def update_schema_label(self) -> None:
        count = len(self.schema_pdfs)

        if count == 0:
            text = "Keine Prinzipschemata ausgewählt"
        elif count == 1:
            text = "1 Prinzipschema ausgewählt"
        else:
            text = f"{count} Prinzipschemata ausgewählt"

        self.schema_label.config(
            text=text
        )

    def choose_output(self) -> None:
        folder = filedialog.askdirectory(
            title="Ausgabeordner auswählen",
        )

        if folder:
            self.output_dir = Path(folder)

            self.output_label.config(
                text=str(self.output_dir)
            )

    def on_pattern_changed(
        self,
        _event: object | None = None,
    ) -> None:
        selected_label = self.room_pattern_var.get()

        if selected_label == CUSTOM_PATTERN_LABEL:
            self.custom_pattern_entry.config(
                state="normal"
            )
        else:
            self.custom_pattern_entry.config(
                state="disabled"
            )

        self.update_pattern_description()

    def update_pattern_description(self) -> None:
        selected_label = self.room_pattern_var.get()

        if selected_label == CUSTOM_PATTERN_LABEL:
            description = (
                "Ein eigenes Erkennungsmuster verwenden. "
                "Diese Option ist für besondere Raumnummernformate gedacht."
            )
        else:
            preset_key = self.pattern_labels_to_keys.get(
                selected_label
            )

            if preset_key is None:
                description = ""
            else:
                description = ROOM_PATTERN_PRESETS[
                    preset_key
                ]["description"]

        self.pattern_description_label.config(
            text=description
        )

    def get_selected_room_pattern(
        self,
    ) -> tuple[str, str | None]:
        selected_label = self.room_pattern_var.get()

        if selected_label == CUSTOM_PATTERN_LABEL:
            custom_pattern = (
                self.custom_pattern_var
                .get()
                .strip()
            )

            if not custom_pattern:
                raise ValueError(
                    "Bitte ein benutzerdefiniertes "
                    "Raumnummernmuster eingeben."
                )

            return (
                DEFAULT_ROOM_PATTERN_KEY,
                custom_pattern,
            )

        preset_key = self.pattern_labels_to_keys.get(
            selected_label
        )

        if preset_key is None:
            raise ValueError(
                "Das gewählte Raumnummernformat "
                "ist unbekannt."
            )

        return (
            preset_key,
            None,
        )

    def set_status(
        self,
        text: str,
    ) -> None:
        self.status.config(
            text=text
        )
        self.root.update_idletasks()

    def set_running_state(
        self,
        running: bool,
    ) -> None:
        if running:
            self.start_button.config(
                state="disabled"
            )
        else:
            self.start_button.config(
                state="normal"
            )

    def start(self) -> None:
        if not self.floorplan_pdfs:
            messagebox.showerror(
                "Fehler",
                "Bitte mindestens einen Grundriss auswählen.",
            )
            return

        if not self.schema_pdfs:
            messagebox.showerror(
                "Fehler",
                "Bitte mindestens ein Prinzipschema auswählen.",
            )
            return

        if self.output_dir is None:
            messagebox.showerror(
                "Fehler",
                "Bitte einen Ausgabeordner auswählen.",
            )
            return

        try:
            (
                room_pattern_key,
                custom_room_pattern,
            ) = self.get_selected_room_pattern()

            self.set_running_state(
                True
            )
            self.set_status(
                "Vergleich wird gestartet ..."
            )

            results = run_comparison(
                floorplan_pdfs=self.floorplan_pdfs,
                schema_pdfs=self.schema_pdfs,
                output_dir=self.output_dir,
                status_callback=self.set_status,
                room_pattern_key=room_pattern_key,
                custom_room_pattern=custom_room_pattern,
            )

            output_pdf_count = len(
                results["output_pdfs"]
            )

            self.set_status(
                "Fertig"
            )

            messagebox.showinfo(
                "Fertig",
                (
                    "Der Vergleich wurde erfolgreich "
                    "abgeschlossen.\n\n"
                    f"{output_pdf_count} markierte PDF-Datei(en) "
                    "und eine Excel-Auswertung wurden erstellt."
                ),
            )

        except Exception as error:
            self.set_status(
                "Fehler"
            )

            messagebox.showerror(
                "Fehler",
                str(error),
            )

        finally:
            self.set_running_state(
                False
            )

    def run(self) -> None:
        self.root.mainloop()


def start_gui() -> None:
    app = LuftmengenGUI()
    app.run()
