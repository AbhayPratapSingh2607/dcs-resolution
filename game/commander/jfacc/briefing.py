"""The turn summary (F13): what a side's plan for the turn is, in a few lines.

Shown at the top of the ATO panel and in the DCS mission briefing: phase and
intent, the key packages and what each is for, the routine lines counted in
one line, and the threats as the side's own intelligence sees them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight, Package

#: How many key packages the summary lists.
KEY_PACKAGES = 5


@dataclass
class KeyPackage:
    tot: datetime
    name: str
    reason: str
    players: bool


@dataclass
class TurnSummary:
    turn: int
    phase: str
    window: Optional[tuple[datetime, datetime]]
    intent: str
    key: list[KeyPackage] = field(default_factory=list)
    more_key: int = 0
    routine: list[str] = field(default_factory=list)
    threats: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        """Plain text, for the DCS mission briefing."""
        when = (
            f", mission {self.window[0]:%H:%M}-{self.window[1]:%H:%M}"
            if self.window
            else ""
        )
        lines = [f"Turn {self.turn}: {self.phase}{when}"]
        if self.intent:
            lines.append(self.intent)
        if self.key:
            lines.append("Key packages:")
            for package in self.key:
                you = " (you)" if package.players else ""
                lines.append(
                    f"  {package.tot:%H:%M} {package.name}{you}: {package.reason}"
                )
            if self.more_key:
                lines.append(f"  and {self.more_key} more")
        if self.routine:
            lines.append("Also: " + ", ".join(self.routine) + ".")
        if self.threats:
            lines.append("Threats (our intelligence): " + ", ".join(self.threats) + ".")
        return "\n".join(lines)


def _default_name(package: Package) -> str:
    task = package.primary_task
    label = task.value if task is not None else "Package"
    return f"{label} {package.target.name}"


def _all(package: Package, test: Callable[[Flight], bool]) -> bool:
    return bool(package.flights) and all(test(f) for f in package.flights)


def turn_summary(
    game: Game,
    blue: bool = True,
    name_of: Callable[[Package], str] = _default_name,
) -> Optional[TurnSummary]:
    """The side's plan for this turn, or None when it doesn't plan with the
    air campaign planner."""
    from game.sim import atoperiod

    from .planner import counts_toward_target

    state = getattr(game, "air_campaign", None)
    side = state.maybe_side(blue) if state is not None else None
    if side is None or not side.history:
        return None
    coalition = game.blue if blue else game.red
    window = atoperiod.window(game) if atoperiod.is_focused(game) else None
    summary = TurnSummary(game.turn, side.phase_title, window, side.intent)

    packages = list(coalition.ato.packages)
    counted = [p for p in packages if counts_toward_target(p)]
    key = [
        p
        for p in counted
        if p.has_players
        or any(f.flight_type is not FlightType.BARCAP for f in p.flights)
    ]
    key.sort(key=lambda p: (not p.has_players, p.time_over_target))
    for package in key[:KEY_PACKAGES]:
        info = package.planning_info or {}
        summary.key.append(
            KeyPackage(
                package.time_over_target,
                name_of(package),
                str(info.get("reason") or name_of(package)),
                bool(package.has_players),
            )
        )
    summary.more_key = max(0, len(key) - KEY_PACKAGES)

    def task_is(task: FlightType) -> Callable[[Flight], bool]:
        return lambda f: f.flight_type is task and not getattr(f, "returning", False)

    counts = {
        "CAP station": sum(
            1 for p in counted if _all(p, lambda f: f.flight_type is FlightType.BARCAP)
        ),
        "AWACS": sum(1 for p in packages if _all(p, task_is(FlightType.AEWC))),
        "tanker": sum(1 for p in packages if _all(p, task_is(FlightType.REFUELING))),
        "ground alert pair": sum(
            1 for p in packages if _all(p, lambda f: bool(getattr(f, "alert", False)))
        ),
        "CAP returning home": sum(
            1
            for p in packages
            if _all(p, lambda f: bool(getattr(f, "returning", False)))
        ),
    }
    for name, n in counts.items():
        if n:
            summary.routine.append(f"{n} {name}{'' if n == 1 else 's'}")

    moes = side.moes or {}
    if moes.get("enemy_fighters"):
        summary.threats.append(f"about {moes['enemy_fighters']:.0f} enemy fighters")
    if moes.get("battle_area_sams"):
        summary.threats.append(
            f"{moes['battle_area_sams']:.0f} SAM sites near the front"
        )
    if side.enemy_sorties_seen:
        summary.threats.append(
            f"{side.enemy_sorties_seen} enemy sorties seen last turn"
        )
    return summary
