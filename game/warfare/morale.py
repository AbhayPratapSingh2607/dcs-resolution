"""Morale: squadrons, front-line forces, SAM crews and national resolve.

Morale is a number from 0 to 1 that drifts back toward a resting value set by
doctrine (and, for everything, by the nation's resolve), and is knocked down
by losses and failures and lifted by success. It changes how units fight:

* Squadrons fly a little better or worse, abort earlier when shaken, and stand
  aircraft down when morale collapses.
* Ground forces fire less and break sooner; a collapsing front may surrender
  units without a fight and is forced to retreat.
* SAM crews that watched neighbouring sites die or were hunted by ARMs keep
  their radars dark and fire wildly.
* National resolve falls with sustained losses relative to the size of the
  force. It lowers income and every morale baseline, but never ends the war.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from game.squadrons import Squadron
    from game.theater import ControlPoint, TheaterGroundObject
    from game.theater.player import Player

DEFAULT_MORALE = 0.75
NEUTRAL_MORALE = 0.75
MIN_RESOLVE = 0.25


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def performance_factor(morale: float, spread: float = 0.15) -> float:
    """Multiplier on performance: 1.0 at neutral morale, 1 - spread when morale
    has collapsed, about 1 + spread / 3 at its best."""
    return 1.0 + spread * (morale - NEUTRAL_MORALE) / NEUTRAL_MORALE


@dataclass
class MoraleState:
    squadrons: dict[UUID, float] = field(default_factory=dict)
    fronts: dict[UUID, float] = field(default_factory=dict)
    sam_crews: dict[UUID, float] = field(default_factory=dict)
    resolve: dict[bool, float] = field(default_factory=dict)
    #: Largest force each side fielded, for normalising losses.
    peak_aircraft: dict[bool, int] = field(default_factory=dict)
    peak_armor: dict[bool, int] = field(default_factory=dict)

    # ----------------------------------------------------------------- squadrons

    def squadron(self, squadron: Squadron) -> float:
        return self.squadrons.get(squadron.id, DEFAULT_MORALE)

    def adjust_squadron(self, squadron: Squadron, delta: float) -> float:
        value = clamp01(self.squadron(squadron) + delta)
        self.squadrons[squadron.id] = value
        return value

    # ----------------------------------------------------------------- fronts

    def front(self, control_point: ControlPoint) -> float:
        return self.fronts.get(control_point.id, DEFAULT_MORALE)

    def adjust_front(self, control_point: ControlPoint, delta: float) -> float:
        value = clamp01(self.front(control_point) + delta)
        self.fronts[control_point.id] = value
        return value

    # ----------------------------------------------------------------- SAM crews

    def sam_crew(self, tgo: TheaterGroundObject) -> float:
        return self.sam_crews.get(tgo.id, DEFAULT_MORALE)

    def adjust_sam_crew(self, tgo: TheaterGroundObject, delta: float) -> float:
        value = clamp01(self.sam_crew(tgo) + delta)
        self.sam_crews[tgo.id] = value
        return value

    # ----------------------------------------------------------------- nations

    def national_resolve(self, player: Player) -> float:
        return self.resolve.get(player.is_blue, 1.0)

    def adjust_resolve(self, player: Player, delta: float) -> float:
        value = max(MIN_RESOLVE, min(1.0, self.national_resolve(player) + delta))
        self.resolve[player.is_blue] = value
        return value

    def baseline(self, doctrine_baseline: float, player: Player) -> float:
        """Resting morale: doctrine, dragged down by national war-weariness."""
        resolve = self.national_resolve(player)
        return clamp01(doctrine_baseline * (0.75 + 0.25 * resolve))

    @staticmethod
    def recover(value: float, baseline: float, rate: float) -> float:
        if value < baseline:
            return min(baseline, value + rate)
        return max(baseline, value - rate * 0.5)


def describe(value: float) -> str:
    """Morale in words, for the UI."""
    if value >= 0.85:
        return "excellent"
    if value >= 0.7:
        return "good"
    if value >= 0.5:
        return "steady"
    if value >= 0.3:
        return "shaken"
    return "broken"
