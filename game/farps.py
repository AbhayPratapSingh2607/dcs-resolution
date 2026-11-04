"""Establishing, maintaining and dismantling player-built FARPs.

FARPs are stored as :class:`DynamicFarp` control points in the theater, so they're
persisted with the save game. :class:`FarpManager` holds no state of its own and
can be created on demand for a coalition.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Optional, TYPE_CHECKING

from dcs.mapping import Point
from shapely.geometry import LineString, Point as ShapelyPoint

from game.ato.closestairfields import ObjectiveDistanceCache
from game.squadrons.detachments import (
    destroy_detachment,
    detachments_at,
    recall_detachment,
)
from game.theater.dynamicfarp import (
    DynamicFarp,
    FARP_CALLSIGNS,
    FAT_COW_CAPACITY,
    FATCOW_FUEL_KEYS,
    FarpKind,
    fatcow_object_name,
)
from game.utils import Heading, nautical_miles

if TYPE_CHECKING:
    from game import Game
    from game.coalition import Coalition
    from game.sim import GameUpdateEvents
    from game.theater import ControlPoint

#: Minimum spacing between a FARP and any other control point.
MIN_CONTROL_POINT_SPACING = nautical_miles(3)
#: Minimum spacing between a FARP and any ground object.
MIN_TGO_SPACING = nautical_miles(1)


@dataclass
class SiteCheck:
    kind: FarpKind
    cost: int
    reasons: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.reasons


class FarpManager:
    def __init__(self, coalition: Coalition) -> None:
        self.coalition = coalition

    @property
    def game(self) -> Game:
        return self.coalition.game

    @property
    def farps(self) -> list[DynamicFarp]:
        return [
            cp
            for cp in self.game.theater.controlpoints
            if isinstance(cp, DynamicFarp) and cp.captured == self.coalition.player
        ]

    @property
    def total_upkeep(self) -> int:
        return sum(f.upkeep_per_turn for f in self.farps)

    def deploy_cost(self, kind: FarpKind) -> int:
        settings = self.game.settings
        if kind is FarpKind.FAT_COW:
            return settings.fat_cow_farp_deploy_cost
        return settings.wet_wing_farp_deploy_cost

    @property
    def max_farps(self) -> int:
        """Limit on FARPs of both types together."""
        return self.game.settings.max_farps

    def capacity(self, kind: FarpKind) -> int:
        if kind is FarpKind.FAT_COW:
            return FAT_COW_CAPACITY
        return self.game.settings.wet_wing_farp_capacity

    # Placement

    def _regular_control_points(self) -> Iterable[ControlPoint]:
        """Non-neutral, non-FARP, non-offmap control points that define territory."""
        for cp in self.game.theater.controlpoints:
            if cp.is_dynamic_farp or cp.is_offmap or cp.captured.is_neutral:
                continue
            if cp.is_fleet:
                continue
            yield cp

    def nearest_territory_owner(self, point: Point) -> Optional[ControlPoint]:
        candidates = list(self._regular_control_points())
        if not candidates:
            return None
        return min(candidates, key=lambda cp: cp.position.distance_to_point(point))

    def distance_to_front_line(self, point: Point) -> Optional[float]:
        """Distance in meters from point to the closest active front line."""
        target = ShapelyPoint(point.x, point.y)
        best: Optional[float] = None
        for front_line in self.game.theater.conflicts():
            coords = [(p.x, p.y) for p in front_line.points]
            if len(coords) < 2:
                distance = front_line.position.distance_to_point(point)
            else:
                distance = LineString(coords).distance(target)
            if best is None or distance < best:
                best = distance
        return best

    def check_site(self, point: Point, kind: FarpKind) -> SiteCheck:
        settings = self.game.settings
        theater = self.game.theater
        check = SiteCheck(kind, self.deploy_cost(kind))
        reasons = check.reasons

        if not settings.enable_dynamic_farps:
            reasons.append("Dynamic FARPs are disabled in the settings.")
            return check

        if len(self.farps) >= self.max_farps:
            reasons.append(f"Limit of {self.max_farps} FARP(s) reached.")
        if self.coalition.budget < check.cost:
            reasons.append(f"Not enough money (${check.cost}M needed).")
        if not theater.is_on_land(point):
            reasons.append("FARPs must be built on land.")

        for cp in theater.controlpoints:
            if cp.position.distance_to_point(point) < MIN_CONTROL_POINT_SPACING.meters:
                reasons.append(f"Too close to {cp.name}.")
                break
        for tgo in theater.ground_objects:
            if tgo.position.distance_to_point(point) < MIN_TGO_SPACING.meters:
                reasons.append(f"Too close to {tgo.obj_name}.")
                break

        front_distance = self.distance_to_front_line(point)
        if front_distance is None:
            reasons.append("There is no active front line.")
            return check

        owner = self.nearest_territory_owner(point)
        if owner is None:
            reasons.append("No territory to build in.")
            return check

        # Both FARP types follow the same rules: friendly territory, within the
        # configured distance band from the front.
        if not owner.is_friendly(self.coalition.player):
            reasons.append("FARPs must be in friendly territory.")
        min_dist = nautical_miles(settings.farp_min_frontline_distance)
        max_dist = nautical_miles(settings.farp_max_frontline_distance)
        if front_distance < min_dist.meters:
            reasons.append(
                f"Too close to the front line (min {min_dist.nautical_miles:.0f}nm)."
            )
        elif front_distance > max_dist.meters:
            reasons.append(
                f"Too far from the front line (max {max_dist.nautical_miles:.0f}nm)."
            )
        return check

    # Lifecycle

    def _next_name(self) -> str:
        used = {cp.name for cp in self.game.theater.controlpoints}
        suffix = 1
        while True:
            for callsign in FARP_CALLSIGNS:
                name = f"FARP {callsign}"
                if suffix > 1:
                    name = f"{name} {suffix}"
                if name not in used:
                    return name
            suffix += 1

    def establish(
        self, point: Point, kind: FarpKind, events: GameUpdateEvents
    ) -> DynamicFarp:
        check = self.check_site(point, kind)
        if not check.valid:
            raise ValueError(" ".join(check.reasons))

        heading = self.game.theater.heading_to_conflict_from(point)
        farp = DynamicFarp(
            self._next_name(),
            point,
            heading or Heading.from_degrees(0),
            self.game.theater,
            self.coalition.player,
            kind,
            self.capacity(kind),
            self.game.turn,
        )
        farp.finish_init(self.game)
        self.game.theater.add_controlpoint(farp)
        self.coalition.adjust_budget(-check.cost)
        self._control_points_changed(events)
        events.update_control_point(farp)
        self.game.message(
            f"{farp.name} established",
            f"{kind.display_name} FARP established for ${check.cost}M. "
            f"Upkeep: ${farp.upkeep_per_turn}M per turn.",
        )
        logging.info(f"Established {kind.value} FARP {farp.name} at {point}")
        return farp

    def dismantle(
        self,
        farp: DynamicFarp,
        events: GameUpdateEvents,
        reason: str = "dismantled",
        destroyed: bool = False,
    ) -> None:
        for det in detachments_at(farp):
            # Helicopters still flying in weren't at the FARP: they turn back.
            if destroyed and det.location == farp:
                destroy_detachment(det, events)
            else:
                recall_detachment(det, events)

        self._remove_flights_involving(farp, events)
        self.game.theater.controlpoints.remove(farp)
        self._control_points_changed(events)
        events.delete_control_point(farp)
        self.game.message(f"{farp.name} {reason}")
        logging.info(f"FARP {farp.name} {reason}")

    def _remove_flights_involving(
        self, farp: DynamicFarp, events: GameUpdateEvents
    ) -> None:
        for coalition in (self.game.blue, self.game.red):
            ato = coalition.ato
            for package in list(ato.packages):
                if package.target == farp:
                    for flight in package.flights:
                        events.delete_flight(flight)
                    ato.remove_package(package)
                    continue
                for flight in list(package.flights):
                    if flight.departure == farp or flight.arrival == farp:
                        events.delete_flight(flight)
                        package.remove_flight(flight)
                    elif flight.divert == farp:
                        flight.divert = None
                if not package.flights:
                    ato.remove_package(package)

    def _control_points_changed(self, events: GameUpdateEvents) -> None:
        ObjectiveDistanceCache.invalidate()
        self.game.compute_threat_zones(events)

    def end_turn(self, events: GameUpdateEvents) -> None:
        """Deducts upkeep and evacuates overrun FARPs.

        Called after the turn counter has advanced and base captures have been
        committed.
        """
        for farp in self.farps:
            owner = self.nearest_territory_owner(farp.position)
            if owner is not None and not owner.is_friendly(self.coalition.player):
                self.dismantle(farp, events, reason="evacuated (overrun)")

        upkeep = self.total_upkeep
        if upkeep:
            self.coalition.adjust_budget(-upkeep)
            logging.info(f"Paid ${upkeep}M FARP upkeep for {self.coalition.player}")

        # Can't pay the bills: abandon the newest FARPs until we're solvent.
        while self.coalition.budget < 0 and self.farps:
            newest = max(self.farps, key=lambda f: f.established_turn)
            self.dismantle(newest, events, reason="abandoned (no funds for upkeep)")

    @staticmethod
    def fuel_depot_names(farp: DynamicFarp) -> set[str]:
        """Unit names of the FARP's fuel statics, as HelipadGenerator creates them.

        pydcs names a static's unit "<group name> object".
        """
        if farp.is_fat_cow:
            return {
                f"{fatcow_object_name(farp.name, key)} object"
                for key in FATCOW_FUEL_KEYS
            }
        names = set()
        for pad_type, pads in (
            ("SINGLE_HELIPAD", farp.helipads),
            ("FARP", farp.helipads_quad),
            ("Invisible FARP", farp.helipads_invisible),
        ):
            for i in range(len(pads)):
                names.add(f"{farp.name} {pad_type} {i}_fuel object")
        return names

    def commit_losses(
        self, killed_unit_names: Iterable[str], events: GameUpdateEvents
    ) -> None:
        """Destroys FARPs whose fuel depots were all destroyed in the mission."""
        killed = set(killed_unit_names)
        for farp in self.farps:
            depots = self.fuel_depot_names(farp)
            if depots and depots <= killed:
                self.dismantle(farp, events, reason="destroyed", destroyed=True)
