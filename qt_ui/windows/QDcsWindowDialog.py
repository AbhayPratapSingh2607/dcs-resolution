"""Choose which part of the 6 hour ATO period to fly in DCS.

Everything before the window is fought by the combat model before the
mission is generated; packages that start after it are fought by the combat
model once the mission results are in (game.sim.atoperiod).
"""

from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QScrollArea,
    QSlider,
    QVBoxLayout,
)

from game import Game
from game.sim import atoperiod
from qt_ui.windows.atotimeline import TimelineWidget

STEP_MIN = 15


class QDcsWindowDialog(QDialog):
    def __init__(self, game: Game, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.game = game
        self.setWindowTitle("Choose the DCS mission window")
        self.setMinimumWidth(820)
        layout = QVBoxLayout()
        self.setLayout(layout)

        bounds = atoperiod.period(game)
        assert bounds is not None
        start, end = bounds
        explanation = QLabel(
            f"This turn's air tasking order covers {start:%H:%M} to {end:%H:%M}. "
            f"Pick the {int(atoperiod.window_length(game).total_seconds() // 60)} "
            "minutes you want to fly in DCS. Missions before the window are "
            "resolved by the combat model first; missions after it are resolved "
            "once you return from DCS."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(atoperiod.max_window_offset_min(game) // STEP_MIN)
        self.slider.setValue(game.air_campaign.window_offset_min // STEP_MIN)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.valueChanged.connect(self.update_window)
        layout.addWidget(self.slider)

        # The plan at a glance, with the window band following the slider.
        self.timeline = TimelineWidget(None, compact=True, game=game)
        self.timeline.setMinimumWidth(0)
        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidget(self.timeline)
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_scroll.setMinimumHeight(220)
        layout.addWidget(self.timeline_scroll)

        self.window_label = QLabel()
        layout.addWidget(self.window_label)
        self.packages = QListWidget()
        layout.addWidget(self.packages)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.update_window()

    def update_window(self) -> None:
        atoperiod.set_window_offset(self.game, self.slider.value() * STEP_MIN)
        bounds = atoperiod.window(self.game)
        if bounds is None:
            return
        start, end = bounds
        self.window_label.setText(
            f"DCS window: <b>{start:%H:%M}</b> to <b>{end:%H:%M}</b>"
        )
        self.timeline.update()
        self.packages.clear()
        packages = atoperiod.packages_in_window(self.game, blue=True)
        period_start = atoperiod.period(self.game)[0]  # type: ignore[index]
        for package in sorted(packages, key=lambda p: p.time_over_target):
            offset = package.time_over_target - period_start
            players = " (players)" if package.has_players else ""
            comp = ", ".join(f"{f.count}x {f.flight_type.value}" for f in package.flights)
            self.packages.addItem(
                f"TOT {package.time_over_target:%H:%M} "
                f"(+{int(offset / timedelta(minutes=1))}m) "
                f"{package.target.name}: {comp}{players}"
            )
        if not packages:
            self.packages.addItem("No friendly packages fly in this window.")
