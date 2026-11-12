"""Guardrail: rescue helicopters flying from a Rescue King must appear after
its C-130 is on station and be back before it leaves
(FarpManager.rescue_conflict). Shared by the timeline, the package dialog and
the King's menu."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMessageBox, QWidget

from game.ato import Package
from game.ato.flighttype import FlightType
from game.farps import FarpManager
from game.server import EventStream
from game.sim import GameUpdateEvents
from qt_ui.models import GameModel


def _farps(game_model: GameModel) -> Optional[FarpManager]:
    game = game_model.game
    return None if game is None else game.blue.farps


def conflict_text(game_model: GameModel, package: Package) -> Optional[str]:
    """Why this package's helicopters fall outside their King's time on
    station, or None."""
    farps = _farps(game_model)
    return None if farps is None else farps.rescue_conflict(package)


def fit_packages(game_model: GameModel, packages: list[Package]) -> None:
    """Moves each package's TOT so its helicopters fit in their King's time
    on station."""
    farps = _farps(game_model)
    if farps is None:
        return
    events = GameUpdateEvents()
    for package in packages:
        tot = farps.fit_to_king(package)
        if tot is None:
            continue
        package.auto_asap = False
        model = game_model.ato_model.find_matching_package_model(package)
        if model is not None:
            model.set_tot(tot)
        else:
            package.time_over_target = tot
        events.update_flights_in_package(package)
    EventStream.put_nowait(events)


def warn_king_conflicts(
    parent: QWidget, game_model: GameModel, package: Package
) -> None:
    """After a package's time changed: if it is a King whose rescues no
    longer fit, or a rescue outside its King's window, say so and offer to
    move the rescues into the window."""
    farps = _farps(game_model)
    if farps is None:
        return
    if any(f.flight_type is FlightType.RESCUE_KING for f in package.flights):
        king = package.target
        conflicts = farps.king_conflicts(king)  # type: ignore[arg-type]
    else:
        why = farps.rescue_conflict(package)
        conflicts = [] if why is None else [(package, why)]
    if not conflicts:
        return
    lines = "\n\n".join(why for _, why in conflicts)
    answer = QMessageBox.warning(
        parent,
        "Outside the Rescue King's time on station",
        f"{lines}\n\nMove the rescue{'s' if len(conflicts) > 1 else ''} into "
        "the King's time on station?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if answer == QMessageBox.StandardButton.Yes:
        fit_packages(game_model, [p for p, _ in conflicts])
