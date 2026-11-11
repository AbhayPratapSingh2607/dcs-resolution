import logging
from typing import Callable, Dict, Optional, TypeVar

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from game.debriefing import Debriefing
from game.sim.aftaction import AfterActionReport
from game.theater import Player
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

T = TypeVar("T")


class LossGrid(QGridLayout):
    def __init__(self, debriefing: Debriefing, player: Player) -> None:
        super().__init__()

        self.add_loss_rows(
            debriefing.air_losses.by_type(player), lambda u: u.display_name
        )
        self.add_loss_rows(
            debriefing.front_line_losses_by_type(player), lambda u: str(u)
        )
        self.add_loss_rows(
            debriefing.motorpool_losses_by_type(player),
            lambda u: f"{u} from motorpool",
        )
        self.add_loss_rows(
            debriefing.convoy_losses_by_type(player), lambda u: f"{u} from convoy"
        )
        self.add_loss_rows(
            debriefing.cargo_ship_losses_by_type(player),
            lambda u: f"{u} from cargo ship",
        )
        self.add_loss_rows(
            debriefing.airlift_losses_by_type(player), lambda u: f"{u} from airlift"
        )
        self.add_loss_rows(debriefing.ground_object_losses_by_type(player), lambda u: u)
        self.add_loss_rows(debriefing.scenery_losses_by_type(player), lambda u: u)

        # TODO: Display dead ground object units and runways.

    def add_loss_rows(self, losses: Dict[T, int], make_name: Callable[[T], str]):
        for unit_type, count in losses.items():
            row = self.rowCount()
            try:
                name = make_name(unit_type)
            except AttributeError:
                logging.exception(f"Could not make unit name for {unit_type}")
                name = unit_type.id
            self.addWidget(QLabel(name), row, 0)
            self.addWidget(QLabel(str(count)), row, 1)


class ScrollingCasualtyReportContainer(QGroupBox):
    def __init__(self, debriefing: Debriefing, player: Player) -> None:
        country = (
            debriefing.player_country if player.is_blue else debriefing.enemy_country
        )
        super().__init__(f"{country}'s lost units:")
        scroll_content = QWidget()
        grid = LossGrid(debriefing, player)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll_content.setLayout(grid)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_content)
        layout = QVBoxLayout()
        layout.addWidget(scroll_area)
        self.setLayout(layout)


class AfterActionReportBox(QGroupBox):
    """What happened and why, for turns resolved by the combat model: losses
    by cause, crew fates, front-line results and key events."""

    def __init__(self, report: AfterActionReport) -> None:
        super().__init__("After-action report:")
        label = QLabel(report.to_html())
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(label)
        scroll.setMinimumHeight(220)
        layout = QVBoxLayout()
        layout.addWidget(scroll)
        self.setLayout(layout)


class PlanReport(QGroupBox):
    """Each key package of the turn's plan: its goal, what it achieved and
    what it lost (F16), before the full loss lists."""

    def __init__(self, html: str) -> None:
        super().__init__("How the plan went:")
        label = QLabel(html)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(label)
        scroll.setMinimumHeight(180)
        layout = QVBoxLayout()
        layout.addWidget(scroll)
        self.setLayout(layout)


class RescueReport(QGroupBox):
    """Lists the downed pilots CSAR recovered this mission, per coalition.

    Rescues are the counterpart to the casualty report: an airframe is still lost,
    but the pilot comes back, so they are reported separately rather than folded
    into the loss grid.
    """

    def __init__(self, debriefing: Debriefing) -> None:
        super().__init__("Pilots recovered by CSAR:")
        layout = QGridLayout()
        self.setLayout(layout)

        any_rescues = False
        for player in (Player.BLUE, Player.RED):
            rescued = debriefing.rescued_pilots_for(player)
            if not rescued:
                continue
            any_rescues = True
            country = (
                debriefing.player_country
                if player.is_blue
                else debriefing.enemy_country
            )
            layout.addWidget(QLabel(f"<b>{country}</b>"), layout.rowCount(), 0)
            for pilot in rescued:
                row = layout.rowCount()
                layout.addWidget(QLabel(pilot.name), row, 0)
                layout.addWidget(QLabel(f"{pilot.squadron} ({pilot.aircraft})"), row, 1)

        if not any_rescues:
            layout.addWidget(QLabel("No pilots were recovered."), 0, 0)


class CaptureReport(QGroupBox):
    """Lists the pilots taken prisoner this turn, and who is holding them.

    Named separately from the casualty grid because a prisoner is not a permanent
    loss: retaking the base that holds them brings them back.
    """

    def __init__(self, debriefing: Debriefing) -> None:
        super().__init__("Pilots captured:")
        layout = QGridLayout()
        self.setLayout(layout)

        any_captures = False
        for player in (Player.BLUE, Player.RED):
            captured = debriefing.captured_pilots_for(player)
            if not captured:
                continue
            any_captures = True
            country = (
                debriefing.player_country
                if player.is_blue
                else debriefing.enemy_country
            )
            layout.addWidget(QLabel(f"<b>{country}</b>"), layout.rowCount(), 0)
            for pilot in captured:
                row = layout.rowCount()
                layout.addWidget(QLabel(pilot.name), row, 0)
                layout.addWidget(QLabel(f"{pilot.squadron} ({pilot.aircraft})"), row, 1)
                layout.addWidget(QLabel(f"held at {pilot.control_point}"), row, 2)

        if not any_captures:
            layout.addWidget(QLabel("No pilots were captured."), 0, 0)


def make_plan_report(debriefing: Debriefing) -> Optional[str]:
    """The plan report for the debriefing window, made once and kept on the
    debriefing. Make it before the turn passes (it reads the ATO and the
    mission window)."""
    if not debriefing.plan_report_made:
        try:
            from qt_ui.atopresentation import plan_debrief_html

            debriefing.plan_report = plan_debrief_html(debriefing, blue=True)
        except Exception:
            logging.exception("Could not summarize the plan's results")
            debriefing.plan_report = None
        debriefing.plan_report_made = True
    return debriefing.plan_report


class QDebriefingWindow(QDialog):
    def __init__(self, debriefing: Debriefing):
        super(QDebriefingWindow, self).__init__()
        self.debriefing = debriefing

        self.setModal(True)
        self.setWindowTitle("Debriefing")
        self.setMinimumSize(300, 200)
        self.setWindowIcon(QIcon("./resources/icon.png"))

        layout = QVBoxLayout()
        self.setLayout(layout)

        header = QLabel(self)
        header.setGeometry(0, 0, 655, 106)
        pixmap = QPixmap("./resources/ui/debriefing.png")
        header.setPixmap(pixmap)
        layout.addWidget(header, 0, Qt.AlignmentFlag.AlignHCenter)

        # Two columns: what the plan did and why on the left, the loss lists
        # and pilots on the right. One column squeezed every box into a few
        # lines on a 1080p screen.
        columns = QHBoxLayout()
        layout.addLayout(columns, 1)
        left = QVBoxLayout()
        right = QVBoxLayout()
        columns.addLayout(left, 3)
        columns.addLayout(right, 2)

        plan = make_plan_report(debriefing)
        if plan:
            left.addWidget(PlanReport(plan), 3)

        report = AfterActionReport.from_debriefing(debriefing)
        if getattr(debriefing, "simulation_log", None) and not report.empty:
            left.addWidget(AfterActionReportBox(report), 2)

        right.addWidget(QLabel("<b>Casualty report</b>"))
        right.addWidget(
            ScrollingCasualtyReportContainer(debriefing, player=Player.BLUE), 1
        )
        right.addWidget(
            ScrollingCasualtyReportContainer(debriefing, player=Player.RED), 2
        )
        right.addWidget(RescueReport(debriefing))
        right.addWidget(CaptureReport(debriefing))
        if left.count() == 0:
            # Nothing for the left column: the losses take the whole width.
            columns.setStretch(0, 0)

        okay = QPushButton("Okay")
        okay.clicked.connect(self.close)
        layout.addWidget(okay)
        self._fit_to_screen()

    #: Preferred size, capped to 90% of the screen.
    PREFERRED_SIZE = (1280, 940)

    def _fit_to_screen(self) -> None:
        width, height = self.PREFERRED_SIZE
        screen = self.screen()
        if screen is not None:
            area = screen.availableGeometry()
            width = min(width, int(area.width() * 0.9))
            height = min(height, int(area.height() * 0.9))
        self.resize(width, height)

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)
        state = self.debriefing.game.check_win_loss()
        GameUpdateSignal.get_instance().gameStateChanged(state)
