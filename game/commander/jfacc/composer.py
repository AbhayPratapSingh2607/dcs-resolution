"""Package composition: threat-scaled packages built against the sortie ledger.

A package is composed in three steps:

1. Size it. Strikers come from weaponeering. Support (sweep, escort, SEAD,
   jamming) comes from the threat on the route and over the target, using the
   profile's threat tables. A tanker is added when the target is beyond the
   strikers' unrefueled radius.
2. Find aircraft. Each flight is filled from the best squadron that has
   mission-capable airframes free over the sortie window, either fresh jets or
   jets that have landed and turned around.
3. Check it. If any required element can't be filled, or the estimated
   attrition is above what the doctrine accepts for this target's priority,
   the package is scrubbed. Doctrine-strict planners don't send a package
   without the support it needs.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType
from game.ato.package import Package
from game.ato.flightplans.planningerror import PlanningError
from game.commander.packagebuilder import PackageBuilder
from game.ato.closestairfields import ObjectiveDistanceCache
from game.procurement import AircraftProcurementRequest
from . import weaponeering
from .profile import PlanningProfile
from .risk import RiskEstimate, estimate
from .sorties import Allocation, SortieLedger
from .threat import RouteThreat, analyse_route

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight
    from game.coalition import Coalition
    from game.dcs.aircrafttype import AircraftType
    from game.squadrons import Squadron
    from game.theater import ControlPoint, MissionTarget


SUPPORT_TASKS = {
    FlightType.ESCORT,
    FlightType.SEAD_ESCORT,
    FlightType.SWEEP,
    FlightType.SEAD_SWEEP,
    FlightType.TARCAP,
}

PATROL_TASKS = {
    FlightType.BARCAP,
    FlightType.TARCAP,
    FlightType.CAS,
    FlightType.AEWC,
    FlightType.REFUELING,
    FlightType.RECOVERY,
}


@dataclass
class FlightRequest:
    task: FlightType
    count: int
    required: bool = True
    preferred_type: Optional[AircraftType] = None
    #: Only aircraft with built-in jamming.
    jammer: bool = False
    note: str = ""
    #: Only squadrons based here.
    home: Optional[ControlPoint] = None
    #: Ground alert: the airframes are held for the whole period and the
    #: flight waits at the runway for the GCI to scramble it.
    alert: bool = False
    #: A flight returning from a sortie flown before the turn (focused
    #: turns, F3): it is on its way home when the mission starts.
    returning: bool = False
    #: Time on station instead of the default (returning flights).
    patrol_minutes: Optional[float] = None


@dataclass
class PackageRequest:
    target: MissionTarget
    flights: list[FlightRequest]
    category_name: str
    reason: str
    risk_kind: str = "routine"
    threat: Optional[RouteThreat] = None
    asap: bool = False
    #: SAM sites destroyed by earlier packages before this one arrives.
    suppressed: Optional[set[object]] = None


@dataclass
class SeadCorridor:
    """Airspace HARM shooters suppress for a while (item 1)."""

    area: Any
    start: datetime
    end: datetime
    shooters: int


#: Flights that open a SEAD corridor.
CORRIDOR_TASKS = {
    FlightType.SEAD,
    FlightType.SEAD_ESCORT,
    FlightType.SEAD_SWEEP,
    FlightType.DEAD,
}


@dataclass
class ComposedPackage:
    package: Package
    risk: Optional[RiskEstimate]
    allocations: list[Allocation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def sorties(self) -> int:
        return sum(f.count for f in self.package.flights)


def _speed_kt(aircraft: AircraftType) -> float:
    if aircraft.helicopter:
        return 110.0
    return 420.0


def _patrol_minutes(game: Game, task: FlightType) -> float:
    settings = game.settings
    if task is FlightType.BARCAP:
        return settings.desired_barcap_mission_duration.total_seconds() / 60
    if task is FlightType.AEWC:
        return settings.desired_awacs_mission_duration.total_seconds() / 60
    if task in (FlightType.REFUELING, FlightType.RECOVERY):
        return settings.desired_tanker_on_station_time.total_seconds() / 60
    if task in (FlightType.CAS, FlightType.TARCAP):
        return 30.0
    return 10.0


#: Package priorities that fly without their full support when it isn't
#: available, as long as the risk estimate allows it.
URGENT_RISK_KINDS = {"troops_in_contact", "defense"}

#: Flights that hold a station for a long time: their SAM exposure counts
#: sites just outside the station too (see threat._add_sam_exposure).
STATION_TASKS = {FlightType.BARCAP, FlightType.TARCAP}

#: Tasks only a few squadrons can fly; other tasks avoid those squadrons.
SCARCE_TASKS = {
    FlightType.SEAD,
    FlightType.SEAD_ESCORT,
    FlightType.SEAD_SWEEP,
    FlightType.DEAD,
}


#: Tasks strategic bombers at an off-map base are tasked for first (T3).
BOMBER_TASKS = {FlightType.STRIKE, FlightType.OCA_RUNWAY}


def _off_map(squadron: Squadron) -> bool:
    from game.theater.controlpoint import ControlPointType

    return squadron.location.cptype is ControlPointType.OFF_MAP


def _scarcity(squadron: Squadron) -> int:
    tasks = squadron.auto_assignable_mission_types
    score = 0
    if any(t in tasks for t in SCARCE_TASKS):
        score += 2
    if getattr(squadron.aircraft, "has_built_in_jamming", False):
        score += 1
    return score


def _low_level_doctrine(coalition: Coalition) -> bool:
    try:
        from game.warfare.doctrine import for_faction_obj

        return for_faction_obj(coalition.faction).low_level_strikes
    except Exception:
        return False


class PackageComposer:
    def __init__(
        self,
        game: Game,
        coalition: Coalition,
        profile: PlanningProfile,
        ledger: SortieLedger,
        conditions: weaponeering.Conditions,
        aewc_available: bool,
    ) -> None:
        self.game = game
        self.coalition = coalition
        self.profile = profile
        self.ledger = ledger
        self.conditions = conditions
        self.aewc_available = aewc_available
        self.packages_cfg = profile.section("packages")
        #: Phase-dependent risk acceptance (set by the planner).
        self.risk_multiplier = 1.0
        #: Campaign phase name, for phase-specific risk rules.
        self.phase_name = ""
        #: The phase allows the outer-layer rollback risk allowance.
        self.rollback_allowed = False
        #: SAM sites that open the rollback against an IADS with no site
        #: inside the normal allowance (item 6; set by the planner).
        self.opener_targets: set[object] = set()
        from .risk import RiskModel

        self.risk_model = RiskModel.from_profile(profile.section("risk").get("model"))
        #: Loss experience factor per package kind (experience.py), set by
        #: the planner each turn.
        self.experience: dict[str, float] = {}
        #: Strike packages fly in at low level (Soviet-style doctrines): the
        #: combat model and the DCS flight plans do, so the risk estimate must.
        self.low_level = _low_level_doctrine(coalition)
        #: Focused turns: CAPs stay on station until this time (the end of
        #: the mission window) rather than for the default patrol duration.
        self.patrol_until: Optional[datetime] = None
        #: SEAD corridors opened this period (item 1).
        self.corridors: list[SeadCorridor] = []

    # ----------------------------------------------------------- analysis

    def origin_for(self, target: MissionTarget) -> Optional[object]:
        airfields = ObjectiveDistanceCache.get_closest_airfields(target)
        for cp in airfields.operational_airfields:
            if cp.captured is self.coalition.player:
                return cp
        return None

    def threat_for(
        self,
        target: MissionTarget,
        exclude: Optional[object] = None,
        suppressed: Optional[set[object]] = None,
    ) -> RouteThreat:
        origin = self.origin_for(target)
        origin_point = origin.position if origin is not None else target.position  # type: ignore[attr-defined]
        return analyse_route(
            self.game,
            self.coalition.player,
            origin_point,
            target,
            self.packages_cfg,
            exclude=exclude,  # type: ignore[arg-type]
            suppressed=suppressed,
        )

    def support_for(self, threat: RouteThreat, strikers: int) -> list[FlightRequest]:
        """Support flights for a package of the given striker count."""
        table = self.profile.threat_support
        air = table.get(threat.air_level)
        sam = table.get(threat.sam_level)
        requests: list[FlightRequest] = []
        if sam is not None and sam.jammer > 0 and self.game.settings.ew_enabled:
            jammer = self._jammer_type()
            if jammer is not None:
                requests.append(
                    FlightRequest(
                        FlightType.SEAD_ESCORT,
                        sam.jammer,
                        required=False,
                        preferred_type=jammer,
                        jammer=True,
                        note="stand-off jamming",
                    )
                )
        if sam is not None and (sam.sead > 0 or threat.sam_weight > 0):
            # Enough HARM shooters to cover the emitters on the ingress leg.
            sead = max(sam.sead, min(math.ceil(2 + threat.sam_weight / 2), 8))
            sead += sead % 2
            requests.append(
                FlightRequest(
                    FlightType.SEAD_ESCORT,
                    sead,
                    note=str(
                        self.packages_cfg.get("sead_label", "SEAD (HARM) support")
                    ),
                )
            )
        counter_air: list[FlightRequest] = []
        if air is not None and air.sweep > 0:
            counter_air.append(
                FlightRequest(FlightType.SWEEP, air.sweep, note="fighter sweep")
            )
        if air is not None and air.escort > 0:
            counter_air.append(
                FlightRequest(FlightType.ESCORT, air.escort, note="close escort")
            )
        # Fighter support stays within the doctrinal ratio to strikers; SEAD
        # is sized to the threat, not the strike force.
        ratio = float(self.packages_cfg.get("max_support_ratio", 1.5))
        limit = max(2, int(round(strikers * ratio)))
        limit += limit % 2
        total = 0
        for request in counter_air:
            if total + request.count > limit:
                # Fighters work in pairs: trim to whole elements.
                request.count = max(2, (limit - total) // 2 * 2)
            total += request.count
            requests.append(request)
        return requests

    def _jammer_type(self) -> Optional[AircraftType]:
        for squadron in self.coalition.air_wing.iter_squadrons():
            aircraft = squadron.aircraft
            if getattr(
                aircraft, "has_built_in_jamming", False
            ) and squadron.can_auto_assign(FlightType.SEAD_ESCORT):
                return aircraft
        return None

    def needs_tanker(self, target: MissionTarget, aircraft: AircraftType) -> bool:
        from game.sim.combat.model.fuel import fuel_profile

        origin = self.origin_for(target)
        if origin is None:
            return False
        distance_km = origin.position.distance_to_point(target.position) / 1000  # type: ignore[attr-defined]
        radius = fuel_profile(aircraft).radius_km
        fraction = float(self.profile.get("enablers", "tanker_radius_fraction", 0.8))
        return distance_km > radius * fraction and fuel_profile(aircraft).can_refuel

    # ------------------------------------------------------------ building

    def patrol_override(self, task: FlightType, tot: datetime) -> Optional[timedelta]:
        """Time on station for a line arriving at ``tot`` in a focused turn.

        A CAP stays until the window ends, within the profile's limits. AEW&C
        and theater tankers stretch their usual time on station by up to half
        again, so one flight covers the window instead of a relief for its
        last minutes."""
        if self.patrol_until is None:
            return None
        if task in (FlightType.AEWC, FlightType.REFUELING):
            usual = timedelta(minutes=_patrol_minutes(self.game, task))
            needed = self.patrol_until - tot
            if needed <= usual:
                return None
            return min(needed, usual * 1.5)
        if task is not FlightType.BARCAP:
            return None
        dca = self.profile.section("dca")
        longest = timedelta(minutes=float(dca.get("max_patrol_min", 90)))
        shortest = timedelta(minutes=float(dca.get("min_patrol_min", 20)))
        return max(shortest, min(longest, self.patrol_until - tot))

    def _sortie_window(
        self,
        squadron: Squadron,
        target: MissionTarget,
        tot: datetime,
        task: FlightType,
        patrol_minutes: Optional[float] = None,
    ) -> tuple[datetime, datetime]:
        distance_nm = (
            squadron.location.position.distance_to_point(target.position) / 1852
        )
        transit = timedelta(hours=distance_nm / _speed_kt(squadron.aircraft))
        if patrol_minutes is not None:
            on_station = timedelta(minutes=patrol_minutes)
        else:
            on_station = self.patrol_override(task, tot) or timedelta(
                minutes=_patrol_minutes(self.game, task)
            )
        takeoff = tot - transit - timedelta(minutes=20)
        land = tot + on_station + transit + timedelta(minutes=15)
        return takeoff, land

    def _place_flight(
        self,
        builder: PackageBuilder,
        request: FlightRequest,
        target: MissionTarget,
        tot: datetime,
        heli: bool,
    ) -> tuple[Optional[Flight], Optional[Allocation], str]:
        from game.ato import Flight
        from game.ato.flightmember import apply_default_player_laser_code

        air_wing = self.coalition.air_wing
        search_target = target
        pf = builder.package.primary_flight
        if pf is not None and pf.flight_type in (
            FlightType.AEWC,
            FlightType.REFUELING,
            FlightType.RECOVERY,
        ):
            search_target = pf.departure
        candidates = air_wing.best_squadrons_for(
            search_target,
            request.task,
            request.count,
            heli,
            this_turn=False,
            preferred_type=request.preferred_type,
        )
        # Keep scarce SEAD shooters and jammers for the packages that need
        # them: other tasks take them only when nothing else can fly it.
        if request.task not in SCARCE_TASKS and not request.jammer:
            candidates = sorted(candidates, key=lambda s: _scarcity(s))
        if request.task in BOMBER_TASKS:
            # Strategic bombers at an off-map base (T3) strike fixed targets
            # first: their distance from the map edge says nothing about
            # their fitness, and they are there for this.
            candidates = sorted(candidates, key=lambda s: not _off_map(s))
        if request.home is not None:
            candidates = [s for s in candidates if s.location is request.home]
        why = "no suitable squadron in range"
        for squadron in candidates:
            if request.jammer and not getattr(
                squadron.aircraft, "has_built_in_jamming", False
            ):
                continue
            if request.alert:
                takeoff, land = self.ledger.period_start, self.ledger.period_end
            else:
                takeoff, land = self._sortie_window(
                    squadron, target, tot, request.task, request.patrol_minutes
                )
            allocation = self.ledger.find(squadron, request.count, takeoff, land)
            if allocation is None:
                why = "no mission-capable aircraft free in the sortie window"
                continue
            if squadron.pilot_limits_enabled and not squadron.can_provide_pilots(
                request.count
            ):
                why = "not enough rested crews"
                continue
            start_type = squadron.location.required_aircraft_start_type
            if start_type is None:
                start_type = self.game.settings.default_start_type
            flight = Flight(
                builder.package,
                squadron,
                request.count,
                request.task,
                start_type,
                divert=builder.find_divert_field(squadron.aircraft, squadron.location),
                claim_inv=False,
            )
            squadron.claim_inventory(allocation.fresh)
            flight.reused_airframes = allocation.reused
            if request.patrol_minutes is not None:
                flight.patrol_duration_override = timedelta(
                    minutes=request.patrol_minutes
                )
            elif not request.alert:
                flight.patrol_duration_override = self.patrol_override(
                    request.task, tot
                )
            flight.returning = request.returning
            for member in flight.iter_members():
                apply_default_player_laser_code(
                    member, self.game.settings, self.coalition.laser_code_registry
                )
            if squadron.location.required_aircraft_start_type is None:
                flight.start_type = self.game.settings.start_type_for(
                    request.task,
                    has_players=flight.roster is not None
                    and flight.roster.player_count > 0,
                )
            if request.alert:
                from game.ato.starttype import StartType

                flight.alert = True
                if squadron.location.required_aircraft_start_type is None:
                    flight.start_type = StartType.RUNWAY
            builder.package.add_flight(flight)
            ok, note = weaponeering.apply(flight, self.profile, self.conditions)
            if not ok:
                builder.package.remove_flight(flight)
                why = note
                continue
            self.ledger.commit(allocation)
            return flight, allocation, note
        return None, None, why

    def compose(
        self, request: PackageRequest, tot: datetime, now: datetime
    ) -> tuple[Optional[ComposedPackage], str]:
        target = request.target
        builder = PackageBuilder(
            target,
            ObjectiveDistanceCache.get_closest_airfields(target),
            self.coalition.air_wing,
            self.coalition.laser_code_registry,
            self.game.db.flights,
            self.coalition.player.is_blue,
            self.game.settings.default_start_type,
            request.asap,
        )
        package = builder.package
        package.time_over_target = tot
        allocations: list[Allocation] = []
        placed: list[tuple[Flight, Allocation]] = []
        jammer_flights: list[Flight] = []
        notes: list[str] = []
        heli = False

        def scrub(reason: str) -> tuple[None, str]:
            for allocation in allocations:
                self.ledger.release(allocation)
            builder.release_planned_aircraft()
            return None, reason

        main = [r for r in request.flights if r.task not in SUPPORT_TASKS]
        support = [r for r in request.flights if r.task in SUPPORT_TASKS]
        # A SEAD corridor already suppressing this package's ingress at its
        # TOT stands in for its own HARM escort (item 1).
        corridor_sead = self.corridor_cover(request, tot)
        if corridor_sead:
            support = [
                r
                for r in support
                if not (r.task is FlightType.SEAD_ESCORT and not r.jammer)
            ]
            notes.append(f"in a SEAD corridor ({corridor_sead} HARM shooters)")
        for flight_request in main + support:
            flight, allocation, note = self._place_flight(
                builder, flight_request, target, tot, heli
            )
            if flight is None or allocation is None:
                self._request_purchase(target, flight_request, heli)
                # Troops in contact don't wait for the full package: missing
                # support is left to the risk check, which allows them more.
                urgent = request.risk_kind in URGENT_RISK_KINDS
                if flight_request.required and not (
                    urgent and flight_request.task in SUPPORT_TASKS
                ):
                    return scrub(f"{flight_request.task.value}: {note}")
                continue
            if package.primary_flight is flight:
                heli = flight.is_helo
            allocations.append(allocation)
            placed.append((flight, allocation))
            if flight_request.jammer:
                jammer_flights.append(flight)
            if note:
                notes.append(note)
        if not package.flights:
            return scrub("no flights")

        # Flight plans: main elements first so escorts can join them.
        try:
            for flight in package.flights:
                if flight.flight_type not in SUPPORT_TASKS:
                    flight.recreate_flight_plan()
            for flight, allocation in list(placed):
                if flight.flight_type not in SUPPORT_TASKS:
                    continue
                try:
                    flight.recreate_flight_plan()
                except Exception as ex:
                    # A support element that can't be routed (e.g. a sweep for
                    # a package without ingress waypoints) is dropped; the
                    # risk check decides whether the rest still goes.
                    logging.info(
                        f"JFACC: dropped {flight.flight_type.value} from "
                        f"{target.name}: {ex!r}"
                    )
                    self.ledger.release(allocation)
                    allocations.remove(allocation)
                    placed.remove((flight, allocation))
                    if flight in jammer_flights:
                        jammer_flights.remove(flight)
                    package.remove_flight(flight)
        except PlanningError as ex:
            return scrub(f"no viable route ({ex})")
        except Exception:
            logging.exception(f"JFACC: flight plan failed for {target.name}")
            return scrub("flight planning failed")

        # Doctrine: no strikers into known radar SAM coverage without SEAD.
        threat = request.threat
        sead_types = {
            FlightType.SEAD,
            FlightType.SEAD_ESCORT,
            FlightType.SEAD_SWEEP,
            FlightType.DEAD,
        }
        has_sead = any(f.flight_type in sead_types for f in package.flights)
        zones = self.coalition.opponent.threat_zone
        route_sam = any(
            zones.waypoints_threatened_by_radar_sam(
                list(f.flight_plan.escorted_waypoints())
            )
            for f in package.flights
            if f.flight_type not in SUPPORT_TASKS and f.flight_type not in PATROL_TASKS
        )
        require_sead = bool(self.packages_cfg.get("require_sead", True))
        if (
            require_sead
            and route_sam
            and not has_sead
            and not corridor_sead
            and request.risk_kind not in URGENT_RISK_KINDS
        ):
            # The SEAD force is what limits this package: ask for more.
            self._request_purchase(
                target, FlightRequest(FlightType.SEAD_ESCORT, 2), heli
            )
            return scrub("route enters radar SAM coverage and no SEAD is available")

        # Risk, judged on the route actually planned.
        risk: Optional[RiskEstimate] = None
        if threat is not None:
            route_threat = self._planned_route_threat(package, request, threat)
            risk, limit, sead_aircraft = self._risk(
                package, route_threat, jammer_flights, request, corridor_sead
            )
            if risk.expected_loss_rate > limit:
                # One more try: add HARM shooters to cover what the route
                # actually crosses.
                needed = math.ceil(2 + route_threat.sam_weight / 2)
                needed += needed % 2
                extra = min(8, needed - sead_aircraft)
                if extra >= 2 and not _holds_station(package):
                    flight, allocation, _ = self._place_flight(
                        builder,
                        FlightRequest(FlightType.SEAD_ESCORT, extra),
                        target,
                        tot,
                        heli,
                    )
                    if flight is None or allocation is None:
                        # More HARM shooters would have made it acceptable.
                        self._request_purchase(
                            target, FlightRequest(FlightType.SEAD_ESCORT, extra), heli
                        )
                    if flight is not None and allocation is not None:
                        allocations.append(allocation)
                        placed.append((flight, allocation))
                        try:
                            flight.recreate_flight_plan()
                        except Exception:
                            return scrub("no viable route for added SEAD")
                        risk, limit, sead_aircraft = self._risk(
                            package,
                            route_threat,
                            jammer_flights,
                            request,
                            corridor_sead,
                        )
            if risk.expected_loss_rate > limit:
                return scrub(
                    f"expected attrition above the limit ({risk.describe()}, "
                    f"limit {limit:.1%}, SAM weight {route_threat.sam_weight:.1f} "
                    f"incl. {route_threat.unknown_weight:.1f} unlocated, "
                    f"air {route_threat.air_strength:.1f}, SEAD {sead_aircraft})"
                )
            request.threat = route_threat
            package.planning_risk = {
                "sam_weight": route_threat.sam_weight,
                "unknown": route_threat.unknown_weight,
                "air": route_threat.air_strength,
                "sead": float(sead_aircraft),
                "estimate": risk.expected_loss_rate,
                "model_estimate": risk.model_estimate,
                "sam_part": risk.sam_component,
                "air_part": risk.air_component,
                "limit": limit,
                "target_defended": float(route_threat.target_defended),
            }

        # Timing: the TOT must be reachable.
        from game.ato.traveltime import TotEstimator

        earliest = TotEstimator(package).earliest_tot(now)
        if package.time_over_target < earliest:
            package.time_over_target = earliest

        # Replace estimated sortie windows with the planned ones.
        for flight, allocation in placed:
            try:
                takeoff = flight.flight_plan.takeoff_time()
                land = flight.flight_plan.landing_time
            except Exception:
                continue
            self.ledger.update(allocation, takeoff, land)
        self._open_corridor(package)
        return ComposedPackage(package, risk, allocations, notes), ""

    # ------------------------------------------------------- SEAD corridors

    def _open_corridor(self, package: Package) -> None:
        """A package with HARM shooters suppresses the airspace along their
        route around its TOT, for other packages too: in the combat model any
        airborne SEAD flight hunts emitters it can reach, and its presence
        deters the sites from radiating."""
        from shapely.geometry import LineString

        shooters = [f for f in package.flights if f.flight_type in CORRIDOR_TASKS]
        count = sum(f.count for f in shooters)
        if not count:
            return
        width_m = float(self.packages_cfg.get("sead_corridor_nm", 12)) * 1852
        before = timedelta(
            minutes=float(self.packages_cfg.get("sead_corridor_lead_min", 10))
        )
        after = timedelta(
            minutes=float(self.packages_cfg.get("sead_corridor_linger_min", 20))
        )
        for flight in shooters:
            points = [
                (w.position.x, w.position.y) for w in flight.flight_plan.waypoints[1:-1]
            ]
            if len(points) < 2:
                continue
            tot = package.time_over_target
            self.corridors.append(
                SeadCorridor(
                    LineString(points).buffer(width_m),
                    tot - before,
                    tot + after,
                    count,
                )
            )
            return

    def corridor_cover(self, request: PackageRequest, tot: datetime) -> int:
        """HARM shooters of the corridors covering this package's ingress at
        its TOT (0: none). The ingress is the last ``ingress_exposure_nm``
        before the target, on the way from the nearest base."""
        from shapely.geometry import LineString

        if not self.corridors or request.threat is None:
            return 0
        if any(
            r.task in CORRIDOR_TASKS
            for r in request.flights
            if r.task not in SUPPORT_TASKS
        ):
            return 0
        target = request.target.position
        origin = self.origin_for(request.target)
        start = origin.position if origin is not None else target  # type: ignore[attr-defined]
        ingress_m = float(self.packages_cfg.get("ingress_exposure_nm", 40)) * 1852
        if start.distance_to_point(target) > ingress_m:
            start = target.point_from_heading(
                target.heading_between_point(start), ingress_m
            )
        leg = LineString([(start.x, start.y), (target.x, target.y)])
        if leg.length <= 0:
            return 0
        share = float(self.packages_cfg.get("sead_corridor_cover", 0.8))
        shooters = 0
        for corridor in self.corridors:
            if not corridor.start <= tot <= corridor.end:
                continue
            if leg.intersection(corridor.area).length / leg.length >= share:
                shooters += corridor.shooters
        return min(shooters, 8)

    def _planned_route_threat(
        self, package: Package, request: PackageRequest, threat: RouteThreat
    ) -> RouteThreat:
        """SAM threat along the main flights' planned routes; the air threat
        carries over from the target-area assessment."""
        from game.theater.theatergroundobject import SamGroundObject
        from .threat import analyse_path

        worst: Optional[RouteThreat] = None
        for flight in package.flights:
            if flight.flight_type in SUPPORT_TASKS:
                continue
            points = [w.position for w in flight.flight_plan.waypoints]
            exclude = (
                request.target if isinstance(request.target, SamGroundObject) else None
            )
            margin_m = 0.0
            if flight.flight_type in STATION_TASKS:
                margin_m = (
                    float(self.packages_cfg.get("station_margin_nm", 15)) * 1852.0
                )
            route = analyse_path(
                self.game,
                self.coalition.player,
                points,
                request.target,
                self.packages_cfg,
                exclude=exclude,
                suppressed=request.suppressed,
                margin_m=margin_m,
            )
            if worst is None or route.sam_weight > worst.sam_weight:
                worst = route
        if worst is None:
            return threat
        worst.air_strength = threat.air_strength
        worst.air_level = threat.air_level
        worst.enemy_aircrew = threat.enemy_aircrew
        return worst

    def _risk(
        self,
        package: Package,
        threat: RouteThreat,
        jammer_flights: list[Flight],
        request: PackageRequest,
        corridor_sead: int = 0,
    ) -> tuple[RiskEstimate, float, int]:
        from game.sim.combat.model.forcequality import for_faction

        sead_types = {
            FlightType.SEAD,
            FlightType.SEAD_ESCORT,
            FlightType.SEAD_SWEEP,
            FlightType.DEAD,
        }
        sead_aircraft = corridor_sead + sum(
            f.count for f in package.flights if f.flight_type in sead_types
        )
        jammers = sum(f.count for f in jammer_flights)
        counter_air = sum(
            f.count
            for f in package.flights
            if f.flight_type
            in (
                FlightType.ESCORT,
                FlightType.SWEEP,
                FlightType.TARCAP,
                FlightType.BARCAP,
            )
        )
        try:
            own_aircrew = for_faction(self.coalition.faction.name).aircrew
        except Exception:
            own_aircrew = 1.0
        standoff = any(
            weaponeering.carries_standoff(f)
            for f in package.flights
            if f.flight_type in weaponeering.ATTACK_TASKS
        )
        risk = estimate(
            threat,
            sead_aircraft,
            jammers,
            counter_air,
            self.aewc_available,
            own_aircrew,
            standoff,
            front_line=_is_front_line(request.target),
            low_level=self.low_level
            and not (
                package.primary_flight is not None and package.primary_flight.is_helo
            ),
            model=self.risk_model,
            station=_holds_station(package),
        )
        from .experience import kind_of

        risk = risk.scaled(self.experience.get(kind_of(package), 1.0))
        limit = min(
            self.profile.attrition_limit
            * self.profile.priority_multiplier(request.risk_kind)
            * self.risk_multiplier,
            self.profile.absolute_attrition_limit,
        )
        limit = max(limit, self._rollback_limit(request, threat))
        override = getattr(self.game.settings, "jfacc_attrition_limit_override", 0)
        if override:
            limit = float(override) / 100
        return risk, limit, sead_aircraft

    def _rollback_limit(self, request: PackageRequest, threat: RouteThreat) -> float:
        """The higher risk allowed for rolling back the outer IADS layer."""
        from game.theater.theatergroundobject import SamGroundObject

        allowance = self.profile.section("risk").get("rollback_allowance") or {}
        if not self.rollback_allowed:
            return 0.0
        if not isinstance(request.target, SamGroundObject):
            return 0.0
        if request.target.id in self.opener_targets:
            # Item 6: no SAM site is within the normal allowance, so the
            # least-defended ones are attacked at a higher cost to start the
            # rollback at all.
            return float(allowance.get("opener_limit", 0.2))
        if threat.sam_weight > float(allowance.get("max_route_weight", 0)):
            return 0.0
        return float(allowance.get("limit", 0.0))

    def _request_purchase(
        self, target: MissionTarget, request: FlightRequest, heli: bool
    ) -> None:
        if not self.coalition.air_wing.can_auto_plan(request.task):
            return
        self.coalition.add_procurement_request(
            AircraftProcurementRequest(
                near=target,
                task_capability=request.task,
                number=request.count,
                heli=heli,
            )
        )


def _holds_station(package: Package) -> bool:
    primary = package.primary_flight
    return primary is not None and primary.flight_type in STATION_TASKS


def _is_front_line(target: object) -> bool:
    from game.theater.frontline import FrontLine

    return isinstance(target, FrontLine)
