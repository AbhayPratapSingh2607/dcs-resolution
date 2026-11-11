"""The opening choices (M4), shown when you press Begin Campaign: H-hour and
the opening emphasis (T7), the pre-war reconnaissance areas (T5), the
strategic surprise (T8) and the planned opening missile strikes (T9), which can
be turned off. Begin Campaign resolves them (game.opening)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.opening import (
    Emphasis,
    H_HOURS,
    Surprise,
    commander_recon,
    missile_strikes_enabled,
    opening_of,
    planned_salvo,
    recon_candidates,
    recon_tasks,
    salvo_size,
)
from game.theater.player import Player


class QOpeningDialog(QDialog):
    def __init__(self, game: Game, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game = game
        self.setWindowTitle("The opening")
        self.resize(620, 820)
        plan = opening_of(game)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Begin Campaign starts the war: the opening missile strikes fly, both "
            "sides' reconnaissance reports, and turn 1 is planned around your "
            "choices. The turn 1 briefing opens with the estimate and the BDA."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        choices = QGroupBox("Opening choices")
        form = QFormLayout(choices)
        self.h_hour = QComboBox()
        self.h_hour.addItem(
            f"Campaign default ({game.conditions.start_time:%H:%M})", None
        )
        for hour in H_HOURS:
            self.h_hour.addItem(f"{hour:02d}:00 – {(hour + 6) % 24:02d}:00", hour)
        index = self.h_hour.findData(plan.h_hour)
        self.h_hour.setCurrentIndex(max(0, index))
        self.h_hour.setToolTip("Which 6 hour period of the day the war starts in.")
        form.addRow("H-hour:", self.h_hour)
        self.emphasis = QComboBox()
        for emphasis in Emphasis:
            self.emphasis.addItem(emphasis.value, emphasis)
        self.emphasis.setCurrentIndex(self.emphasis.findData(plan.emphasis))
        self.emphasis.setToolTip(
            "Weights the turn 1 target list and the opening missile strikes."
        )
        form.addRow("Opening emphasis:", self.emphasis)
        self.surprise = QComboBox()
        for surprise in Surprise:
            self.surprise.addItem(surprise.value, surprise)
        current = getattr(game.settings, "strategic_surprise", Surprise.PARTIAL)
        self.surprise.setCurrentIndex(max(0, self.surprise.findData(current)))
        self.surprise.setToolTip(
            "How ready the enemy is at H-hour: its SAMs, radars, decoys, "
            "aircraft and alert fighters."
        )
        form.addRow("Strategic surprise:", self.surprise)
        layout.addWidget(choices)

        layout.addWidget(self._salvo_box(), 1)

        self.tasks = recon_tasks(game, Player.BLUE)
        recon = QGroupBox(f"Pre-war reconnaissance ({self.tasks} areas)")
        recon_layout = QVBoxLayout(recon)
        note = QLabel(
            "Each area raises what intelligence knows within 40 nm of the base. "
            "The enemy reconnoitres its own."
        )
        note.setWordWrap(True)
        recon_layout.addWidget(note)
        self.areas = QListWidget()
        chosen = set(plan.recon.get(True) or commander_recon(game, Player.BLUE))
        for cp in recon_candidates(game, Player.BLUE):
            item = QListWidgetItem(cp.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if cp.name in chosen else Qt.CheckState.Unchecked
            )
            self.areas.addItem(item)
        self.areas.itemChanged.connect(self._limit)
        recon_layout.addWidget(self.areas)
        self.count = QLabel()
        recon_layout.addWidget(self.count)
        layout.addWidget(recon, 1)
        self._limit()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Begin Campaign")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    #: How the salvo's target classes read in the list.
    CLASS_NAMES = {
        "airfield": "Airfield (runway and parked aircraft)",
        "sam_lorad": "Long-range SAM",
        "sam_merad": "Medium-range SAM",
        "ewr": "Early warning radar",
        "c2_node": "Command and control",
        "power": "Power plant",
        "fuel": "Fuel depot",
        "ammo": "Ammunition depot",
        "factory": "Factory",
        "building": "Building",
    }

    def _salvo_box(self) -> QGroupBox:
        missiles, sized = salvo_size(self.game)
        box = QGroupBox("Opening missile strikes")
        box_layout = QVBoxLayout(box)
        self.strikes = QCheckBox("Fire the opening salvo")
        self.strikes.setChecked(missiles > 0 and missile_strikes_enabled(self.game))
        self.strikes.setEnabled(missiles > 0)
        self.strikes.setToolTip(
            "Unchecked, the war opens without the cruise missile salvo: the "
            "enemy's airfields and air defenses are untouched on turn 1."
        )
        box_layout.addWidget(self.strikes)
        size = QLabel(
            f"{missiles} cruise missiles: {sized}."
            if missiles
            else f"No opening missile strikes: {sized}."
        )
        size.setWordWrap(True)
        box_layout.addWidget(size)
        self.salvo_table = QTableWidget(0, 4)
        self.salvo_table.setHorizontalHeaderLabels(
            ["Target", "Type", "Near", "Missiles"]
        )
        self.salvo_table.verticalHeader().setVisible(False)
        self.salvo_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.salvo_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.salvo_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.salvo_table.setVisible(missiles > 0)
        box_layout.addWidget(self.salvo_table)
        self.salvo_note = QLabel()
        self.salvo_note.setWordWrap(True)
        box_layout.addWidget(self.salvo_note)
        self.emphasis.currentIndexChanged.connect(lambda *_: self._update_salvo())
        self.strikes.toggled.connect(lambda *_: self._update_salvo())
        self._update_salvo()
        return box

    def _update_salvo(self) -> None:
        planned = planned_salvo(self.game, self.emphasis.currentData())
        self.salvo_table.setRowCount(len(planned))
        for row, shot in enumerate(planned):
            kind = self.CLASS_NAMES.get(
                shot.target_class, shot.target_class.replace("_", " ").capitalize()
            )
            base = getattr(shot.target, "control_point", None)
            near = base.name if base is not None else ""
            for column, text in enumerate((shot.name, kind, near, str(shot.missiles))):
                item = QTableWidgetItem(text)
                if column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.salvo_table.setItem(row, column, item)
        on = self.strikes.isChecked()
        self.salvo_table.setEnabled(on)
        if not self.strikes.isEnabled():
            self.salvo_note.setText("")
        elif not on:
            self.salvo_note.setText(
                "Turned off: the war opens without the salvo, and these targets "
                "are left for your air campaign."
            )
        elif not planned:
            self.salvo_note.setText(
                "Intelligence knows no fixed targets to fire at yet."
            )
        else:
            self.salvo_note.setText(
                f"{len(planned)} targets, chosen against what intelligence knows "
                "now and weighted by the opening emphasis. The pre-war "
                "reconnaissance flown at Begin Campaign can still change the list."
            )

    def _checked(self) -> list[str]:
        return [
            self.areas.item(i).text()
            for i in range(self.areas.count())
            if self.areas.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _limit(self, item: Optional[QListWidgetItem] = None) -> None:
        checked = self._checked()
        if len(checked) > self.tasks and item is not None:
            self.areas.blockSignals(True)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.areas.blockSignals(False)
            checked = self._checked()
        self.count.setText(f"{len(checked)} of {self.tasks} areas chosen")

    def accept(self) -> None:
        plan = opening_of(self.game)
        plan.h_hour = self.h_hour.currentData()
        plan.emphasis = self.emphasis.currentData()
        self.game.settings.strategic_surprise = self.surprise.currentData()
        if self.strikes.isEnabled():
            self.game.settings.opening_missile_strikes = self.strikes.isChecked()
        plan.recon[True] = self._checked()
        super().accept()
