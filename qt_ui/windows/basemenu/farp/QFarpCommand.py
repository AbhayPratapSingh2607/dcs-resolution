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
from game.ato.flightplans.rescueking import is_tanker_king, is_tanker_type
from game.server import EventStream
from game.sim import GameUpdateEvents
from game.squadrons import Squadron
from game.squadrons.detachments import (
    create_detachment,
    detachment_errors,
    detachments_at,
    free_farp_slots,
    is_en_route,
    max_detachment_size,
    recall_detachment,
)
from game.theater import ParkingType
from game.theater.dynamicfarp import DynamicFarp
from game.utils import meters
from qt_ui.models import GameModel
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

#: King aircraft list entry for the KC-130 from outside the air wing.
OUTSIDE_TANKER = "outside_tanker"


def is_tanker_aircraft(squadron: Squadron) -> bool:
    return is_tanker_type(squadron.aircraft)


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

        if farp.is_rescue_king:
            # Enemy fighter bases within reach: a warning, not a refusal.
            try:
                coalition = self.game_model.game.coalition_for(farp.captured)
                warnings = coalition.farps.king_fighter_warnings(farp.position)
            except Exception:
                warnings = []
            if warnings:
                warning = QLabel(" ".join(warnings))
                warning.setWordWrap(True)
                warning.setStyleSheet("color: #ffb347;")
                self.main_layout.addWidget(warning)

        self.king_selector: Optional[QComboBox] = None
        self.king_button: Optional[QPushButton] = None
        #: Index of the aircraft orbiting now in king_selector.
        self._king_current_index: Optional[int] = None
        if farp.is_rescue_king:
            king_box = QGroupBox("King aircraft")
            king_layout = QHBoxLayout()
            king_box.setLayout(king_layout)
            self.king_selector = QComboBox()
            self.king_selector.currentIndexChanged.connect(self._on_king_changed)
            king_layout.addWidget(self.king_selector, stretch=3)
            self.king_button = QPushButton("Change")
            self.king_button.setProperty("style", "btn-success")
            self.king_button.setToolTip(
                "Cancel the current orbit flight and send the selected aircraft "
                "instead. A KC-130 refuels helicopters; a C-130 doesn't."
            )
            self.king_button.clicked.connect(self._change_king_aircraft)
            king_layout.addWidget(self.king_button)
            self.main_layout.addWidget(king_box)

            station_box = QGroupBox("Time on station")
            station_layout = QHBoxLayout()
            station_box.setLayout(station_layout)
            self.on_station_spinner = QSpinBox()
            self.on_station_spinner.setRange(30, 360)
            self.on_station_spinner.setSingleStep(5)
            self.on_station_spinner.setSuffix(" min")
            minutes = farp.king_on_station_minutes
            if minutes is None:
                minutes = self.game.settings.csar_king_on_station
            self.on_station_spinner.setValue(minutes)
            self.on_station_spinner.setToolTip(
                "How long the C-130 stays on its orbit. The rescue helicopters "
                "must appear after it is there and be back before it leaves. "
                "Drag the King on the ATO timeline to move its time."
            )
            station_layout.addWidget(self.on_station_spinner)
            self.on_station_button = QPushButton("Set")
            self.on_station_button.setProperty("style", "btn-success")
            self.on_station_button.clicked.connect(self._set_on_station)
            station_layout.addWidget(self.on_station_button)
            station_layout.addStretch()
            self.main_layout.addWidget(station_box)

        self.detachments_box = QGroupBox("Stationed detachments")
        self.detachments_layout = QVBoxLayout()
        self.detachments_box.setLayout(self.detachments_layout)
        self.main_layout.addWidget(self.detachments_box)

        assign_box = QGroupBox(
            "Send rescue helicopters" if farp.is_rescue_king else "Assign a detachment"
        )
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
        dismantle_button = QPushButton(
            "Remove Rescue King" if farp.is_rescue_king else "Dismantle FARP"
        )
        dismantle_button.setProperty("style", "btn-danger")
        dismantle_button.clicked.connect(self._dismantle)
        dismantle_row.addWidget(dismantle_button)
        self.deploy_button: Optional[QPushButton] = None
        if farp.king_pending:
            # Just placed from the map: closing the menu without this takes it
            # away again (QBaseMenu2._cancel_pending_king).
            self.deploy_button = QPushButton("Deploy King")
            self.deploy_button.setProperty("style", "btn-success")
            self.deploy_button.setToolTip(
                "Confirm the King with the aircraft and helicopters above. "
                "Closing this window instead cancels it."
            )
            self.deploy_button.clicked.connect(self._deploy_king)
            dismantle_row.addWidget(self.deploy_button)
        self.main_layout.addLayout(dismantle_row)

        self.refresh()

    @property
    def game(self) -> Game:
        game = self.game_model.game
        assert game is not None
        return game

    def _restrictions_text(self) -> str:
        if self.farp.is_rescue_king:
            return (
                "Any CSAR-capable helicopter can be sent here; it arrives at once. "
                "They start in the air over the King, fly CSAR only (to the "
                "nearest downed pilot, or a rescue you plan from the King), and "
                "go back to their squadron when the turn ends."
            )
        return (
            "Any helicopter can be stationed here and fly any task it is capable "
            "of. Detachments can't purchase aircraft; recall them to reinforce. "
            "If the FARP's fuel is destroyed, the helicopters parked here are lost."
        )

    def _status_text(self) -> str:
        total = self.farp.total_aircraft_parking(ParkingType(True, True, True))
        used = total - free_farp_slots(self.farp)
        en_route = sum(
            d.owned_aircraft for d in detachments_at(self.farp) if is_en_route(d)
        )
        slots = f"Helicopter slots: {used}/{total} in use"
        if self.farp.is_rescue_king:
            lines = ["<b>Rescue King</b>", self._king_text(), slots]
            if self.farp.king_pending:
                lines.append(
                    "<b>Not deployed yet:</b> choose the aircraft and helicopters, "
                    "then press Deploy King. Closing this window cancels it."
                )
            return "<br/>".join(lines)
        if en_route:
            slots += f" ({en_route} en route, arriving next turn)"
        if not self.farp.established:
            return "<br/>".join(
                [
                    f"<b>{self.farp.kind.display_name} FARP - awaiting equipment</b>",
                    self._setup_text(),
                    "Helicopters can be stationed here once it is set up. Upkeep "
                    f"(${self.farp.upkeep_per_turn}M per turn) starts then.",
                ]
            )
        lines = [
            f"<b>{self.farp.kind.display_name} FARP</b>",
            slots,
            f"Upkeep: ${self.farp.upkeep_per_turn}M per turn",
        ]
        return "<br/>".join(lines)

    def _king_text(self) -> str:
        manager = self.farp.coalition.farps
        flight = manager.king_flight(manager.king_package(self.farp))
        if flight is None:
            return "No C-130 or KC-130 orbits it this turn: pick one below."
        air_wing = list(self.farp.coalition.air_wing.iter_squadrons())
        if flight.squadron in air_wing:
            origin = f"of {flight.squadron}"
        else:
            origin = "from outside your air wing"
        tanker = ", refueling helicopters" if is_tanker_king(flight) else ""
        text = (
            f"A {flight.unit_type.display_name} {origin} circles here this "
            f"turn{tanker}."
        )
        window = manager.king_window(self.farp)
        if window is not None:
            text += f" On station {window[0]:%H:%M}-{window[1]:%H:%M}."
        for _, why in manager.king_conflicts(self.farp):
            text += f"<br/><span style='color:#e8a33d'>⚠ {why}</span>"
        return text

    def _set_on_station(self) -> None:
        from qt_ui.windows.basemenu.farp.kingguard import warn_king_conflicts

        manager = self.farp.coalition.farps
        events = GameUpdateEvents()
        manager.set_king_on_station(self.farp, self.on_station_spinner.value(), events)
        self._publish(events)
        package = manager.king_package(self.farp)
        if package is not None:
            warn_king_conflicts(self, self.game_model, package)
        self.refresh()

    def _setup_text(self) -> str:
        package = self.farp.coalition.farps.setup_package(self.farp)
        if package is None or not package.flights:
            return (
                "No transport is available this turn. One will be tasked when "
                "available."
            )
        flight = package.flights[0]
        how = "land at" if flight.is_helo else "make a low airdrop pass over"
        return (
            f"{flight.unit_type.display_name} from {flight.departure} must {how} "
            "the site this turn. The FARP is set up at the end of the turn if it "
            "does."
        )

    def _refresh_king_selector(self) -> None:
        """Lists the C-130/KC-130 squadrons (and, with no transport needed,
        the KC-130 from outside the air wing) with the current one selected.
        Item data: a Squadron, or OUTSIDE_TANKER."""
        selector = self.king_selector
        if selector is None:
            return
        manager = self.farp.coalition.farps
        current = manager.king_flight(manager.king_package(self.farp))
        air_wing = list(self.farp.coalition.air_wing.iter_squadrons())
        current_squadron = (
            current.squadron
            if current is not None and current.squadron in air_wing
            else None
        )
        selector.blockSignals(True)
        selector.clear()
        model = cast(QStandardItemModel, selector.model())
        selected: Optional[int] = None
        if manager.no_transport_needed:
            selector.addItem(
                "KC-130 tanker from outside your air wing (refuels helicopters)",
                OUTSIDE_TANKER,
            )
            if current is not None and current_squadron is None:
                selected = 0
        for squadron, reason in manager.king_squadrons(
            self.farp.position, current_squadron
        ):
            distance = meters(
                squadron.location.position.distance_to_point(self.farp.position)
            )
            role = (
                "tanker, refuels helicopters"
                if is_tanker_aircraft(squadron)
                else "no refueling"
            )
            text = (
                f"{squadron} ({squadron.aircraft.display_name}, {role}) at "
                f"{squadron.location} - {distance.nautical_miles:.0f}nm"
            )
            if reason is not None:
                text += f" - unavailable: {reason}"
            selector.addItem(text, squadron)
            index = selector.count() - 1
            if reason is not None:
                entry = model.item(index)
                entry.setEnabled(False)
                entry.setToolTip(reason)
            if squadron is current_squadron:
                selected = index
        if selector.count() == 0:
            selector.addItem("No C-130 or KC-130 squadron in your air wing", None)
            model.item(0).setEnabled(False)
        if selected is not None:
            selector.setCurrentIndex(selected)
        self._king_current_index = selected
        selector.blockSignals(False)
        self._on_king_changed()

    def _on_king_changed(self) -> None:
        if self.king_selector is None or self.king_button is None:
            return
        index = self.king_selector.currentIndex()
        data = self.king_selector.currentData()
        item = cast(QStandardItemModel, self.king_selector.model()).item(index)
        self.king_button.setEnabled(
            data is not None
            and item is not None
            and item.isEnabled()
            and index != self._king_current_index
        )

    def _change_king_aircraft(self) -> None:
        if self.king_selector is None:
            return
        data = self.king_selector.currentData()
        if data is None:
            return
        squadron = None if data == OUTSIDE_TANKER else data
        events = GameUpdateEvents()
        now = self.game_model.sim_controller.current_time_in_sim_if_game_loaded
        try:
            flight = self.farp.coalition.farps.set_king_aircraft(
                self.farp, squadron, now, events
            )
        except ValueError as ex:
            QMessageBox.warning(self, "Could not change the King aircraft", str(ex))
            return
        if flight is None:
            QMessageBox.warning(
                self,
                "Could not change the King aircraft",
                "The orbit couldn't be planned; see the log.",
            )
        self._publish(events)
        if flight is not None:
            from qt_ui.windows.basemenu.farp.kingguard import warn_king_conflicts

            warn_king_conflicts(self, self.game_model, flight.package)
        self.refresh()

    def refresh(self) -> None:
        self.status_label.setText(self._status_text())
        self._refresh_king_selector()

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
        if is_en_route(det):
            text = (
                f"{det} - {det.owned_aircraft}x {det.aircraft.display_name}, "
                f"{len(det.active_pilots)} pilots - en route from "
                f"{det.location}, arriving next turn"
            )
            button_text = "Cancel"
            tooltip = f"Cancel the move; the helicopters stay with {det.parent}."
        else:
            text = (
                f"{det} - {det.owned_aircraft}x {det.aircraft.display_name} "
                f"({det.untasked_aircraft} untasked), "
                f"{len(det.active_pilots)} pilots"
            )
            button_text = "Recall"
            tooltip = f"Send the helicopters back to {det.parent}."
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label, stretch=1)
        recall = QPushButton(button_text)
        recall.setToolTip(tooltip)
        recall.clicked.connect(lambda: self._recall(det))
        layout.addWidget(recall, alignment=Qt.AlignmentFlag.AlignRight)
        return row

    def _candidate_squadrons(self) -> list[tuple[Squadron, Optional[str]]]:
        """Every helicopter squadron that could serve here, eligible ones first.

        Squadrons that can't send a detachment right now are listed with the reason
        rather than hidden, so it's clear why a helicopter type isn't offered.
        """
        candidates: list[tuple[Squadron, Optional[str]]] = []
        manager = self.farp.coalition.farps
        for squadron in self.farp.coalition.air_wing.iter_squadrons():
            if squadron.is_detachment or not squadron.aircraft.helicopter:
                continue
            if self.farp.is_rescue_king and not manager.can_rescue_from_king(squadron):
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
            if self.farp.is_rescue_king:
                self.farp.coalition.farps.station_king_helicopters(
                    self.farp, squadron, self.count_spinner.value(), now, events
                )
            else:
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

    def _deploy_king(self) -> None:
        self.farp.king_pending = False
        self.window().close()

    def _dismantle(self) -> None:
        if self.farp.is_rescue_king:
            question = (
                f"Remove {self.farp.name}? Its C-130 and rescue flights are "
                "cancelled and the helicopters go back to their squadrons."
            )
        elif self.farp.established:
            question = (
                f"Dismantle {self.farp.name}? Stationed helicopters return to "
                "their squadrons and the deployment cost is not refunded."
            )
        else:
            question = (
                f"Cancel {self.farp.name}? Its setup flight is cancelled and the "
                "deployment cost is refunded."
            )
        result = QMessageBox.question(
            self,
            "Remove Rescue King" if self.farp.is_rescue_king else "Dismantle FARP",
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        # Removed here: closing the window has nothing left to cancel.
        self.farp.king_pending = False
        events = GameUpdateEvents()
        self.farp.coalition.farps.dismantle(self.farp, events)
        EventStream.put_nowait(events)
        self.game_model.ato_model.replace_from_game(player=True)
        GameUpdateSignal.get_instance().updateBudget(self.game)
        self.window().close()
