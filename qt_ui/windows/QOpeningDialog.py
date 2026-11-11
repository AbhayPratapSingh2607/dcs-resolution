"""The opening choices (M4), shown when you press Begin Campaign: H-hour and
the opening emphasis (T7), the pre-war reconnaissance areas (T5) and the
strategic surprise (T8). Begin Campaign resolves them (game.opening)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.opening import (
    Emphasis,
    H_HOURS,
    Surprise,
    commander_recon,
    opening_of,
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
        self.resize(560, 640)
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
        missiles, sized = salvo_size(game)
        salvo = QLabel(
            f"Opening missile strikes: {missiles} cruise missiles ({sized})."
            if missiles
            else f"No opening missile strikes ({sized})."
        )
        salvo.setWordWrap(True)
        form.addRow(salvo)
        layout.addWidget(choices)

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
        plan.recon[True] = self._checked()
        super().accept()
