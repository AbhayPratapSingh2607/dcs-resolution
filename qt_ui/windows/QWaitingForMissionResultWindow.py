from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Optional

from PySide6 import QtCore
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon, QMovie, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QWidget,
)
from jinja2 import Environment, FileSystemLoader, select_autoescape

from game import Game
from game.ato.flightstate import Uninitialized
from game.debriefing import Debriefing
from game.theater import Player
from game.profiling import logged_duration
from game.server import EventStream
from game.sim import GameUpdateEvents
from qt_ui.simcontroller import SimController
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.QDebriefingWindow import make_plan_report
from qt_ui.windows.farplosses import report_lost_farps


class DebriefingFileWrittenSignal(QObject):
    instance = None
    debriefingReceived = Signal(Debriefing)

    def __init__(self):
        super(DebriefingFileWrittenSignal, self).__init__()
        DebriefingFileWrittenSignal.instance = self

    def sendDebriefing(self, debriefing: Debriefing):
        self.debriefingReceived.emit(debriefing)

    @staticmethod
    def get_instance() -> DebriefingFileWrittenSignal:
        return DebriefingFileWrittenSignal.instance


DebriefingFileWrittenSignal()


class QWaitingForMissionResultWindow(QDialog):
    def __init__(
        self,
        game: Game,
        sim_controller: SimController,
        parent: Optional[QWidget] = None,
        simulated: Optional[Debriefing] = None,
    ) -> None:
        super(QWaitingForMissionResultWindow, self).__init__(parent=parent)
        self.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.game = game
        self.sim_controller = sim_controller
        self.setWindowTitle(
            "Simulated turn results"
            if simulated is not None
            else "Waiting for mission completion."
        )
        self.setWindowIcon(QIcon("./resources/icon.png"))
        self.setMinimumHeight(570)

        self.initUi()
        self.wait_thread = None
        if simulated is not None:
            # The turn was fought by the combat model; there is no DCS mission
            # to wait for.
            self.manually_submit2.setVisible(False)
            self.updateLayout(simulated)
            return
        DebriefingFileWrittenSignal.get_instance().debriefingReceived.connect(
            self.updateLayout
        )
        self.wait_thread = sim_controller.wait_for_debriefing(
            lambda debriefing: self.on_debriefing_update(debriefing)
        )

    def initUi(self):
        self.layout = QGridLayout()

        header = QLabel(self)
        header.setGeometry(0, 0, 655, 106)
        pixmap = QPixmap("./resources/ui/conflict.png")
        header.setPixmap(pixmap)
        self.layout.addWidget(header, 0, 0)

        self.gridLayout = QGridLayout()

        jinja = Environment(
            loader=FileSystemLoader("resources/ui/templates"),
            autoescape=select_autoescape(
                disabled_extensions=("",),
                default_for_string=True,
                default=True,
            ),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.instructions_text = QTextBrowser()
        self.instructions_text.setHtml(
            jinja.get_template("mission_start_EN.j2").render()
        )
        self.instructions_text.setOpenExternalLinks(True)
        self.gridLayout.addWidget(self.instructions_text, 1, 0)

        progress = QLabel("")
        progress.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        progress_bar = QMovie("./resources/ui/loader.gif")
        progress.setMovie(progress_bar)

        self.actions = QGroupBox("Actions :")
        self.actions_layout = QHBoxLayout()
        self.actions.setLayout(self.actions_layout)

        self.manually_submit = QPushButton("Manually Submit [Advanced users]")
        self.manually_submit.clicked.connect(self.submit_manually)
        self.actions_layout.addWidget(self.manually_submit)
        self.cancel = QPushButton("Abort mission")
        self.cancel.clicked.connect(self.reset_game_state)
        self.actions_layout.addWidget(self.cancel)
        self.gridLayout.addWidget(self.actions, 2, 0)

        self.actions2 = QGroupBox("Actions :")
        self.actions2_layout = QHBoxLayout()
        self.actions2.setLayout(self.actions2_layout)
        self.manually_submit2 = QPushButton("Manually Submit [Advanced users]")
        self.manually_submit2.clicked.connect(self.submit_manually)
        self.actions2_layout.addWidget(self.manually_submit2)
        self.cancel2 = QPushButton("Abort mission")
        self.cancel2.clicked.connect(self.reset_game_state)
        self.actions2_layout.addWidget(self.cancel2)
        self.proceed = QPushButton("Accept results")
        self.proceed.setProperty("style", "btn-success")
        self.proceed.clicked.connect(self.process_debriefing)
        self.actions2_layout.addWidget(self.proceed)

        progress_bar.start()
        self.layout.addLayout(self.gridLayout, 1, 0)
        self.setLayout(self.layout)

    @staticmethod
    def add_update_row(
        description: str, blue: int, red: int, layout: QGridLayout
    ) -> None:
        row = layout.rowCount()
        layout.addWidget(QLabel(f"<b>{description}</b>"), row, 0)
        layout.addWidget(QLabel(f"{blue}"), row, 1)
        layout.addWidget(QLabel(f"{red}"), row, 2)

    def updateLayout(self, debriefing: Debriefing) -> None:
        updateBox = QGroupBox("Mission status")
        update_layout = QGridLayout()
        updateBox.setLayout(update_layout)
        self.debriefing = debriefing

        blue = debriefing.loss_counts(Player.BLUE)
        red = debriefing.loss_counts(Player.RED)

        update_layout.addWidget(
            QLabel(f"<b>{debriefing.player_country} (OwnFor)</b>"), 0, 1
        )
        update_layout.addWidget(
            QLabel(f"<b>{debriefing.enemy_country} (OpFor)</b>"), 0, 2
        )

        rows = [
            ("Aircraft lost", blue.aircraft, red.aircraft),
            ("Front line units lost", blue.front_line, red.front_line),
            ("Motorpool units lost", blue.motorpool, red.motorpool),
            ("Convoy units lost", blue.convoy, red.convoy),
            ("Shipping cargo lost", blue.cargo_ships, red.cargo_ships),
            ("Airlift cargo lost", blue.airlift_cargo, red.airlift_cargo),
            ("Ground Objects lost", blue.ground_objects, red.ground_objects),
            ("Scenery Objects lost", blue.scenery, red.scenery),
            ("Bases lost", blue.bases_lost, red.bases_lost),
            ("Runways destroyed", blue.runways_destroyed, red.runways_destroyed),
            ("Pilots rescued (CSAR)", blue.pilots_rescued, red.pilots_rescued),
        ]
        for label, blue_count, red_count in rows:
            self.add_update_row(label, blue_count, red_count, update_layout)

        # Clear previous content of the window
        for i in reversed(range(self.gridLayout.count())):
            try:
                self.gridLayout.itemAt(i).widget().setParent(None)
            except:
                logging.exception("Failed to clear window")

        # Set new window content
        self.gridLayout.addWidget(updateBox, 0, 0)
        log = getattr(debriefing, "simulation_log", [])
        if log:
            self.gridLayout.addWidget(self.combat_log_box(log), 3, 0)
            self._grow_for_log()

        if not debriefing.state_data.mission_ended:
            self.gridLayout.addWidget(QLabel("<b>Mission is being played</b>"), 1, 0)
            self.gridLayout.addWidget(self.actions, 2, 0)
        else:
            self.gridLayout.addWidget(QLabel("<b>Mission is over</b>"), 1, 0)
            self.gridLayout.addWidget(self.actions2, 2, 0)

    #: Window height once the combat log shows: the 570 px default clipped the
    #: log under the actions. Capped to the screen.
    LOG_WINDOW_HEIGHT = 900

    def _grow_for_log(self) -> None:
        height = max(self.LOG_WINDOW_HEIGHT, self.sizeHint().height())
        screen = self.screen()
        if screen is not None:
            height = min(height, int(screen.availableGeometry().height() * 0.9))
        if self.height() < height:
            self.setMinimumHeight(height)
            self.resize(self.width(), height)

    @staticmethod
    def combat_log_box(log: list) -> QGroupBox:
        """Narrative of the combat resolved while fast forwarding."""
        box = QGroupBox(f"Combat resolved while fast forwarding ({len(log)} events)")
        layout = QGridLayout()
        box.setLayout(layout)
        browser = QTextBrowser()
        colors = {"blue": "#5f9ee8", "red": "#e86060"}
        lines = []
        for entry in log:
            color = colors.get(entry.side, "#c8c8c8")
            text = html.escape(entry.text)
            lines.append(
                f"<span style='color:#888'>{entry.time:%H:%M:%S}</span> "
                f"<b>{html.escape(entry.domain.value)}</b> "
                f"<span style='color:{color}'>{text}</span>"
            )
        browser.setHtml("<br>".join(lines))
        browser.setMinimumHeight(320)
        layout.addWidget(browser, 0, 0)
        return box

    def on_debriefing_update(self, debriefing: Debriefing) -> None:
        try:
            logging.info("On Debriefing update")
            logging.debug(debriefing)
            DebriefingFileWrittenSignal.get_instance().sendDebriefing(debriefing)
        except Exception:
            logging.exception("Got an error while sending debriefing")

    def process_debriefing(self):
        # Turn processing takes a while: the same busy dialog as Take off,
        # with the work on a worker thread so the window stays responsive and
        # shows which step it is on. It can't be cancelled: a turn processed
        # halfway would leave the campaign inconsistent.
        from qt_ui.widgets.busy import BusyDialog

        with report_lost_farps(self.game, self.parentWidget()):
            with logged_duration("Turn processing"):
                with BusyDialog(self, "End of mission", cancellable=False) as busy:
                    busy.run(
                        "End of mission detected, processing the mission data…",
                        lambda: self.sim_controller.process_results(self.debriefing),
                    )
                    # The plan report reads this turn's ATO and mission
                    # window; pass_turn replaces both with the next turn's.
                    busy.run(
                        "Writing the debriefing…",
                        lambda: make_plan_report(self.debriefing),
                    )
                    busy.run(
                        "Planning the next turn…",
                        self.game.pass_turn,
                    )
                GameUpdateSignal.get_instance().sendDebriefing(self.debriefing)
                GameUpdateSignal.get_instance().updateGame(self.game)
            self.close()

    def closeEvent(self, evt):
        super(QWaitingForMissionResultWindow, self).closeEvent(evt)
        if self.wait_thread is not None:
            self.wait_thread.stop()

    def submit_manually(self):
        file = QFileDialog.getOpenFileName(
            self, "Select game file to open", filter="json(*.json)", dir="."
        )
        if file[0] != "":
            logging.debug("Processing manually submitted %s", file[0])
            # Stop the current waiting thread as we manually submit the results
            if self.wait_thread is not None:
                self.wait_thread.stop()
            self.on_debriefing_update(
                self.sim_controller.debrief_current_state(Path(file[0]), force_end=True)
            )

    def reject(self):
        self.reset_game_state()
        super().reject()

    def reset_game_state(self):
        self.sim_controller.set_game(self.game)
        events = GameUpdateEvents()
        for _, f in self.game.db.flights.objects.items():
            f.state = Uninitialized(f, self.game.settings)
            events.update_flight(f)
        for cp in self.game.theater.controlpoints:
            cp.release_parking_slots()
        from game.warfare.firemissions import reset_in_mission

        reset_in_mission(self.game)
        GameUpdateSignal.get_instance().updateGame(self.game)
        EventStream().put_nowait(events)
        self.close()
