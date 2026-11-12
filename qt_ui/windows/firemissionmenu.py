"""Plan fire mission… in the package dialog of an enemy site or airfield (what a
right-click on the map opens): a missile strike instead of, or as well as,
the package (game.warfare.firemissions)."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import QPushButton, QWidget

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
            text, hint, enabled = "Plan fire mission…", "", True
        button.setText(text)
        button.setToolTip(hint)
        button.setEnabled(enabled)

    def plan() -> None:
        plan_at(game, target, parent if parent is not None else button.window())
        refresh()

    button.clicked.connect(plan)
    refresh()
    return button
