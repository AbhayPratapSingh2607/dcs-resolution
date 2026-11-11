"""Decoys in DCS (game.warfare.deception).

Each decoy of a ground object becomes an inert vehicle group of the site's
own vehicle types (its radar and launchers) at the decoy's position: alarm
state green (radars off) and weapons held, so it neither radiates nor
shoots. A package that took the decoy for the site (the decoy call) gets its
attack tasks pointed at this group, the same tasks it would fly against the
real one; a player flying to the believed position finds the same thing.

Decoys aren't tracked: destroying one in DCS changes nothing in the
campaign (the debrief ignores units it doesn't know); the decoy call decides
what the strike did to the picture.
"""

from __future__ import annotations

import logging
import math
from typing import Optional, TYPE_CHECKING

from dcs import Mission
from dcs.mapping import Point
from dcs.task import OptAlarmState, OptROE
from dcs.unitgroup import VehicleGroup
from dcs.unittype import VehicleType

if TYPE_CHECKING:
    from game import Game
    from game.theater import TheaterGroundObject

#: Vehicles per decoy and their spacing.
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


def decoy_group_name(tgo_name: str, index: int) -> str:
    """The DCS group of a site's decoy, by its index in the site's decoys
    (the index a decoy call names)."""
    return f"Decoy {tgo_name} {index + 1}"


class DecoyGenerator:
    def __init__(self, mission: Mission, game: Game) -> None:
        self.mission = mission
        self.game = game
        self.targeted: list[tuple[float, float]] = []

    def generate(self) -> int:
        from game.warfare.deception import enabled

        war_state = getattr(self.game, "war_state", None)
        if war_state is None or not enabled(self.game):
            return 0
        by_id = {t.id: t for t in self.game.theater.ground_objects}
        # Decoys a package in the mission will attack spawn even where the
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
            logging.info(f"Spawned {placed} decoys")
        return placed

    def _spawn(
        self, tgo: TheaterGroundObject, offsets: list[tuple[float, float]]
    ) -> int:
        types: list[type[VehicleType]] = []
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
            name = decoy_group_name(tgo.name, i)
            group: Optional[VehicleGroup] = None
            for j, unit_type in enumerate(types):
                angle = 2 * math.pi * j / len(types)
                spot = point.point_from_heading(
                    math.degrees(angle), SPACING_M if j else 0
                )
                if group is None:
                    group = self.mission.vehicle_group(
                        country, name, unit_type, position=spot
                    )
                    group.units[0].name = f"{name} #1"
                else:
                    vehicle = self.mission.vehicle(f"{name} #{j + 1}", unit_type)
                    vehicle.position = spot
                    group.add_unit(vehicle)
            if group is None:
                continue
            # Inert: radars off and weapons held, so it neither radiates
            # (nothing for ARMs) nor shoots.
            group.points[0].tasks.append(OptAlarmState(1))
            group.points[0].tasks.append(OptROE(OptROE.Values.WeaponHold))
            placed += 1
        return placed
