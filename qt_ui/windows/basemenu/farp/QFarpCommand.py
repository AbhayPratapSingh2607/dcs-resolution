from __future__ import annotations

from typing import Optional, cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.server import EventStream
from game.sim import GameUpdateEvents
from game.squadrons import Squadron
from game.squadrons.detachments import (
    create_detachment,
    detachment_errors,
    detachments_at,
    free_farp_slots,
    max_detachment_size,
    recall_detachment,
)
from game.theater import ParkingType
from game.theater.dynamicfarp import DynamicFarp
from game.utils import meters
from qt_ui.models import GameModel
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal


class QFarpCommand(QFrame):
    """Base menu tab for managing a player-established FARP."""

    def __init__(self, farp: DynamicFarp, game_model: GameModel) -> None:
        super().__init__()
        self.farp = farp
        self.game_model = game_model

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.main_layout.addWidget(self.status_label)

        self.detachments_box = QGroupBox("Stationed detachments")
        self.detachments_layout = QVBoxLayout()
        self.detachments_box.setLayout(self.detachments_layout)
        self.main_layout.addWidget(self.detachments_box)

        assign_box = QGroupBox("Assign a detachment")
        assign_layout = QHBoxLayout()
        assign_box.setLayout(assign_layout)
        self.squadron_selector = QComboBox()
        self.squadron_selector.currentIndexChanged.connect(self._on_squadron_changed)
        assign_layout.addWidget(self.squadron_selector, stretch=3)
        self.count_spinner = QSpinBox()
        self.count_spinner.setMinimum(1)
        assign_layout.addWidget(QLabel("Aircraft:"))
        assign_layout.addWidget(self.count_spinner)
        self.assign_button = QPushButton("Assign")
        self.assign_button.setProperty("style", "btn-success")
        self.assign_button.clicked.connect(self._assign)
        assign_layout.addWidget(self.assign_button)
        self.main_layout.addWidget(assign_box)

        restrictions = QLabel(self._restrictions_text())
        restrictions.setWordWrap(True)
        self.main_layout.addWidget(restrictions)

        self.main_layout.addStretch()

        dismantle_row = QHBoxLayout()
        dismantle_row.addStretch()
        dismantle_button = QPushButton("Dismantle FARP")
        dismantle_button.setProperty("style", "btn-danger")
        dismantle_button.clicked.connect(self._dismantle)
        dismantle_row.addWidget(dismantle_button)
        self.main_layout.addLayout(dismantle_row)

        self.refresh()

    @property
    def game(self) -> Game:
        game = self.game_model.game
        assert game is not None
        return game

    def _restrictions_text(self) -> str:
        return (
            "Any helicopter can be stationed here and fly any task it is capable "
            "of. Detachments can't purchase aircraft; recall them to reinforce. "
            "If the FARP's fuel is destroyed, the helicopters parked here are lost."
        )

    def _status_text(self) -> str:
        total = self.farp.total_aircraft_parking(ParkingType(True, True, True))
        used = total - free_farp_slots(self.farp)
        lines = [
            f"<b>{self.farp.kind.display_name} FARP</b>",
            f"Helicopter slots: {used}/{total} in use",
            f"Upkeep: ${self.farp.upkeep_per_turn}M per turn",
        ]
        return "<br/>".join(lines)

    def refresh(self) -> None:
        self.status_label.setText(self._status_text())

        while self.detachments_layout.count():
            item = self.detachments_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        detachments = detachments_at(self.farp)
        if not detachments:
            self.detachments_layout.addWidget(QLabel("No helicopters stationed."))
        for det in detachments:
            self.detachments_layout.addWidget(self._detachment_row(det))

        self.squadron_selector.blockSignals(True)
        self.squadron_selector.clear()
        model = cast(QStandardItemModel, self.squadron_selector.model())
        first_enabled: Optional[int] = None
        for squadron, reason in self._candidate_squadrons():
            distance = meters(
                squadron.location.position.distance_to_point(self.farp.position)
            )
            text = (
                f"{squadron} ({squadron.aircraft.display_name}) at "
                f"{squadron.location} - {distance.nautical_miles:.0f}nm"
            )
            if reason is not None:
                text += f" - unavailable: {reason}"
            self.squadron_selector.addItem(text, squadron)
            index = self.squadron_selector.count() - 1
            if reason is not None:
                entry = model.item(index)
                entry.setEnabled(False)
                entry.setToolTip(reason)
            elif first_enabled is None:
                first_enabled = index
        if first_enabled is not None:
            self.squadron_selector.setCurrentIndex(first_enabled)
        self.squadron_selector.blockSignals(False)
        self._on_squadron_changed()

    def _detachment_row(self, det: Squadron) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        row.setLayout(layout)
        layout.addWidget(
            QLabel(
                f"{det} - {det.owned_aircraft}x {det.aircraft.display_name} "
                f"({det.untasked_aircraft} untasked), "
                f"{len(det.active_pilots)} pilots"
            ),
            stretch=1,
        )
        recall = QPushButton("Recall")
        recall.clicked.connect(lambda: self._recall(det))
        layout.addWidget(recall, alignment=Qt.AlignmentFlag.AlignRight)
        return row

    def _candidate_squadrons(self) -> list[tuple[Squadron, Optional[str]]]:
        """Every helicopter squadron that could serve here, eligible ones first.

        Squadrons that can't send a detachment right now are listed with the reason
        rather than hidden, so it's clear why a helicopter type isn't offered.
        """
        candidates: list[tuple[Squadron, Optional[str]]] = []
        for squadron in self.farp.coalition.air_wing.iter_squadrons():
            if squadron.is_detachment or not squadron.aircraft.helicopter:
                continue
            if squadron.location == self.farp:
                continue
            reason: Optional[str] = None
            if max_detachment_size(squadron, self.farp) <= 0:
                errors = detachment_errors(squadron, self.farp, 1)
                reason = errors[0] if errors else "no aircraft available"
            candidates.append((squadron, reason))
        candidates.sort(key=lambda c: c[1] is not None)
        return candidates

    def _selected_squadron(self) -> Optional[Squadron]:
        return self.squadron_selector.currentData()

    def _on_squadron_changed(self) -> None:
        squadron = self._selected_squadron()
        if squadron is None:
            self.count_spinner.setMaximum(1)
            self.assign_button.setEnabled(False)
            return
        size = max_detachment_size(squadron, self.farp)
        self.count_spinner.setMaximum(max(1, size))
        self.assign_button.setEnabled(size > 0)

    def _publish(self, events: GameUpdateEvents) -> None:
        events.update_control_point(self.farp)
        EventStream.put_nowait(events)
        self.game_model.ato_model.replace_from_game(player=True)
        GameUpdateSignal.get_instance().updateBudget(self.game)

    def _assign(self) -> None:
        squadron = self._selected_squadron()
        if squadron is None:
            return
        events = GameUpdateEvents()
        now = self.game_model.sim_controller.current_time_in_sim_if_game_loaded
        try:
            create_detachment(
                squadron, self.farp, self.count_spinner.value(), now, events
            )
        except ValueError as ex:
            QMessageBox.warning(self, "Could not assign detachment", str(ex))
            return
        self._publish(events)
        self.refresh()

    def _recall(self, det: Squadron) -> None:
        events = GameUpdateEvents()
        recall_detachment(det, events)
        self._publish(events)
        self.refresh()

    def _dismantle(self) -> None:
        result = QMessageBox.question(
            self,
            "Dismantle FARP",
            f"Dismantle {self.farp.name}? Stationed helicopters return to their "
            "squadrons and the deployment cost is not refunded.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        events = GameUpdateEvents()
        self.farp.coalition.farps.dismantle(self.farp, events)
        EventStream.put_nowait(events)
        self.game_model.ato_model.replace_from_game(player=True)
        GameUpdateSignal.get_instance().updateBudget(self.game)
        self.window().close()
