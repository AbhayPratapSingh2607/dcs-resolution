"""Establishing, maintaining and dismantling player-built FARPs.

FARPs are stored as :class:`DynamicFarp` control points in the theater, so they're
persisted with the save game. :class:`FarpManager` holds no state of its own and
can be created on demand for a coalition.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional, TYPE_CHECKING

from dcs.mapping import Point
from shapely.geometry import LineString, Point as ShapelyPoint

from game.ato import Flight, FlightType, Package
from game.ato.closestairfields import ObjectiveDistanceCache
from game.ato.flightplans.planningerror import PlanningError
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
    farp_footprint_radius,
    fatcow_object_name,
)
from game.theater.farpterrain import SiteTerrain, UNKNOWN_SITE
from game.utils import Heading, meters, nautical_miles

if TYPE_CHECKING:
    from game import Game
    from game.coalition import Coalition
    from game.squadrons import Squadron
    from game.sim import GameUpdateEvents
    from game.theater import ControlPoint, FrontLine

#: Minimum spacing between a FARP and any other control point.
MIN_CONTROL_POINT_SPACING = nautical_miles(3)
#: Minimum spacing between a FARP and any ground object.
MIN_TGO_SPACING = nautical_miles(1)


@dataclass(frozen=True)
class FrontSituation:
    """Where a point is relative to its nearest front line."""

    front_line: FrontLine
    #: Distance in meters to where the front currently is.
    distance: float
    #: Whether the front has moved past the point, putting it on the enemy side.
    behind_enemy_lines: bool


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
        # Nothing to maintain until the equipment has been delivered.
        return sum(f.upkeep_per_turn for f in self.farps if f.established)

    @property
    def instant_setup(self) -> bool:
        return self.game.settings.enable_instant_farp_cheat

    # Setup flights

    def setup_squadron(self, kind: FarpKind, point: Point) -> Optional[Squadron]:
        """The nearest squadron that can fly a FARP's equipment in.

        A Fat Cow is set up by a transport helicopter that lands at the site. A Wet
        Wing is airdropped by a transport plane; if the coalition has none
        available, a transport helicopter can fly it in instead.
        """
        candidates: dict[bool, list[Squadron]] = {True: [], False: []}
        for squadron in self.coalition.air_wing.iter_squadrons():
            if squadron.is_detachment or squadron.untasked_aircraft < 1:
                continue
            if not squadron.has_available_pilots:
                continue
            if not squadron.aircraft.capable_of(FlightType.TRANSPORT):
                continue
            candidates[squadron.aircraft.helicopter].append(squadron)
        preferred = [True] if kind is FarpKind.FAT_COW else [False, True]
        for helicopter in preferred:
            if candidates[helicopter]:
                return min(
                    candidates[helicopter],
                    key=lambda s: s.location.position.distance_to_point(point),
                )
        return None

    def setup_package(self, farp: DynamicFarp) -> Optional[Package]:
        for package in self.coalition.ato.packages:
            if package.target == farp:
                return package
        return None

    def plan_setup_flight(
        self,
        farp: DynamicFarp,
        now: datetime,
        events: Optional[GameUpdateEvents] = None,
    ) -> Optional[Flight]:
        """Plans the flight that delivers a FARP's equipment this turn."""
        squadron = self.setup_squadron(farp.kind, farp.position)
        if squadron is None:
            return None
        package = Package(farp, self.game.db.flights)
        start_type = squadron.location.required_aircraft_start_type
        if start_type is None:
            start_type = self.game.settings.default_start_type
        flight = Flight(
            package, squadron, 1, FlightType.TRANSPORT, start_type, divert=None
        )
        package.add_flight(flight)
        try:
            flight.recreate_flight_plan()
        except PlanningError:
            logging.exception(f"Could not plan the setup flight for {farp.name}")
            package.remove_flight(flight)
            return None
        package.set_tot_asap(now)
        self.coalition.ato.add_package(package)
        if events is not None:
            events.new_flight(flight)
        return flight

    def plan_setup_flights(self, now: datetime) -> None:
        """Plans setup flights for FARPs still waiting for their equipment.

        Called at the start of each turn, after the ATO has been cleared. With the
        instant FARP cheat on, waiting FARPs are set up immediately instead.
        """
        for farp in self.farps:
            if farp.established or self.setup_package(farp) is not None:
                continue
            if self.instant_setup:
                farp.establish()
                continue
            if self.plan_setup_flight(farp, now) is None:
                self.game.message(
                    f"{farp.name} is waiting for a transport",
                    "No transport aircraft is available to fly the FARP's "
                    "equipment in this turn.",
                )

    def commit_setups(self, farp_ids: Iterable[str], events: GameUpdateEvents) -> None:
        """Establishes FARPs whose equipment was delivered in the mission."""
        delivered = set(farp_ids)
        for farp in self.farps:
            if farp.established or str(farp.id) not in delivered:
                continue
            package = self.setup_package(farp)
            if package is not None and package.flights:
                farp.setup_aircraft = package.flights[0].unit_type
            farp.establish()
            events.update_control_point(farp)
            self.game.message(
                f"{farp.name} established",
                f"The FARP's equipment has been delivered. Upkeep: "
                f"${farp.upkeep_per_turn}M per turn.",
            )

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

    def front_situation(self, point: Point) -> Optional[FrontSituation]:
        """Where point is relative to the nearest front line, or None if there's
        no active front.

        A front sits at a point on the route between two bases, moving along it as
        the battle goes, and the ground war spreads out across the route from there
        (see _front_segment). The point is behind
        enemy lines when, measured along that route, it's past the front on the
        enemy's side.
        """
        best: Optional[FrontSituation] = None
        target = ShapelyPoint(point.x, point.y)
        for front_line in self.game.theater.conflicts():
            front = self._front_segment(front_line)
            distance = front.distance(target)
            if best is not None and distance >= best.distance:
                continue
            coords = [(p.x, p.y) for p in front_line.points]
            behind = False
            if len(coords) >= 2:
                progress = LineString(coords).project(ShapelyPoint(point.x, point.y))
                past_front = progress > front_line.blue_route_progress
                behind = past_front if self.coalition.player.is_blue else not past_front
            best = FrontSituation(front_line, distance, behind)
        return best

    def _front_segment(self, front_line: FrontLine) -> LineString:
        """Where the ground war is: a line across the route through the front's
        current position, as wide as the front line width setting and clipped to
        land, like the mission generator lays out the front."""
        from game.missiongenerator.frontlineconflictdescription import (
            FrontLineConflictDescription,
        )

        center = front_line.current_position
        across = front_line.blue_forward_heading.right
        half_width = int(self.game.settings.max_frontline_width * 1000 / 2)
        ends = [
            FrontLineConflictDescription.extend_ground_position(
                center, half_width, heading, self.game.theater
            )
            for heading in (across, across.opposite)
        ]
        return LineString([(p.x, p.y) for p in ends])

    def distance_to_front_line(self, point: Point) -> Optional[float]:
        """Distance in meters from point to where the nearest front line is."""
        situation = self.front_situation(point)
        return situation.distance if situation is not None else None

    def site_terrain(self, point: Point, kind: FarpKind) -> SiteTerrain:
        """What the theater's terrain grid says about the area a FARP of this kind
        would cover at point."""
        terrain = self.game.theater.farp_terrain
        if terrain is None:
            return UNKNOWN_SITE
        radius = farp_footprint_radius(kind, self.capacity(kind))
        return terrain.survey(point, radius)

    def check_site(self, point: Point, kind: FarpKind) -> SiteCheck:
        settings = self.game.settings
        theater = self.game.theater
        check = SiteCheck(kind, self.deploy_cost(kind))
        reasons = check.reasons

        if not settings.enable_dynamic_farps:
            reasons.append("Dynamic FARPs are disabled in the settings.")
            return check
        if not self.coalition.player.is_blue:
            # Only the player establishes FARPs. The AI plans missions for
            # helicopters stationed at them, but never builds one.
            reasons.append("Only the player can establish FARPs.")
            return check

        if not self.instant_setup and self.setup_squadron(kind, point) is None:
            if kind is FarpKind.FAT_COW:
                reasons.append(
                    "No transport helicopter available to fly the equipment in."
                )
            else:
                reasons.append(
                    "No transport aircraft available to airdrop the equipment."
                )

        if len(self.farps) >= self.max_farps:
            reasons.append(f"Limit of {self.max_farps} FARP(s) reached.")
        if self.coalition.budget < check.cost:
            reasons.append(f"Not enough money (${check.cost}M needed).")
        if not theater.is_on_land(point):
            reasons.append("FARPs must be built on land.")
        else:
            terrain = self.site_terrain(point, kind)
            if terrain.steep:
                reasons.append("Terrain too uneven for a FARP.")
            if terrain.built_up:
                reasons.append("Too close to a built-up area.")

        for cp in theater.controlpoints:
            if cp.position.distance_to_point(point) < MIN_CONTROL_POINT_SPACING.meters:
                reasons.append(f"Too close to {cp.name}.")
                break
        for tgo in theater.ground_objects:
            if tgo.position.distance_to_point(point) < MIN_TGO_SPACING.meters:
                reasons.append(f"Too close to {tgo.obj_name}.")
                break

        situation = self.front_situation(point)
        if situation is None:
            reasons.append("There is no active front line.")
            return check
        front_distance = situation.distance

        owner = self.nearest_territory_owner(point)
        if owner is None:
            reasons.append("No territory to build in.")
            return check

        # Both FARP types follow the same rules: friendly territory, within the
        # configured distance band from the front.
        if not owner.is_friendly(self.coalition.player):
            reasons.append("FARPs must be in friendly territory.")
        elif situation.behind_enemy_lines:
            reasons.append("FARPs must be on our side of the front line.")
        min_dist = nautical_miles(settings.farp_min_frontline_distance)
        # A maximum of 0 means no limit.
        max_nm = settings.farp_max_frontline_distance
        max_dist = nautical_miles(max_nm)
        if front_distance < min_dist.meters:
            reasons.append(
                f"Too close to the front line (min {min_dist.nautical_miles:.0f}nm)."
            )
        elif max_nm > 0 and front_distance > max_dist.meters:
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
        self,
        point: Point,
        kind: FarpKind,
        events: GameUpdateEvents,
        now: Optional[datetime] = None,
    ) -> DynamicFarp:
        """Orders a FARP at point.

        Unless the instant FARP cheat is on, the FARP is only set up once a
        transport has flown its equipment in (see plan_setup_flight).
        """
        check = self.check_site(point, kind)
        if not check.valid:
            raise ValueError(" ".join(check.reasons))
        instant = self.instant_setup

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
            established=instant,
        )
        farp.finish_init(self.game)
        self.game.theater.add_controlpoint(farp)
        self.coalition.adjust_budget(-check.cost)
        self._control_points_changed(events)
        events.update_control_point(farp)
        if instant:
            self.game.message(
                f"{farp.name} established",
                f"{kind.display_name} FARP established for ${check.cost}M. "
                f"Upkeep: ${farp.upkeep_per_turn}M per turn.",
            )
        else:
            flight = self.plan_setup_flight(
                farp, now or self.game.conditions.start_time, events
            )
            how = "land at" if flight is None or flight.is_helo else "airdrop over"
            self.game.message(
                f"{farp.name} ordered",
                f"{kind.display_name} FARP ordered for ${check.cost}M. A transport "
                f"must {how} the site to set it up.",
            )
        logging.info(f"Ordered {kind.value} FARP {farp.name} at {point}")
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
        if not farp.established:
            # Nothing was delivered, so the deployment cost is returned.
            cost = self.deploy_cost(farp.kind)
            self.coalition.adjust_budget(cost)
            reason = f"{reason} before it was set up (${cost}M refunded)"
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
        """Deducts upkeep, evacuates overrun FARPs and warns about threatened ones.

        Called after the turn counter has advanced and base captures have been
        committed.
        """
        for farp in self.farps:
            if (cause := self._overrun_cause(farp)) is not None:
                self.dismantle(
                    farp,
                    events,
                    reason=f"lost: {cause}. Its helicopters fell back to base",
                )
        self._warn_about_nearby_fronts()

        upkeep = self.total_upkeep
        if upkeep:
            self.coalition.adjust_budget(-upkeep)
            logging.info(f"Paid ${upkeep}M FARP upkeep for {self.coalition.player}")

        # Can't pay the bills: abandon the newest FARPs until we're solvent.
        while self.coalition.budget < 0 and self.farps:
            newest = max(self.farps, key=lambda f: f.established_turn)
            self.dismantle(newest, events, reason="abandoned (no funds for upkeep)")

    def _overrun_cause(self, farp: DynamicFarp) -> Optional[str]:
        """Why the enemy has taken the FARP's ground, or None if it hasn't: its
        nearest base was captured, or the front line moved past it.

        The FARP and its equipment are lost (no refund); the helicopters stationed
        there escape to their home base.
        """
        owner = self.nearest_territory_owner(farp.position)
        if owner is not None and not owner.is_friendly(self.coalition.player):
            return f"{owner.name} was captured"
        situation = self.front_situation(farp.position)
        if situation is not None and situation.behind_enemy_lines:
            return "the front line moved past it"
        return None

    def _warn_about_nearby_fronts(self) -> None:
        """Warns about FARPs the front line has come within the minimum building
        distance of. Only being overrun costs the FARP."""
        min_dist = nautical_miles(self.game.settings.farp_min_frontline_distance)
        for farp in self.farps:
            situation = self.front_situation(farp.position)
            if situation is None or situation.distance >= min_dist.meters:
                continue
            self.game.message(
                f"{farp.name} is threatened",
                f"The front line is {meters(situation.distance).nautical_miles:.1f}nm "
                f"from "
                f"{farp.name}. If it moves past the FARP, the FARP will be lost.",
            )

    @staticmethod
    def fuel_depot_names(farp: DynamicFarp) -> set[str]:
        """Unit names of the FARP's fuel statics, as HelipadGenerator creates them.

        pydcs names a static's unit "<group name> object". The Fat Cow layout's
        statics are named like their group instead (see TgoGenerator._place_layout).
        """
        if farp.is_fat_cow:
            return {fatcow_object_name(farp.name, key) for key in FATCOW_FUEL_KEYS}
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
