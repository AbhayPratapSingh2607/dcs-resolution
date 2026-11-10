"""Your seat (P1): the squadron and mission type the player would like to
fly. One preference per campaign; it never changes the plan, only which of
its flights are offered first."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.ato.flighttype import FlightType
from game.commander.jfacc.seat import (
    PlayerPreference,
    flyable_squadrons,
    offered_mission_types,
    preference_of,
)


class PlayerSeatControls(QFormLayout):
    """The two combo boxes, shared by the dialog and the air wing step."""

    def __init__(self, game: Game, preference: Optional[PlayerPreference] = None) -> None:
        super().__init__()
        self.game = game
        preference = preference or preference_of(game)
        self.squadron = QComboBox()
        self.squadron.addItem("Any squadron", None)
        for squadron in flyable_squadrons(game):
            label = f"{squadron.name} ({squadron.aircraft.display_name}, {squadron.location.name})"
            self.squadron.addItem(label, squadron.id)
            if squadron.id == preference.squadron_id:
                self.squadron.setCurrentIndex(self.squadron.count() - 1)
        self.mission = QComboBox()
        self.mission.addItem("Any mission type", None)
        for task in offered_mission_types(game):
            self.mission.addItem(task.value, task)
            if task is preference.mission_type:
                self.mission.setCurrentIndex(self.mission.count() - 1)
        self.addRow("Squadron", self.squadron)
        self.addRow("Mission type", self.mission)

    def refresh_squadrons(self) -> None:
        """The air wing may have changed (squadrons added or removed)."""
        current = self.squadron.currentData()
        self.squadron.clear()
        self.squadron.addItem("Any squadron", None)
        for squadron in flyable_squadrons(self.game):
            label = f"{squadron.name} ({squadron.aircraft.display_name}, {squadron.location.name})"
            self.squadron.addItem(label, squadron.id)
            if squadron.id == current:
                self.squadron.setCurrentIndex(self.squadron.count() - 1)

    def apply(self) -> PlayerPreference:
        preference = preference_of(self.game)
        preference.squadron_id = self.squadron.currentData()
        mission = self.mission.currentData()
        preference.mission_type = mission if isinstance(mission, FlightType) else None
        return preference


class QPlayerSeatDialog(QDialog):
    def __init__(self, game: Game, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game = game
        self.setWindowTitle("Your seat")
        self.setMinimumWidth(480)
        layout = QVBoxLayout()
        self.setLayout(layout)
        note = QLabel(
            "Which squadron, or which kind of mission, would you like to fly? The "
            "commander's plan never changes for it: each turn you are offered the "
            "best matches from the real plan, your squadron's flights first, then "
            "your mission type, then anything else you can fly. In each, the main "
            "push comes first."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.controls = PlayerSeatControls(game)
        layout.addLayout(self.controls)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        self.controls.apply()
        super().accept()
