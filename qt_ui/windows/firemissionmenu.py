"""Plan fire mission… in the package dialog of an enemy site or airfield (what a
right-click on the map opens): a missile strike instead of, or as well as,
the package (game.warfare.firemissions)."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from game import Game


def strike_target(game: Optional[Game], target: Any) -> bool:
    """An enemy ground object or airfield, from turn 1 with fire missions on."""
    from game.theater import ControlPoint, TheaterGroundObject
    from game.warfare.firemissions import enabled

    if game is None or game.turn < 1 or not enabled(game):
        return False
    if isinstance(target, TheaterGroundObject):
        return target.control_point.captured.is_red and not target.is_dead
    if isinstance(target, ControlPoint):
        return target.captured.is_red and not target.is_fleet
    return False


def strike_summary(game: Game, target: Any) -> tuple[str, str, bool]:
    """(button text, tooltip, enabled) for a strike on the target: the launcher
    the dialog proposes, its missiles and the chance of the headline outcome."""
    from game.warfare.firemissions import (
        best_launcher,
        rounds_for,
        rounds_left,
        stock_left,
        strike_odds,
        unreachable_reason,
    )

    label = "Plan fire mission…"
    why = unreachable_reason(game, game.blue.player, target)
    if why is not None:
        return label, why, False
    launcher = best_launcher(game, game.blue.player, target)
    if launcher is None:
        return label, "No launcher in reach has missiles left this turn.", False
    rounds = min(rounds_left(game, launcher), rounds_for(launcher, target))
    odds = strike_odds(game, launcher, target, rounds)
    what, chance = odds.outcome
    stock = stock_left(game, launcher)
    hint = "\n".join(
        [f"{launcher.name}: {rounds} {launcher.weapon}", *odds.lines]
        + (
            [f"{stock} of {launcher.magazine} left in its magazine"]
            if stock is not None
            else []
        )
    )
    return (
        f"Plan fire mission… ({rounds} {launcher.weapon}, {chance:.0%} {what})",
        hint,
        True,
    )


def fire_mission_button(
    game: Optional[Game], target: Any, parent: Optional[QWidget] = None
) -> Optional[QPushButton]:
    """The button for the package dialog, or None when the target isn't one
    a strike can be planned on."""
    if game is None or not strike_target(game, target):
        return None
    from qt_ui.windows.QFireMissionsDialog import plan_at

    button = QPushButton()
    button.setProperty("style", "btn-danger")

    def refresh() -> None:
        try:
            text, hint, enabled = strike_summary(game, target)
        except Exception:
            text, hint, enabled = "", "", True
        # The odds are in the dialog the button opens; disabled, it says why.
        button.setText("Plan Fire Mission")
        button.setToolTip("" if enabled else hint)
        button.setEnabled(enabled)

    def plan() -> None:
        plan_at(game, target, parent if parent is not None else button.window())
        refresh()

    button.clicked.connect(plan)
    refresh()
    return button


def planned_against(game: Game, target: Any) -> list:
    """This turn's fire missions (yours) at the target, by time."""
    from game.warfare.firemissions import FireStatus, missions_this_turn

    target_id = getattr(target, "id", None)
    return sorted(
        (
            m
            for m in missions_this_turn(game, game.blue.player)
            if m.target_id == target_id and m.status is not FireStatus.CANCELLED
        ),
        key=lambda m: m.time,
    )


def fire_mission_banner(
    game: Optional[Game], target: Any, parent: Optional[QWidget] = None
) -> Optional[QLabel]:
    """A line for the package dialog naming the fire missions planned at the
    package's target; hidden when there are none. Follows planning and moves
    (QFireMissionsDialog.fire_mission_signals)."""
    if game is None or not strike_target(game, target):
        return None
    from game.warfare.firemissions import FireStatus
    from qt_ui.windows.QFireMissionsDialog import fire_mission_signals, mission_zero

    label = QLabel(parent)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setStyleSheet(
        "QLabel { background: rgba(255, 107, 61, 40); border: 1px solid #ff6b3d;"
        " border-radius: 3px; padding: 4px 8px; }"
    )

    def clock(when: Any) -> str:
        minutes = int((when - mission_zero(game)).total_seconds() // 60)
        sign = "-" if minutes < 0 else ""
        minutes = abs(minutes)
        return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}:00"

    def refresh() -> None:
        try:
            missions = planned_against(game, target)
        except Exception:
            missions = []
        if not missions:
            label.hide()
            return
        parts = []
        for m in missions:
            status = (
                m.result or "fired"
                if m.status is FireStatus.FIRED
                else (
                    "in the DCS mission"
                    if m.status is FireStatus.IN_MISSION
                    else "planned"
                )
            )
            parts.append(
                f"<b>{clock(m.time)}</b> {m.rounds} {m.weapon} from "
                f"{m.launcher_name} ({status})"
            )
        count = len(missions)
        label.setText(
            f"<span style='color:#ff6b3d'>&#9673;</span> <b>{count} fire "
            f"mission{'s' if count != 1 else ''} at {target.name}:</b> "
            + " &middot; ".join(parts)
        )
        label.show()

    fire_mission_signals().changed.connect(refresh)
    label.destroyed.connect(lambda *_: _disconnect(refresh))
    refresh()
    return label


def _disconnect(slot: Any) -> None:
    from qt_ui.windows.QFireMissionsDialog import fire_mission_signals

    try:
        fire_mission_signals().changed.disconnect(slot)
    except (RuntimeError, TypeError):
        pass
