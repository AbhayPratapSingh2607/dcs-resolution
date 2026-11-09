"""The "Air campaign" page of the Intelligence window: the JFACC planner's
campaign phase, commander's intent, sortie apportionment, the prioritized
target list with battle damage assessment, and why packages were scrubbed.

Only the player's own side is shown: the enemy's plans are not known.
"""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from game.game import Game
from qt_ui.windows.intel_picture import SortableItem

TARGET_COLUMNS = (
    "Rank",
    "Target",
    "System",
    "Class",
    "Priority",
    "Intel confidence",
    "Assessed / desired effect",
    "BDA confidence",
    "Status",
    "Tasked",
)

MOE_LABELS = {
    "c2_degraded": ("Enemy IADS C2 degraded", "{:.0%}"),
    "air_superiority": ("Air superiority ratio", "{:.2f}"),
    "own_fighters": ("Own fighter strength", "{:.0f}"),
    "enemy_fighters": ("Enemy fighter strength (estimate)", "{:.0f}"),
    "battle_area_sams": ("Known battle-area SAMs active", "{:.0f}"),
    "enemy_ground_strength": ("Enemy front-line strength (estimate)", "{:.0f}"),
    "min_force_ratio": ("Weakest front force ratio", "{:.2f}"),
    "main_effort_force_ratio": ("Main effort force ratio", "{:.2f}"),
}


class AirCampaignTab(QWidget):
    def __init__(self, game: Game) -> None:
        super().__init__()
        layout = QVBoxLayout()
        self.setLayout(layout)
        side = game.air_campaign.maybe_side(True)
        if side is None or not side.history:
            layout.addWidget(
                QLabel(
                    "Your side uses the legacy planner. The doctrine-driven air "
                    "campaign planner can be selected in Settings > Campaign "
                    "Management > HQ Automation."
                )
            )
            layout.addStretch(1)
            return
        layout.addWidget(self._phase(side))
        layout.addWidget(self._apportionment(side))
        layout.addWidget(self._targets(side), stretch=1)
        layout.addWidget(self._scrubbed(side))

    @staticmethod
    def _phase(side) -> QGroupBox:  # type: ignore[no-untyped-def]
        box = QGroupBox(side.phase.title)
        layout = QVBoxLayout()
        box.setLayout(layout)
        intent = QLabel(f"<b>Commander's intent:</b> {side.intent}")
        intent.setWordWrap(True)
        layout.addWidget(intent)
        if side.history:
            last = side.history[-1]
            layout.addWidget(
                QLabel(f"Phase since turn {last.turn}: {last.reason}")
            )
        moes = []
        for key, (label, fmt) in MOE_LABELS.items():
            if key in side.moes:
                value = side.moes[key]
                text = "-" if value >= 99 else fmt.format(value)
                moes.append(f"{label}: <b>{text}</b>")
        moe_label = QLabel(" &nbsp;|&nbsp; ".join(moes))
        moe_label.setWordWrap(True)
        layout.addWidget(moe_label)
        if side.qra:
            qra = QLabel(f"<b>Ground alert (QRA):</b> {'; '.join(side.qra)}")
            qra.setWordWrap(True)
            layout.addWidget(qra)
        return box

    @staticmethod
    def _apportionment(side) -> QGroupBox:  # type: ignore[no-untyped-def]
        box = QGroupBox(
            f"Apportionment: {sum(side.planned.values())} of "
            f"{side.total_sorties} available sorties planned"
        )
        layout = QVBoxLayout()
        box.setLayout(layout)
        table = QTableWidget(len(side.apportioned), 3)
        table.setHorizontalHeaderLabels(["Category", "Apportioned", "Planned"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, (category, quota) in enumerate(side.apportioned.items()):
            table.setItem(row, 0, QTableWidgetItem(category.title))
            table.setItem(row, 1, SortableItem(str(quota), quota))
            planned = side.planned.get(category, 0)
            table.setItem(row, 2, SortableItem(str(planned), planned))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setMaximumHeight(30 + 24 * len(side.apportioned))
        layout.addWidget(table)
        return box

    @staticmethod
    def _targets(side) -> QGroupBox:  # type: ignore[no-untyped-def]
        box = QGroupBox("Joint integrated prioritized target list")
        layout = QVBoxLayout()
        box.setLayout(layout)
        table = QTableWidget(len(side.jiptl), len(TARGET_COLUMNS))
        table.setHorizontalHeaderLabels(TARGET_COLUMNS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for row, line in enumerate(side.jiptl):
            values = [
                SortableItem(str(line.rank), line.rank),
                QTableWidgetItem(line.name),
                QTableWidgetItem(line.system.value.upper()),
                QTableWidgetItem(line.target_class.replace("_", " ")),
                SortableItem(f"{line.priority:.2f}", line.priority),
                SortableItem(f"{line.confidence:.0%}", line.confidence),
                SortableItem(
                    f"{line.assessed_effect:.0%} / {line.desired_effect:.0%}",
                    line.assessed_effect,
                ),
                SortableItem(f"{line.bda_confidence:.0%}", line.bda_confidence),
                QTableWidgetItem(line.status),
                QTableWidgetItem("yes" if line.planned else ""),
            ]
            for column, item in enumerate(values):
                if column in (0, 4, 5, 6, 7):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, column, item)
        table.setSortingEnabled(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table)
        return box

    @staticmethod
    def _scrubbed(side) -> QGroupBox:  # type: ignore[no-untyped-def]
        reasons: Counter[str] = Counter(why.split(" (")[0] for _, why in side.scrubbed)
        box = QGroupBox(f"Packages considered but not tasked: {len(side.scrubbed)}")
        layout = QVBoxLayout()
        box.setLayout(layout)
        for why, count in reasons.most_common(6):
            layout.addWidget(QLabel(f"{count} x {why}"))
        return box
