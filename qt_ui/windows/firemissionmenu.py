"""Right-click on an enemy site or airfield on the map: plan a package or a
missile strike (game.warfare.firemissions)."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QMenu, QWidget

from game import Game


def _strike_target(game: Game, target: Any) -> bool:
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


def strike_menu(game: Game, target: Any, parent: Optional[QWidget] = None) -> bool:
    """Shows the menu at the cursor. Returns False when the target isn't one a
    strike can be planned on, so the caller opens the package dialog."""
    if not _strike_target(game, target):
        return False
    from game.warfare.firemissions import (
        best_launcher,
        rounds_for,
        rounds_left,
        stock_left,
        strike_odds,
        unreachable_reason,
    )
    from qt_ui.dialogs import Dialog
    from qt_ui.windows.QFireMissionsDialog import plan_at

    menu = QMenu(parent)
    menu.setToolTipsVisible(True)
    menu.addSection(target.name)
    package = menu.addAction("Plan package…")
    package.triggered.connect(lambda: Dialog.open_new_package_dialog(target, parent))

    why = unreachable_reason(game, game.blue.player, target)
    label = "Plan missile strike…"
    hint = why or ""
    if why is None:
        # The best launcher in reach with missiles left: what the dialog
        # proposes first, and its odds.
        launcher = best_launcher(game, game.blue.player, target)
        if launcher is None:
            why = "No launcher in reach has missiles left this turn."
            hint = why
        else:
            left = rounds_left(game, launcher)
            rounds = min(left, rounds_for(launcher, target))
            odds = strike_odds(game, launcher, target, rounds)
            what, chance = odds.outcome
            label = (
                f"Plan missile strike… ({rounds} {launcher.weapon}, "
                f"{chance:.0%} {what})"
            )
            stock = stock_left(game, launcher)
            hint = "\n".join(
                [f"{launcher.name}: {rounds} {launcher.weapon}", *odds.lines]
                + (
                    [f"{stock} of {launcher.magazine} left in its magazine"]
                    if stock is not None
                    else []
                )
            )
    strike = menu.addAction(label)
    strike.setToolTip(hint)
    strike.setEnabled(why is None)
    strike.triggered.connect(lambda: plan_at(game, target, parent))
    menu.popup(QCursor.pos())
    return True
