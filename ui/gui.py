from __future__ import annotations

import getpass
import re
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from config.settings import (
    DEFAULT_ROOM_PATTERN_KEY,
    ROOM_PATTERN_PRESETS,
)
from luftmengen_vergleich import run_comparison


CUSTOM_PATTERN_LABEL = "Benutzerdefiniertes Muster"

APP_VERSION = "1.0"

BACKGROUND_COLOR = "#F3F6F8"
CARD_COLOR = "#FFFFFF"
PRIMARY_COLOR = "#079ED1"
PRIMARY_HOVER_COLOR = "#087FA8"
TEXT_COLOR = "#17212B"
MUTED_TEXT_COLOR = "#66727C"
BORDER_COLOR = "#D7E0E5"
SUCCESS_COLOR = "#238636"
ERROR_COLOR = "#C62828"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LOGO_PATH = (
    PROJECT_ROOT
    / "assets"
    / "eicher_pauli_logo.jpg"
)


class LuftmengenGUI:
    def __init__(self) -> None:
        self.root = tk.Tk()

        self.root.title(
            f"Luftmengenvergleich – Version {APP_VERSION}"
        )

        self.root.geometry("940x830")
        self.root.minsize(900, 780)

        self.root.configure(
            bg=BACKGROUND_COLOR
        )

        self.floorplan_pdfs: list[Path] = []
        self.schema_pdfs: list[Path] = []
        self.output_dir: Path | None = None

        self.pattern_labels_to_keys = {
            settings["label"]: key
            for key, settings
            in ROOM_PATTERN_PRESETS.items()
        }

        default_label = ROOM_PATTERN_PRESETS[
            DEFAULT_ROOM_PATTERN_KEY
        ]["label"]

        self.room_pattern_var = tk.StringVar(
            value=default_label
        )

        self.custom_pattern_var = tk.StringVar()

        self.logo_image: ImageTk.PhotoImage | None = None

        self.interactive_widgets: list[
            tk.Widget
        ] = []

        self.configure_styles()
        self.create_widgets()
        self.update_pattern_description()

    def configure_styles(self) -> None:
        """Konfiguriert die Darstellung der ttk-Elemente."""
        style = ttk.Style(
            self.root
        )

        try:
            style.theme_use(
                "clam"
            )
        except tk.TclError:
            pass

        style.configure(
            "Room.TCombobox",
            padding=7,
            fieldbackground=CARD_COLOR,
            background=CARD_COLOR,
            foreground=TEXT_COLOR,
            bordercolor=BORDER_COLOR,
            lightcolor=BORDER_COLOR,
            darkcolor=BORDER_COLOR,
            arrowcolor=PRIMARY_COLOR,
            font=("Segoe UI", 10),
        )

        style.map(
            "Room.TCombobox",
            fieldbackground=[
                (
                    "readonly",
                    CARD_COLOR,
                ),
            ],
            foreground=[
                (
                    "readonly",
                    TEXT_COLOR,
                ),
            ],
            selectbackground=[
                (
                    "readonly",
                    CARD_COLOR,
                ),
            ],
            selectforeground=[
                (
                    "readonly",
                    TEXT_COLOR,
                ),
            ],
        )

        style.configure(
            "Comparison.Horizontal.TProgressbar",
            troughcolor="#DDE7EC",
            background=PRIMARY_COLOR,
            bordercolor="#DDE7EC",
            lightcolor=PRIMARY_COLOR,
            darkcolor=PRIMARY_COLOR,
            thickness=12,
        )

    def create_widgets(self) -> None:
        """Erstellt das vollständige Fenster."""
        self.create_header()

        content = tk.Frame(
            self.root,
            bg=BACKGROUND_COLOR,
        )

        content.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=(18, 10),
        )

        self.create_files_card(
            content
        )

        self.create_pattern_card(
            content
        )

        self.create_output_card(
            content
        )

        self.create_action_area(
            content
        )

        self.create_footer()

    def create_header(self) -> None:
        """Erstellt den Kopfbereich mit Logo und Titel."""
        header = tk.Frame(
            self.root,
            bg=CARD_COLOR,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )

        header.pack(
            fill="x"
        )

        header_content = tk.Frame(
            header,
            bg=CARD_COLOR,
        )

        header_content.pack(
            fill="x",
            padx=30,
            pady=18,
        )

        logo_frame = tk.Frame(
            header_content,
            bg=CARD_COLOR,
        )

        logo_frame.pack(
            side="left"
        )

        self.load_logo(
            logo_frame
        )

        title_frame = tk.Frame(
            header_content,
            bg=CARD_COLOR,
        )

        title_frame.pack(
            side="right",
            fill="both",
            expand=True,
            padx=(30, 0),
        )

        tk.Label(
            title_frame,
            text="Luftmengenvergleich",
            font=(
                "Segoe UI",
                23,
                "bold",
            ),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="e",
        ).pack(
            fill="x"
        )

        tk.Label(
            title_frame,
            text=(
                "Automatischer Vergleich von "
                "Grundrissen und Prinzipschemata"
            ),
            font=(
                "Segoe UI",
                10,
            ),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="e",
        ).pack(
            fill="x",
            pady=(4, 0),
        )

    def load_logo(
        self,
        parent: tk.Widget,
    ) -> None:
        """Lädt das eicher+pauli-Logo als JPG."""
        if not LOGO_PATH.exists():
            self.create_text_logo(
                parent
            )
            return

        try:
            with Image.open(
                LOGO_PATH
            ) as image:
                logo = image.convert(
                    "RGB"
                )

                logo.thumbnail(
                    (
                        330,
                        90,
                    ),
                    Image.Resampling.LANCZOS,
                )

                self.logo_image = (
                    ImageTk.PhotoImage(
                        logo
                    )
                )

            tk.Label(
                parent,
                image=self.logo_image,
                bg=CARD_COLOR,
            ).pack()

        except Exception:
            self.create_text_logo(
                parent
            )

    def create_text_logo(
        self,
        parent: tk.Widget,
    ) -> None:
        """Zeigt eine Ersatzdarstellung, falls das Logo fehlt."""
        tk.Label(
            parent,
            text="eicher+pauli",
            font=(
                "Segoe UI",
                22,
                "bold",
            ),
            fg=PRIMARY_COLOR,
            bg=CARD_COLOR,
        ).pack(
            anchor="w"
        )

        tk.Label(
            parent,
            text="Energie und Planung",
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
        ).pack(
            anchor="w"
        )

    def create_card(
        self,
        parent: tk.Widget,
        title: str,
    ) -> tk.Frame:
        """Erstellt einen einheitlichen weissen Inhaltsbereich."""
        outer = tk.Frame(
            parent,
            bg=CARD_COLOR,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )

        outer.pack(
            fill="x",
            pady=7,
        )

        tk.Label(
            outer,
            text=title,
            font=(
                "Segoe UI",
                11,
                "bold",
            ),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
        ).pack(
            fill="x",
            padx=20,
            pady=(15, 8),
        )

        separator = tk.Frame(
            outer,
            bg=BORDER_COLOR,
            height=1,
        )

        separator.pack(
            fill="x",
            padx=20,
        )

        inner = tk.Frame(
            outer,
            bg=CARD_COLOR,
        )

        inner.pack(
            fill="x",
            padx=20,
            pady=14,
        )

        return inner

    def create_files_card(
        self,
        parent: tk.Widget,
    ) -> None:
        """Erstellt den Bereich für die PDF-Auswahl."""
        frame = self.create_card(
            parent,
            "1. Dateien auswählen",
        )

        frame.columnconfigure(
            1,
            weight=1,
        )

        self.create_file_selection_row(
            frame=frame,
            row=0,
            title="Grundrisse",
            add_command=self.choose_floorplans,
            clear_command=self.clear_floorplans,
        )

        self.floorplan_label = tk.Label(
            frame,
            text="Keine Grundrisse ausgewählt",
            font=(
                "Segoe UI",
                9,
            ),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
        )

        self.floorplan_label.grid(
            row=1,
            column=1,
            columnspan=2,
            sticky="w",
            padx=(12, 0),
            pady=(0, 12),
        )

        self.create_file_selection_row(
            frame=frame,
            row=2,
            title="Prinzipschemata",
            add_command=self.choose_schemas,
            clear_command=self.clear_schemas,
        )

        self.schema_label = tk.Label(
            frame,
            text="Keine Prinzipschemata ausgewählt",
            font=(
                "Segoe UI",
                9,
            ),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
        )

        self.schema_label.grid(
            row=3,
            column=1,
            columnspan=2,
            sticky="w",
            padx=(12, 0),
        )

    def create_file_selection_row(
        self,
        frame: tk.Frame,
        row: int,
        title: str,
        add_command,
        clear_command,
    ) -> None:
        """Erstellt eine Zeile für eine Dateikategorie."""
        tk.Label(
            frame,
            text=f"{title}:",
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
            width=18,
        ).grid(
            row=row,
            column=0,
            sticky="w",
            pady=5,
        )

        add_button = self.create_secondary_button(
            frame,
            "Dateien hinzufügen",
            add_command,
        )

        add_button.grid(
            row=row,
            column=1,
            sticky="w",
            padx=(12, 8),
            pady=5,
        )

        clear_button = self.create_light_button(
            frame,
            "Auswahl leeren",
            clear_command,
        )

        clear_button.grid(
            row=row,
            column=2,
            sticky="w",
            pady=5,
        )

        self.interactive_widgets.extend(
            [
                add_button,
                clear_button,
            ]
        )

    def create_pattern_card(
        self,
        parent: tk.Widget,
    ) -> None:
        """Erstellt die Auswahl des Raumnummernformats."""
        frame = self.create_card(
            parent,
            "2. Raumnummernformat",
        )

        frame.columnconfigure(
            1,
            weight=1,
        )

        tk.Label(
            frame,
            text="Format:",
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 15),
            pady=5,
        )

        pattern_options = [
            settings["label"]
            for settings
            in ROOM_PATTERN_PRESETS.values()
        ]

        pattern_options.append(
            CUSTOM_PATTERN_LABEL
        )

        self.pattern_combobox = ttk.Combobox(
            frame,
            textvariable=self.room_pattern_var,
            values=pattern_options,
            state="readonly",
            width=42,
            style="Room.TCombobox",
        )

        self.pattern_combobox.grid(
            row=0,
            column=1,
            sticky="w",
            pady=5,
        )

        self.pattern_combobox.bind(
            "<<ComboboxSelected>>",
            self.on_pattern_changed,
        )

        self.interactive_widgets.append(
            self.pattern_combobox
        )

        self.pattern_description_label = tk.Label(
            frame,
            text="",
            font=(
                "Segoe UI",
                9,
            ),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            justify="left",
            wraplength=700,
            anchor="w",
        )

        self.pattern_description_label.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(5, 10),
        )

        self.custom_pattern_label = tk.Label(
            frame,
            text="Eigenes Muster:",
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
        )

        self.custom_pattern_label.grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 15),
            pady=5,
        )

        self.custom_pattern_entry = tk.Entry(
            frame,
            textvariable=self.custom_pattern_var,
            width=48,
            font=(
                "Consolas",
                10,
            ),
            relief="solid",
            borderwidth=1,
            disabledbackground="#EDF1F3",
            disabledforeground="#8A949B",
        )

        self.custom_pattern_entry.grid(
            row=2,
            column=1,
            sticky="w",
            pady=5,
            ipady=5,
        )

        self.custom_pattern_entry.config(
            state="disabled"
        )

        self.interactive_widgets.append(
            self.custom_pattern_entry
        )

        self.custom_help_label = tk.Label(
            frame,
            text=(
                "USZ-Standard erkennt auch Nominal und Havarie. "
                "Mehrere Luftmengenblöcke derselben Raumnummer "
                "werden als «Mehrfach / uneindeutig» markiert."
            ),
            font=(
                "Segoe UI",
                9,
            ),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            justify="left",
            wraplength=700,
            anchor="w",
        )

        self.custom_help_label.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 0),
        )

    def create_output_card(
        self,
        parent: tk.Widget,
    ) -> None:
        """Erstellt den Bereich für den Ausgabeordner."""
        frame = self.create_card(
            parent,
            "3. Ausgabe",
        )

        frame.columnconfigure(
            1,
            weight=1,
        )

        output_button = self.create_secondary_button(
            frame,
            "Ausgabeordner auswählen",
            self.choose_output,
        )

        output_button.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 15),
            pady=4,
        )

        self.interactive_widgets.append(
            output_button
        )

        self.output_label = tk.Label(
            frame,
            text="Kein Ausgabeordner ausgewählt",
            font=(
                "Segoe UI",
                9,
            ),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
            justify="left",
            wraplength=600,
        )

        self.output_label.grid(
            row=0,
            column=1,
            sticky="w",
        )

    def create_action_area(
        self,
        parent: tk.Widget,
    ) -> None:
        """Erstellt Startknopf, Status und Fortschrittsbalken."""
        action_frame = tk.Frame(
            parent,
            bg=BACKGROUND_COLOR,
        )

        action_frame.pack(
            fill="x",
            pady=(15, 5),
        )

        self.start_button = tk.Button(
            action_frame,
            text="Vergleich starten",
            font=(
                "Segoe UI",
                12,
                "bold",
            ),
            fg="white",
            bg=PRIMARY_COLOR,
            activeforeground="white",
            activebackground=PRIMARY_HOVER_COLOR,
            relief="flat",
            cursor="hand2",
            command=self.start,
            padx=35,
            pady=12,
        )

        self.start_button.pack()

        self.progress = ttk.Progressbar(
            action_frame,
            orient="horizontal",
            mode="determinate",
            maximum=6,
            value=0,
            length=600,
            style="Comparison.Horizontal.TProgressbar",
        )

        self.progress.pack(
            pady=(18, 8)
        )

        self.status = tk.Label(
            action_frame,
            text="Bereit",
            font=(
                "Segoe UI",
                10,
            ),
            fg=MUTED_TEXT_COLOR,
            bg=BACKGROUND_COLOR,
            wraplength=760,
        )

        self.status.pack()

    def create_footer(self) -> None:
        """Erstellt Fusszeile mit Benutzer, Datum und Version."""
        username = getpass.getuser()

        current_date = datetime.now().strftime(
            "%d.%m.%Y"
        )

        footer = tk.Frame(
            self.root,
            bg="#E7EDF0",
        )

        footer.pack(
            fill="x",
            side="bottom",
        )

        tk.Label(
            footer,
            text=(
                f"Benutzer: {username}    |    "
                f"Datum: {current_date}"
            ),
            font=(
                "Segoe UI",
                9,
            ),
            fg=MUTED_TEXT_COLOR,
            bg="#E7EDF0",
        ).pack(
            side="left",
            padx=25,
            pady=9,
        )

        tk.Label(
            footer,
            text=(
                f"eicher+pauli · "
                f"Luftmengenvergleich v{APP_VERSION}"
            ),
            font=(
                "Segoe UI",
                9,
            ),
            fg=MUTED_TEXT_COLOR,
            bg="#E7EDF0",
        ).pack(
            side="right",
            padx=25,
            pady=9,
        )

    def create_secondary_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
    ) -> tk.Button:
        """Erstellt einen blauen Sekundärbutton."""
        return tk.Button(
            parent,
            text=text,
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
            fg="white",
            bg=PRIMARY_COLOR,
            activeforeground="white",
            activebackground=PRIMARY_HOVER_COLOR,
            relief="flat",
            cursor="hand2",
            command=command,
            padx=14,
            pady=7,
        )

    def create_light_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
    ) -> tk.Button:
        """Erstellt einen zurückhaltenden hellen Button."""
        return tk.Button(
            parent,
            text=text,
            font=(
                "Segoe UI",
                9,
            ),
            fg=TEXT_COLOR,
            bg="#E8EEF1",
            activeforeground=TEXT_COLOR,
            activebackground="#D9E3E8",
            relief="flat",
            cursor="hand2",
            command=command,
            padx=14,
            pady=7,
        )

    def choose_floorplans(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Grundrisse auswählen",
            filetypes=[
                (
                    "PDF-Dateien",
                    "*.pdf",
                ),
            ],
        )

        for selected_path in selected:
            path = Path(
                selected_path
            )

            if path not in self.floorplan_pdfs:
                self.floorplan_pdfs.append(
                    path
                )

        self.update_floorplan_label()

    def choose_schemas(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Prinzipschemata auswählen",
            filetypes=[
                (
                    "PDF-Dateien",
                    "*.pdf",
                ),
            ],
        )

        for selected_path in selected:
            path = Path(
                selected_path
            )

            if path not in self.schema_pdfs:
                self.schema_pdfs.append(
                    path
                )

        self.update_schema_label()

    def clear_floorplans(self) -> None:
        self.floorplan_pdfs.clear()
        self.update_floorplan_label()

    def clear_schemas(self) -> None:
        self.schema_pdfs.clear()
        self.update_schema_label()

    def update_floorplan_label(self) -> None:
        count = len(
            self.floorplan_pdfs
        )

        if count == 0:
            text = (
                "Keine Grundrisse ausgewählt"
            )
        elif count == 1:
            text = (
                f"1 Grundriss ausgewählt: "
                f"{self.floorplan_pdfs[0].name}"
            )
        else:
            text = (
                f"{count} Grundrisse ausgewählt"
            )

        self.floorplan_label.config(
            text=text
        )

    def update_schema_label(self) -> None:
        count = len(
            self.schema_pdfs
        )

        if count == 0:
            text = (
                "Keine Prinzipschemata ausgewählt"
            )
        elif count == 1:
            text = (
                f"1 Prinzipschema ausgewählt: "
                f"{self.schema_pdfs[0].name}"
            )
        else:
            text = (
                f"{count} Prinzipschemata ausgewählt"
            )

        self.schema_label.config(
            text=text
        )

    def choose_output(self) -> None:
        initial_directory: str | None = None

        if self.output_dir is not None:
            initial_directory = str(
                self.output_dir
            )

        elif self.floorplan_pdfs:
            initial_directory = str(
                self.floorplan_pdfs[0].parent
            )

        dialog_arguments: dict[
            str,
            object,
        ] = {
            "title": "Ausgabeordner auswählen",
        }

        if initial_directory is not None:
            dialog_arguments[
                "initialdir"
            ] = initial_directory

        folder = filedialog.askdirectory(
            **dialog_arguments
        )

        if folder:
            self.output_dir = Path(
                folder
            )

            self.output_label.config(
                text=str(
                    self.output_dir
                )
            )

    def on_pattern_changed(
        self,
        _event: object | None = None,
    ) -> None:
        selected_label = (
            self.room_pattern_var.get()
        )

        if (
            selected_label
            == CUSTOM_PATTERN_LABEL
        ):
            self.custom_pattern_entry.config(
                state="normal"
            )

            self.custom_pattern_entry.focus_set()

        else:
            self.custom_pattern_entry.config(
                state="disabled"
            )

        self.update_pattern_description()

    def update_pattern_description(self) -> None:
        selected_label = (
            self.room_pattern_var.get()
        )

        if (
            selected_label
            == CUSTOM_PATTERN_LABEL
        ):
            description = (
                "Sonderformat für besondere "
                "Raumnummern. Beispiel für "
                "RAUM-101: "
                r"\bRAUM-\d+[a-z]?\b"
            )

        else:
            preset_key = (
                self.pattern_labels_to_keys.get(
                    selected_label
                )
            )

            if preset_key is None:
                description = ""

            else:
                description = (
                    ROOM_PATTERN_PRESETS[
                        preset_key
                    ]["description"]
                )

                if (
                    preset_key
                    == "usz_standard"
                ):
                    description += (
                        " Nominal und Havarie "
                        "werden automatisch erkannt."
                    )

        self.pattern_description_label.config(
            text=description
        )

    def get_selected_room_pattern(
        self,
    ) -> tuple[
        str,
        str | None,
    ]:
        selected_label = (
            self.room_pattern_var.get()
        )

        if (
            selected_label
            == CUSTOM_PATTERN_LABEL
        ):
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

            try:
                re.compile(
                    custom_pattern
                )

            except re.error as error:
                raise ValueError(
                    "Das benutzerdefinierte "
                    "Raumnummernmuster ist ungültig:\n"
                    f"{error}"
                ) from error

            return (
                DEFAULT_ROOM_PATTERN_KEY,
                custom_pattern,
            )

        preset_key = (
            self.pattern_labels_to_keys.get(
                selected_label
            )
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

    def update_progress_from_message(
        self,
        message: str,
    ) -> None:
        """Aktualisiert Status und Fortschritt anhand der Programmmeldung."""
        self.status.config(
            text=message,
            fg=MUTED_TEXT_COLOR,
        )

        match = re.match(
            r"^\s*([1-6])/6",
            message,
        )

        if match:
            progress_value = int(
                match.group(1)
            )

            self.progress.config(
                value=progress_value
            )

        self.root.update_idletasks()

    def thread_safe_status(
        self,
        message: str,
    ) -> None:
        """Leitet Statusmeldungen sicher an den GUI-Thread weiter."""
        self.root.after(
            0,
            self.update_progress_from_message,
            message,
        )

    def set_running_state(
        self,
        running: bool,
    ) -> None:
        """Aktiviert oder deaktiviert Eingabeelemente."""
        widget_state = (
            "disabled"
            if running
            else "normal"
        )

        for widget in self.interactive_widgets:
            try:
                if (
                    widget
                    is self.custom_pattern_entry
                    and not running
                    and self.room_pattern_var.get()
                    != CUSTOM_PATTERN_LABEL
                ):
                    widget.config(
                        state="disabled"
                    )

                elif (
                    widget
                    is self.pattern_combobox
                ):
                    widget.config(
                        state=(
                            "disabled"
                            if running
                            else "readonly"
                        )
                    )

                else:
                    widget.config(
                        state=widget_state
                    )

            except tk.TclError:
                pass

        self.start_button.config(
            state=(
                "disabled"
                if running
                else "normal"
            ),
            text=(
                "Vergleich läuft …"
                if running
                else "Vergleich starten"
            ),
        )

    def validate_inputs(self) -> None:
        """Prüft die Eingaben vor dem Start."""
        if not self.floorplan_pdfs:
            raise ValueError(
                "Bitte mindestens einen "
                "Grundriss auswählen."
            )

        if not self.schema_pdfs:
            raise ValueError(
                "Bitte mindestens ein "
                "Prinzipschema auswählen."
            )

        if self.output_dir is None:
            raise ValueError(
                "Bitte einen Ausgabeordner "
                "auswählen."
            )

    def start(self) -> None:
        """Validiert die Eingaben und startet den Vergleich."""
        try:
            self.validate_inputs()

            (
                room_pattern_key,
                custom_room_pattern,
            ) = self.get_selected_room_pattern()

        except Exception as error:
            messagebox.showerror(
                "Eingabe prüfen",
                str(error),
            )

            return

        self.progress.config(
            value=0
        )

        self.status.config(
            text="Vergleich wird vorbereitet …",
            fg=MUTED_TEXT_COLOR,
        )

        self.set_running_state(
            True
        )

        worker = threading.Thread(
            target=self.run_comparison_worker,
            args=(
                room_pattern_key,
                custom_room_pattern,
            ),
            daemon=True,
        )

        worker.start()

    def run_comparison_worker(
        self,
        room_pattern_key: str,
        custom_room_pattern: str | None,
    ) -> None:
        """Führt die zeitintensive Verarbeitung im Hintergrund aus."""
        try:
            results = run_comparison(
                floorplan_pdfs=self.floorplan_pdfs,
                schema_pdfs=self.schema_pdfs,
                output_dir=self.output_dir,
                status_callback=self.thread_safe_status,
                room_pattern_key=room_pattern_key,
                custom_room_pattern=custom_room_pattern,
            )

            self.root.after(
                0,
                self.handle_success,
                results,
            )

        except Exception as error:
            self.root.after(
                0,
                self.handle_error,
                error,
            )

    def handle_success(
        self,
        results: dict[
            str,
            object,
        ],
    ) -> None:
        """Behandelt einen erfolgreichen Programmabschluss."""
        self.progress.config(
            value=6
        )

        self.status.config(
            text=(
                "Vergleich erfolgreich abgeschlossen."
            ),
            fg=SUCCESS_COLOR,
        )

        self.set_running_state(
            False
        )

        output_pdfs = results.get(
            "output_pdfs",
            [],
        )

        output_excel = results.get(
            "output_excel",
            "",
        )

        pdf_count = (
            len(output_pdfs)
            if isinstance(
                output_pdfs,
                list,
            )
            else 0
        )

        messagebox.showinfo(
            "Vergleich abgeschlossen",
            (
                "Der Luftmengenvergleich wurde "
                "erfolgreich abgeschlossen.\n\n"
                f"Markierte PDFs: {pdf_count}\n"
                f"Excel-Auswertung:\n{output_excel}"
            ),
        )

    def handle_error(
        self,
        error: Exception,
    ) -> None:
        """Behandelt einen Fehler aus dem Hintergrundprozess."""
        self.status.config(
            text=(
                "Bei der Verarbeitung ist "
                "ein Fehler aufgetreten."
            ),
            fg=ERROR_COLOR,
        )

        self.set_running_state(
            False
        )

        messagebox.showerror(
            "Fehler",
            str(error),
        )

    def run(self) -> None:
        self.root.mainloop()


def start_gui() -> None:
    app = LuftmengenGUI()
    app.run()
