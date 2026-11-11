"""Decoys in DCS (game.warfare.deception).

Each decoy of a ground object becomes a few inert statics of the site's own
vehicle types (its radar and launchers) at the decoy's position, so a package
that took the decoy for the site (the decoy call) bombs something that looks
like it, and a player flying to the believed position finds the same.
Decoys aren't tracked: destroying one in DCS changes nothing in the
campaign; the decoy call decides what the strike did to the picture.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from dcs import Mission
from dcs.mapping import Point
from dcs.unittype import VehicleType

if TYPE_CHECKING:
    from game import Game
    from game.theater import TheaterGroundObject

#: Statics per decoy and their spacing.
UNITS_PER_DECOY = 3
SPACING_M = 60.0


def decoy_points(
    tgo: TheaterGroundObject, offsets: list[tuple[float, float]]
) -> list[Point]:
    """The decoys' positions: offsets are (east, north) metres from the site."""
    return [
        Point(tgo.position.x + north, tgo.position.y + east, tgo.position._terrain)
        for east, north in offsets
    ]


class DecoyGenerator:
    def __init__(self, mission: Mission, game: Game) -> None:
        self.mission = mission
        self.game = game

    def generate(self) -> int:
        from game.warfare.deception import enabled

        war_state = getattr(self.game, "war_state", None)
        if war_state is None or not enabled(self.game):
            return 0
        by_id = {t.id: t for t in self.game.theater.ground_objects}
        # Decoys a package in the mission will bomb spawn even where the
        # ground units are culled.
        self.targeted = [
            (call.x, call.y)
            for _, call in getattr(self.game.air_campaign, "dcs_decoy_calls", [])
        ]
        placed = 0
        for tgo_id, offsets in list(war_state.deception.items()):
            tgo = by_id.get(tgo_id)
            if tgo is None or tgo.is_dead or not offsets:
                continue
            try:
                placed += self._spawn(tgo, offsets)
            except Exception:
                logging.exception(f"Could not spawn the decoys of {tgo.name}")
        if placed:
            logging.info(f"Spawned {placed} decoy statics")
        return placed

    def _spawn(
        self, tgo: TheaterGroundObject, offsets: list[tuple[float, float]]
    ) -> int:
        types = []
        for unit in tgo.units:
            unit_type = getattr(unit, "type", None)
            if (
                unit.alive
                and isinstance(unit_type, type)
                and issubclass(unit_type, VehicleType)
                and unit_type not in types
            ):
                types.append(unit_type)
            if len(types) >= UNITS_PER_DECOY:
                break
        if not types:
            return 0
        country = self.mission.country(tgo.control_point.coalition.faction.country.name)
        if country is None:
            return 0
        placed = 0
        for i, point in enumerate(decoy_points(tgo, offsets)):
            targeted = any(
                math.hypot(point.x - x, point.y - y) < 100 for x, y in self.targeted
            )
            if not targeted and self.game.position_culled(point):
                continue
            for j, unit_type in enumerate(types):
                angle = 2 * math.pi * j / len(types)
                spot = point.point_from_heading(
                    math.degrees(angle), SPACING_M if j else 0
                )
                self.mission.static_group(
                    country=country,
                    name=f"Decoy {tgo.name} {i + 1}-{j + 1}",
                    _type=unit_type,
                    position=spot,
                    heading=0,
                )
                placed += 1
        return placed
