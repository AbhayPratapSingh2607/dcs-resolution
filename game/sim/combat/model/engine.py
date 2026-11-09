"""The combat model: shared state for every engagement during one simulation run."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Optional, TYPE_CHECKING

from game.sim.combatlog import CombatDomain
from .airframe import AirframeState, build_airframe
from .environment import CombatEnvironment
from .forcequality import NEUTRAL, ForceQuality, for_faction
from .profiles import CombatProfiles

if TYPE_CHECKING:
    from .aircrew import LossCause
    from dcs import Point

    from game import Game
    from game.ato import Flight
    from game.sim.gameupdateevents import GameUpdateEvents
    from game.sim.simulationresults import SimulationResults
    from game.theater import TheaterGroundObject
    from game.theater.player import Player
    from .airdefense import SamSiteState
    from game.warfare.doctrine import CombatDoctrine
    from game.warfare.iads import SiteNetworkStatus


def radar_horizon_km(antenna_m: float, target_m: float) -> float:
    """Distance to the radar horizon with standard 4/3 earth refraction."""
    return 4.12 * (math.sqrt(max(antenna_m, 0.0)) + math.sqrt(max(target_m, 0.0)))


def distance_km(a: Point, b: Point) -> float:
    return a.distance_to_point(b) / 1000


def poisson(rng: random.Random, mean: float) -> int:
    if mean <= 0:
        return 0
    if mean > 30:
        return max(0, round(rng.gauss(mean, math.sqrt(mean))))
    limit = math.exp(-mean)
    k = 0
    p = rng.random()
    while p > limit:
        k += 1
        p *= rng.random()
    return k


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class SurveillanceSource:
    position: Point
    #: Detection range against a 5 m^2 target, km.
    range_km: float
    #: Antenna height, m. AWACS sit at altitude, ground radars on masts.
    antenna_m: float

    def detects(self, target: Point, target_alt_m: float, target_rcs: float) -> bool:
        reach = self.range_km * (max(target_rcs, 1e-4) / 5.0) ** 0.25
        reach = min(reach, radar_horizon_km(self.antenna_m, target_alt_m))
        return distance_km(self.position, target) <= reach


class SideAwareness:
    """Off-board picture available to one side: AWACS, EWR and GCI radars."""

    def __init__(self, model: CombatModel, player: Player) -> None:
        self.sources: list[SurveillanceSource] = []
        profiles: CombatProfiles = model.profiles
        game = model.game
        coalition = game.coalition_for(player)
        from game.ato.flighttype import FlightType

        for package in coalition.ato.packages:
            for flight in package.flights:
                if flight.flight_type is not FlightType.AEWC:
                    continue
                if not flight.alive or not flight.state.in_flight:
                    continue
                profile = profiles.aircraft(flight.unit_type)
                if profile.awacs_km <= 0:
                    continue
                try:
                    altitude = flight.state.estimate_altitude()[0].meters  # type: ignore[attr-defined]
                except Exception:
                    altitude = 9000
                self.sources.append(
                    SurveillanceSource(
                        flight.state.estimate_position(), profile.awacs_km, altitude
                    )
                )

        from game.theater.theatergroundobject import EwrGroundObject

        for cp in game.theater.control_points_for(player):
            for tgo in cp.ground_objects:
                is_ewr = isinstance(tgo, EwrGroundObject) or getattr(
                    tgo, "is_ewr_site", False
                )
                if tgo.is_dead or not is_ewr:
                    continue
                detection = tgo.max_detection_range().kilometers
                if detection <= 0:
                    continue
                self.sources.append(SurveillanceSource(tgo.position, detection, 20))

        if model.ew_enabled:
            self._apply_jamming(model, player)

    def _apply_jamming(self, model: CombatModel, player: Player) -> None:
        """Stand-off jammers in range blind early warning radars (and to a lesser
        degree AWACS, which sit high and far back)."""
        from game.ato.flighttype import FlightType

        jammers: list[Point] = []
        enemy = model.game.coalition_for(player.opponent)
        for package in enemy.ato.packages:
            for flight in package.flights:
                if not flight.alive or not flight.state.in_flight:
                    continue
                if flight.flight_type is FlightType.AEWC:
                    continue
                if any(a.offensive_jammer for a in model.airframes(flight)):
                    jammers.append(flight.state.estimate_position())
        if not jammers:
            return
        jammed = []
        for source in self.sources:
            near = sum(1 for j in jammers if distance_km(j, source.position) <= 200)
            if near:
                factor = 0.9 if source.antenna_m > 1000 else 0.65
                source = SurveillanceSource(
                    source.position,
                    source.range_km * factor ** min(near, 3),
                    source.antenna_m,
                )
            jammed.append(source)
        self.sources = jammed

    def covers(self, target: Point, target_alt_m: float, target_rcs: float) -> bool:
        return any(s.detects(target, target_alt_m, target_rcs) for s in self.sources)


class CombatModel:
    def __init__(self, game: Game, results: SimulationResults) -> None:
        self.game = game
        self.results = results
        self.settings = game.settings
        self.profiles: CombatProfiles = CombatProfiles.instance()
        try:
            self.env = CombatEnvironment.from_conditions(game.conditions)
        except Exception:
            self.env = CombatEnvironment.clear_day()
        self._rng_counter = 0
        self._airframes: dict[int, AirframeState] = {}
        self.sam_sites: dict[str, SamSiteState] = {}
        self._awareness_cache: dict[tuple[bool, datetime], SideAwareness] = {}
        #: Flights that have already flown their attack run.
        self.attacked_flights: set[int] = set()
        #: Damage bookkeeping for targets without a per-unit alive flag (parked
        #: aircraft, convoy vehicles, ship hit points), keyed by (kind, id).
        self.attack_tallies: defaultdict[
            tuple[str, int], defaultdict[object, float]
        ] = defaultdict(lambda: defaultdict(float))
        #: Last time each SEAD flight hunted for emitters.
        self.sead_hunts: dict[int, datetime] = {}
        self._quality: dict[bool, ForceQuality] = {}
        self._network_cache: dict[str, Optional[SiteNetworkStatus]] = {}
        self._doctrine: dict[bool, CombatDoctrine] = {}
        results.on_ground_unit_killed = self.invalidate_network
        #: Sites each side has seen fire during this simulation.
        self.revealed: dict[bool, set[object]] = {}
        #: (flight id, site key) -> until when the flight keeps clear of a
        #: SAM envelope it was engaged in (threat-avoidance doctrine).
        self.sam_avoidance: dict[tuple[int, str], datetime] = {}
        #: Last ARM launched at each site, for SEAD deterrence.
        self.arm_launches: dict[str, datetime] = {}
        self.arm_threat_cache: dict[str, tuple[int, bool]] = {}
        #: (package, site) pairs whose opening SEAD shots have been fired.
        self.preempted: set[tuple[int, str]] = set()
        #: Shot statistics for calibration: kind -> [shots, kills].
        self.shot_stats: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])

    def quality(self, player: Player) -> ForceQuality:
        """Training, readiness and doctrine of a side, from its faction."""
        if not getattr(self.settings, "combat_model_force_quality", True):
            return NEUTRAL
        key = player.is_blue
        if key not in self._quality:
            try:
                name = self.game.coalition_for(player).faction.name
            except AttributeError:
                name = ""
            self._quality[key] = for_faction(name)
        return self._quality[key]

    @property
    def lethality(self) -> float:
        return float(getattr(self.settings, "combat_model_lethality", 1.0))

    def rng(self) -> random.Random:
        """Each engagement gets its own deterministic stream derived from the seed."""
        self._rng_counter += 1
        return random.Random(f"{self.results.seed}:{self._rng_counter}")

    def airframes(self, flight: Flight) -> list[AirframeState]:
        """Live airframes of a flight, persistent across engagements so missiles
        fired and countermeasures used carry over."""
        result = []
        for member in flight.roster.members:
            key = id(member)
            airframe = self._airframes.get(key)
            if airframe is None or airframe.flight is not flight:
                airframe = build_airframe(
                    flight,
                    member,
                    self.profiles,
                    self.quality(flight.squadron.player),
                )
                # Confident squadrons fly a little better; shaken ones worse.
                from game.warfare.morale import performance_factor

                airframe.skill *= performance_factor(self.squadron_morale(flight))
                self._airframes[key] = airframe
            if airframe.alive:
                result.append(airframe)
        return result

    def site_emcon(self, tgo: TheaterGroundObject) -> str:
        """The emission control order the owning side's IADS management gave
        the site (game.commander.jfacc.iads), "" to follow doctrine."""
        cache = self.__dict__.setdefault("_emcon_cache", {})
        key = str(tgo.id)
        if key not in cache:
            from game.commander.jfacc.iads import emcon_order

            cache[key] = emcon_order(self.game, tgo)
        return str(cache[key])

    def awareness(self, player: Player, time: datetime) -> SideAwareness:
        key = (player.is_blue, time)
        if key not in self._awareness_cache:
            if len(self._awareness_cache) > 8:
                self._awareness_cache.clear()
            self._awareness_cache[key] = SideAwareness(self, player)
        return self._awareness_cache[key]

    def doctrine(self, player: Player) -> CombatDoctrine:
        if player.is_blue not in self._doctrine:
            from game.warfare.doctrine import CombatDoctrine, for_faction_obj

            try:
                faction = self.game.coalition_for(player).faction
                self._doctrine[player.is_blue] = for_faction_obj(faction)
            except Exception:
                self._doctrine[player.is_blue] = CombatDoctrine()
        return self._doctrine[player.is_blue]

    def _morale(self) -> object:
        war_state = getattr(self.game, "war_state", None)
        if war_state is None or not getattr(self.settings, "morale_enabled", True):
            return None
        return getattr(war_state, "morale", None)

    def squadron_morale(self, flight: Flight) -> float:
        morale = self._morale()
        if morale is None:
            return 0.75
        return float(morale.squadron(flight.squadron))  # type: ignore[attr-defined]

    def front_morale(self, control_point: object) -> float:
        morale = self._morale()
        if morale is None:
            return 0.75
        return float(morale.front(control_point))  # type: ignore[attr-defined]

    def sam_crew_morale(self, tgo: TheaterGroundObject) -> float:
        morale = self._morale()
        if morale is None:
            return 0.75
        return float(morale.sam_crew(tgo))  # type: ignore[attr-defined]

    def abort_factor(self, flight: Flight) -> float:
        """How readily a flight gives up: doctrine and squadron morale."""
        doctrine = self.doctrine(flight.squadron.player)
        return doctrine.abort_threshold * (1.0 + (0.75 - self.squadron_morale(flight)))

    @property
    def ew_enabled(self) -> bool:
        return bool(getattr(self.settings, "ew_enabled", True))

    def site_network(self, tgo: TheaterGroundObject) -> Optional[SiteNetworkStatus]:
        """IADS dependency status of a SAM site, cached per simulation (the
        network only changes when units die, which invalidates the cache)."""
        key = str(tgo.id)
        if key not in self._network_cache:
            try:
                from game.warfare.iads import site_status

                self._network_cache[key] = site_status(self.game, tgo)
            except Exception:
                self._network_cache[key] = None
        return self._network_cache[key]

    def invalidate_network(self) -> None:
        self._network_cache.clear()

    def record_intel(
        self, observer: Player, tgo: TheaterGroundObject, quality: float, source: str
    ) -> None:
        """Notes something a side learned about an enemy ground object."""
        from game.warfare import IntelEvent
        from game.warfare.intel import IntelSource

        self.results.intel_events.append(
            IntelEvent(observer.is_blue, tgo.id, quality, IntelSource[source])
        )
        self.revealed.setdefault(observer.is_blue, set()).add(tgo.id)

    def credit(self, flight: Flight, kind: str, tgo: object = None) -> None:
        """Credits a flight with an achievement (or failure) for morale."""
        from game.warfare import CombatCredit

        tgo_id = getattr(tgo, "id", None)
        self.results.combat_credits.append(CombatCredit(flight, kind, tgo_id))

    def war_state(self) -> object:
        return getattr(self.game, "war_state", None)

    def knows_site(self, viewer: Player, tgo: TheaterGroundObject) -> bool:
        """Whether the viewer knew about this site before the mission, or has
        since seen it shoot."""
        if tgo.id in self.revealed.get(viewer.is_blue, set()):
            return True
        war_state = self.war_state()
        if war_state is None or not hasattr(war_state, "knows"):
            return True
        try:
            return bool(war_state.knows(self.game, viewer, tgo))
        except Exception:
            return True

    @staticmethod
    def side_name(player: Player) -> str:
        return "blue" if player.is_blue else "red"

    def log(self, time: datetime, domain: CombatDomain, side: str, text: str) -> None:
        self.results.log.add(time, domain, side, text)

    def kill_airframe(
        self,
        airframe: AirframeState,
        time: datetime,
        events: GameUpdateEvents,
        domain: CombatDomain,
        cause: str,
        loss_cause: Optional[LossCause] = None,
    ) -> bool:
        """Destroys an airframe. Player aircraft are never killed by the model; the
        player gets to fight for themselves in DCS."""
        if not airframe.alive:
            return False
        side = self.side_name(airframe.flight.squadron.player)
        whole_turn = (
            getattr(self.settings.fast_forward_stop_condition, "name", "")
            == "END_OF_TURN"
        )
        if airframe.is_player and not whole_turn:
            airframe.damaged = True
            self.log(
                time,
                domain,
                side,
                f"{airframe.name} (player) would have been hit by {cause}; player aircraft are not killed by auto-resolve",
            )
            return False
        airframe.alive = False
        # Where and how it went down, for the crew's fate (CSAR) and the report.
        from .aircrew import LossCause, detail_for

        self.results.air_loss_details.append(
            detail_for(airframe, loss_cause or LossCause.OTHER, cause)
        )
        self.results.kill_flight_member(airframe.flight, airframe.member, events)
        self.log(time, domain, side, f"{airframe.name} destroyed by {cause}")
        from game.ato.flighttype import FlightType

        if airframe.flight.flight_type is FlightType.REFUELING and not any(
            a.alive for a in self.airframes(airframe.flight)
        ):
            self.log(
                time,
                domain,
                side,
                f"{airframe.flight} lost: flights relying on it are now short of fuel",
            )
        return True

    def iter_package_airframes(
        self, flight: Flight, max_km: float = 80
    ) -> Iterator[AirframeState]:
        """Airframes of other flights in the same package that are airborne nearby."""
        if not flight.state.in_flight:
            return
        position = flight.state.estimate_position()
        for other in flight.package.flights:
            if other is flight or not other.alive or not other.state.in_flight:
                continue
            if distance_km(other.state.estimate_position(), position) > max_km:
                continue
            yield from self.airframes(other)

    def tgo_side(self, tgo: TheaterGroundObject) -> str:
        return self.side_name(tgo.control_point.captured)

    def target_altitude_factor(self, altitude_m: float) -> float:
        """Missiles fly further in thin air."""
        return 0.7 + 0.3 * clamp(altitude_m / 9000, 0.0, 1.0)

    def describe_side(self, player: Player) -> str:
        return self.side_name(player)


def player_of(flight: Flight) -> Player:
    return flight.squadron.player


def optional_alt(flight: Flight) -> Optional[float]:
    try:
        return float(flight.state.estimate_altitude()[0].meters)  # type: ignore[attr-defined]
    except Exception:
        return None
