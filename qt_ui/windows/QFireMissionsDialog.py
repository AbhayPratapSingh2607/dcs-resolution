"""The Fire Missions window: blue's cruise missile, missile and artillery
strikes for this turn (game.warfare.firemissions).

The list shows each mission's time, launcher, rounds, target and what became
of it. Add (or Plan fire mission… on an enemy site) picks a launcher, a target
in its reach, the rounds and the time; Suggest lets the commander fill what
the launchers have left. Missions timed inside the DCS window are fired in
DCS, the rest by the combat model.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.server import EventStream
from game.sim import GameUpdateEvents
from game.sim.atoperiod import window
from game.warfare.firemissions import (
    FireMission,
    FireStatus,
    best_launcher,
    Launcher,
    default_time,
    enabled,
    launchers,
    missions_this_turn,
    period_bounds,
    plan_ai_fire_missions,
    unreachable_reason,
    plan_mission,
    remove_mission,
    rounds_for,
    rounds_left,
    stock_free,
    stock_left,
    strike_odds,
    target_class_of,
    target_of,
    targets_for,
)


class _FireMissionSignals(QObject):
    #: Fire missions were planned, moved or removed: the timeline redraws.
    changed = Signal()


_signals: Optional[_FireMissionSignals] = None


def fire_mission_signals() -> _FireMissionSignals:
    global _signals
    if _signals is None:
        _signals = _FireMissionSignals()
    return _signals


def notify_map(game: Game, missions: list[FireMission]) -> None:
    """Refresh the targets' strike marks on the map."""
    from game.theater import ControlPoint

    events = GameUpdateEvents()
    for mission in missions:
        target = target_of(game, mission)
        if isinstance(target, ControlPoint):
            events.update_control_point(target)
        elif target is not None:
            events.update_tgo(target)  # type: ignore[arg-type]
    EventStream.put_nowait(events)
    fire_mission_signals().changed.emit()


def launcher_label(game: Game, launcher: Launcher, left: int) -> str:
    stock = stock_left(game, launcher)
    campaign = (
        f", {stock} of {launcher.magazine} in magazine" if stock is not None else ""
    )
    return (
        f"{launcher.name} — {launcher.kind.value}, {left} of "
        f"{launcher.capacity} {launcher.weapon} this turn{campaign}, "
        f"{launcher.range_m / 1000:.0f} km"
    )


def mission_zero(game: Game) -> Any:
    """Time +0:00 of the fire mission clock: the DCS mission's start, or the
    period's start when the turn has no DCS window."""
    bounds = window(game)
    return bounds[0] if bounds is not None else period_bounds(game)[0]


class OffsetTimeEdit(QSpinBox):
    """A time as minutes from the DCS mission start, shown like the package
    TOT box: "00:00:00" at the start, "02:15:00", "-00:30:00" before it."""

    STEP_MIN = 5

    def __init__(self, game: Game, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        from datetime import timedelta

        self.zero = mission_zero(game)
        start, end = period_bounds(game)
        minute = timedelta(minutes=1)
        self.setRange(
            int((start - self.zero) / minute), int((end - self.zero) / minute)
        )
        self.setSingleStep(self.STEP_MIN)
        self.setAccelerated(True)
        self.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        # Room for "-00:00:00" plus the arrows (the app stylesheet's spin box
        # min-width would otherwise win over a minimum set here).
        self.setStyleSheet("QSpinBox { min-width: 78px; }")
        self.setToolTip(
            "Time from the start of the DCS mission (00:00:00). Before it is "
            "negative; up and down step 5 minutes, or type e.g. 02:15:00."
        )

    def textFromValue(self, value: int) -> str:
        sign = "-" if value < 0 else ""
        value = abs(value)
        return f"{sign}{value // 60:02d}:{value % 60:02d}:00"

    def valueFromText(self, text: str) -> int:
        text = text.strip().replace(" ", "")
        sign = -1 if text.startswith("-") else 1
        text = text.lstrip("+-")
        hours, _, rest = text.partition(":")
        minutes, _, seconds = rest.partition(":")
        try:
            value = int(hours or 0) * 60 + int(minutes or 0)
            value += round(int(seconds or 0) / 60)
        except ValueError:
            return self.value()
        return sign * value

    def validate(self, text: str, pos: int) -> Any:
        import re

        from PySide6.QtGui import QValidator

        if re.fullmatch(r"\s*[+-]?\d{0,2}(:\d{0,2}(:\d{0,2})?)?\s*", text):
            return (
                QValidator.State.Intermediate
                if text.strip() in ("", "+", "-")
                else QValidator.State.Acceptable
            )
        return QValidator.State.Invalid

    def when(self) -> Any:
        from datetime import timedelta

        return self.zero + timedelta(minutes=self.value())

    def set_when(self, when: Any) -> None:
        from datetime import timedelta

        self.setValue(int((when - self.zero) / timedelta(minutes=1)))


def in_window_note(game: Game, when: Any) -> str:
    bounds = window(game)
    if bounds is not None and bounds[0] <= when <= bounds[1]:
        return "Inside the DCS window: fired in the mission you fly."
    return "Outside the DCS window: fired by the combat model."


class QFireMissionEditor(QDialog):
    """Plans one fire mission."""

    def __init__(
        self, game: Game, target: Any = None, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.game = game
        self.mission: Optional[FireMission] = None
        self.wanted_target = target
        self.setWindowTitle(
            f"Plan fire mission: {target.name}"
            if target is not None
            else "Plan fire mission"
        )
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.launcher = QComboBox()
        for launcher in launchers(game, game.blue.player):
            left = rounds_left(game, launcher)
            if target is not None and not any(
                t is target for _, t in targets_for(game, launcher)
            ):
                continue
            self.launcher.addItem(launcher_label(game, launcher, left), launcher)
        if target is not None:
            best = best_launcher(game, game.blue.player, target)
            for index in range(self.launcher.count()):
                if best is not None and self.launcher.itemData(index) == best:
                    self.launcher.setCurrentIndex(index)
        form.addRow("Launcher:", self.launcher)
        self.target = QComboBox(self)
        if target is None:
            form.addRow("Target:", self.target)
        else:
            # Opened on a target (the package dialog): it's in the title.
            self.target.hide()
        self.rounds = QSpinBox()
        form.addRow("Rounds:", self.rounds)
        self.time = OffsetTimeEdit(game)
        self.time.set_when(default_time(game))
        self.clock = QLabel()
        time_row = QHBoxLayout()
        time_row.addWidget(self.time)
        time_row.addWidget(self.clock)
        time_row.addStretch(1)
        form.addRow("Time:", time_row)
        self.odds = QLabel()
        self.odds.setWordWrap(True)
        self.odds.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.odds)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Plan")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.launcher.currentIndexChanged.connect(lambda *_: self._fill_targets())
        self.target.currentIndexChanged.connect(lambda *_: self._update())
        self.time.valueChanged.connect(lambda *_: self._update())
        self.rounds.valueChanged.connect(lambda *_: self._update_odds())
        self._fill_targets()

    @property
    def selected_launcher(self) -> Optional[Launcher]:
        return self.launcher.currentData()

    def _fill_targets(self) -> None:
        self.target.blockSignals(True)
        self.target.clear()
        launcher = self.selected_launcher
        if launcher is not None:
            for distance, target in targets_for(self.game, launcher):
                kind = target_class_of(target).replace("_", " ")
                base = getattr(target, "control_point", None)
                near = f", near {base.name}" if base is not None else ""
                self.target.addItem(
                    f"{target.name} ({kind}, {distance / 1000:.0f} km{near})", target
                )
                if target is self.wanted_target:
                    self.target.setCurrentIndex(self.target.count() - 1)
        self.target.blockSignals(False)
        self._update()

    def _update(self) -> None:
        launcher = self.selected_launcher
        target = self.target.currentData()
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.clock.setText(
            f"<span style='color:#9aa7b2'>{self.time.when():%H:%M}</span>"
        )
        self.odds.setText("")
        if launcher is None:
            self.note.setWordWrap(True)
            self.note.setText(
                unreachable_reason(self.game, self.game.blue.player, self.wanted_target)
                or "No launcher can reach this target."
                if self.wanted_target is not None
                else "Your side has no cruise missile ships, missile sites or "
                "front-line artillery."
            )
            ok.setEnabled(False)
            return
        left = rounds_left(self.game, launcher)
        self.rounds.setRange(1 if left else 0, max(left, 0))
        if target is not None and left:
            self.rounds.setValue(min(left, rounds_for(launcher, target)))
        ok.setEnabled(target is not None and left > 0)
        if left <= 0:
            free = stock_free(self.game, launcher)
            self.note.setText(
                f"{launcher.name}'s magazine is empty: no {launcher.weapon} left "
                "for the campaign."
                if free == 0 and stock_left(self.game, launcher) == 0
                else f"{launcher.name} has fired all it can this turn."
            )
            return
        if target is None:
            self.note.setText("No known enemy target within reach.")
            return
        self.note.setText(in_window_note(self.game, self.time.when()))
        self._update_odds()

    def _update_odds(self) -> None:
        launcher = self.selected_launcher
        target = self.target.currentData()
        rounds = self.rounds.value()
        if launcher is None or target is None or rounds <= 0:
            self.odds.setText("")
            return
        try:
            odds = strike_odds(self.game, launcher, target, rounds)
        except Exception:
            self.odds.setText("")
            return
        what, chance = odds.outcome
        lines = [
            f"<b style='font-size:13px'>Chance of {what}: {chance:.0%}</b>",
            *odds.lines,
        ]
        left = stock_left(self.game, launcher)
        if left is not None:
            free = stock_free(self.game, launcher) or 0
            lines.append(
                f"Uses {rounds} {launcher.weapon}: {launcher.name} keeps "
                f"{max(free - rounds, 0)} of {launcher.magazine} for the campaign"
            )
        else:
            lines.append(f"Uses {rounds} {launcher.weapon}")
        self.odds.setText("<br>".join(lines))

    def accept(self) -> None:
        launcher = self.selected_launcher
        target = self.target.currentData()
        if launcher is None or target is None or self.rounds.value() <= 0:
            return
        self.mission = plan_mission(
            self.game,
            launcher,
            target,
            self.rounds.value(),
            self.time.when(),
        )
        notify_map(self.game, [self.mission])
        super().accept()


class QFireMissionsDialog(QDialog):
    COLUMNS = ["Time", "Launcher", "Rounds", "Target", "Status"]

    def __init__(self, game: Game, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game = game
        self.setWindowTitle("Fire missions")
        self.resize(900, 520)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Cruise missile ships, missile sites and front-line artillery fire "
            "these this turn. Each launcher fires up to its capacity every turn. "
            "Missions timed inside the DCS window are fired in DCS; the rest by "
            "the combat model at their time. The enemy's commander plans its own."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.capacity = QLabel()
        self.capacity.setWordWrap(True)
        layout.addWidget(self.capacity)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        for column in range(len(self.COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.add = QPushButton("Add…")
        self.add.setProperty("style", "btn-success")
        self.add.clicked.connect(self.add_mission)
        buttons.addWidget(self.add)
        self.remove = QPushButton("Remove")
        self.remove.setProperty("style", "btn-danger")
        self.remove.clicked.connect(self.remove_selected)
        buttons.addWidget(self.remove)
        self.suggest = QPushButton("Suggest")
        self.suggest.setToolTip(
            "Let the commander plan what the launchers have left, at the "
            "highest value targets in reach, spread over the turn."
        )
        self.suggest.clicked.connect(self.suggest_missions)
        buttons.addWidget(self.suggest)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.refresh()

    def missions(self) -> list[FireMission]:
        return sorted(
            missions_this_turn(self.game, self.game.blue.player), key=lambda m: m.time
        )

    def refresh(self) -> None:
        missions = self.missions()
        self.table.setRowCount(len(missions))
        for row, mission in enumerate(missions):
            status = (
                mission.result
                if mission.status in (FireStatus.FIRED, FireStatus.CANCELLED)
                and mission.result
                else mission.status.value
            )
            if mission.status is FireStatus.PLANNED:
                status = in_window_note(self.game, mission.time).split(":")[0]
            values = [
                f"{mission.time:%H:%M}",
                f"{mission.launcher_name} ({mission.kind.value})",
                f"{mission.rounds} {mission.weapon}",
                mission.target_name,
                status,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, mission)
                self.table.setItem(row, column, item)
        available = launchers(self.game, self.game.blue.player)
        if not enabled(self.game):
            text = "Fire missions are turned off in the settings."
        elif self.game.turn < 1:
            text = "Fire missions start on turn 1; the opening salvo is planned at Begin Campaign."
        elif not available:
            text = (
                "Your side has no cruise missile ships (Ticonderoga, Arleigh "
                "Burke), missile sites or front-line artillery."
            )
        else:
            text = "Left this turn: " + "; ".join(
                f"{l.name} {rounds_left(self.game, l)}/{l.capacity} {l.weapon}"
                + (
                    f" ({stock_left(self.game, l)}/{l.magazine} for the campaign)"
                    if stock_left(self.game, l) is not None
                    else ""
                )
                for l in available
            )
        self.capacity.setText(text)
        can_plan = enabled(self.game) and self.game.turn >= 1 and bool(available)
        self.add.setEnabled(can_plan)
        self.suggest.setEnabled(can_plan)

    def _selected(self) -> list[FireMission]:
        rows = {index.row() for index in self.table.selectedIndexes()}
        found = []
        for row in sorted(rows):
            item = self.table.item(row, 0)
            if item is not None:
                found.append(item.data(Qt.ItemDataRole.UserRole))
        return found

    def add_mission(self) -> None:
        if QFireMissionEditor(self.game, parent=self).exec():
            self.refresh()

    def remove_selected(self) -> None:
        selected = self._selected()
        fired = [m for m in selected if m.status is FireStatus.FIRED]
        if fired:
            QMessageBox.information(
                self, "Fire missions", "Missions already fired can't be removed."
            )
        removed = [m for m in selected if m.status is not FireStatus.FIRED]
        for mission in removed:
            remove_mission(self.game, mission)
        notify_map(self.game, removed)
        self.refresh()

    def suggest_missions(self) -> None:
        planned = plan_ai_fire_missions(self.game, self.game.blue.player, share=1.0)
        for mission in planned:
            mission.auto = False
        notify_map(self.game, planned)
        self.refresh()
        if not planned:
            QMessageBox.information(
                self,
                "Fire missions",
                "Nothing to suggest: the launchers have no rounds left or no "
                "known target in reach.",
            )


def plan_at(game: Game, target: Any, parent: Optional[QWidget] = None) -> bool:
    """Plan fire mission… on an enemy site or airfield."""
    return bool(QFireMissionEditor(game, target, parent).exec())
