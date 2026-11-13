"""Establishing, maintaining and dismantling player-built FARPs.

FARPs are stored as :class:`DynamicFarp` control points in the theater, so they're
persisted with the save game. :class:`FarpManager` holds no state of its own and
can be created on demand for a coalition.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    RESCUE_KING_CAPACITY,
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
#: A Rescue King this close to an enemy fighter base gets a warning: its
#: fighters can be on the King within minutes of taking off.
KING_FIGHTER_WARNING = nautical_miles(120)


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
    #: Risks worth knowing that don't stop the site being used.
    warnings: list[str] = field(default_factory=list)

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
    def ground_farps(self) -> list[DynamicFarp]:
        """Wet Wings and Fat Cows: the FARPs on the ground."""
        return [f for f in self.farps if not f.is_rescue_king]

    @property
    def kings(self) -> list[DynamicFarp]:
        return [f for f in self.farps if f.is_rescue_king]

    @property
    def total_upkeep(self) -> int:
        # Nothing to maintain until the equipment has been delivered.
        return sum(f.upkeep_per_turn for f in self.farps if f.established)

    @property
    def instant_setup(self) -> bool:
        settings = self.game.settings
        # With no transport needed, nothing flies the equipment in.
        return settings.enable_instant_farp_cheat or settings.farps_need_no_transport

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
        for king in self.kings:
            if self.king_package(king) is None:
                self.plan_king_flight(king, now)
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
        if kind is FarpKind.RESCUE_KING:
            # A sortie, not a base: the aircraft are the cost.
            return 0
        if kind is FarpKind.FAT_COW:
            return settings.fat_cow_farp_deploy_cost
        return settings.wet_wing_farp_deploy_cost

    @property
    def max_farps(self) -> int:
        """Limit on FARPs of both types together."""
        return self.game.settings.max_farps

    def capacity(self, kind: FarpKind) -> int:
        if kind is FarpKind.RESCUE_KING:
            return RESCUE_KING_CAPACITY
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
        if kind is FarpKind.RESCUE_KING:
            return self.check_king_site(point)
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

        if len(self.ground_farps) >= self.max_farps:
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
        if kind is FarpKind.RESCUE_KING:
            return self.establish_king(point, events, now)
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
        for king in self.kings:
            self.dismantle(
                king,
                events,
                reason="is over: its helicopters went back to their squadron",
            )
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
        for farp in self.ground_farps:
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

    # Rescue Kings

    @property
    def no_transport_needed(self) -> bool:
        """FARPs and Rescue Kings need no transport from the air wing."""
        return self.game.settings.farps_need_no_transport

    def king_squadrons(
        self, point: Point, current: Optional[Squadron] = None
    ) -> list[tuple[Squadron, Optional[str]]]:
        """Every C-130/KC-130 squadron that could orbit a King at ``point``,
        nearest first, with why it can't (None if it can).

        ``current`` is the squadron already flying the orbit: its aircraft is
        claimed by that flight, so it counts as available.
        """
        squadrons: list[tuple[Squadron, Optional[str]]] = []
        for s in self.coalition.air_wing.iter_squadrons():
            if s.is_detachment or not s.capable_of(FlightType.RESCUE_KING):
                continue
            reason: Optional[str] = None
            if s is current:
                pass
            elif not s.can_auto_assign(FlightType.RESCUE_KING):
                reason = "Rescue King is turned off for this squadron (Air Wing)"
            elif s.untasked_aircraft < 1:
                reason = "no aircraft free"
            elif not s.can_provide_pilots(1):
                reason = "no crew free"
            squadrons.append((s, reason))
        squadrons.sort(key=lambda c: c[0].location.position.distance_to_point(point))
        return squadrons

    def king_squadron(self, point: Point) -> Optional[Squadron]:
        """The nearest C-130/KC-130 squadron with Rescue King turned on and an
        aircraft and crew free: the King's orbit unless the player picks
        another."""
        for squadron, reason in self.king_squadrons(point):
            if reason is None:
                return squadron
        return None

    @staticmethod
    def king_flight(package: Optional[Package]) -> Optional[Flight]:
        if package is None:
            return None
        for flight in package.flights:
            if flight.flight_type is FlightType.RESCUE_KING:
                return flight
        return None

    def king_package(self, king: DynamicFarp) -> Optional[Package]:
        """The package of the King's orbit flight (other packages, such as a
        CAP over it, can target the King too)."""
        for package in self.coalition.ato.packages:
            if package.target == king and self.king_flight(package) is not None:
                return package
        return None

    def set_king_aircraft(
        self,
        king: DynamicFarp,
        squadron: Optional[Squadron],
        now: Optional[datetime] = None,
        events: Optional[GameUpdateEvents] = None,
    ) -> Optional[Flight]:
        """Changes the aircraft orbiting ``king``: ``squadron`` of the air
        wing, or None for the KC-130 from outside it (only when FARPs need no
        transport). The old orbit flight is cancelled and a new one planned."""
        if squadron is None and not self.no_transport_needed:
            raise ValueError(
                "A KC-130 from outside the air wing needs the setting "
                "'FARPs and Rescue Kings need no transport aircraft'."
            )
        package = self.king_package(king)
        current = self.king_flight(package)
        if squadron is not None:
            available = dict(
                self.king_squadrons(
                    king.position, current.squadron if current else None
                )
            )
            if squadron not in available:
                raise ValueError(f"{squadron} can't fly Rescue King.")
            if available[squadron] is not None:
                raise ValueError(f"{squadron}: {available[squadron]}.")
        tot: Optional[datetime] = None
        if package is not None:
            if not package.auto_asap:
                tot = package.time_over_target
            for flight in list(package.flights):
                if events is not None:
                    events.delete_flight(flight)
                package.remove_flight(flight)
            self.coalition.ato.remove_package(package)
        king.king_squadron_choice = squadron
        king.king_outside_tanker = squadron is None
        return self.plan_king_flight(
            king, now or self.game.conditions.start_time, events, tot
        )

    def _king_orbit_squadron(self, king: DynamicFarp) -> Optional[Squadron]:
        """Who flies the King's orbit: the player's choice if it can still go,
        else the KC-130 from outside the air wing when FARPs need no transport,
        else the nearest squadron with Rescue King on. None for the outside
        KC-130 is told apart from "nobody" by ``no_transport_needed``."""
        choice = king.king_squadron_choice
        if choice is not None:
            for squadron, reason in self.king_squadrons(king.position):
                if squadron is choice and reason is None:
                    return choice
        if self.no_transport_needed and (
            king.king_outside_tanker or king.king_squadron_choice is None
        ):
            return None
        return self.king_squadron(king.position)

    @staticmethod
    def can_rescue_from_king(squadron: Squadron) -> bool:
        """Whether helicopters of ``squadron`` can be sent to a Rescue King."""
        return (
            not squadron.is_detachment
            and squadron.aircraft.helicopter
            and squadron.capable_of(FlightType.CSAR)
        )

    def rescue_squadron(self, point: Point) -> Optional[Squadron]:
        """The squadron a new King's helicopters come from unless the player
        picks others: the nearest one with CSAR enabled that can spare a pair,
        else one that can spare a single helicopter."""
        candidates = [
            s
            for s in self.coalition.air_wing.iter_squadrons()
            if self.can_rescue_from_king(s)
            and s.destination is None
            and s.untasked_aircraft >= 1
            and s.can_provide_pilots(1)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda s: (
                not s.can_auto_assign(FlightType.CSAR),
                not s.can_provide_pilots(RESCUE_KING_CAPACITY)
                or s.untasked_aircraft < RESCUE_KING_CAPACITY,
                s.location.position.distance_to_point(point),
            ),
        )

    def check_king_site(self, point: Point) -> SiteCheck:
        check = SiteCheck(FarpKind.RESCUE_KING, 0)
        reasons = check.reasons
        if not self.game.settings.enable_dynamic_farps:
            reasons.append("Dynamic FARPs are disabled in the settings.")
            return check
        if not self.coalition.player.is_blue:
            reasons.append("Only the player can place a Rescue King.")
            return check
        if not self.no_transport_needed and self.king_squadron(point) is None:
            reasons.append(
                "No C-130 or KC-130 squadron with Rescue King turned on and an "
                "aircraft and crew free to fly the King's orbit."
            )
        if self.rescue_squadron(point) is None:
            reasons.append("No CSAR-capable helicopter and crew to send to it.")
        defenses = self.coalition.opponent.threat_zone.air_defenses
        if defenses.intersects(ShapelyPoint(point.x, point.y)):
            reasons.append("Inside enemy air defense coverage.")
        for king in self.kings:
            if (
                king.position.distance_to_point(point)
                < MIN_CONTROL_POINT_SPACING.meters
            ):
                reasons.append(f"Too close to {king.name}.")
                break
        try:
            check.warnings.extend(self.king_fighter_warnings(point))
        except Exception:
            # Advisory only: never let it stop a placement.
            logging.exception("Could not check enemy fighter bases near a King")
        return check

    def king_fighter_warnings(self, point: Point) -> list[str]:
        """Enemy fighter bases within reach of a King at this point. Not a
        reason to refuse it (the player may cover it with CAP), but a C-130
        circling alone near a fighter base is easy prey."""
        bases: list[tuple[float, str]] = []
        enemy = self.coalition.opponent
        for cp in self.game.theater.controlpoints:
            if cp.captured != enemy.player:
                continue
            distance = cp.position.distance_to_point(point)
            if distance > KING_FIGHTER_WARNING.meters:
                continue
            fighters: dict[str, int] = {}
            for squadron in enemy.air_wing.iter_squadrons():
                if squadron.location is not cp or squadron.owned_aircraft <= 0:
                    continue
                if not squadron.aircraft.capable_of(FlightType.BARCAP):
                    continue
                name = squadron.aircraft.display_name
                fighters[name] = fighters.get(name, 0) + squadron.owned_aircraft
            if fighters:
                listed = ", ".join(f"{n} {t}" for t, n in fighters.items())
                bases.append(
                    (
                        distance,
                        f"{cp.name} ({listed}) is "
                        f"{meters(distance).nautical_miles:.0f} nm away",
                    )
                )
        if not bases:
            return []
        bases.sort()
        return [
            "Warning: enemy fighters can reach the King, and nothing escorts "
            "it. Cover it with a CAP. "
            + "; ".join(text for _, text in bases[:3])
            + "."
        ]

    def _next_king_name(self) -> str:
        used = {cp.name for cp in self.game.theater.controlpoints}
        number = 1
        while f"King {number}" in used:
            number += 1
        return f"King {number}"

    def establish_king(
        self, point: Point, events: GameUpdateEvents, now: Optional[datetime] = None
    ) -> DynamicFarp:
        """Places a Rescue King: a C-130 orbits ``point`` for the rest of the
        turn, and rescue helicopters are stationed on it at once.

        The nearest CSAR helicopters go first; the player can swap them in the
        King's menu (QFarpCommand), which the map opens after placing it.
        """
        heli_parent = self.rescue_squadron(point)
        assert heli_parent is not None
        heading = self.game.theater.heading_to_conflict_from(point)
        king = DynamicFarp(
            self._next_king_name(),
            point,
            heading or Heading.from_degrees(0),
            self.game.theater,
            self.coalition.player,
            FarpKind.RESCUE_KING,
            RESCUE_KING_CAPACITY,
            self.game.turn,
            established=True,
        )
        king.finish_init(self.game)
        self.game.theater.add_controlpoint(king)
        self._control_points_changed(events)
        events.update_control_point(king)

        now = now or self.game.conditions.start_time
        flight = self.plan_king_flight(king, now, events)
        count = min(RESCUE_KING_CAPACITY, heli_parent.untasked_aircraft)
        if heli_parent.pilot_limits_enabled:
            count = min(count, heli_parent.number_of_available_pilots)
        self.station_king_helicopters(king, heli_parent, count, now, events)
        aircraft = flight.unit_type if flight is not None else "C-130"
        self.game.message(
            f"{king.name} on station",
            f"A {aircraft} orbits {king.name} this turn with {count} "
            f"{heli_parent.aircraft} of {heli_parent.name}. Change the King "
            f"aircraft or the helicopters in the menu of {king.name}. The "
            "helicopters fly a rescue of the nearest downed pilot; or plan one "
            "by hand.",
        )
        logging.info(f"Placed Rescue King {king.name} at {point}")
        return king

    def station_king_helicopters(
        self,
        king: DynamicFarp,
        squadron: Squadron,
        count: int,
        now: Optional[datetime] = None,
        events: Optional[GameUpdateEvents] = None,
    ) -> Squadron:
        """Sends ``count`` helicopters of ``squadron`` to the King at once, for
        CSAR only, and sends them to the nearest downed pilot."""
        from game.squadrons.detachments import create_detachment

        if not self.can_rescue_from_king(squadron):
            raise ValueError(f"{squadron} can't fly CSAR.")
        now = now or self.game.conditions.start_time
        det = create_detachment(squadron, king, count, now, events, instant=True)
        # They are there for the rescue: the planner only sends them on CSAR.
        det.set_auto_assignable_mission_types({FlightType.CSAR})
        self.plan_king_rescues(king, now, events)
        return det

    def plan_king_rescues(
        self,
        king: DynamicFarp,
        now: datetime,
        events: Optional[GameUpdateEvents] = None,
    ) -> list[Flight]:
        """Sends the King's idle helicopters to the nearest downed pilots no
        rescue is planned for yet.

        A King is placed after the turn's air tasking order was planned, so
        nothing else would task them this turn.
        """
        from game.ato.starttype import StartType

        radius = meters(self.game.settings.csar_cluster_radius)
        covered = {
            id(package.target)
            for package in self.coalition.ato.packages
            if any(f.flight_type is FlightType.CSAR for f in package.flights)
        }
        waiting = [p for p in self.coalition.downed_pilots if id(p) not in covered]
        planned: list[Flight] = []
        for det in detachments_at(king):
            if det.location != king or det.untasked_aircraft < 1:
                continue
            reach = det.aircraft.max_mission_range.meters
            in_reach = [
                p
                for p in waiting
                if p.position.distance_to_point(king.position) <= reach
            ]
            if not in_reach:
                continue
            pilot = min(
                in_reach, key=lambda p: p.position.distance_to_point(king.position)
            )
            package = Package(pilot, self.game.db.flights, auto_asap=True)
            flight = Flight(
                package,
                det,
                det.untasked_aircraft,
                FlightType.CSAR,
                StartType.IN_FLIGHT,
                divert=None,
            )
            package.add_flight(flight)
            try:
                flight.recreate_flight_plan()
            except PlanningError:
                logging.exception(f"Could not plan a rescue from {king.name}")
                package.remove_flight(flight)
                continue
            package.set_tot_asap(now)
            self.coalition.ato.add_package(package)
            if events is not None:
                events.new_flight(flight)
            planned.append(flight)
            # One lift collects the whole cluster.
            for other in pilot.cluster(radius):
                if other in waiting:
                    waiting.remove(other)
        return planned

    def _king_tanker_squadron(self, king: DynamicFarp) -> Squadron:
        """A KC-130 that isn't part of the air wing, to fly the King's orbit
        when the settings say no transport aircraft is needed."""
        from game.campaignloader.squadrondefgenerator import SquadronDefGenerator
        from game.dcs.aircrafttype import AircraftType
        from game.squadrons import Squadron

        faction = self.coalition.faction
        # The KC-130J (UH-60L mod) refuels UH-60Ls; otherwise the stock KC-130.
        aircraft = AircraftType.named("KC-130")
        for name in ("KC-130J", "KC-130"):
            try:
                candidate = AircraftType.named(name)
            except KeyError:
                continue
            if candidate in faction.all_aircrafts:
                aircraft = candidate
                break
        squadron_def = SquadronDefGenerator(faction).generate_for_aircraft(aircraft)
        squadron_def.name = f"{king.name} Tanker"
        squadron = Squadron.create_from(
            squadron_def, FlightType.RESCUE_KING, 1, king, self.coalition, self.game
        )
        squadron.set_auto_assignable_mission_types({FlightType.RESCUE_KING})
        squadron.owned_aircraft = 1
        squadron.untasked_aircraft = 1
        squadron._recruit_pilots(1)
        return squadron

    def plan_king_flight(
        self,
        king: DynamicFarp,
        now: datetime,
        events: Optional[GameUpdateEvents] = None,
        tot: Optional[datetime] = None,
    ) -> Optional[Flight]:
        """The aircraft that orbits the King this turn (_king_orbit_squadron):
        a C-130/KC-130 of the air wing, or with no transport needed
        (settings), a KC-130 tanker from outside it."""
        from game.ato.starttype import StartType

        squadron = self._king_orbit_squadron(king)
        start_type = StartType.ON_STATION
        if squadron is None and self.no_transport_needed:
            squadron = self._king_tanker_squadron(king)
            # It appears in the air over the King.
            start_type = StartType.IN_FLIGHT
        if squadron is None:
            self.game.message(
                f"{king.name} has no C-130",
                "No C-130 or KC-130 squadron with Rescue King turned on has an "
                f"aircraft and crew free to orbit it this turn. Pick one in the "
                f"menu of {king.name}.",
            )
            return None
        package = Package(king, self.game.db.flights)
        flight = Flight(
            package,
            squadron,
            1,
            FlightType.RESCUE_KING,
            start_type,
            divert=None,
        )
        if king.king_on_station_minutes is not None:
            flight.patrol_duration_override = timedelta(
                minutes=king.king_on_station_minutes
            )
        package.add_flight(flight)
        try:
            flight.recreate_flight_plan()
        except PlanningError:
            logging.exception(f"Could not plan the C-130 for {king.name}")
            package.remove_flight(flight)
            return None
        if tot is not None:
            # Replanned with another aircraft: keep the time the player set.
            package.auto_asap = False
            package.time_over_target = tot
        else:
            package.set_tot_asap(now)
        self.coalition.ato.add_package(package)
        if events is not None:
            events.new_flight(flight)
        return flight

    # The King's time on station, and the rescues flown from it

    def king_window(self, king: DynamicFarp) -> Optional[tuple[datetime, datetime]]:
        """When the King is on its orbit: its helicopters can start there and
        come back to it in this window. None if nothing orbits it."""
        flight = self.king_flight(self.king_package(king))
        if flight is None:
            return None
        plan = flight.flight_plan
        return plan.patrol_start_time, plan.patrol_end_time  # type: ignore[attr-defined]

    def set_king_on_station(
        self,
        king: DynamicFarp,
        minutes: int,
        events: Optional[GameUpdateEvents] = None,
    ) -> list[tuple[Package, str]]:
        """Sets how long the King stays on its orbit and replans it. Returns
        the rescues that no longer fit in its window."""
        king.king_on_station_minutes = minutes
        flight = self.king_flight(self.king_package(king))
        if flight is not None:
            flight.patrol_duration_override = timedelta(minutes=minutes)
            flight.recreate_flight_plan()
            if events is not None:
                events.update_flight(flight)
        return self.king_conflicts(king)

    @staticmethod
    def _king_of(package: Package) -> Optional[DynamicFarp]:
        for flight in package.flights:
            departure = flight.departure
            if (
                flight.flight_type is not FlightType.RESCUE_KING
                and isinstance(departure, DynamicFarp)
                and departure.is_rescue_king
            ):
                return departure
        return None

    def king_rescues(self, king: DynamicFarp) -> list[Package]:
        """Packages with helicopters flying from the King."""
        return [p for p in self.coalition.ato.packages if self._king_of(p) is king]

    @staticmethod
    def _rescue_span(package: Package) -> Optional[tuple[datetime, datetime]]:
        """From when the package's helicopters appear at the King until they
        are back at it."""
        starts: list[datetime] = []
        ends: list[datetime] = []
        for flight in package.flights:
            departure = flight.departure
            if not (isinstance(departure, DynamicFarp) and departure.is_rescue_king):
                continue
            plan = flight.flight_plan
            starts.append(plan.startup_time())
            ends.append(plan.landing_time)
        if not starts:
            return None
        return min(starts), max(ends)

    def rescue_conflict(self, package: Package) -> Optional[str]:
        """Why the package's helicopters fall outside their King's time on
        station, or None if they fit (or don't fly from a King)."""
        king = self._king_of(package)
        if king is None:
            return None
        window = self.king_window(king)
        span = self._rescue_span(package)
        if window is None or span is None:
            return None
        (start, end), (first, last) = span, window
        if start >= first and end <= last:
            return None
        return (
            f"The helicopters from {king.name} fly {start:%H:%M}-{end:%H:%M}, "
            f"outside its time on station ({first:%H:%M}-{last:%H:%M}): "
            + (
                "they would appear before the C-130 is there."
                if start < first
                else "the C-130 would be gone before they are back."
            )
        )

    def fit_to_king(self, package: Package) -> Optional[datetime]:
        """The TOT nearest the package's that keeps its helicopters inside
        their King's time on station; None if it already fits. If the rescue
        is longer than the window, its start is kept inside."""
        king = self._king_of(package)
        if king is None:
            return None
        window = self.king_window(king)
        span = self._rescue_span(package)
        if window is None or span is None:
            return None
        (start, end), (first, last) = span, window
        shift = timedelta()
        if end > last:
            shift = last - end
        if start + shift < first:
            shift = first - start
        if not shift:
            return None
        return package.time_over_target + shift

    def king_conflicts(self, king: DynamicFarp) -> list[tuple[Package, str]]:
        conflicts = []
        for package in self.king_rescues(king):
            why = self.rescue_conflict(package)
            if why is not None:
                conflicts.append((package, why))
        return conflicts
