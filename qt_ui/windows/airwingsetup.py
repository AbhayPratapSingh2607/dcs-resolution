"""The air wing setup window of a new campaign.

Three steps, per side:

1. **Bases.** Every base the side owns is listed, ships first, then the
   airfields closest to farthest from the battle. Each gets a preset from a
   drop-down: the faction's own presets made for that kind of base and its
   distance from the battle (game.campaignloader.factionpresets), the
   hand-made historical ones the faction can fly, the campaign's own
   squadrons, or none. The row shows the squadrons the base will have.
2. **More aircraft.** Optional extra squadrons of any of the faction's
   aircraft, at any base that can take them.
3. **Apply and continue.** Config files can be saved and loaded, and the
   old squadron-by-squadron editor is one click away for fine edits.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Optional

import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.ato.flighttype import FlightType
from game.campaignloader.airwingpreset import (
    AirWingPresetLoader,
    BasePresetPlacer,
    PresetPlan,
    RankedBase,
    apply_base_preset,
    ranked_bases,
)
from game.campaignloader.factionpresets import (
    BaseChoice,
    faction_aircraft,
    faction_presets,
    presets_for_base,
)
from game.coalition import Coalition
from game.dcs.aircrafttype import AircraftType
from game.persistency import airwing_dir
from game.squadrons import Squadron
from game.squadrons.squadrondef import SquadronDef
from game.theater import ControlPoint

KEEP = "keep"
EMPTY = "empty"

#: Default sizes for squadrons added in step 2.
SUPPORT_SIZE = 4
DEFAULT_SIZE = 12

MUTED = "#9fb0c0"
WARN = "#e0a040"


def _squadron_text(squadrons: list[Squadron]) -> str:
    if not squadrons:
        return "no squadrons"
    return " · ".join(
        f"{s.aircraft.display_name} ×{s.max_size} ({s.primary_task.value})"
        for s in squadrons
    )


def _plan_text(plan: PresetPlan) -> str:
    if not plan.placements:
        return "no squadrons"
    return " · ".join(
        f"{p.aircraft.display_name} ×{p.config.max_size} ({p.config.primary.value})"
        for p in plan.placements
    )


class BaseRow:
    """One base: its label, the preset picked for it and what it will have."""

    def __init__(
        self,
        page: SideSetupPage,
        ranked: RankedBase,
        choices: list[BaseChoice],
        grid: QGridLayout,
        row: int,
    ) -> None:
        self.page = page
        self.ranked = ranked
        self.base = ranked.base
        self.plan: Optional[PresetPlan] = None

        title = QLabel(f"<b>{html.escape(ranked.label)}</b>")
        title.setWordWrap(True)
        grid.addWidget(title, row, 0)

        self.combo = QComboBox()
        self.combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.combo.setMinimumContentsLength(40)
        current = page.squadrons_at(self.base)
        self.combo.addItem(
            (
                f"Keep the campaign's squadrons ({len(current)})"
                if current
                else "No squadrons (as the campaign has it)"
            ),
            KEEP,
        )
        for choice in choices:
            self.combo.addItem(choice.label, choice)
            self.combo.setItemData(
                self.combo.count() - 1,
                choice.base_preset.preset.description,
                Qt.ItemDataRole.ToolTipRole,
            )
        if current:
            self.combo.addItem("No squadrons", EMPTY)
        self.combo.currentIndexChanged.connect(lambda _: self.update())
        grid.addWidget(self.combo, row, 1)

        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        grid.addWidget(self.detail, row + 1, 0, 1, 2)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #3a4a5a;")
        grid.addWidget(divider, row + 2, 0, 1, 2)
        self.update()

    @property
    def choice(self) -> object:
        return self.combo.currentData()

    @property
    def has_presets(self) -> bool:
        return any(
            isinstance(self.combo.itemData(i), BaseChoice)
            for i in range(self.combo.count())
        )

    def pick_first_preset(self) -> None:
        for i in range(self.combo.count()):
            if isinstance(self.combo.itemData(i), BaseChoice):
                self.combo.setCurrentIndex(i)
                return

    def keep(self) -> None:
        self.combo.setCurrentIndex(0)

    def resolve(self) -> Optional[PresetPlan]:
        choice = self.choice
        if not isinstance(choice, BaseChoice):
            return None
        return BasePresetPlacer(
            self.page.game, self.page.coalition, self.base, replace_at_base=True
        ).resolve(choice.base_preset.as_preset())

    def update(self) -> None:
        choice = self.choice
        self.plan = self.resolve()
        if choice == KEEP:
            text = _squadron_text(self.page.squadrons_at(self.base))
            warnings: list[str] = []
        elif choice == EMPTY:
            text = "no squadrons"
            warnings = []
        else:
            assert self.plan is not None
            text = _plan_text(self.plan)
            warnings = list(self.plan.warnings)
        notes = self.plan.notes if self.plan is not None and choice != KEEP else []
        parts = [f"<span style='color:{MUTED}'>Will have: {html.escape(text)}</span>"]
        parts += [
            f"<span style='color:{MUTED}'><i>{html.escape(n)}</i></span>" for n in notes
        ]
        parts += [
            f"<span style='color:{WARN}'>⚠ {html.escape(w)}</span>" for w in warnings
        ]
        self.detail.setText("<br>".join(parts))
        self.page.update_totals()

    def apply(self) -> int:
        """Makes the base's squadrons; returns how many were created."""
        choice = self.choice
        if choice == KEEP:
            return 0
        if choice == EMPTY:
            clear_base(self.page.coalition, self.base)
            return 0
        plan = self.resolve()
        if plan is None:
            return 0
        created = apply_base_preset(
            plan, self.page.game, self.page.coalition, self.base, replace_at_base=True
        )
        return len(created)

    def planned_aircraft(self) -> int:
        choice = self.choice
        if choice == KEEP:
            return sum(s.max_size for s in self.page.squadrons_at(self.base))
        if choice == EMPTY or self.plan is None:
            return 0
        return sum(p.config.max_size for p in self.plan.placements)


def clear_base(coalition: Coalition, base: ControlPoint) -> None:
    air_wing = coalition.air_wing
    for squadrons in air_wing.squadrons.values():
        for squadron in [s for s in squadrons if s.location is base]:
            air_wing.unclaim_squadron_def(squadron)
            squadrons.remove(squadron)


class ExtraSquadron:
    """A squadron added in step 2, made when the setup is applied."""

    def __init__(
        self,
        page: SideSetupPage,
        aircraft: AircraftType,
        base: ControlPoint,
        task: FlightType,
        squadron_def: Optional[SquadronDef],
        base_label: str,
    ) -> None:
        self.page = page
        self.aircraft = aircraft
        self.base = base
        self.task = task
        self.squadron_def = squadron_def

        self.widget = QWidget()
        layout = QHBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        name = squadron_def.name if squadron_def is not None else "new squadron"
        label = QLabel(
            f"<b>{html.escape(aircraft.display_name)}</b> — {html.escape(task.value)}, "
            f"{html.escape(name)}<br><span style='color:{MUTED}'>"
            f"{html.escape(base_label)}</span>"
        )
        label.setWordWrap(True)
        layout.addWidget(label, stretch=1)
        layout.addWidget(QLabel("Aircraft:"))
        self.size = QSpinBox()
        self.size.setRange(1, 40)
        self.size.setValue(
            SUPPORT_SIZE
            if task in (FlightType.AEWC, FlightType.REFUELING)
            else DEFAULT_SIZE
        )
        self.size.valueChanged.connect(lambda _: page.update_totals())
        layout.addWidget(self.size)
        remove = QPushButton("Remove")
        remove.clicked.connect(lambda: page.remove_extra(self))
        layout.addWidget(remove)

    def apply(self) -> Squadron:
        coalition = self.page.coalition
        squadron_def = (
            self.squadron_def
            or coalition.air_wing.squadron_def_generator.generate_for_aircraft(
                self.aircraft
            )
        )
        squadron = Squadron.create_from(
            squadron_def,
            self.task,
            self.size.value(),
            self.base,
            coalition,
            self.page.game,
        )
        # Like a preset's squadrons: deployed in full at the start.
        squadron.preset_purchase = self.size.value()
        coalition.air_wing.add_squadron(squadron)
        return squadron


class SideSetupPage(QWidget):
    def __init__(
        self, game: Game, coalition: Coalition, aircraft_present: bool
    ) -> None:
        super().__init__()
        self.game = game
        self.coalition = coalition
        self.aircraft_present = aircraft_present
        self.rows: list[BaseRow] = []
        self.extras: list[ExtraSquadron] = []
        self.handmade = AirWingPresetLoader.load_all()
        self.generated = faction_presets(coalition.faction)

        layout = QVBoxLayout(self)

        faction = coalition.faction
        header = QLabel(
            f"<b>{html.escape(faction.name)}</b> — "
            f"{len(faction_aircraft(faction))} "
            "aircraft types"
        )
        layout.addWidget(header)

        # Step 1: a preset for each base.
        bases_box = QGroupBox("1. Pick a preset for each base")
        bases_layout = QVBoxLayout(bases_box)
        intro = QLabel(
            "Ships are listed first, then airfields from closest to farthest from "
            "the battle. Each base is offered presets made for it from this "
            "faction's aircraft: air wings for carriers, assault groups for LHAs, "
            "ground attack and fighters near the front, support and bombers at the "
            "rear. Historical presets follow when the faction has their aircraft."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {MUTED};")
        bases_layout.addWidget(intro)
        quick = QHBoxLayout()
        suggest = QPushButton("Use the first preset at every base")
        suggest.clicked.connect(self.pick_first_everywhere)
        quick.addWidget(suggest)
        keep_all = QPushButton("Keep the campaign's squadrons everywhere")
        keep_all.clicked.connect(self.keep_everywhere)
        quick.addWidget(keep_all)
        quick.addStretch()
        bases_layout.addLayout(quick)

        self.rows_widget = QWidget()
        self.rows_grid = QGridLayout(self.rows_widget)
        self.rows_grid.setColumnStretch(0, 2)
        self.rows_grid.setColumnStretch(1, 3)
        self.rows_grid.setVerticalSpacing(4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.rows_widget)
        bases_layout.addWidget(scroll, stretch=1)
        layout.addWidget(bases_box, stretch=1)

        # Step 2: more aircraft.
        extras_box = QGroupBox("2. Add more aircraft (optional)")
        extras_layout = QVBoxLayout(extras_box)
        extras_intro = QLabel(
            "Add a squadron of any of the faction's aircraft to a base that can "
            "take it."
        )
        extras_intro.setStyleSheet(f"color: {MUTED};")
        extras_layout.addWidget(extras_intro)
        self.extras_widget = QWidget()
        self.extras_list = QVBoxLayout(self.extras_widget)
        self.extras_list.setContentsMargins(0, 0, 0, 0)
        extras_scroll = QScrollArea()
        extras_scroll.setWidgetResizable(True)
        extras_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        extras_scroll.setWidget(self.extras_widget)
        extras_scroll.setMaximumHeight(170)
        extras_scroll.setVisible(False)  # Shown once a squadron is added.
        self.extras_scroll = extras_scroll
        extras_layout.addWidget(extras_scroll)
        add_row = QHBoxLayout()
        add = QPushButton("Add aircraft…")
        add.clicked.connect(self.add_extra)
        add_row.addWidget(add)
        add_row.addStretch()
        extras_layout.addLayout(add_row)
        layout.addWidget(extras_box)

        self.totals = QLabel()
        layout.addWidget(self.totals)
        self.rebuild()

    # ------------------------------------------------------------- state

    def squadrons_at(self, base: ControlPoint) -> list[Squadron]:
        return [
            s
            for s in self.coalition.air_wing.iter_squadrons()
            if s.location is base and not s.is_detachment
        ]

    def rebuild(self) -> None:
        """Lists the bases afresh, every one on Keep (after applying, loading
        a config or the advanced editor)."""
        while self.rows_grid.count():
            item = self.rows_grid.takeAt(0)
            if item is not None and (widget := item.widget()) is not None:
                widget.deleteLater()
        self.rows = []
        year = self.game.date.year
        aircraft = faction_aircraft(self.coalition.faction)
        unusable: list[str] = []
        for ranked in ranked_bases(self.game, self.coalition):
            if not self.squadrons_at(ranked.base) and not any(
                ranked.base.can_operate(a) for a in aircraft
            ):
                unusable.append(ranked.base.name)
                continue
            choices = presets_for_base(
                self.coalition.faction, ranked, year, self.handmade, self.generated
            )
            self.rows.append(
                BaseRow(self, ranked, choices, self.rows_grid, len(self.rows) * 3)
            )
        end = len(self.rows) * 3
        if unusable:
            note = QLabel(
                "Not listed, no parking for this faction's aircraft: "
                + ", ".join(unusable)
            )
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {MUTED};")
            self.rows_grid.addWidget(note, end, 0, 1, 2)
            end += 1
        self.rows_grid.setRowStretch(end, 1)
        for extra in list(self.extras):
            self.remove_extra(extra)
        self.update_totals()

    def update_totals(self) -> None:
        if not hasattr(self, "totals"):
            return
        aircraft = sum(r.planned_aircraft() for r in self.rows) + sum(
            e.size.value() for e in self.extras
        )
        changed = sum(1 for r in self.rows if r.choice != KEEP)
        if hasattr(self, "extras_scroll"):
            self.extras_scroll.setVisible(bool(self.extras))
        self.totals.setText(
            f"<b>{aircraft} aircraft</b> in the air wing after applying"
            + (f" · {changed} base(s) changed" if changed else "")
            + (f" · {len(self.extras)} squadron(s) added" if self.extras else "")
        )

    @property
    def has_changes(self) -> bool:
        return bool(self.extras) or any(r.choice != KEEP for r in self.rows)

    # ----------------------------------------------------------- actions

    def pick_first_everywhere(self) -> None:
        for row in self.rows:
            if row.has_presets:
                row.pick_first_preset()

    def keep_everywhere(self) -> None:
        for row in self.rows:
            row.keep()

    def add_extra(self) -> None:
        from qt_ui.windows.AirWingConfigurationDialog import SquadronConfigPopup

        ranked = ranked_bases(self.game, self.coalition)
        types = {
            a
            for a in faction_aircraft(self.coalition.faction)
            if any(r.base.can_operate(a) for r in ranked)
        }
        popup = SquadronConfigPopup(
            None, types, ranked, self.coalition.air_wing.squadron_defs
        )
        if popup.exec_() != QDialog.DialogCode.Accepted:
            return
        aircraft = popup.aircraft_type_selector.currentData()
        base = popup.squadron_base_selector.currentData()
        task = popup.primary_task_selector.selected_task
        if aircraft is None or base is None or task is None:
            return
        extra = ExtraSquadron(
            self,
            aircraft,
            base,
            task,
            popup.squadron_def_selector.currentData(),
            popup.squadron_base_selector.currentText(),
        )
        self.extras.append(extra)
        self.extras_list.addWidget(extra.widget)
        self.update_totals()

    def remove_extra(self, extra: ExtraSquadron) -> None:
        if extra in self.extras:
            self.extras.remove(extra)
        extra.widget.setParent(None)  # type: ignore[call-overload]
        extra.widget.deleteLater()
        self.update_totals()

    def apply(self) -> int:
        """Makes the chosen squadrons; returns how many were created. The
        page is then listed afresh."""
        created = 0
        for row in self.rows:
            try:
                created += row.apply()
            except Exception:
                logging.exception(f"Could not apply the preset at {row.base}")
        for extra in self.extras:
            extra.apply()
            created += 1
        self.rebuild()
        return created


class AirWingSetupDialog(QDialog):
    def __init__(self, game: Game, aircraft_present: bool, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.game = game
        self.aircraft_present = aircraft_present
        self.setWindowTitle("Air Wing Setup")
        self.resize(1200, 900)
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                min(1200, int(available.width() * 0.9)),
                min(900, int(available.height() * 0.9)),
            )

        layout = QVBoxLayout(self)
        intro = QLabel(
            "<b>Set up each side's air wing.</b> 1: pick a preset for each base. "
            "2: add more aircraft if you like. 3: click <b>Apply and continue</b>. "
            "You can save the result as a config and load it in another campaign."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.tabs = QTabWidget()
        self.pages: list[SideSetupPage] = []
        for coalition in game.coalitions:
            page = SideSetupPage(game, coalition, aircraft_present)
            name = "Blue" if coalition.player.is_blue else "Red"
            self.tabs.addTab(page, f"{name}: {coalition.faction.name}")
            self.pages.append(page)
        layout.addWidget(self.tabs, stretch=1)

        from qt_ui.windows.QPlayerSeatDialog import PlayerSeatControls

        seat_box = QGroupBox(
            "Your seat: what you'd like to fly (you can change it later from the "
            "Your flight tab)"
        )
        seat_layout = QVBoxLayout(seat_box)
        self.seat_controls = PlayerSeatControls(game)
        seat_layout.addLayout(self.seat_controls)
        layout.addWidget(seat_box)

        buttons = QHBoxLayout()
        advanced = QPushButton("Advanced editor…")
        advanced.setToolTip(
            "Applies the choices so far, then opens the squadron-by-squadron "
            "editor (names, liveries, tasks, sizes)."
        )
        advanced.clicked.connect(self.open_advanced_editor)
        buttons.addWidget(advanced)
        load = QPushButton("Load config…")
        load.clicked.connect(self.load_config)
        buttons.addWidget(load)
        save = QPushButton("Save config…")
        save.setToolTip("Applies the choices so far and saves this side's air wing.")
        save.clicked.connect(self.save_config)
        buttons.addWidget(save)
        buttons.addStretch()
        apply = QPushButton("Apply and continue")
        apply.setProperty("style", "btn-accept")
        apply.setDefault(True)
        apply.clicked.connect(self.accept)
        buttons.addWidget(apply)
        layout.addLayout(buttons)

    @property
    def current_page(self) -> SideSetupPage:
        page = self.tabs.currentWidget()
        assert isinstance(page, SideSetupPage)
        return page

    def apply_all(self) -> int:
        return sum(page.apply() for page in self.pages)

    def refresh_seat(self) -> None:
        try:
            self.seat_controls.refresh_squadrons()
        except Exception:
            logging.exception("Could not list the squadrons for the seat")

    def open_advanced_editor(self) -> None:
        from qt_ui.windows.AirWingConfigurationDialog import (
            AirWingConfigurationDialog,
        )

        self.apply_all()
        AirWingConfigurationDialog(self.game, self.aircraft_present, self).exec_()
        for page in self.pages:
            page.rebuild()
        self.refresh_seat()

    def save_config(self) -> None:
        from qt_ui.windows.AirWingConfigurationDialog import air_wing_config_data

        page = self.current_page
        dialog = QFileDialog(
            self,
            caption="Save Air Wing Config",
            directory=str(airwing_dir()),
            filter="*.yaml;*.yml",
        )
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDefaultSuffix("yaml")
        if not dialog.exec_():
            return
        page.apply()
        self.refresh_seat()
        filename = dialog.selectedFiles()[0]
        with open(filename, "w", encoding="utf-8") as f:
            yaml.safe_dump(air_wing_config_data(page.coalition), f, allow_unicode=True)
        QMessageBox.information(
            self, "Air wing saved", f"Saved to {Path(filename).name}."
        )

    def load_config(self) -> None:
        from qt_ui.windows.AirWingConfigurationDialog import (
            load_air_wing_config_data,
        )

        page = self.current_page
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Load Air Wing Config",
            str(airwing_dir()),
            "*.yaml;*.yml",
        )
        if not filename:
            return
        with open(filename, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        try:
            load_air_wing_config_data(page.coalition, data)
        except Exception as ex:
            logging.exception(f"Could not load the air wing config {filename}")
            QMessageBox.warning(self, "Could not load", str(ex))
            return
        page.rebuild()
        self.refresh_seat()

    def accept(self) -> None:
        self.apply_all()
        self.refresh_seat()
        try:
            self.seat_controls.apply()
        except Exception:
            logging.exception("Could not keep the player's seat")
        super().accept()

    def reject(self) -> None:
        if any(page.has_changes for page in self.pages):
            result = QMessageBox.question(
                self,
                "Discard the choices?",
                "Continue with the campaign's own air wing and discard the presets "
                "picked here?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        super().reject()
