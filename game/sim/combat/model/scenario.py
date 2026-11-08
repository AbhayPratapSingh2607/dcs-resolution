"""Synthetic scenarios for testing and calibrating the combat model.

These build just enough of a game to run the engagement engines with real
aircraft, weapon and air defense data, without loading a campaign. They are
used by ``tests/sim/combat`` and ``resources/tools/combat_calibration.py``.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional, Type, cast

from dcs import Point
from dcs.mapping import Point as MapPoint
from dcs.terrain import Caucasus
from dcs.unit import Skill
from dcs.unittype import FlyingType, VehicleType

from game.ato.flightmember import FlightMember
from game.ato.flighttype import FlightType
from game.ato.loadouts import Loadout
from game.data.weapons import Weapon, WeaponGroup
from game.dcs.aircrafttype import AircraftType
from game.settings import Settings
from game.sim.gameupdateevents import GameUpdateEvents
from game.sim.simulationresults import SimulationResults
from game.theater.player import Player
from game.utils import Distance, Speed, kph, meters
from .engine import CombatModel
from .environment import CombatEnvironment

_TERRAIN = Caucasus()
_ids = itertools.count(1)


def point(x_km: float, y_km: float) -> Point:
    return MapPoint(x_km * 1000, y_km * 1000, _TERRAIN)


def weapon(group_name: str, per_pylon: int = 1) -> Weapon:
    """A weapon of the named group, preferring a single-round pylon load."""
    WeaponGroup.load_all()
    group = WeaponGroup.named(group_name)
    from .profiles import CombatProfiles

    profiles = CombatProfiles.instance()
    candidates = []
    for w in group.weapons:
        try:
            profile = profiles.weapon(w)
        except KeyError:
            continue
        candidates.append((abs(profile.count - per_pylon), w))
    if not candidates:
        raise KeyError(group_name)
    return min(candidates, key=lambda c: c[0])[1]


def loadout(*weapons: tuple[str, int]) -> Loadout:
    """Loadout from (weapon group, number of pylons) pairs."""
    pylons: dict[int, Optional[Weapon]] = {}
    pylon = itertools.count(1)
    for name, pylon_count in weapons:
        for _ in range(pylon_count):
            pylons[next(pylon)] = weapon(name)
    return Loadout("scenario", pylons, None)


class SimState:
    def __init__(self, position: Point, altitude_m: float, speed_kph: float) -> None:
        self.position = position
        self.altitude_m = altitude_m
        self.speed_kph = speed_kph
        self.in_flight = True
        self.alive = True
        self.in_combat = False

    def estimate_position(self) -> Point:
        return self.position

    def estimate_altitude(self) -> tuple[Distance, str]:
        return meters(self.altitude_m), "BARO"

    def estimate_speed(self) -> Speed:
        return kph(self.speed_kph)


class SimRoster:
    def __init__(self, members: list[FlightMember]) -> None:
        self.members = members

    @property
    def max_size(self) -> int:
        return len(self.members)


@dataclass(eq=False)
class SimSquadron:
    aircraft: AircraftType
    player: Player
    skill: Skill
    settings: Settings
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    @property
    def base_skill(self) -> Skill:
        return self.skill

    def pilot_skill(self, pilot: Any) -> Skill:
        return self.skill


@dataclass(eq=False)
class SimPackage:
    target: Any
    flights: list[SimFlight] = field(default_factory=list)


class SimFlight:
    def __init__(
        self,
        squadron: SimSquadron,
        flight_type: FlightType,
        count: int,
        loadout_: Loadout,
        package: SimPackage,
        position: Point,
        altitude_m: float,
        speed_kph: float,
    ) -> None:
        self.id = uuid.uuid4()
        self.squadron = squadron
        self.flight_type = flight_type
        self.package = package
        self.roster = SimRoster(
            [FlightMember(None, loadout_.clone()) for _ in range(count)]
        )
        self.state: Any = SimState(position, altitude_m, speed_kph)
        self.callsign = None
        package.flights.append(self)

    @property
    def unit_type(self) -> AircraftType:
        return self.squadron.aircraft

    @property
    def count(self) -> int:
        return len(self.roster.members)

    @property
    def alive(self) -> bool:
        return self.state.alive

    def set_state(self, state: Any) -> None:
        self.state = state

    def abort(self) -> None:
        pass

    def __str__(self) -> str:
        return f"[{self.flight_type}] {self.count} x {self.unit_type}"


class SimAto:
    def __init__(self) -> None:
        self.packages: list[SimPackage] = []


class SimCoalition:
    def __init__(self, faction: str) -> None:
        from types import SimpleNamespace

        self.ato = SimAto()
        self.faction = SimpleNamespace(name=faction)


class SimTheater:
    def __init__(self) -> None:
        self.control_points: dict[bool, list[Any]] = {True: [], False: []}

    def control_points_for(
        self, player: Player, state_check: bool = False
    ) -> Iterable[Any]:
        return self.control_points[player.is_blue]

    def conflicts(self) -> Iterable[Any]:
        return []


class SimGame:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        blue_faction: str = "",
        red_faction: str = "",
    ) -> None:
        self.settings = settings or Settings()
        self.conditions = None
        self.blue = SimCoalition(blue_faction)
        self.red = SimCoalition(red_faction)
        self.theater = SimTheater()
        self.ground_planners: dict[Any, Any] = {}
        self.turn = 1

    def coalition_for(self, player: Player) -> SimCoalition:
        return self.blue if player.is_blue else self.red


@dataclass(eq=False)
class SimControlPoint:
    captured: Player
    name: str = "Base"
    position: Any = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    ground_objects: list[Any] = field(default_factory=list)
    squadrons: list[Any] = field(default_factory=list)

    @property
    def coalition(self) -> Any:
        from types import SimpleNamespace

        iads = SimpleNamespace(update_tgo=lambda tgo, events: None)
        return SimpleNamespace(
            game=SimpleNamespace(theater=SimpleNamespace(iads_network=iads))
        )


class SimGroup:
    def __init__(self, units: list[Any]) -> None:
        self.units = units


class SimTgo:
    """Minimal stand-in for a TheaterGroundObject holding real TheaterUnits."""

    def __init__(
        self,
        name: str,
        position: Point,
        control_point: SimControlPoint,
        units: list[Type[VehicleType]],
        iads: bool = False,
    ) -> None:
        from game.theater.theatergroup import TheaterUnit
        from dcs.mapping import Point as P

        self.id = uuid.uuid4()
        self.name = name
        self.position = position
        self.control_point = control_point
        self.is_iads = iads
        self.is_ewr_site = False
        self.is_naval_control_point = False
        self.is_control_point = False
        self.task = None
        from game.point_with_heading import PointWithHeading
        from game.utils import Heading

        self.groups = [
            SimGroup(
                [
                    TheaterUnit(
                        next(_ids),
                        f"{name}-{i}",
                        t,
                        PointWithHeading.from_point(
                            P(position.x, position.y, _TERRAIN), Heading.from_degrees(0)
                        ),
                        cast(Any, self),
                    )
                    for i, t in enumerate(units)
                ]
            )
        ]
        control_point.ground_objects.append(self)

    @property
    def units(self) -> Iterable[Any]:
        for group in self.groups:
            yield from group.units

    @property
    def is_dead(self) -> bool:
        return not any(u.alive for u in self.units)

    @property
    def has_aa(self) -> bool:
        return any(u.alive and u.is_anti_air for u in self.units)

    def max_threat_range(self) -> Distance:
        return max(
            (u.threat_range for u in self.units),
            default=meters(0),
            key=lambda d: d.meters,
        )

    def max_detection_range(self) -> Distance:
        return max(
            (u.detection_range for u in self.units),
            default=meters(0),
            key=lambda d: d.meters,
        )

    def invalidate_threat_poly(self) -> None:
        pass

    def is_friendly(self, to_player: Player) -> bool:
        return self.control_point.captured is to_player

    def threat_poly(self) -> None:
        return None

    def __hash__(self) -> int:
        return hash(self.id)


def ensure_headless() -> None:
    """Unit data loading wants a DCS saved games folder; give it a scratch one."""
    from game import persistency

    if getattr(persistency, "_dcs_saved_game_folder", None) is None:
        import tempfile

        persistency.setup(
            tempfile.mkdtemp(prefix="retribution-scenario-"), False, 16890
        )


class Scenario:
    """A battlefield: a game, a model and the flights in it."""

    def __init__(
        self,
        seed: int = 1,
        env: Optional[CombatEnvironment] = None,
        settings: Optional[Settings] = None,
        blue: str = "",
        red: str = "",
    ) -> None:
        """``blue``/``red`` are faction names; they select the force quality
        tier (see resources/combat/force_quality.yaml). Empty means the default
        tier for both, i.e. equally capable sides."""
        ensure_headless()
        self.game = SimGame(settings, blue, red)
        self.results = SimulationResults(seed=seed)
        self.model = CombatModel(self.game, self.results)  # type: ignore[arg-type]
        self.model.env = env or CombatEnvironment.clear_day()
        self.events = GameUpdateEvents()
        self.time = datetime(2000, 6, 1, 12, 0)
        self.blue_cp = SimControlPoint(Player.BLUE, "Blue base", point(-60, 0))
        self.red_cp = SimControlPoint(Player.RED, "Red base", point(120, 0))
        self.game.theater.control_points[True].append(self.blue_cp)
        self.game.theater.control_points[False].append(self.red_cp)

    def package(self, player: Player, target: Any = None) -> SimPackage:
        package = SimPackage(target)
        self.game.coalition_for(player).ato.packages.append(package)
        return package

    def flight(
        self,
        player: Player,
        aircraft: Type[FlyingType],
        flight_type: FlightType,
        count: int,
        weapons: Loadout,
        position: Point,
        *,
        altitude_m: float = 8000,
        speed_kph: float = 900,
        skill: Skill = Skill.High,
        package: Optional[SimPackage] = None,
    ) -> SimFlight:
        aircraft_type = next(AircraftType.for_dcs_type(aircraft))
        squadron = SimSquadron(aircraft_type, player, skill, self.game.settings)
        if package is None:
            package = self.package(player)
        return SimFlight(
            squadron,
            flight_type,
            count,
            weapons,
            package,
            position,
            altitude_m,
            speed_kph,
        )

    def sam(
        self,
        name: str,
        position: Point,
        units: list[Type[VehicleType]],
        player: Player = Player.RED,
        iads: bool = False,
    ) -> SimTgo:
        cp = self.red_cp if player is Player.RED else self.blue_cp
        return SimTgo(name, position, cp, units, iads)

    def air_combat(self, flights: list[SimFlight], max_seconds: float = 900) -> Any:
        from .airtoair import AirEngagement

        engagement = AirEngagement.create(self.model, flights, self.time)  # type: ignore[arg-type]
        elapsed = 0.0
        while elapsed < max_seconds:
            elapsed += 1
            if engagement.step(1.0, self.events):
                break
        return engagement

    def sam_transit(
        self, flight: SimFlight, sites: list[SimTgo], windows: int = 1
    ) -> int:
        """Exposes a flight to the sites for ``windows`` one-minute engagement
        windows. Returns losses."""
        from datetime import timedelta
        from .airdefense import AirDefenseEngagement

        before = flight.count
        for window in range(windows):
            engagement = AirDefenseEngagement.create(
                self.model,
                cast(Any, flight),
                cast(Any, sites),
                self.time + timedelta(minutes=window),
                timedelta(minutes=1),
            )
            while not engagement.step(1.0, self.events):
                pass
            if not flight.alive:
                break
        return before - flight.count

    def ewr(self, name: str, position: Point, player: Player = Player.RED) -> SimTgo:
        """An early warning radar that cues the side's networked SAMs."""
        from dcs.vehicles import AirDefence

        site = self.sam(name, position, [AirDefence.x_55G6_EWR], player, iads=True)
        site.is_ewr_site = True
        return site

    def target(
        self,
        name: str,
        position: Point,
        units: list[Type[Any]],
        player: Player = Player.RED,
    ) -> SimTgo:
        cp = self.red_cp if player is Player.RED else self.blue_cp
        return SimTgo(name, position, cp, units)

    def strike(self, flight: SimFlight) -> Any:
        from .attack import AttackRun

        return AttackRun(self.model, flight, self.time, self.events).run()  # type: ignore[arg-type]

    def losses(self, player: Player) -> int:
        return sum(
            1
            for loss in self.results.air_losses
            if loss.flight.squadron.player is player
        )
