from datetime import datetime
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
)

import qt_ui.uiconstants as CONST
from game import Game, persistency
from game.ato.flightstate import Uninitialized
from game.ato.package import Package
from game.ato.traveltime import TotEstimator
from game.profiling import logged_duration
from game.server import EventStream
from game.settings.settings import FastForwardStopCondition
from game.sim import GameUpdateEvents
from game.theater.dynamicfarp import FarpKind
from game.utils import meters
from qt_ui.models import GameModel
from qt_ui.simcontroller import SimController
from qt_ui.uiflags import UiFlags
from qt_ui.widgets.QBudgetBox import QBudgetBox
from qt_ui.widgets.QConditionsWidget import QConditionsWidget
from qt_ui.widgets.QFactionsInfos import QFactionsInfos
from qt_ui.widgets.QIntelBox import QIntelBox
from qt_ui.widgets.busy import BusyDialog
from qt_ui.widgets.clientslots import MaxPlayerCount
from qt_ui.widgets.simspeedcontrols import SimSpeedControls
from qt_ui.windows.AirWingDialog import AirWingDialog
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.PendingTransfersDialog import PendingTransfersDialog
from qt_ui.windows.QWaitingForMissionResultWindow import QWaitingForMissionResultWindow
from qt_ui.windows.farplosses import report_lost_farps


class QTopPanel(QFrame):
    def __init__(
        self, game_model: GameModel, sim_controller: SimController, ui_flags: UiFlags
    ) -> None:
        super(QTopPanel, self).__init__()
        self.game_model = game_model
        self.sim_controller = sim_controller
        self.dialog: Optional[QDialog] = None

        self.setMaximumHeight(70)

        self.conditionsWidget = QConditionsWidget(sim_controller)
        self.budgetBox = QBudgetBox(self.game)

        pass_turn_text = "Pass Turn"
        if not self.game or self.game.turn == 0:
            pass_turn_text = "Begin Campaign"
        self.passTurnButton = QPushButton(pass_turn_text)
        self.passTurnButton.setIcon(CONST.ICONS["PassTurn"])
        self.passTurnButton.setProperty("style", "btn-primary")
        self.passTurnButton.clicked.connect(self.passTurn)
        if not self.game:
            self.passTurnButton.setEnabled(False)

        self.proceedButton = QPushButton("Take off")
        self.proceedButton.setIcon(CONST.ICONS["Proceed"])
        self.proceedButton.setProperty("style", "start-button")
        self.proceedButton.clicked.connect(self.launch_mission)
        if not self.game or self.game.turn == 0:
            self.proceedButton.setEnabled(False)

        self.factionsInfos = QFactionsInfos(self.game)

        self.air_wing = QPushButton("Air Wing")
        self.air_wing.setDisabled(True)
        self.air_wing.setProperty("style", "btn-primary")
        self.air_wing.clicked.connect(self.open_air_wing)

        self.transfers = QPushButton("Transfers")
        self.transfers.setDisabled(True)
        self.transfers.setProperty("style", "btn-primary")
        self.transfers.clicked.connect(self.open_transfers)

        self.fire_missions = QPushButton("Fire Missions")
        self.fire_missions.setDisabled(True)
        self.fire_missions.setProperty("style", "btn-primary")
        self.fire_missions.setToolTip(
            "Plan cruise missile, missile and artillery strikes for this turn."
        )
        self.fire_missions.clicked.connect(self.open_fire_missions)

        self.wet_wing = QPushButton("Wet Wing")
        self.wet_wing.setProperty("style", "btn-primary")
        self.wet_wing.setToolTip(
            "Place a Wet Wing FARP (set up by a C-130) on the map: more "
            "helicopters, costs more."
        )
        self.wet_wing.clicked.connect(lambda: self.place_farp(FarpKind.WET_WING))

        self.fat_cow = QPushButton("Fat Cow")
        self.fat_cow.setProperty("style", "btn-primary")
        self.fat_cow.setToolTip(
            "Place a Fat Cow FARP (set up by a CH-47) on the map: 2 helicopters, "
            "cheaper."
        )
        self.fat_cow.clicked.connect(lambda: self.place_farp(FarpKind.FAT_COW))

        self.farpBox = QGroupBox("FARPs")
        self.farpBoxLayout = QHBoxLayout()
        self.farpBoxLayout.addWidget(self.wet_wing)
        self.farpBoxLayout.addWidget(self.fat_cow)
        self.farpBox.setLayout(self.farpBoxLayout)
        self.farpBox.setVisible(False)

        self.intel_box = QIntelBox(self.game)

        self.buttonBox = QGroupBox("Misc")
        self.buttonBoxLayout = QHBoxLayout()
        self.buttonBoxLayout.addWidget(self.air_wing)
        self.buttonBoxLayout.addWidget(self.transfers)
        self.buttonBoxLayout.addWidget(self.fire_missions)
        self.buttonBox.setLayout(self.buttonBoxLayout)

        self.simSpeedControls = SimSpeedControls(sim_controller)

        self.proceedBox = QGroupBox("Proceed")
        self.proceedBoxLayout = QHBoxLayout()
        if ui_flags.show_sim_speed_controls:
            self.proceedBoxLayout.addLayout(self.simSpeedControls)
        self.proceedBoxLayout.addLayout(MaxPlayerCount(self.game_model.ato_model))
        self.proceedBoxLayout.addWidget(self.passTurnButton)
        self.proceedBoxLayout.addWidget(self.proceedButton)
        self.proceedBox.setLayout(self.proceedBoxLayout)

        self.controls = [
            self.air_wing,
            self.transfers,
            self.wet_wing,
            self.fat_cow,
            self.simSpeedControls,
            self.passTurnButton,
            self.proceedButton,
        ]

        self.layout = QHBoxLayout()

        self.layout.addWidget(self.factionsInfos)
        self.layout.addWidget(self.conditionsWidget)
        self.layout.addWidget(self.budgetBox)
        self.layout.addWidget(self.intel_box)
        self.layout.addWidget(self.buttonBox)
        self.layout.addWidget(self.farpBox)
        self.layout.addStretch(1)
        self.layout.addWidget(self.proceedBox)

        self.layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(self.layout)

        GameUpdateSignal.get_instance().gameupdated.connect(self.setGame)
        GameUpdateSignal.get_instance().budgetupdated.connect(self.budget_update)

    @property
    def game(self) -> Optional[Game]:
        return self.game_model.game

    def setGame(self, game: Optional[Game]):
        if game is None:
            return

        self.air_wing.setEnabled(True)
        self.transfers.setEnabled(True)
        # From turn 1: turn 0's strikes are the opening salvo.
        self.fire_missions.setEnabled(game.turn >= 1)

        self.conditionsWidget.setCurrentTurn(game.turn, game.conditions)

        if game.conditions.weather.clouds:
            base_m = game.conditions.weather.clouds.base
            base_ft = int(meters(base_m).feet)
            self.conditionsWidget.setToolTip(f"Cloud Base: {base_m}m / {base_ft}ft")
        else:
            self.conditionsWidget.setToolTip("")

        self.intel_box.set_game(game)
        self.budgetBox.setGame(game)
        self.factionsInfos.setGame(game)
        # The game model may not have switched to the new game yet (its handler
        # runs after this one), so check the game being loaded.
        self.update_farp_buttons(game)

        self.setControls(True)

        if game.turn > 0:
            self.passTurnButton.setText("Pass Turn")
        elif game.turn == 0:
            self.passTurnButton.setText("Begin Campaign")
            self.proceedButton.setEnabled(False)
            self.simSpeedControls.setEnabled(False)
        else:
            raise RuntimeError(f"game.turn out of bounds!\n  value = {game.turn}")

    def update_farp_buttons(self, game: Optional[Game] = None) -> None:
        """Shows the FARP buttons only while dynamic FARPs are enabled."""
        if game is None:
            game = self.game
        self.farpBox.setVisible(game is not None and game.settings.enable_dynamic_farps)

    @staticmethod
    def place_farp(kind: FarpKind) -> None:
        EventStream.put_nowait(GameUpdateEvents().begin_farp_placement(kind.value))

    def open_air_wing(self):
        self.dialog = AirWingDialog(self.game_model, self.window())
        self.dialog.show()

    def open_fire_missions(self) -> None:
        from qt_ui.windows.QFireMissionsDialog import QFireMissionsDialog

        self.dialog = QFireMissionsDialog(self.game, self.window())
        self.dialog.show()

    def open_transfers(self):
        self.dialog = PendingTransfersDialog(self.game_model)
        self.dialog.show()

    def passTurn(self):
        if self.game.turn == 0:
            # Begin Campaign: the opening choices first (game.opening, M4).
            from qt_ui.windows.QOpeningDialog import QOpeningDialog

            if not QOpeningDialog(self.game, self.window()).exec():
                return
        with report_lost_farps(self.game, self.window()):
            with logged_duration("Skipping turn"):
                self.game.pass_turn(no_action=True)
                GameUpdateSignal.get_instance().updateGame(self.game)
                state = self.game_model.game.check_win_loss()
                GameUpdateSignal.get_instance().gameStateChanged(state)
                self.proceedButton.setEnabled(True)

    def negative_start_packages(self, now: datetime) -> List[Package]:
        packages = []
        for package in self.game_model.ato_model.ato.packages:
            if not package.flights:
                continue
            for flight in package.flights:
                if isinstance(flight.state, Uninitialized):
                    flight.state.reinitialize(now)
                if flight.state.is_waiting_for_start:
                    startup = flight.flight_plan.startup_time()
                    if startup < now:
                        packages.append(package)
                        break
        return packages

    @staticmethod
    def fix_tots(packages: List[Package]) -> None:
        for package in packages:
            estimator = TotEstimator(package)
            package.time_over_target = estimator.earliest_tot()

    def confirm_no_client_launch(self) -> bool:
        result = QMessageBox.question(
            self,
            "Continue without player pilots?",
            (
                "No player pilots have been assigned to flights. Continuing will allow "
                "the AI to perform the mission, but players will be unable to "
                "participate.<br />"
                "<br />"
                "To assign player pilots to a flight, select a package from the "
                "Packages panel on the left of the main window, and then a flight from "
                "the Flights panel below the Packages panel. The edit button below the "
                "Flights panel will allow you to assign specific pilots to the flight. "
                "If you have no player pilots available, the checkbox next to the "
                "name will convert them to a player.<br />"
                "<br />Click 'Yes' to continue with an AI only mission"
                "<br />Click 'No' if you'd like to make more changes."
            ),
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return result == QMessageBox.StandardButton.Yes

    def confirm_negative_start_time(self, negative_starts: List[Package]) -> bool:
        formatted = "<br />".join(
            [f"{p.primary_task} {p.target.name}" for p in negative_starts]
        )
        mbox = QMessageBox(
            QMessageBox.Icon.Question,
            "Continue with past start times?",
            (
                "Some flights in the following packages have start times set "
                "earlier than mission start time:<br />"
                "<br />"
                f"{formatted}<br />"
                "<br />"
                "Flight start times are estimated based on the package TOT, so it "
                "is possible that not all flights will be able to reach the "
                "target area at their assigned times.<br />"
                "<br />"
                "You can either continue with the mission as planned, with the "
                "misplanned flights potentially flying too fast and/or missing "
                "their rendezvous; automatically fix negative TOTs; or cancel "
                "mission start and fix the packages manually."
            ),
            parent=self,
        )
        auto = mbox.addButton(
            "Fix TOTs automatically", QMessageBox.ButtonRole.ActionRole
        )
        ignore = mbox.addButton(
            "Continue without fixing", QMessageBox.ButtonRole.DestructiveRole
        )
        cancel = mbox.addButton(QMessageBox.StandardButton.Cancel)
        mbox.setEscapeButton(cancel)
        mbox.exec_()
        clicked = mbox.clickedButton()
        if clicked == auto:
            self.fix_tots(negative_starts)
            return True
        elif clicked == ignore:
            return True
        return False

    def check_no_missing_pilots(self) -> bool:
        missing_pilots = []
        for package in self.game.blue.ato.packages:
            for flight in package.flights:
                if flight.missing_pilots > 0:
                    missing_pilots.append((package, flight))

        if not missing_pilots:
            return False

        formatted = "<br />".join(
            [f"{p.primary_task} {p.target}: {f}" for p, f in missing_pilots]
        )
        mbox = QMessageBox(
            QMessageBox.Icon.Critical,
            "Flights are missing pilots",
            (
                "The following flights are missing one or more pilots:<br />"
                "<br />"
                f"{formatted}<br />"
                "<br />"
                "You must either assign pilots to those flights or cancel those "
                "missions."
            ),
            parent=self,
        )
        mbox.setEscapeButton(mbox.addButton(QMessageBox.StandardButton.Close))
        mbox.exec_()
        return True

    def launch_mission(self):
        """Finishes planning and waits for mission completion."""
        if (
            self.game.settings.fast_forward_stop_condition
            is FastForwardStopCondition.END_OF_TURN
        ):
            self.simulate_turn()
            return

        from game.sim import atoperiod

        full_turn = atoperiod.period(self.game) is not None and not atoperiod.is_focused(
            self.game
        )
        if full_turn:
            # P4: the mission starts when your flight starts up. Without a
            # player flight, pick one, fast-forward, or fly an AI-only window.
            if not self.place_mission_window():
                return
        elif not self.game.ato_has_clients() and not self.confirm_no_client_launch():
            return

        if self.check_no_missing_pilots():
            return

        if atoperiod.period(self.game) is not None:
            if not full_turn and atoperiod.max_window_offset_min(self.game) > 0:
                from qt_ui.windows.QDcsWindowDialog import QDcsWindowDialog

                if not QDcsWindowDialog(self.game, self).exec():
                    return
            with BusyDialog(self, "Take off") as busy:
                with logged_duration("Resolving the ATO period before the DCS window"):
                    busy.run(
                        "Fighting the period up to your mission with the combat "
                        "model…",
                        lambda: self.sim_controller.advance_to_window(
                            busy.should_stop
                        ),
                    )
            if busy.should_stop():
                return

        negative_starts = self.negative_start_packages(
            self.sim_controller.current_time_in_sim
        )
        if negative_starts:
            if not self.confirm_negative_start_time(negative_starts):
                return

        with BusyDialog(self, "Take off") as busy:
            if self.game.settings.fast_forward_stop_condition not in [
                FastForwardStopCondition.DISABLED,
                FastForwardStopCondition.MANUAL,
            ]:
                with logged_duration("Simulating to first contact"):
                    busy.run(
                        "Simulating to first contact…",
                        lambda: self.sim_controller.run_to_first_contact(
                            busy.should_stop
                        ),
                    )
            if busy.should_stop():
                return
            busy.run(
                "Generating the DCS mission…",
                lambda: self.sim_controller.generate_miz(
                    persistency.mission_path_for("retribution_nextturn.miz")
                ),
            )
        if busy.should_stop():
            # Generating can't stop halfway; the mission is written but
            # nothing waits for it. Take off again to fly it.
            return

        waiting = QWaitingForMissionResultWindow(self.game, self.sim_controller, self)
        waiting.exec_()

    def place_mission_window(self) -> bool:
        """Full turns: the DCS window follows the player's flight. Returns
        False when the launch should stop here."""
        from game.sim import atoperiod

        if atoperiod.align_window_to_players(self.game):
            late = atoperiod.late_player_flights(self.game)
            if late:
                bounds = atoperiod.window(self.game)
                names = "<br />".join(
                    f"{f.squadron.name} {f.flight_type.value} {f.package.target.name} "
                    f"(startup {f.flight_plan.startup_time():%H:%M})"
                    for f in late[:6]
                )
                result = QMessageBox.question(
                    self,
                    "A player flight starts late",
                    (
                        f"The mission starts at {bounds[0]:%H:%M}, when the first "  # type: ignore[index]
                        f"player flight starts up, and the planned mission window "
                        f"ends at {bounds[1]:%H:%M}. These player flights start "  # type: ignore[index]
                        f"after that, so they will be a long wait in DCS:<br /><br />"
                        f"{names}<br /><br />Fly anyway?"
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                return result == QMessageBox.StandardButton.Yes
            return True

        box = QMessageBox(self)
        box.setWindowTitle("No player flight")
        box.setText(
            "You are not in any flight. Take one from the <b>Your flight</b> tab "
            "or the Flights panel, fast-forward the whole turn with the combat "
            "model, or fly an AI-only mission in a window of your choice."
        )
        fast_forward = box.addButton("Fast-forward the turn", QMessageBox.ButtonRole.AcceptRole)
        ai_only = box.addButton("Fly AI-only, pick a window", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Back", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is fast_forward:
            self.simulate_turn()
            return False
        if clicked is ai_only:
            if atoperiod.max_window_offset_min(self.game) > 0:
                from qt_ui.windows.QDcsWindowDialog import QDcsWindowDialog

                return bool(QDcsWindowDialog(self.game, self).exec())
            return True
        return False

    def simulate_turn(self) -> None:
        """Fights the whole turn with the combat model instead of DCS."""
        if self.check_no_missing_pilots():
            return
        with BusyDialog(self, "Fast-forward") as busy:
            with logged_duration("Simulating entire turn"):
                busy.run(
                    "Fighting the whole turn with the combat model…",
                    lambda: self.sim_controller.simulate_whole_turn(
                        busy.should_stop
                    ),
                )
                if busy.should_stop():
                    return
                debriefing = busy.run(
                    "Collecting the results…", self.sim_controller.debrief_simulated
                )
        waiting = QWaitingForMissionResultWindow(
            self.game, self.sim_controller, self, simulated=debriefing
        )
        waiting.exec_()

    def budget_update(self, game: Game):
        self.budgetBox.setGame(game)

    def setControls(self, enabled: bool):
        for controller in self.controls:
            controller.setEnabled(enabled)

    def check_for_contact(self) -> bool:
        if (
            len(self.game.blue.ato.packages) == 0
            and len(self.game.red.ato.packages) == 0
        ):
            mbox = QMessageBox(
                QMessageBox.Icon.Critical,
                "No flights planned",
                (
                    "No flights are planned and fast forward to first contact "
                    "is enabled. You must either plan flights or disable fast forward."
                ),
                parent=self,
            )
            mbox.setEscapeButton(mbox.addButton(QMessageBox.StandardButton.Close))
            mbox.exec_()
            return False
        return True
