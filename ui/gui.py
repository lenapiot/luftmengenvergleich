from __future__ import annotations
import traceback

import getpass
import inspect
import re
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from config.settings import (
    DEFAULT_ROOM_PATTERN_KEY,
    ROOM_PATTERN_PRESETS,
)
from hk.nummernkontrolle import run_hk_number_check
from hk.lastvergleich import (
    compare_loads_with_schema,
    determine_document_building,
    extract_and_consolidate_schema,
    extract_loads_from_excel_checked,
    extract_loads_from_excels_checked,
    extract_loads_from_pdfs_checked,
)
from hk.lastvergleich_excel import export_load_comparison_excel
from luft.nummernkontrolle import run_luft_number_check
from luftmengen_vergleich import run_comparison


CUSTOM_PATTERN_LABEL = "Benutzerdefiniertes Muster"

APP_VERSION = "1.3"

BACKGROUND_COLOR = "#F3F6F8"
CARD_COLOR = "#FFFFFF"
PRIMARY_COLOR = "#079ED1"
PRIMARY_HOVER_COLOR = "#087FA8"
TEXT_COLOR = "#17212B"
MUTED_TEXT_COLOR = "#66727C"
BORDER_COLOR = "#D7E0E5"
SUCCESS_COLOR = "#238636"
ERROR_COLOR = "#C62828"
WARNING_COLOR = "#A15C00"

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
            f"Planvergleich – Version {APP_VERSION}"
        )

        # Etwas grösser als bisher, aber bewusst NICHT maximiert.
        # So bleibt das Programm ein normales Fenster und der Startbutton
        # des Lastvergleichs ist trotzdem direkt sichtbar.
        self.root.geometry("1280x1150")
        self.root.minsize(1050, 760)

        self.root.configure(
            bg=BACKGROUND_COLOR
        )

        self.active_module = tk.StringVar(
            value="lueftung"
        )

        # Lüftung
        self.floorplan_pdfs: list[Path] = []
        self.schema_pdfs: list[Path] = []
        self.output_dir: Path | None = None

        # Lüftung Schemanummernkontrolle
        self.luft_num_pairs: list[dict[str, str]] = []
        self.luft_num_output_dir: Path | None = None

        # HK Nummernkontrolle
        self.hk_pairs: list[dict[str, str]] = []
        self.hk_output_dir: Path | None = None

        # HK Lastvergleich
        self.hk_load_schema_pdfs: list[Path] = []
        self.hk_load_source_type = tk.StringVar(value="pdf")
        self.hk_load_scope = tk.StringVar(value="beides")
        self.hk_load_excel_paths: list[Path] = []
        self.hk_heating_pdfs: list[Path] = []
        self.hk_cooling_pdfs: list[Path] = []
        self.hk_load_output_dir: Path | None = None

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

        self.lueftung_widgets: list[tk.Widget] = []
        self.luft_num_widgets: list[tk.Widget] = []
        self.hk_widgets: list[tk.Widget] = []
        self.hk_load_widgets: list[tk.Widget] = []

        self.configure_styles()
        self.create_widgets()
        self.show_lueftung_module()
        self.update_pattern_description()

    # ========================================================
    # STYLE / GRUNDLAYOUT
    # ========================================================

    def configure_styles(self) -> None:
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
        self.create_header()

        self.content = tk.Frame(
            self.root,
            bg=BACKGROUND_COLOR,
        )

        self.content.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=(18, 10),
        )

        self.create_module_selector(
            self.content
        )

        self.module_area = tk.Frame(
            self.content,
            bg=BACKGROUND_COLOR,
        )

        self.module_area.pack(
            fill="both",
            expand=True,
        )

        self.create_lueftung_area()
        self.create_luft_num_area()
        self.create_hk_area()
        self.create_hk_load_area()

        self.create_footer()

    def create_header(self) -> None:
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
            text="Planvergleich",
            font=("Segoe UI", 23, "bold"),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="e",
        ).pack(
            fill="x"
        )

        tk.Label(
            title_frame,
            text=(
                "Lüftung · Heizung/Kälte · "
                "automatische Schema- und Listenprüfung"
            ),
            font=("Segoe UI", 10),
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

                self.logo_image = ImageTk.PhotoImage(
                    logo
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
        tk.Label(
            parent,
            text="eicher+pauli",
            font=("Segoe UI", 22, "bold"),
            fg=PRIMARY_COLOR,
            bg=CARD_COLOR,
        ).pack(
            anchor="w"
        )

        tk.Label(
            parent,
            text="Energie und Planung",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
        ).pack(
            anchor="w"
        )

    def create_module_selector(
        self,
        parent: tk.Widget,
    ) -> None:
        selector = tk.Frame(
            parent,
            bg=BACKGROUND_COLOR,
        )

        selector.pack(
            fill="x",
            pady=(0, 12),
        )

        self.lueftung_button = self.create_module_button(
            selector,
            "Lüftung – Luftmengenvergleich",
            self.show_lueftung_module,
        )

        self.lueftung_button.pack(
            side="left",
            padx=(0, 10),
        )

        self.luft_num_button = self.create_module_button(
            selector,
            "Lüftung – Schemanummernkontrolle",
            self.show_luft_num_module,
        )

        self.luft_num_button.pack(
            side="left",
            padx=(0, 10),
        )

        self.hk_button = self.create_module_button(
            selector,
            "Heizung/Kälte – Nummernkontrolle",
            self.show_hk_module,
        )

        self.hk_button.pack(
            side="left",
            padx=(0, 10),
        )

        self.hk_load_button = self.create_module_button(
            selector,
            "Heizung/Kälte – Lastvergleich",
            self.show_hk_load_module,
        )

        self.hk_load_button.pack(
            side="left",
        )

    def create_module_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_COLOR,
            bg="#E8EEF1",
            activeforeground=TEXT_COLOR,
            activebackground="#D9E3E8",
            relief="flat",
            cursor="hand2",
            command=command,
            padx=12,
            pady=10,
        )

    def set_module_button_states(
        self,
        active: str,
    ) -> None:
        buttons = {
            "lueftung": self.lueftung_button,
            "luft_num": self.luft_num_button,
            "hk": self.hk_button,
            "hk_load": self.hk_load_button,
        }

        for key, button in buttons.items():
            if key == active:
                button.config(
                    fg="white",
                    bg=PRIMARY_COLOR,
                )
            else:
                button.config(
                    fg=TEXT_COLOR,
                    bg="#E8EEF1",
                )

    def create_card(
        self,
        parent: tk.Widget,
        title: str,
    ) -> tk.Frame:
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
            font=("Segoe UI", 11, "bold"),
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

    # ========================================================
    # MODULWECHSEL
    # ========================================================

    def show_lueftung_module(self) -> None:
        self.active_module.set(
            "lueftung"
        )

        self.luft_num_frame.pack_forget()
        self.hk_frame.pack_forget()
        self.hk_load_frame.pack_forget()

        self.lueftung_frame.pack(
            fill="both",
            expand=True,
        )

        self.set_module_button_states(
            "lueftung"
        )

    def show_luft_num_module(self) -> None:
        self.active_module.set(
            "luft_num"
        )

        self.lueftung_frame.pack_forget()
        self.hk_frame.pack_forget()
        self.hk_load_frame.pack_forget()

        self.luft_num_frame.pack(
            fill="both",
            expand=True,
        )

        self.set_module_button_states(
            "luft_num"
        )

    def show_hk_module(self) -> None:
        self.active_module.set(
            "hk"
        )

        self.lueftung_frame.pack_forget()
        self.luft_num_frame.pack_forget()
        self.hk_load_frame.pack_forget()

        self.hk_frame.pack(
            fill="both",
            expand=True,
        )

        self.set_module_button_states(
            "hk"
        )

    def show_hk_load_module(self) -> None:
        self.active_module.set(
            "hk_load"
        )

        self.lueftung_frame.pack_forget()
        self.luft_num_frame.pack_forget()
        self.hk_frame.pack_forget()

        self.hk_load_frame.pack(
            fill="both",
            expand=True,
        )

        self.set_module_button_states(
            "hk_load"
        )

    # ========================================================
    # LÜFTUNG – GUI
    # ========================================================

    def create_lueftung_area(self) -> None:
        self.lueftung_frame = tk.Frame(
            self.module_area,
            bg=BACKGROUND_COLOR,
        )

        self.create_lueftung_files_card(
            self.lueftung_frame
        )
        self.create_lueftung_pattern_card(
            self.lueftung_frame
        )
        self.create_lueftung_output_card(
            self.lueftung_frame
        )
        self.create_lueftung_action_area(
            self.lueftung_frame
        )

    def create_file_selection_row(
        self,
        frame: tk.Frame,
        row: int,
        title: str,
        add_command,
        clear_command,
        widget_list: list[tk.Widget],
    ) -> None:
        tk.Label(
            frame,
            text=f"{title}:",
            font=("Segoe UI", 10, "bold"),
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

        widget_list.extend(
            [
                add_button,
                clear_button,
            ]
        )

    def create_lueftung_files_card(
        self,
        parent: tk.Widget,
    ) -> None:
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
            widget_list=self.lueftung_widgets,
        )

        self.floorplan_label = tk.Label(
            frame,
            text="Keine Grundrisse ausgewählt",
            font=("Segoe UI", 9),
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
            widget_list=self.lueftung_widgets,
        )

        self.schema_label = tk.Label(
            frame,
            text="Keine Prinzipschemata ausgewählt",
            font=("Segoe UI", 9),
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

    def create_lueftung_pattern_card(
        self,
        parent: tk.Widget,
    ) -> None:
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
            font=("Segoe UI", 10, "bold"),
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

        self.lueftung_widgets.append(
            self.pattern_combobox
        )

        self.pattern_description_label = tk.Label(
            frame,
            text="",
            font=("Segoe UI", 9),
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
            font=("Segoe UI", 10, "bold"),
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
            font=("Consolas", 10),
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

        self.lueftung_widgets.append(
            self.custom_pattern_entry
        )

        self.custom_help_label = tk.Label(
            frame,
            text=(
                "USZ-Standard erkennt auch Nominal und Havarie. "
                "Mehrere Luftmengenblöcke derselben Raumnummer "
                "werden als «Mehrfach / uneindeutig» markiert."
            ),
            font=("Segoe UI", 9),
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

    def create_lueftung_output_card(
        self,
        parent: tk.Widget,
    ) -> None:
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

        self.lueftung_widgets.append(
            output_button
        )

        self.output_label = tk.Label(
            frame,
            text="Kein Ausgabeordner ausgewählt",
            font=("Segoe UI", 9),
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

    def create_lueftung_action_area(
        self,
        parent: tk.Widget,
    ) -> None:
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
            text="Luftmengenvergleich starten",
            font=("Segoe UI", 12, "bold"),
            fg="white",
            bg=PRIMARY_COLOR,
            activeforeground="white",
            activebackground=PRIMARY_HOVER_COLOR,
            relief="flat",
            cursor="hand2",
            command=self.start_lueftung,
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
            font=("Segoe UI", 10),
            fg=MUTED_TEXT_COLOR,
            bg=BACKGROUND_COLOR,
            wraplength=760,
        )

        self.status.pack()

    # ========================================================
    # LÜFTUNG SCHEMANUMMERNKONTROLLE – GUI
    # ========================================================

    def create_luft_num_area(self) -> None:
        self.luft_num_frame = tk.Frame(
            self.module_area,
            bg=BACKGROUND_COLOR,
        )

        self.create_luft_num_info_card(
            self.luft_num_frame
        )
        self.create_luft_num_pairs_card(
            self.luft_num_frame
        )
        self.create_luft_num_output_card(
            self.luft_num_frame
        )
        self.create_luft_num_action_area(
            self.luft_num_frame
        )

    def create_luft_num_info_card(
        self,
        parent: tk.Widget,
    ) -> None:
        frame = self.create_card(
            parent,
            "Lüftung – Schemanummernkontrolle Schema/BML",
        )

        tk.Label(
            frame,
            text=(
                "Dieses Modul vergleicht die hellblauen und dunkelblauen "
                "Lüftungs-Schemanummern (z. B. L1 1.12 oder L13 4.10) "
                "aus einem Prinzipschema mit der Spalte «ep_Schemanummer» "
                "aus der dazugehörigen Betriebsmittelliste."
            ),
            font=("Segoe UI", 10),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            justify="left",
            wraplength=900,
            anchor="w",
        ).pack(
            fill="x"
        )

    def create_luft_num_pairs_card(
        self,
        parent: tk.Widget,
    ) -> None:
        frame = self.create_card(
            parent,
            "1. Schema/BML-Paare auswählen",
        )

        button_frame = tk.Frame(
            frame,
            bg=CARD_COLOR,
        )

        button_frame.pack(
            fill="x",
        )

        add_button = self.create_secondary_button(
            button_frame,
            "Paar hinzufügen",
            self.add_luft_num_pair,
        )

        add_button.pack(
            side="left",
            padx=(0, 8),
        )

        clear_button = self.create_light_button(
            button_frame,
            "Paarliste leeren",
            self.clear_luft_num_pairs,
        )

        clear_button.pack(
            side="left",
        )

        self.luft_num_widgets.extend(
            [
                add_button,
                clear_button,
            ]
        )

        self.luft_num_pairs_label = tk.Label(
            frame,
            text="Keine Paare ausgewählt",
            font=("Segoe UI", 9),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            justify="left",
            anchor="w",
            wraplength=900,
        )

        self.luft_num_pairs_label.pack(
            fill="x",
            pady=(12, 0),
        )

    def create_luft_num_output_card(
        self,
        parent: tk.Widget,
    ) -> None:
        frame = self.create_card(
            parent,
            "2. Ausgabe",
        )

        frame.columnconfigure(
            1,
            weight=1,
        )

        output_button = self.create_secondary_button(
            frame,
            "Ausgabeordner auswählen",
            self.choose_luft_num_output,
        )

        output_button.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 15),
            pady=4,
        )

        self.luft_num_widgets.append(
            output_button
        )

        self.luft_num_output_label = tk.Label(
            frame,
            text="Kein Ausgabeordner ausgewählt",
            font=("Segoe UI", 9),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
            justify="left",
            wraplength=650,
        )

        self.luft_num_output_label.grid(
            row=0,
            column=1,
            sticky="w",
        )

    def create_luft_num_action_area(
        self,
        parent: tk.Widget,
    ) -> None:
        action_frame = tk.Frame(
            parent,
            bg=BACKGROUND_COLOR,
        )

        action_frame.pack(
            fill="x",
            pady=(15, 5),
        )

        self.luft_num_start_button = tk.Button(
            action_frame,
            text="Lüftungs-Schemanummernkontrolle starten",
            font=("Segoe UI", 12, "bold"),
            fg="white",
            bg=PRIMARY_COLOR,
            activeforeground="white",
            activebackground=PRIMARY_HOVER_COLOR,
            relief="flat",
            cursor="hand2",
            command=self.start_luft_num,
            padx=35,
            pady=12,
        )

        self.luft_num_start_button.pack()

        self.luft_num_progress = ttk.Progressbar(
            action_frame,
            orient="horizontal",
            mode="determinate",
            maximum=1,
            value=0,
            length=600,
            style="Comparison.Horizontal.TProgressbar",
        )

        self.luft_num_progress.pack(
            pady=(18, 8)
        )

        self.luft_num_status = tk.Label(
            action_frame,
            text="Bereit",
            font=("Segoe UI", 10),
            fg=MUTED_TEXT_COLOR,
            bg=BACKGROUND_COLOR,
            wraplength=760,
        )

        self.luft_num_status.pack()

    # ========================================================
    # HK NUMMERNKONTROLLE – GUI
    # ========================================================

    def create_hk_area(self) -> None:
        self.hk_frame = tk.Frame(
            self.module_area,
            bg=BACKGROUND_COLOR,
        )

        self.create_hk_info_card(
            self.hk_frame
        )
        self.create_hk_pairs_card(
            self.hk_frame
        )
        self.create_hk_output_card(
            self.hk_frame
        )
        self.create_hk_action_area(
            self.hk_frame
        )

    def create_hk_info_card(
        self,
        parent: tk.Widget,
    ) -> None:
        frame = self.create_card(
            parent,
            "Heizung/Kälte – Nummernkontrolle Schema/BML",
        )

        tk.Label(
            frame,
            text=(
                "Dieses Modul vergleicht die blauen Positionsnummern "
                "aus einem Prinzipschema mit der Spalte «Pos. Nr.» "
                "aus der dazugehörigen Betriebsmittelliste."
            ),
            font=("Segoe UI", 10),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            justify="left",
            wraplength=820,
            anchor="w",
        ).pack(
            fill="x"
        )

    def create_hk_pairs_card(
        self,
        parent: tk.Widget,
    ) -> None:
        frame = self.create_card(
            parent,
            "1. Schema/BML-Paare auswählen",
        )

        button_frame = tk.Frame(
            frame,
            bg=CARD_COLOR,
        )

        button_frame.pack(
            fill="x",
        )

        add_button = self.create_secondary_button(
            button_frame,
            "Paar hinzufügen",
            self.add_hk_pair,
        )

        add_button.pack(
            side="left",
            padx=(0, 8),
        )

        clear_button = self.create_light_button(
            button_frame,
            "Paarliste leeren",
            self.clear_hk_pairs,
        )

        clear_button.pack(
            side="left",
        )

        self.hk_widgets.extend(
            [
                add_button,
                clear_button,
            ]
        )

        self.hk_pairs_label = tk.Label(
            frame,
            text="Keine Paare ausgewählt",
            font=("Segoe UI", 9),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            justify="left",
            anchor="w",
            wraplength=820,
        )

        self.hk_pairs_label.pack(
            fill="x",
            pady=(12, 0),
        )

    def create_hk_output_card(
        self,
        parent: tk.Widget,
    ) -> None:
        frame = self.create_card(
            parent,
            "2. Ausgabe",
        )

        frame.columnconfigure(
            1,
            weight=1,
        )

        output_button = self.create_secondary_button(
            frame,
            "Ausgabeordner auswählen",
            self.choose_hk_output,
        )

        output_button.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 15),
            pady=4,
        )

        self.hk_widgets.append(
            output_button
        )

        self.hk_output_label = tk.Label(
            frame,
            text="Kein Ausgabeordner ausgewählt",
            font=("Segoe UI", 9),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
            justify="left",
            wraplength=600,
        )

        self.hk_output_label.grid(
            row=0,
            column=1,
            sticky="w",
        )

    def create_hk_action_area(
        self,
        parent: tk.Widget,
    ) -> None:
        action_frame = tk.Frame(
            parent,
            bg=BACKGROUND_COLOR,
        )

        action_frame.pack(
            fill="x",
            pady=(15, 5),
        )

        self.hk_start_button = tk.Button(
            action_frame,
            text="HK-Nummernkontrolle starten",
            font=("Segoe UI", 12, "bold"),
            fg="white",
            bg=PRIMARY_COLOR,
            activeforeground="white",
            activebackground=PRIMARY_HOVER_COLOR,
            relief="flat",
            cursor="hand2",
            command=self.start_hk,
            padx=35,
            pady=12,
        )

        self.hk_start_button.pack()

        self.hk_progress = ttk.Progressbar(
            action_frame,
            orient="horizontal",
            mode="determinate",
            maximum=1,
            value=0,
            length=600,
            style="Comparison.Horizontal.TProgressbar",
        )

        self.hk_progress.pack(
            pady=(18, 8)
        )

        self.hk_status = tk.Label(
            action_frame,
            text="Bereit",
            font=("Segoe UI", 10),
            fg=MUTED_TEXT_COLOR,
            bg=BACKGROUND_COLOR,
            wraplength=760,
        )

        self.hk_status.pack()

    # ========================================================
    # HK LASTVERGLEICH – GUI
    # ========================================================

    def create_hk_load_area(self) -> None:
        self.hk_load_frame = tk.Frame(
            self.module_area,
            bg=BACKGROUND_COLOR,
        )

        self.create_hk_load_info_card(
            self.hk_load_frame
        )
        self.create_hk_load_files_card(
            self.hk_load_frame
        )
        self.create_hk_load_output_card(
            self.hk_load_frame
        )
        self.create_hk_load_action_area(
            self.hk_load_frame
        )


    def create_hk_load_info_card(
        self,
        parent: tk.Widget,
    ) -> None:
        frame = self.create_card(
            parent,
            "Heizung/Kälte – Lastvergleich",
        )

        tk.Label(
            frame,
            text=(
                "Ein oder mehrere Strangschemata werden jeweils einzeln mit den "
                "vorhandenen Heiz- und/oder Kühllasten verglichen. Als Lastquelle "
                "können PDF-Grundrisse oder eine gemeinsame Excel-Datei verwendet werden."
            ),
            font=("Segoe UI", 10),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
            justify="left",
            wraplength=900,
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            frame,
            text=(
                "Gebäudelogik: MIT1-Schemata werden nur mit MIT1-Räumen verglichen, "
                "MIT2-Schemata nur mit MIT2-Räumen. Ein echtes MIT12-Schema verwendet "
                "MIT1 und MIT2. Räume werden nicht aufgrund ihrer Ebene ausgeschlossen."
            ),
            font=("Segoe UI", 9, "bold"),
            fg=WARNING_COLOR,
            bg="#FFF8E1",
            justify="left",
            wraplength=900,
            anchor="w",
            padx=12,
            pady=10,
        ).pack(fill="x", pady=(12, 0))

        tk.Label(
            frame,
            text=(
                "PDF-Sonderregel: Heizlast -1 W = 0 W + geprüft; "
                "Kühllast +1 W = 0 W + geprüft. Bei Excel ist 0 W ein echter 0-W-Wert."
            ),
            font=("Segoe UI", 9),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            justify="left",
            wraplength=900,
            anchor="w",
        ).pack(fill="x", pady=(10, 0))



    def create_hk_load_files_card(
        self,
        parent: tk.Widget,
    ) -> None:
        frame = self.create_card(
            parent,
            "1. Dateien und Prüfumfang",
        )

        frame.columnconfigure(1, weight=1)

        # ----------------------------------------------------
        # STRANGSCHEMATA
        # ----------------------------------------------------
        tk.Label(
            frame,
            text="Strangschemata:",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
            width=20,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=4)

        schema_folder = self.create_secondary_button(
            frame,
            "Ordner hinzufügen (empfohlen)",
            self.choose_hk_load_schema_folder,
        )
        schema_folder.grid(
            row=0, column=1, sticky="w",
            padx=(12, 8), pady=4
        )

        schema_files = self.create_light_button(
            frame,
            "Einzelne PDFs hinzufügen",
            self.choose_hk_load_schemas,
        )
        schema_files.grid(
            row=0, column=2, sticky="w",
            padx=(0, 8), pady=4
        )

        schema_clear = self.create_light_button(
            frame,
            "Auswahl leeren",
            self.clear_hk_load_schema,
        )
        schema_clear.grid(
            row=0, column=3, sticky="w", pady=4
        )

        self.hk_load_widgets.extend(
            [schema_folder, schema_files, schema_clear]
        )

        self.hk_load_schema_label = tk.Label(
            frame,
            text="Keine Strangschemata ausgewählt",
            font=("Segoe UI", 9),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
            justify="left",
            wraplength=720,
        )
        self.hk_load_schema_label.grid(
            row=1, column=1, columnspan=3,
            sticky="w", padx=(12, 0), pady=(0, 6)
        )

        # ----------------------------------------------------
        # LASTQUELLE + PRÜFUMFANG
        # ----------------------------------------------------
        tk.Label(
            frame,
            text="Lastquelle:",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
            width=20,
            anchor="w",
        ).grid(row=2, column=0, sticky="w", pady=4)

        source_frame = tk.Frame(frame, bg=CARD_COLOR)
        source_frame.grid(
            row=2, column=1, columnspan=3,
            sticky="w", padx=(12, 0), pady=4
        )

        self.hk_source_pdf_radio = tk.Radiobutton(
            source_frame,
            text="PDF-Grundrisse",
            variable=self.hk_load_source_type,
            value="pdf",
            command=self.update_hk_load_source_controls,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=("Segoe UI", 9),
        )
        self.hk_source_pdf_radio.pack(
            side="left", padx=(0, 18)
        )

        self.hk_source_excel_radio = tk.Radiobutton(
            source_frame,
            text="Excel",
            variable=self.hk_load_source_type,
            value="excel",
            command=self.update_hk_load_source_controls,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=("Segoe UI", 9),
        )
        self.hk_source_excel_radio.pack(side="left")

        self.hk_load_widgets.extend(
            [self.hk_source_pdf_radio, self.hk_source_excel_radio]
        )

        tk.Label(
            frame,
            text="Prüfumfang:",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
            width=20,
            anchor="w",
        ).grid(row=3, column=0, sticky="w", pady=4)

        scope_frame = tk.Frame(frame, bg=CARD_COLOR)
        scope_frame.grid(
            row=3, column=1, columnspan=3,
            sticky="w", padx=(12, 0), pady=4
        )

        self.hk_scope_radios = []
        for label, value in (
            ("Heiz- und Kühllast", "beides"),
            ("Nur Heizlast", "heizung"),
            ("Nur Kühllast", "kuehlung"),
        ):
            radio = tk.Radiobutton(
                scope_frame,
                text=label,
                variable=self.hk_load_scope,
                value=value,
                command=self.update_hk_load_source_controls,
                bg=CARD_COLOR,
                fg=TEXT_COLOR,
                activebackground=CARD_COLOR,
                font=("Segoe UI", 9),
            )
            radio.pack(
                side="left", padx=(0, 18)
            )
            self.hk_scope_radios.append(radio)
            self.hk_load_widgets.append(radio)

        # ----------------------------------------------------
        # EXCEL-BEREICH
        # Nur sichtbar, wenn Excel gewählt ist.
        # ----------------------------------------------------
        self.hk_excel_source_frame = tk.Frame(
            frame,
            bg=CARD_COLOR,
        )
        self.hk_excel_source_frame.grid(
            row=4,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=(3, 0),
        )
        self.hk_excel_source_frame.columnconfigure(
            1,
            weight=1,
        )

        tk.Label(
            self.hk_excel_source_frame,
            text="Excel-Dateien:",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
            width=20,
            anchor="w",
        ).grid(
            row=0, column=0,
            sticky="w", pady=4
        )

        self.hk_excel_button = self.create_secondary_button(
            self.hk_excel_source_frame,
            "Excel-Dateien hinzufügen",
            self.choose_hk_load_excel,
        )
        self.hk_excel_button.grid(
            row=0, column=1,
            sticky="w", padx=(12, 8), pady=4
        )

        self.hk_excel_folder_button = self.create_light_button(
            self.hk_excel_source_frame,
            "Ordner hinzufügen",
            self.choose_hk_load_excel_folder,
        )
        self.hk_excel_folder_button.grid(
            row=0, column=2,
            sticky="w", padx=(0, 8), pady=4
        )

        self.hk_excel_clear_button = self.create_light_button(
            self.hk_excel_source_frame,
            "Auswahl leeren",
            self.clear_hk_load_excel,
        )
        self.hk_excel_clear_button.grid(
            row=0, column=3,
            sticky="w", pady=4
        )

        self.hk_load_widgets.extend(
            [
                self.hk_excel_button,
                self.hk_excel_folder_button,
                self.hk_excel_clear_button,
            ]
        )

        self.hk_excel_label = tk.Label(
            self.hk_excel_source_frame,
            text="Keine Excel-Dateien ausgewählt",
            font=("Segoe UI", 9),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
            justify="left",
            wraplength=720,
        )
        self.hk_excel_label.grid(
            row=1, column=1, columnspan=3,
            sticky="w", padx=(12, 0), pady=(0, 4)
        )

        # ----------------------------------------------------
        # PDF-BEREICH
        # Nur sichtbar, wenn PDF gewählt ist.
        # ----------------------------------------------------
        self.hk_pdf_source_frame = tk.Frame(
            frame,
            bg=CARD_COLOR,
        )
        self.hk_pdf_source_frame.grid(
            row=4,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=(3, 0),
        )
        self.hk_pdf_source_frame.columnconfigure(
            1,
            weight=1,
        )

        self.create_hk_load_multirow(
            frame=self.hk_pdf_source_frame,
            row=0,
            title="Heizlast-Grundrisse",
            add_files_command=self.choose_hk_heating_pdfs,
            add_folder_command=self.choose_hk_heating_folder,
            clear_command=self.clear_hk_heating_pdfs,
        )

        self.hk_heating_label = tk.Label(
            self.hk_pdf_source_frame,
            text="Keine Heizlast-Grundrisse ausgewählt",
            font=("Segoe UI", 9),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
            justify="left",
            wraplength=720,
        )
        self.hk_heating_label.grid(
            row=1, column=1, columnspan=3,
            sticky="w", padx=(12, 0), pady=(0, 5)
        )

        self.create_hk_load_multirow(
            frame=self.hk_pdf_source_frame,
            row=2,
            title="Kühllast-Grundrisse",
            add_files_command=self.choose_hk_cooling_pdfs,
            add_folder_command=self.choose_hk_cooling_folder,
            clear_command=self.clear_hk_cooling_pdfs,
        )

        self.hk_cooling_label = tk.Label(
            self.hk_pdf_source_frame,
            text="Keine Kühllast-Grundrisse ausgewählt",
            font=("Segoe UI", 9),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
            justify="left",
            wraplength=720,
        )
        self.hk_cooling_label.grid(
            row=3, column=1, columnspan=3,
            sticky="w", padx=(12, 0), pady=(0, 3)
        )

        self.hk_pdf_hint_label = tk.Label(
            self.hk_pdf_source_frame,
            text=(
                "Empfohlen: Ordner hinzufügen. So wird die "
                "Windows/Adobe-PDF-Vorschau bei vielen Dateien umgangen."
            ),
            font=("Segoe UI", 8),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            justify="left",
            wraplength=850,
            anchor="w",
        )
        self.hk_pdf_hint_label.grid(
            row=4, column=0, columnspan=4,
            sticky="w", pady=(7, 0)
        )

        self.update_hk_load_source_controls()

    def create_hk_load_multirow(
        self,
        frame: tk.Frame,
        row: int,
        title: str,
        add_files_command,
        add_folder_command,
        clear_command,
    ) -> None:
        tk.Label(
            frame,
            text=f"{title}:",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_COLOR,
            bg=CARD_COLOR,
            width=20,
            anchor="w",
        ).grid(
            row=row,
            column=0,
            sticky="w",
            pady=5,
        )

        add_folder = self.create_secondary_button(
            frame,
            "Ordner hinzufügen (empfohlen)",
            add_folder_command,
        )

        add_folder.grid(
            row=row,
            column=1,
            sticky="w",
            padx=(12, 8),
            pady=5,
        )

        add_files = self.create_light_button(
            frame,
            "Einzelne PDFs hinzufügen",
            add_files_command,
        )

        add_files.grid(
            row=row,
            column=2,
            sticky="w",
            padx=(0, 8),
            pady=5,
        )

        clear_button = self.create_light_button(
            frame,
            "Auswahl leeren",
            clear_command,
        )

        clear_button.grid(
            row=row,
            column=3,
            sticky="w",
            pady=5,
        )

        self.hk_load_widgets.extend(
            [
                add_folder,
                add_files,
                clear_button,
            ]
        )

        if not hasattr(self, "hk_pdf_control_groups"):
            self.hk_pdf_control_groups = {}

        self.hk_pdf_control_groups[title] = [
            add_folder,
            add_files,
            clear_button,
        ]

    def create_hk_load_output_card(
        self,
        parent: tk.Widget,
    ) -> None:
        frame = self.create_card(
            parent,
            "2. Excel-Ausgabe",
        )

        frame.columnconfigure(
            1,
            weight=1,
        )

        output_button = self.create_secondary_button(
            frame,
            "Ausgabeordner auswählen",
            self.choose_hk_load_output,
        )

        output_button.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 15),
            pady=4,
        )

        self.hk_load_widgets.append(
            output_button
        )

        self.hk_load_output_label = tk.Label(
            frame,
            text="Kein Ausgabeordner ausgewählt",
            font=("Segoe UI", 9),
            fg=MUTED_TEXT_COLOR,
            bg=CARD_COLOR,
            anchor="w",
            justify="left",
            wraplength=650,
        )

        self.hk_load_output_label.grid(
            row=0,
            column=1,
            sticky="w",
        )

    def create_hk_load_action_area(
        self,
        parent: tk.Widget,
    ) -> None:
        action_frame = tk.Frame(
            parent,
            bg=BACKGROUND_COLOR,
        )

        action_frame.pack(
            fill="x",
            pady=(15, 5),
        )

        self.hk_load_start_button = tk.Button(
            action_frame,
            text="Lastvergleich starten",
            font=("Segoe UI", 12, "bold"),
            fg="white",
            bg=PRIMARY_COLOR,
            activeforeground="white",
            activebackground=PRIMARY_HOVER_COLOR,
            relief="flat",
            cursor="hand2",
            command=self.start_hk_load,
            padx=35,
            pady=12,
        )

        self.hk_load_start_button.pack()

        self.hk_load_progress = ttk.Progressbar(
            action_frame,
            orient="horizontal",
            mode="determinate",
            maximum=5,
            value=0,
            length=600,
            style="Comparison.Horizontal.TProgressbar",
        )

        self.hk_load_progress.pack(
            pady=(18, 8)
        )

        self.hk_load_status = tk.Label(
            action_frame,
            text="Bereit",
            font=("Segoe UI", 10),
            fg=MUTED_TEXT_COLOR,
            bg=BACKGROUND_COLOR,
            wraplength=900,
        )

        self.hk_load_status.pack()

    # ========================================================
    # ALLGEMEINE BUTTONS / FOOTER
    # ========================================================

    def create_footer(self) -> None:
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
            font=("Segoe UI", 9),
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
                f"Planvergleich v{APP_VERSION}"
            ),
            font=("Segoe UI", 9),
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
        return tk.Button(
            parent,
            text=text,
            font=("Segoe UI", 9, "bold"),
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
        return tk.Button(
            parent,
            text=text,
            font=("Segoe UI", 9),
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

    # ========================================================
    # LÜFTUNG – LOGIK
    # ========================================================

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
            text = "Keine Grundrisse ausgewählt"
        elif count == 1:
            text = (
                f"1 Grundriss ausgewählt: "
                f"{self.floorplan_pdfs[0].name}"
            )
        else:
            text = f"{count} Grundrisse ausgewählt"

        self.floorplan_label.config(
            text=text
        )

    def update_schema_label(self) -> None:
        count = len(
            self.schema_pdfs
        )

        if count == 0:
            text = "Keine Prinzipschemata ausgewählt"
        elif count == 1:
            text = (
                f"1 Prinzipschema ausgewählt: "
                f"{self.schema_pdfs[0].name}"
            )
        else:
            text = f"{count} Prinzipschemata ausgewählt"

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

        dialog_arguments: dict[str, object] = {
            "title": "Ausgabeordner auswählen",
        }

        if initial_directory is not None:
            dialog_arguments["initialdir"] = initial_directory

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
        selected_label = self.room_pattern_var.get()

        if selected_label == CUSTOM_PATTERN_LABEL:
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
        selected_label = self.room_pattern_var.get()

        if selected_label == CUSTOM_PATTERN_LABEL:
            description = (
                "Sonderformat für besondere "
                "Raumnummern. Beispiel für "
                "RAUM-101: "
                r"\bRAUM-\d+[a-z]?\b"
            )
        else:
            preset_key = self.pattern_labels_to_keys.get(
                selected_label
            )

            if preset_key is None:
                description = ""
            else:
                description = (
                    ROOM_PATTERN_PRESETS[
                        preset_key
                    ]["description"]
                )

                if preset_key == "usz_standard":
                    description += (
                        " Nominal und Havarie "
                        "werden automatisch erkannt."
                    )

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

    def update_progress_from_message(
        self,
        message: str,
    ) -> None:
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
        self.root.after(
            0,
            self.update_progress_from_message,
            message,
        )

    def set_lueftung_running_state(
        self,
        running: bool,
    ) -> None:
        widget_state = (
            "disabled"
            if running
            else "normal"
        )

        for widget in self.lueftung_widgets:
            try:
                if (
                    widget is self.custom_pattern_entry
                    and not running
                    and self.room_pattern_var.get()
                    != CUSTOM_PATTERN_LABEL
                ):
                    widget.config(
                        state="disabled"
                    )
                elif widget is self.pattern_combobox:
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
                else "Luftmengenvergleich starten"
            ),
        )

    def validate_lueftung_inputs(self) -> None:
        if not self.floorplan_pdfs:
            raise ValueError(
                "Bitte mindestens einen Grundriss auswählen."
            )

        if not self.schema_pdfs:
            raise ValueError(
                "Bitte mindestens ein Prinzipschema auswählen."
            )

        if self.output_dir is None:
            raise ValueError(
                "Bitte einen Ausgabeordner auswählen."
            )

    def start_lueftung(self) -> None:
        try:
            self.validate_lueftung_inputs()

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

        self.set_lueftung_running_state(
            True
        )

        worker = threading.Thread(
            target=self.run_lueftung_worker,
            args=(
                room_pattern_key,
                custom_room_pattern,
            ),
            daemon=True,
        )

        worker.start()

    def run_lueftung_worker(
        self,
        room_pattern_key: str,
        custom_room_pattern: str | None,
    ) -> None:
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
                self.handle_lueftung_success,
                results,
            )

        except Exception as error:
            self.root.after(
                0,
                self.handle_lueftung_error,
                error,
            )

    def handle_lueftung_success(
        self,
        results: dict[str, object],
    ) -> None:
        self.progress.config(
            value=6
        )

        self.status.config(
            text="Vergleich erfolgreich abgeschlossen.",
            fg=SUCCESS_COLOR,
        )

        self.set_lueftung_running_state(
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
            if isinstance(output_pdfs, list)
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

    def handle_lueftung_error(
        self,
        error: Exception,
    ) -> None:
        self.status.config(
            text=(
                "Bei der Verarbeitung ist "
                "ein Fehler aufgetreten."
            ),
            fg=ERROR_COLOR,
        )

        self.set_lueftung_running_state(
            False
        )

        messagebox.showerror(
            "Fehler",
            str(error),
        )

    # ========================================================
    # HK NUMMERNKONTROLLE – LOGIK
    # ========================================================

    # ========================================================
    # LÜFTUNG SCHEMANUMMERNKONTROLLE – DATEIAUSWAHL / START
    # ========================================================

    def add_luft_num_pair(self) -> None:
        schema_pdf = filedialog.askopenfilename(
            title="Lüftungs-Prinzipschema auswählen",
            filetypes=[
                (
                    "PDF-Dateien",
                    "*.pdf",
                ),
            ],
        )

        if not schema_pdf:
            return

        bml_excel = filedialog.askopenfilename(
            title="Lüftungs-Betriebsmittelliste auswählen",
            filetypes=[
                (
                    "Excel-Dateien",
                    "*.xlsx *.xlsm",
                ),
            ],
        )

        if not bml_excel:
            return

        pair_number = len(
            self.luft_num_pairs
        ) + 1

        schema_stem = Path(
            schema_pdf
        ).stem

        default_name = re.sub(
            r'[<>:"/\\|?*]+',
            "_",
            schema_stem,
        )

        pair_name = simpledialog.askstring(
            title=f"Paar {pair_number}: Name",
            prompt=(
                "Wie soll diese Auswertung heissen?\n\n"
                "Beispiele:\n"
                "- Gastro\n"
                "- Pflege\n"
                "- Lüftung_MIT1"
            ),
            initialvalue=default_name,
        )

        if pair_name is None or not pair_name.strip():
            pair_name = default_name

        self.luft_num_pairs.append(
            {
                "name": pair_name.strip(),
                "schema_pdf": schema_pdf,
                "bml_excel": bml_excel,
            }
        )

        self.update_luft_num_pairs_label()

    def clear_luft_num_pairs(self) -> None:
        self.luft_num_pairs.clear()
        self.update_luft_num_pairs_label()

    def update_luft_num_pairs_label(self) -> None:
        if not self.luft_num_pairs:
            text = "Keine Paare ausgewählt"
        else:
            lines = [
                (
                    f"{index}. {pair['name']} "
                    f"({Path(pair['schema_pdf']).name} / "
                    f"{Path(pair['bml_excel']).name})"
                )
                for index, pair
                in enumerate(
                    self.luft_num_pairs,
                    start=1,
                )
            ]

            text = "\n".join(
                lines
            )

        self.luft_num_pairs_label.config(
            text=text
        )

    def choose_luft_num_output(self) -> None:
        initial_directory: str | None = None

        if self.luft_num_output_dir is not None:
            initial_directory = str(
                self.luft_num_output_dir
            )

        dialog_arguments: dict[str, object] = {
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
            self.luft_num_output_dir = Path(
                folder
            )

            self.luft_num_output_label.config(
                text=str(
                    self.luft_num_output_dir
                )
            )

    def validate_luft_num_inputs(self) -> None:
        if not self.luft_num_pairs:
            raise ValueError(
                "Bitte mindestens ein Lüftungs-Schema/BML-Paar hinzufügen."
            )

        if self.luft_num_output_dir is None:
            raise ValueError(
                "Bitte einen Ausgabeordner auswählen."
            )

    def set_luft_num_running_state(
        self,
        running: bool,
    ) -> None:
        widget_state = (
            "disabled"
            if running
            else "normal"
        )

        for widget in self.luft_num_widgets:
            try:
                widget.config(
                    state=widget_state
                )
            except tk.TclError:
                pass

        self.luft_num_start_button.config(
            state=(
                "disabled"
                if running
                else "normal"
            ),
            text=(
                "Lüftungs-Kontrolle läuft …"
                if running
                else "Lüftungs-Schemanummernkontrolle starten"
            ),
        )

    def start_luft_num(self) -> None:
        try:
            self.validate_luft_num_inputs()

        except Exception as error:
            messagebox.showerror(
                "Eingabe prüfen",
                str(error),
            )
            return

        self.luft_num_progress.config(
            maximum=max(
                len(self.luft_num_pairs),
                1,
            ),
            value=0,
        )

        self.luft_num_status.config(
            text=(
                "Lüftungs-Schemanummernkontrolle "
                "wird vorbereitet …"
            ),
            fg=MUTED_TEXT_COLOR,
        )

        self.set_luft_num_running_state(
            True
        )

        worker = threading.Thread(
            target=self.run_luft_num_worker,
            daemon=True,
        )

        worker.start()

    def run_luft_num_worker(self) -> None:
        try:
            output_paths: list[Path] = []

            for index, pair in enumerate(
                self.luft_num_pairs,
                start=1,
            ):
                self.root.after(
                    0,
                    self.update_luft_num_progress,
                    index - 1,
                    (
                        f"{index}/{len(self.luft_num_pairs)} "
                        f"wird verarbeitet: {pair['name']}"
                    ),
                )

                output_path = run_luft_number_check(
                    schema_pdf=pair[
                        "schema_pdf"
                    ],
                    bml_excel=pair[
                        "bml_excel"
                    ],
                    output_dir=(
                        self.luft_num_output_dir
                    ),
                    name=(
                        "Lueftung_"
                        "Schemanummernkontrolle_"
                        f"{index}_{pair['name']}"
                    ),
                )

                output_paths.append(
                    output_path
                )

            self.root.after(
                0,
                self.handle_luft_num_success,
                output_paths,
            )

        except Exception as error:
            self.root.after(
                0,
                self.handle_luft_num_error,
                error,
            )

    def update_luft_num_progress(
        self,
        value: int,
        message: str,
    ) -> None:
        self.luft_num_progress.config(
            value=value
        )

        self.luft_num_status.config(
            text=message,
            fg=MUTED_TEXT_COLOR,
        )

    def handle_luft_num_success(
        self,
        output_paths: list[Path],
    ) -> None:
        self.luft_num_progress.config(
            value=len(
                output_paths
            )
        )

        self.luft_num_status.config(
            text=(
                "Lüftungs-Schemanummernkontrolle "
                "erfolgreich abgeschlossen."
            ),
            fg=SUCCESS_COLOR,
        )

        self.set_luft_num_running_state(
            False
        )

        result_text = "\n".join(
            str(path)
            for path in output_paths
        )

        messagebox.showinfo(
            "Lüftungs-Schemanummernkontrolle abgeschlossen",
            (
                "Die Lüftungs-Schemanummernkontrolle "
                "wurde erfolgreich abgeschlossen.\n\n"
                f"Erstellte Dateien: {len(output_paths)}\n\n"
                f"{result_text}"
            ),
        )

    def handle_luft_num_error(
        self,
        error: Exception,
    ) -> None:
        self.luft_num_status.config(
            text=(
                "Bei der Lüftungs-Schemanummernkontrolle "
                "ist ein Fehler aufgetreten."
            ),
            fg=ERROR_COLOR,
        )

        self.set_luft_num_running_state(
            False
        )

        messagebox.showerror(
            "Fehler",
            str(error),
        )

    def add_hk_pair(self) -> None:
        pair_number = len(
            self.hk_pairs
        ) + 1

        schema_pdf = filedialog.askopenfilename(
            title=f"Paar {pair_number}: Prinzipschema-PDF auswählen",
            filetypes=[
                (
                    "PDF-Dateien",
                    "*.pdf",
                ),
            ],
        )

        if not schema_pdf:
            return

        bml_excel = filedialog.askopenfilename(
            title=f"Paar {pair_number}: Passende BML-Excel auswählen",
            filetypes=[
                (
                    "Excel-Dateien",
                    "*.xlsx",
                ),
            ],
        )

        if not bml_excel:
            return

        default_name = Path(
            schema_pdf
        ).stem

        pair_name = simpledialog.askstring(
            title=f"Paar {pair_number}: Name",
            prompt=(
                "Wie soll diese Auswertung heissen?\n\n"
                "Beispiele:\n"
                "- Heizung_Kaelte\n"
                "- Verteilung_MIT1\n"
                "- Verteilung_MIT2"
            ),
            initialvalue=default_name,
        )

        if pair_name is None or not pair_name.strip():
            pair_name = default_name

        self.hk_pairs.append(
            {
                "name": pair_name.strip(),
                "schema_pdf": schema_pdf,
                "bml_excel": bml_excel,
            }
        )

        self.update_hk_pairs_label()

    def clear_hk_pairs(self) -> None:
        self.hk_pairs.clear()
        self.update_hk_pairs_label()

    def update_hk_pairs_label(self) -> None:
        if not self.hk_pairs:
            text = "Keine Paare ausgewählt"
        else:
            lines = [
                f"{index}. {pair['name']}"
                for index, pair
                in enumerate(
                    self.hk_pairs,
                    start=1,
                )
            ]

            text = "\n".join(
                lines
            )

        self.hk_pairs_label.config(
            text=text
        )

    def choose_hk_output(self) -> None:
        initial_directory: str | None = None

        if self.hk_output_dir is not None:
            initial_directory = str(
                self.hk_output_dir
            )

        dialog_arguments: dict[str, object] = {
            "title": "Ausgabeordner auswählen",
        }

        if initial_directory is not None:
            dialog_arguments["initialdir"] = initial_directory

        folder = filedialog.askdirectory(
            **dialog_arguments
        )

        if folder:
            self.hk_output_dir = Path(
                folder
            )

            self.hk_output_label.config(
                text=str(
                    self.hk_output_dir
                )
            )

    def validate_hk_inputs(self) -> None:
        if not self.hk_pairs:
            raise ValueError(
                "Bitte mindestens ein Schema/BML-Paar hinzufügen."
            )

        if self.hk_output_dir is None:
            raise ValueError(
                "Bitte einen Ausgabeordner auswählen."
            )

    def set_hk_running_state(
        self,
        running: bool,
    ) -> None:
        widget_state = (
            "disabled"
            if running
            else "normal"
        )

        for widget in self.hk_widgets:
            try:
                widget.config(
                    state=widget_state
                )
            except tk.TclError:
                pass

        self.hk_start_button.config(
            state=(
                "disabled"
                if running
                else "normal"
            ),
            text=(
                "HK-Kontrolle läuft …"
                if running
                else "HK-Nummernkontrolle starten"
            ),
        )

    def start_hk(self) -> None:
        try:
            self.validate_hk_inputs()

        except Exception as error:
            messagebox.showerror(
                "Eingabe prüfen",
                str(error),
            )
            return

        self.hk_progress.config(
            maximum=max(
                len(self.hk_pairs),
                1,
            ),
            value=0,
        )

        self.hk_status.config(
            text="HK-Nummernkontrolle wird vorbereitet …",
            fg=MUTED_TEXT_COLOR,
        )

        self.set_hk_running_state(
            True
        )

        worker = threading.Thread(
            target=self.run_hk_worker,
            daemon=True,
        )

        worker.start()

    def run_hk_worker(self) -> None:
        try:
            output_paths: list[Path] = []

            for index, pair in enumerate(
                self.hk_pairs,
                start=1,
            ):
                self.root.after(
                    0,
                    self.update_hk_progress,
                    index - 1,
                    (
                        f"{index}/{len(self.hk_pairs)} "
                        f"wird verarbeitet: {pair['name']}"
                    ),
                )

                output_path = run_hk_number_check(
                    schema_pdf=pair["schema_pdf"],
                    bml_excel=pair["bml_excel"],
                    output_dir=self.hk_output_dir,
                    name=(
                        f"HK_Nummernkontrolle_"
                        f"{index}_{pair['name']}"
                    ),
                )

                output_paths.append(
                    output_path
                )

            self.root.after(
                0,
                self.handle_hk_success,
                output_paths,
            )

        except Exception as error:
            self.root.after(
                0,
                self.handle_hk_error,
                error,
            )

    def update_hk_progress(
        self,
        value: int,
        message: str,
    ) -> None:
        self.hk_progress.config(
            value=value
        )

        self.hk_status.config(
            text=message,
            fg=MUTED_TEXT_COLOR,
        )

    def handle_hk_success(
        self,
        output_paths: list[Path],
    ) -> None:
        self.hk_progress.config(
            value=len(
                output_paths
            )
        )

        self.hk_status.config(
            text="HK-Nummernkontrolle erfolgreich abgeschlossen.",
            fg=SUCCESS_COLOR,
        )

        self.set_hk_running_state(
            False
        )

        result_text = "\n".join(
            str(path)
            for path in output_paths
        )

        messagebox.showinfo(
            "HK-Nummernkontrolle abgeschlossen",
            (
                "Die HK-Nummernkontrolle wurde "
                "erfolgreich abgeschlossen.\n\n"
                f"Erstellte Dateien: {len(output_paths)}\n\n"
                f"{result_text}"
            ),
        )

    def handle_hk_error(
        self,
        error: Exception,
    ) -> None:
        self.hk_status.config(
            text=(
                "Bei der HK-Nummernkontrolle ist "
                "ein Fehler aufgetreten."
            ),
            fg=ERROR_COLOR,
        )

        self.set_hk_running_state(
            False
        )

        messagebox.showerror(
            "Fehler",
            str(error),
        )

    # ========================================================
    # HK LASTVERGLEICH – DATEIAUSWAHL
    # ========================================================


    def choose_hk_load_schema(self) -> None:
        # Rückwärtskompatibler Alias
        self.choose_hk_load_schemas()


    def clear_hk_load_schema(self) -> None:
        self.hk_load_schema_pdfs.clear()
        self.update_hk_load_schema_label()


    def update_hk_load_schema_label(self) -> None:
        self.hk_load_schema_label.config(
            text=self.format_hk_load_selection(
                self.hk_load_schema_pdfs,
                "Keine Strangschemata ausgewählt",
            )
        )


    def choose_hk_load_schemas(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Ein oder mehrere Strangschemata auswählen",
            filetypes=[("PDF-Dateien", "*.pdf")],
        )

        self.add_unique_paths(
            self.hk_load_schema_pdfs,
            selected,
        )
        self.update_hk_load_schema_label()

    def choose_hk_load_schema_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Ordner mit Strangschemata auswählen",
        )

        if not folder:
            return

        self.add_unique_paths(
            self.hk_load_schema_pdfs,
            sorted(Path(folder).glob("*.pdf")),
        )
        self.update_hk_load_schema_label()


    def choose_hk_load_excel(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Eine oder mehrere Heiz-/Kühllast-Excel-Dateien auswählen",
            filetypes=[
                ("Excel-Dateien", "*.xlsx *.xlsm"),
                ("Alle Dateien", "*.*"),
            ],
        )

        self.add_unique_paths(
            self.hk_load_excel_paths,
            selected,
        )
        self.update_hk_load_excel_label()


    def choose_hk_load_excel_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Ordner mit Heiz-/Kühllast-Excel-Dateien auswählen",
        )

        if not folder:
            return

        folder_path = Path(folder)

        excel_files = sorted(
            [
                path
                for path in folder_path.iterdir()
                if (
                    path.is_file()
                    and path.suffix.casefold()
                    in {".xlsx", ".xlsm"}
                    and not path.name.startswith("~$")
                )
            ]
        )

        self.add_unique_paths(
            self.hk_load_excel_paths,
            excel_files,
        )
        self.update_hk_load_excel_label()

    def update_hk_load_excel_label(self) -> None:
        self.hk_excel_label.config(
            text=self.format_hk_load_selection(
                self.hk_load_excel_paths,
                "Keine Excel-Dateien ausgewählt",
            )
        )


    def clear_hk_load_excel(self) -> None:
        self.hk_load_excel_paths.clear()
        self.update_hk_load_excel_label()

    def update_hk_load_source_controls(self) -> None:
        source_type = self.hk_load_source_type.get()
        scope = self.hk_load_scope.get()

        excel_frame = getattr(
            self,
            "hk_excel_source_frame",
            None,
        )
        pdf_frame = getattr(
            self,
            "hk_pdf_source_frame",
            None,
        )

        if source_type == "excel":
            if pdf_frame is not None:
                pdf_frame.grid_remove()
            if excel_frame is not None:
                excel_frame.grid()

        else:
            if excel_frame is not None:
                excel_frame.grid_remove()
            if pdf_frame is not None:
                pdf_frame.grid()

        groups = getattr(
            self,
            "hk_pdf_control_groups",
            {},
        )

        heating_enabled = (
            source_type == "pdf"
            and scope in {"heizung", "beides"}
        )
        cooling_enabled = (
            source_type == "pdf"
            and scope in {"kuehlung", "beides"}
        )

        for widget in groups.get(
            "Heizlast-Grundrisse",
            [],
        ):
            widget.config(
                state=(
                    "normal"
                    if heating_enabled
                    else "disabled"
                )
            )

        for widget in groups.get(
            "Kühllast-Grundrisse",
            [],
        ):
            widget.config(
                state=(
                    "normal"
                    if cooling_enabled
                    else "disabled"
                )
            )

        # Die nicht benötigte PDF-Auswahl zusätzlich optisch ausblenden.
        if pdf_frame is not None and source_type == "pdf":
            if hasattr(self, "hk_heating_label"):
                if heating_enabled:
                    self.hk_heating_label.grid()
                else:
                    self.hk_heating_label.grid_remove()

            if hasattr(self, "hk_cooling_label"):
                if cooling_enabled:
                    self.hk_cooling_label.grid()
                else:
                    self.hk_cooling_label.grid_remove()

    def add_unique_paths(
        self,
        target: list[Path],
        paths,
    ) -> None:
        for path_value in paths:
            path = Path(
                path_value
            )

            # Diese Hilfsfunktion wird sowohl für PDFs als auch
            # für Excel-Dateien verwendet.
            if (
                path.suffix.lower()
                in {".pdf", ".xlsx", ".xlsm"}
                and path not in target
            ):
                target.append(
                    path
                )

    def choose_hk_heating_pdfs(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Heizlast-Grundrisse auswählen",
            filetypes=[
                (
                    "PDF-Dateien",
                    "*.pdf",
                ),
            ],
        )

        self.add_unique_paths(
            self.hk_heating_pdfs,
            selected,
        )
        self.update_hk_heating_label()

    def choose_hk_cooling_pdfs(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Kühllast-Grundrisse auswählen",
            filetypes=[
                (
                    "PDF-Dateien",
                    "*.pdf",
                ),
            ],
        )

        self.add_unique_paths(
            self.hk_cooling_pdfs,
            selected,
        )
        self.update_hk_cooling_label()

    def choose_hk_heating_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Ordner mit Heizlast-Grundrissen auswählen",
        )

        if not folder:
            return

        self.add_unique_paths(
            self.hk_heating_pdfs,
            sorted(
                Path(
                    folder
                ).glob(
                    "*.pdf"
                )
            ),
        )
        self.update_hk_heating_label()

    def choose_hk_cooling_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Ordner mit Kühllast-Grundrissen auswählen",
        )

        if not folder:
            return

        self.add_unique_paths(
            self.hk_cooling_pdfs,
            sorted(
                Path(
                    folder
                ).glob(
                    "*.pdf"
                )
            ),
        )
        self.update_hk_cooling_label()

    def clear_hk_heating_pdfs(self) -> None:
        self.hk_heating_pdfs.clear()
        self.update_hk_heating_label()

    def clear_hk_cooling_pdfs(self) -> None:
        self.hk_cooling_pdfs.clear()
        self.update_hk_cooling_label()

    def format_hk_load_selection(
        self,
        paths: list[Path],
        empty_text: str,
    ) -> str:
        if not paths:
            return empty_text

        if len(paths) <= 3:
            return "\n".join(
                path.name
                for path in paths
            )

        first_names = "\n".join(
            path.name
            for path in paths[:3]
        )

        return (
            f"{first_names}\n"
            f"… und {len(paths) - 3} weitere PDF(s)"
        )

    def update_hk_heating_label(self) -> None:
        self.hk_heating_label.config(
            text=self.format_hk_load_selection(
                self.hk_heating_pdfs,
                "Keine Heizlast-Grundrisse ausgewählt",
            )
        )

    def update_hk_cooling_label(self) -> None:
        self.hk_cooling_label.config(
            text=self.format_hk_load_selection(
                self.hk_cooling_pdfs,
                "Keine Kühllast-Grundrisse ausgewählt",
            )
        )

    def choose_hk_load_output(self) -> None:
        initial_directory: str | None = None

        if self.hk_load_output_dir is not None:
            initial_directory = str(
                self.hk_load_output_dir
            )
        elif self.hk_load_schema_pdfs:
            initial_directory = str(
                self.hk_load_schema_pdfs[0].parent
            )

        dialog_arguments: dict[str, object] = {
            "title": "Ausgabeordner für Lastvergleich auswählen",
        }

        if initial_directory is not None:
            dialog_arguments[
                "initialdir"
            ] = initial_directory

        folder = filedialog.askdirectory(
            **dialog_arguments
        )

        if folder:
            self.hk_load_output_dir = Path(
                folder
            )

            self.hk_load_output_label.config(
                text=str(
                    self.hk_load_output_dir
                )
            )

    # ========================================================
    # HK LASTVERGLEICH – LOGIK
    # ========================================================


    def validate_hk_load_inputs(self) -> None:
        if not self.hk_load_schema_pdfs:
            raise ValueError(
                "Bitte mindestens ein Strangschema auswählen."
            )

        source_type = self.hk_load_source_type.get()
        scope = self.hk_load_scope.get()

        if scope not in {
            "heizung",
            "kuehlung",
            "beides",
        }:
            raise ValueError(
                "Bitte einen gültigen Prüfumfang auswählen."
            )

        if source_type == "excel":
            if not self.hk_load_excel_paths:
                raise ValueError(
                    "Bitte mindestens eine Heiz-/Kühllast-Excel auswählen."
                )

        elif source_type == "pdf":
            if (
                scope in {"heizung", "beides"}
                and not self.hk_heating_pdfs
            ):
                raise ValueError(
                    "Bitte mindestens einen Heizlast-Grundriss auswählen."
                )

            if (
                scope in {"kuehlung", "beides"}
                and not self.hk_cooling_pdfs
            ):
                raise ValueError(
                    "Bitte mindestens einen Kühllast-Grundriss auswählen."
                )
        else:
            raise ValueError(
                "Bitte PDF oder Excel als Lastquelle auswählen."
            )

        if self.hk_load_output_dir is None:
            raise ValueError(
                "Bitte einen Ausgabeordner auswählen."
            )

    def set_hk_load_running_state(
        self,
        running: bool,
    ) -> None:
        state = (
            "disabled"
            if running
            else "normal"
        )

        for widget in self.hk_load_widgets:
            try:
                widget.config(
                    state=state
                )
            except tk.TclError:
                pass

        self.hk_load_start_button.config(
            state=state,
            text=(
                "Lastvergleich läuft …"
                if running
                else "Lastvergleich starten"
            ),
        )

    def set_hk_load_progress(
        self,
        value: int,
        message: str,
    ) -> None:
        self.hk_load_progress.config(
            value=value
        )

        self.hk_load_status.config(
            text=message,
            fg=MUTED_TEXT_COLOR,
        )

    def thread_safe_hk_load_progress(
        self,
        value: int,
        message: str,
    ) -> None:
        self.root.after(
            0,
            self.set_hk_load_progress,
            value,
            message,
        )


    def start_hk_load(self) -> None:
        try:
            self.validate_hk_load_inputs()

        except Exception as error:
            messagebox.showerror(
                "Eingabe prüfen",
                str(error),
            )
            return

        self.hk_load_progress.config(
            value=0,
            maximum=max(
                1,
                len(self.hk_load_schema_pdfs),
            ),
        )

        self.hk_load_status.config(
            text="Lastvergleich wird vorbereitet …",
            fg=MUTED_TEXT_COLOR,
        )

        self.set_hk_load_running_state(True)

        worker = threading.Thread(
            target=self.run_hk_load_worker,
            daemon=True,
        )
        worker.start()


    def run_hk_load_worker(self) -> None:
        try:
            assert self.hk_load_output_dir is not None

            source_type = self.hk_load_source_type.get()
            mode = self.hk_load_scope.get()

            compare_heating = mode in {
                "heizung",
                "beides",
            }
            compare_cooling = mode in {
                "kuehlung",
                "beides",
            }

            created_files: list[Path] = []
            result_rows: list[dict[str, object]] = []

            total = len(
                self.hk_load_schema_pdfs
            )

            for index, schema_path in enumerate(
                self.hk_load_schema_pdfs,
                start=1,
            ):
                self.thread_safe_hk_load_progress(
                    index - 1,
                    (
                        f"Strangschema {index}/{total} wird ausgewertet: "
                        f"{schema_path.name}"
                    ),
                )

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
                        "Gebäudeumfang des Strangschemas konnte nicht "
                        f"erkannt werden:\n{schema_path.name}"
                    )

                if source_type == "excel":
                    assert self.hk_load_excel_paths

                    (
                        heating,
                        cooling,
                        check_dataframe,
                    ) = extract_loads_from_excels_checked(
                        excel_paths=self.hk_load_excel_paths,
                        mode=mode,
                        expected_building=building,
                    )

                    if (
                        not check_dataframe.empty
                        and "lastart"
                        in check_dataframe.columns
                    ):
                        heating_check = (
                            check_dataframe.loc[
                                check_dataframe[
                                    "lastart"
                                ].astype(str)
                                == "Heizlast"
                            ]
                            .copy()
                            .reset_index(drop=True)
                        )

                        cooling_check = (
                            check_dataframe.loc[
                                check_dataframe[
                                    "lastart"
                                ].astype(str)
                                == "Kühllast"
                            ]
                            .copy()
                            .reset_index(drop=True)
                        )
                    else:
                        heating_check = (
                            check_dataframe.copy()
                        )
                        cooling_check = (
                            check_dataframe.copy()
                        )

                    heating_sources = (
                        list(self.hk_load_excel_paths)
                        if compare_heating
                        else []
                    )
                    cooling_sources = (
                        list(self.hk_load_excel_paths)
                        if compare_cooling
                        else []
                    )

                else:
                    if compare_heating:
                        (
                            heating,
                            heating_check,
                        ) = extract_loads_from_pdfs_checked(
                            self.hk_heating_pdfs,
                            "Heizlast",
                            expected_building=building,
                        )
                    else:
                        heating = schema.iloc[0:0].copy()
                        heating_check = schema.iloc[0:0].copy()

                    if compare_cooling:
                        (
                            cooling,
                            cooling_check,
                        ) = extract_loads_from_pdfs_checked(
                            self.hk_cooling_pdfs,
                            "Kühllast",
                            expected_building=building,
                        )
                    else:
                        cooling = schema.iloc[0:0].copy()
                        cooling_check = schema.iloc[0:0].copy()

                    heating_sources = (
                        self.hk_heating_pdfs
                        if compare_heating
                        else []
                    )
                    cooling_sources = (
                        self.hk_cooling_pdfs
                        if compare_cooling
                        else []
                    )

                comparison = compare_loads_with_schema(
                    heating=heating,
                    cooling=cooling,
                    consolidated_schema=schema,
                    compare_heating=compare_heating,
                    compare_cooling=compare_cooling,
                )

                timestamp = datetime.now().strftime(
                    "%Y%m%d_%H%M%S"
                )

                safe_schema_stem = (
                    schema_path.stem
                    .replace(" ", "_")
                    .replace("/", "_")
                    .replace("\\", "_")
                )

                output_path = (
                    self.hk_load_output_dir
                    / (
                        f"Lastvergleich_{building}_"
                        f"{safe_schema_stem}_{timestamp}.xlsx"
                    )
                )

                export_kwargs = {
                    "output_path": output_path,
                    "comparison": comparison,
                    "schema_pdf": schema_path,
                    "heating_pdfs": heating_sources,
                    "cooling_pdfs": cooling_sources,
                    "building": building,
                    "heating_check": heating_check,
                    "cooling_check": cooling_check,
                }

                # Neue Exportversion kennt source_type/comparison_scope.
                # Falls lokal noch die ältere Exportdatei liegt, läuft
                # die GUI trotzdem weiter statt mit TypeError abzubrechen.
                export_parameters = inspect.signature(
                    export_load_comparison_excel
                ).parameters

                if "source_type" in export_parameters:
                    export_kwargs["source_type"] = source_type

                if "comparison_scope" in export_parameters:
                    export_kwargs["comparison_scope"] = mode

                export_load_comparison_excel(
                    **export_kwargs
                )

                created_files.append(
                    output_path
                )

                counts = (
                    comparison[
                        "status_gesamt"
                    ]
                    .value_counts()
                    .to_dict()
                )

                result_rows.append(
                    {
                        "schema": schema_path.name,
                        "building": building,
                        "counts": counts,
                        "output_path": output_path,
                    }
                )

                self.thread_safe_hk_load_progress(
                    index,
                    (
                        f"{index}/{total} abgeschlossen: "
                        f"{schema_path.name}"
                    ),
                )

            result = {
                "created_files": created_files,
                "results": result_rows,
                "source_type": source_type,
                "scope": mode,
            }

            self.root.after(
                0,
                self.handle_hk_load_success,
                result,
            )

        except Exception as error:
            self.root.after(
                0,
                self.handle_hk_load_error,
                error,
            )


    def handle_hk_load_success(
        self,
        result: dict[str, object],
    ) -> None:
        created_files = result.get(
            "created_files",
            [],
        )
        results = result.get(
            "results",
            [],
        )

        self.hk_load_progress.config(
            value=max(
                1,
                len(created_files)
                if isinstance(created_files, list)
                else 1,
            )
        )

        self.hk_load_status.config(
            text=(
                "Lastvergleich erfolgreich abgeschlossen. "
                f"{len(created_files) if isinstance(created_files, list) else 0} "
                "Ergebnisdatei(en) erstellt."
            ),
            fg=SUCCESS_COLOR,
        )

        self.set_hk_load_running_state(False)
        self.update_hk_load_source_controls()

        summary_lines: list[str] = []

        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue

                counts = item.get(
                    "counts",
                    {},
                )

                status_text = (
                    ", ".join(
                        f"{status}: {count}"
                        for status, count in counts.items()
                    )
                    if isinstance(counts, dict)
                    else ""
                )

                summary_lines.append(
                    (
                        f"{item.get('schema', '')}\n"
                        f"Gebäude: {item.get('building', '')}\n"
                        f"{status_text}"
                    )
                )

        output_dir_text = (
            str(self.hk_load_output_dir)
            if self.hk_load_output_dir is not None
            else ""
        )

        messagebox.showinfo(
            "Lastvergleich abgeschlossen",
            (
                f"{len(created_files) if isinstance(created_files, list) else 0} "
                "Strangschema/Strangschemata wurden verarbeitet.\n\n"
                + "\n\n".join(summary_lines)
                + "\n\nAusgabeordner:\n"
                + output_dir_text
            ),
        )

    def handle_hk_load_error(
        self,
        error: Exception,
    ) -> None:
        self.hk_load_status.config(
            text=(
                "Beim HK-Lastvergleich ist ein Fehler aufgetreten."
            ),
            fg=ERROR_COLOR,
        )

        self.set_hk_load_running_state(
            False
        )
        self.update_hk_load_source_controls()

        details = "".join(
            traceback.format_exception(
                type(error),
                error,
                error.__traceback__,
            )
        )

        print(
            "\n===== HK-LASTVERGLEICH FEHLER =====\n"
            + details
            + "====================================\n"
        )

        messagebox.showerror(
            "Fehler",
            (
                f"{error}\n\n"
                "Der vollständige Fehler steht im PowerShell-Fenster."
            ),
        )

    # ========================================================
    # START
    # ========================================================

    def run(self) -> None:
        self.root.mainloop()


def start_gui() -> None:
    app = LuftmengenGUI()
    app.run()
