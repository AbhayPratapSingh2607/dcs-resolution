"""Air-to-ground attack runs.

When a flight reaches its IP the model flies the attack: the flight descends
(or doesn't) to its release altitude, runs the gauntlet of point defenses
around the target unless its weapons outrange them, and delivers whatever it
is actually carrying. Hits depend on guidance (lasers need a designator and a
clear line through the clouds, TV seekers need daylight, GPS doesn't care but
can't hit moving targets, dumb bombs need a skilled pilot and good
visibility), and kills depend on the warhead against what was hit (rockets
don't drop hardened shelters, 2000 lb bombs do).
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType
from game.data.radar_db import TELARS, TRACK_RADARS, UNITS_WITH_RADAR
from game.data.units import UnitClass
from game.sim.combatlog import CombatDomain
from .airdefense import engage_site, fire_arms, site_for
from .aircrew import LossCause
from .airframe import AirframeState, WeaponStore
from .engine import CombatModel, clamp, distance_km

#: Hit chance factor with a FAC(A) on station (V3; game.commander.jfacc.faca).
FAC_BONUS = 1.25
from .profiles import Guidance, SHIP_HIT_POINTS, Warhead, WeaponRole

if TYPE_CHECKING:
    from dcs import Point

    from game.ato import Flight
    from game.sim.gameupdateevents import GameUpdateEvents
    from game.theater import ControlPoint, TheaterGroundObject
    from game.theater.theatergroup import TheaterUnit


class TargetClass(Enum):
    ARMOR = "armor"
    SOFT = "soft"
    STRUCTURE = "structure"
    SHIP = "ship"
    AIRCRAFT = "aircraft"


#: Probability that a hit kills, by warhead and target class.
KILL_MATRIX: dict[Warhead, dict[TargetClass, float]] = {
    Warhead.LIGHT: {
        TargetClass.ARMOR: 0.12,
        TargetClass.SOFT: 0.65,
        TargetClass.STRUCTURE: 0.1,
        TargetClass.SHIP: 0.03,
        TargetClass.AIRCRAFT: 0.6,
    },
    Warhead.MEDIUM: {
        TargetClass.ARMOR: 0.55,
        TargetClass.SOFT: 0.9,
        TargetClass.STRUCTURE: 0.7,
        TargetClass.SHIP: 0.15,
        TargetClass.AIRCRAFT: 0.9,
    },
    Warhead.HEAVY: {
        TargetClass.ARMOR: 0.8,
        TargetClass.SOFT: 0.95,
        TargetClass.STRUCTURE: 0.85,
        TargetClass.SHIP: 0.35,
        TargetClass.AIRCRAFT: 0.95,
    },
    Warhead.ANTITANK: {
        TargetClass.ARMOR: 0.85,
        TargetClass.SOFT: 0.8,
        TargetClass.STRUCTURE: 0.25,
        TargetClass.SHIP: 0.08,
        TargetClass.AIRCRAFT: 0.85,
    },
    Warhead.CLUSTER: {
        TargetClass.ARMOR: 0.45,
        TargetClass.SOFT: 0.85,
        TargetClass.STRUCTURE: 0.12,
        TargetClass.SHIP: 0.05,
        TargetClass.AIRCRAFT: 0.9,
    },
    Warhead.PENETRATOR: {
        TargetClass.ARMOR: 0.5,
        TargetClass.SOFT: 0.6,
        TargetClass.STRUCTURE: 0.9,
        TargetClass.SHIP: 0.2,
        TargetClass.AIRCRAFT: 0.8,
    },
    Warhead.FRAGMENTATION: {
        TargetClass.ARMOR: 0.1,
        TargetClass.SOFT: 0.7,
        TargetClass.STRUCTURE: 0.1,
        TargetClass.SHIP: 0.02,
        TargetClass.AIRCRAFT: 0.7,
    },
    Warhead.ANTISHIP: {
        TargetClass.ARMOR: 0.6,
        TargetClass.SOFT: 0.85,
        TargetClass.STRUCTURE: 0.6,
        TargetClass.SHIP: 1.0,
        TargetClass.AIRCRAFT: 0.9,
    },
}

#: Damage a hit does to a ship, in ship hit points.
SHIP_DAMAGE = {
    Warhead.ANTISHIP: 1.0,
    Warhead.HEAVY: 0.5,
    Warhead.PENETRATOR: 0.4,
    Warhead.MEDIUM: 0.25,
    Warhead.ANTITANK: 0.1,
    Warhead.CLUSTER: 0.05,
    Warhead.LIGHT: 0.03,
    Warhead.FRAGMENTATION: 0.03,
}

#: Runway crater value of a hit.
RUNWAY_DAMAGE = {
    Warhead.PENETRATOR: 2.0,
    Warhead.HEAVY: 1.0,
    Warhead.MEDIUM: 0.5,
    Warhead.CLUSTER: 0.2,
}

VISUAL_DELIVERY = (
    Guidance.UNGUIDED,
    Guidance.ROCKET,
    Guidance.CLUSTER,
    Guidance.RUNWAY,
    Guidance.GUN,
)
LOW_LEVEL_DELIVERY = (Guidance.ROCKET, Guidance.GUN, Guidance.ATGM)


@dataclass
class AimPoint:
    """Something that can be hit: a theater unit, a front-line group, a parked
    squadron, a convoy vehicle, a runway."""

    kind: str
    target_class: TargetClass
    priority: float
    unit: Optional[TheaterUnit] = None
    group: object = None
    origin: Optional[ControlPoint] = None
    squadron: object = None
    convoy: object = None
    unit_type: object = None
    moving: bool = False
    alive: bool = True


@dataclass
class AttackReport:
    released: int = 0
    hits: int = 0
    kills: int = 0
    losses: int = 0
    runway_score: float = 0.0
    notes: list[str] = field(default_factory=list)


class AttackRun:
    def __init__(
        self,
        model: CombatModel,
        flight: Flight,
        time: datetime,
        events: GameUpdateEvents,
    ) -> None:
        self.model = model
        self.flight = flight
        self.time = time
        self.events = events
        self.rng: random.Random = model.rng()
        self.side = model.side_name(flight.squadron.player)
        self.report = AttackReport()
        self.target = flight.package.target
        self._risk: Optional[float] = None
        self._roe_caution = False
        #: Accuracy penalty for a rushed pass at the edge of range.
        self._fuel_factor = 1.0
        #: A FAC(A) is on station over this front (V3).
        self._fac = False

    # ------------------------------------------------------------------ entry

    def run(self) -> AttackReport:
        airframes = self.model.airframes(self.flight)
        if not airframes:
            return self.report
        flight_type = self.flight.flight_type
        if flight_type is FlightType.AIR_ASSAULT:
            return self.report
        from game.commander.jfacc.faca import fac_capable, fac_on_station, is_fac

        if is_fac(self.flight) and fac_capable(self.flight):
            # FAC(A): marks and talks the CAS on; it does not attack itself.
            return self.report
        self._fac = self._is_front_line() and fac_on_station(
            self.model.game, self.flight.squadron.player, self.target
        )

        if flight_type in (
            FlightType.SEAD,
            FlightType.SEAD_SWEEP,
            FlightType.SEAD_ESCORT,
        ):
            self._sead(airframes)
            return self.report

        roles = (WeaponRole.A2G, WeaponRole.ANTISHIP, WeaponRole.ARM)
        attacked = self.model.attacked_flights
        first_pass = id(self.flight) not in attacked
        attacked.add(id(self.flight))
        if not any(True for a in airframes for _ in a.a2g_stores(roles)):
            if first_pass:
                self.model.log(
                    self.time,
                    CombatDomain.STRIKE,
                    self.side,
                    f"{self.flight} reaches {self.target.name} with no usable weapons",
                )
            return self.report

        if first_pass and self._short_of_fuel():
            return self.report

        if self._strike_decoy(airframes):
            return self.report

        aim_points, defenses_at = self._aim_points()
        if not aim_points and self.flight.flight_type is not FlightType.OCA_RUNWAY:
            self.model.log(
                self.time,
                CombatDomain.STRIKE,
                self.side,
                f"{self.flight} finds nothing left to attack at {self.target.name}",
            )
            return self.report

        if self._restrictive_roe():
            from game.warfare.collateral import risk_at

            try:
                self._roe_caution = (
                    risk_at(self.model.game, self.target.position) >= 0.2
                )
            except Exception:
                self._roe_caution = False
        survivors = self._run_gauntlet(airframes, defenses_at)
        for airframe in survivors:
            self._deliver(airframe, aim_points)
        self._summarize()
        self._report_intel()
        return self.report

    def _short_of_fuel(self) -> bool:
        """At the edge of its range a flight has no time to set up: one rushed
        pass, or it turns back before the target (see fuel.py)."""
        from .fuel import fuel_margin, strike_abort_chance, strike_accuracy_factor

        margin = fuel_margin(self.model, self.flight, self.time)
        self._fuel_factor = strike_accuracy_factor(margin)
        if self.rng.random() < strike_abort_chance(margin):
            self.model.log(
                self.time,
                CombatDomain.STRIKE,
                self.side,
                f"{self.flight} is short of fuel and turns back before reaching "
                f"{self.target.name}",
            )
            return True
        return False

    def _strike_decoy(self, airframes: list[AirframeState]) -> bool:
        """If the attackers' picture of the target is a decoy, they bomb the
        decoy. Returns True when that happened."""
        war_state = self.model.war_state()
        if war_state is None or not hasattr(war_state, "picture"):
            return False
        if not hasattr(self.target, "groups") or not hasattr(
            self.target, "control_point"
        ):
            return False
        from game.warfare.deception import consume_decoy, decoyed

        viewer = self.flight.squadron.player
        try:
            picture = war_state.picture(self.model.game, viewer)
        except Exception:
            return False
        index = decoyed(picture, self.target)  # type: ignore[arg-type]
        if index is None:
            return False
        for airframe in airframes:
            for store in airframe.a2g_stores(self._roles()):
                self.report.released += store.remaining
                store.remaining = 0
        consume_decoy(war_state, self.target, index)  # type: ignore[arg-type]
        contact = picture.contact(self.target)
        if self.rng.random() < 0.25 + 0.4 * picture.isr:
            # The crews realise they hit a dummy.
            picture.expose(self.target, self.rng)
            note = "the crews report a decoy"
        else:
            if contact is not None:
                contact.decoy_index = None
                contact.believed_dead = {u.id for u in self.target.units}  # type: ignore[attr-defined]
            note = "reported destroyed"
        self.model.log(
            self.time,
            CombatDomain.STRIKE,
            self.side,
            f"{self.flight} attacks {self.target.name}: the weapons hit decoys ({note})",
        )
        self.model.credit(self.flight, "strike_success", None)
        return True

    def _collateral(self, weapon: object, point: AimPoint, hit: bool) -> None:
        """Civilian casualties from weapons that go astray or spread widely."""
        from game.warfare.collateral import (
            AREA_WEAPONS,
            WEAPON_SPREAD,
            enabled,
            risk_at,
        )

        game = self.model.game
        if not hasattr(game, "theater") or not enabled(game):
            return
        guidance = weapon.guidance.value  # type: ignore[attr-defined]
        if hit and guidance not in AREA_WEAPONS:
            return
        if self._risk is None:
            try:
                self._risk = risk_at(
                    game, self.target.position, getattr(self.target, "category", "")
                )
            except Exception:
                self._risk = 0.0
        p = self._risk * WEAPON_SPREAD.get(guidance, 0.1) * (0.3 if hit else 1.0)
        if self.rng.random() < p:
            self.model.results.collateral_events.append(
                self.flight.squadron.player.is_blue
            )
            self.report.notes.append("civilian casualties reported")

    def _restrictive_roe(self) -> bool:
        from game.warfare.collateral import restrictive

        game = self.model.game
        if not hasattr(game, "coalition_for"):
            return False
        try:
            return restrictive(game, self.flight.squadron.player)
        except Exception:
            return False

    def _report_intel(self) -> None:
        if self.report.kills > 0:
            self.model.credit(self.flight, "strike_success", None)
        if hasattr(self.target, "groups") and hasattr(self.target, "control_point"):
            self.model.record_intel(
                self.flight.squadron.player, self.target, 0.8, "STRIKE"  # type: ignore[arg-type]
            )

    # ------------------------------------------------------------------ targets

    def _target_position(self) -> Point:
        return self.target.position

    def _aim_points(self) -> tuple[list[AimPoint], Point]:
        from game.theater import ControlPoint, TheaterGroundObject
        from game.theater.frontline import FrontLine
        from game.transfers import CargoShip, Convoy

        target = self.target
        flight_type = self.flight.flight_type
        points: list[AimPoint] = []
        if isinstance(target, FrontLine):
            points = self._front_line_points(target)
        elif isinstance(target, Convoy):
            already = self.model_kills("convoy", target)
            for unit_type, count in target.units.items():
                profile = self.model.profiles.ground_unit(unit_type)
                for _ in range(max(0, count - int(already[unit_type]))):
                    points.append(
                        AimPoint(
                            "convoy",
                            TargetClass.ARMOR if profile.armored else TargetClass.SOFT,
                            1.0,
                            convoy=target,
                            unit_type=unit_type,
                            moving=True,
                        )
                    )
        elif isinstance(target, CargoShip):
            points.append(
                AimPoint(
                    "cargo_ship", TargetClass.SHIP, 1.0, convoy=target, moving=True
                )
            )
        elif isinstance(target, ControlPoint):
            if flight_type is FlightType.OCA_AIRCRAFT:
                for squadron in target.squadrons:
                    parked = squadron.untasked_aircraft - int(
                        self.model_kills("parked", squadron)[None]
                    )
                    for _ in range(max(0, parked)):
                        points.append(
                            AimPoint(
                                "parked", TargetClass.AIRCRAFT, 1.0, squadron=squadron
                            )
                        )
            elif flight_type is FlightType.OCA_RUNWAY:
                pass
            else:
                for tgo in target.ground_objects:
                    if not tgo.is_dead:
                        points.extend(self._tgo_points(tgo))
        elif isinstance(target, TheaterGroundObject) or hasattr(target, "groups"):
            points = self._tgo_points(target)  # type: ignore[arg-type]
        return points, target.position

    def model_kills(self, kind: str, key: object) -> defaultdict[object, float]:
        return self.model.attack_tallies[(kind, id(key))]

    def _tgo_points(self, tgo: TheaterGroundObject) -> list[AimPoint]:
        flight_type = self.flight.flight_type
        points = []
        for unit in tgo.units:
            if not unit.alive:
                continue
            target_class = self._unit_class(unit)
            priority = 1.0
            is_radar = (
                unit.type in TRACK_RADARS
                or unit.type in TELARS
                or unit.type in UNITS_WITH_RADAR
            )
            if flight_type is FlightType.DEAD:
                priority = 3.0 if is_radar else (2.0 if unit.is_anti_air else 0.5)
            elif flight_type is FlightType.STRIKE:
                priority = 2.0 if unit.is_static else 1.0
            elif flight_type is FlightType.ANTISHIP:
                priority = 2.0 if unit.is_ship else 0.2
            points.append(AimPoint("unit", target_class, priority, unit=unit))
        return points

    def _unit_class(self, unit: TheaterUnit) -> TargetClass:
        if unit.is_ship:
            return TargetClass.SHIP
        if unit.is_static or not unit.is_vehicle:
            return TargetClass.STRUCTURE
        unit_type = unit.unit_type
        if unit_type is not None:
            from game.dcs.groundunittype import GroundUnitType

            if (
                isinstance(unit_type, GroundUnitType)
                and self.model.profiles.ground_unit(unit_type).armored
            ):
                return TargetClass.ARMOR
        return TargetClass.SOFT

    def _front_line_points(self, front_line: object) -> list[AimPoint]:
        own = self.flight.squadron.player
        blue_cp = front_line.blue_cp  # type: ignore[attr-defined]
        red_cp = front_line.red_cp  # type: ignore[attr-defined]
        enemy_cp, own_cp = (red_cp, blue_cp) if own.is_blue else (blue_cp, red_cp)
        planner = self.model.game.ground_planners.get(enemy_cp.id)
        if planner is None:
            return []
        points = []
        for group in planner.units_per_cp.get(own_cp.id, []):
            profile = self.model.profiles.ground_unit(group.unit_type)
            target_class = TargetClass.ARMOR if profile.armored else TargetClass.SOFT
            priority = 0.6 if profile.indirect else 1.0
            for _ in range(group.size):
                points.append(
                    AimPoint(
                        "front",
                        target_class,
                        priority,
                        group=group,
                        origin=enemy_cp,
                        moving=True,
                    )
                )
        return points

    # ------------------------------------------------------------------ defenses

    def _point_defenses(self, position: Point) -> list[TheaterGroundObject]:
        enemy = self.flight.squadron.player.opponent
        defenses = []
        for cp in self.model.game.theater.control_points_for(enemy):
            for tgo in cp.ground_objects:
                if tgo.is_dead or not tgo.has_aa:
                    continue
                reach = tgo.max_threat_range().kilometers
                if reach <= 0:
                    continue
                if distance_km(tgo.position, position) <= reach + 2:
                    defenses.append(tgo)
        return defenses

    def _primary_store(self, airframe: AirframeState) -> Optional[WeaponStore]:
        roles = self._roles()
        stores = list(airframe.a2g_stores(roles))
        if not stores:
            return None
        return max(stores, key=lambda s: s.profile.range_km)

    def _roles(self) -> tuple[WeaponRole, ...]:
        if self.flight.flight_type is FlightType.ANTISHIP:
            return (WeaponRole.ANTISHIP, WeaponRole.A2G)
        return (WeaponRole.A2G, WeaponRole.ANTISHIP, WeaponRole.ARM)

    def _attack_altitude(
        self, airframe: AirframeState, store: Optional[WeaponStore]
    ) -> float:
        cruise = airframe.altitude_m
        if airframe.profile.helicopter:
            return 50.0
        if store is None:
            return cruise
        doctrine = self.model.doctrine(self.flight.squadron.player)
        if doctrine.low_level_strikes and not store.profile.standoff:
            # Low-level penetration and pop-up attack.
            return 300.0
        guidance = store.profile.guidance
        env = self.model.env
        if guidance in LOW_LEVEL_DELIVERY:
            return min(cruise, 1200.0)
        if guidance in VISUAL_DELIVERY:
            altitude = min(cruise, 2500.0)
        else:
            altitude = cruise
        if (
            env.cloud_base_m is not None
            and env.cloud_cover >= 0.5
            and guidance
            not in (Guidance.GPS, Guidance.ANTISHIP, Guidance.ANTI_RADIATION)
        ):
            if altitude > env.cloud_base_m and env.cloud_base_m > 900:
                # Duck under the weather to see the target.
                altitude = env.cloud_base_m - 300
        return max(altitude, 150.0)

    def _run_gauntlet(
        self, airframes: list[AirframeState], position: Point
    ) -> list[AirframeState]:
        from game.ato.flighttype import FlightType as FT

        if self._is_front_line():
            return self._front_line_flak(airframes)
        defenses = self._point_defenses(position)
        if not defenses:
            return airframes
        survivors_before = len(airframes)
        for tgo in defenses:
            site = site_for(self.model, tgo)
            reach = tgo.max_threat_range().kilometers
            site_to_target = distance_km(tgo.position, position)
            for airframe in self.model.airframes(self.flight):
                store = self._primary_store(airframe)
                release_km = store.profile.range_km * 0.8 if store is not None else 2.0
                exposure_km = site_to_target + max(release_km, 1.0)
                if exposure_km > reach:
                    continue  # Released from outside this site's reach.
                altitude = self._attack_altitude(airframe, store)
                engage_site(
                    self.model,
                    None,
                    site,
                    self.flight,
                    self.time,
                    self.events,
                    self.rng,
                    attack_altitude_m=altitude,
                    only=[airframe],
                    range_km=exposure_km,
                )
        alive = self.model.airframes(self.flight)
        self.report.losses += survivors_before - len(alive)
        return alive

    def _is_front_line(self) -> bool:
        from game.theater.frontline import FrontLine

        return isinstance(self.target, FrontLine)

    def _front_line_flak(self, airframes: list[AirframeState]) -> list[AirframeState]:
        """Organic air defense of the front-line forces: MANPADS, AAA, SHORAD."""
        aa_strength = 0.0
        for point in self._front_line_points(self.target):
            group = point.group
            profile = self.model.profiles.ground_unit(group.unit_type)  # type: ignore[attr-defined]
            aa_strength += profile.air_defense
        # Every unit carries some small arms and the odd MANPADS.
        aa_strength += 0.05 * len(self._front_line_points(self.target))
        env = self.model.env
        for airframe in list(airframes):
            store = self._primary_store(airframe)
            altitude = self._attack_altitude(airframe, store)
            exposure = 1.0 if altitude < 3500 else 0.25
            if store is not None and store.profile.range_km >= 8:
                exposure *= 0.4
            defender = self.model.quality(self.flight.squadron.player.opponent)
            p_unit = (
                0.025
                * (0.6 + 0.4 * env.visual_factor)
                * self.model.lethality
                * (0.5 + 0.5 * defender.sam_crew)
            )
            p_unit *= 1.3 - 0.5 * airframe.skill
            p_loss = 1 - (1 - p_unit) ** (aa_strength * exposure)
            if self.rng.random() < p_loss:
                if self.model.kill_airframe(
                    airframe,
                    self.time,
                    self.events,
                    CombatDomain.STRIKE,
                    "ground fire over the front",
                    LossCause.GROUND_FIRE,
                ):
                    self.report.losses += 1
        return self.model.airframes(self.flight)

    # ------------------------------------------------------------------ delivery

    def _designated(self, airframe: AirframeState) -> bool:
        if airframe.has_tgp:
            return True
        for other in self.model.airframes(self.flight):
            if other.has_tgp:
                return True
        return any(
            a.has_tgp for a in self.model.iter_package_airframes(self.flight, 40)
        )

    def _guidance_factor(
        self,
        airframe: AirframeState,
        guidance: Guidance,
        altitude: float,
        point: AimPoint,
    ) -> float:
        env = self.model.env
        if guidance is Guidance.LASER:
            factor = env.laser_factor(altitude)
            if not self._designated(airframe) and not self._fac:
                factor *= 0.3
            return factor
        if guidance is Guidance.TV:
            return env.tv_factor(altitude)
        if guidance is Guidance.IIR:
            return env.line_of_sight_through_cloud(altitude) * max(
                0.5, env.visibility_factor
            )
        if guidance is Guidance.GPS:
            factor = 0.25 if point.moving else 1.0
            defender = self.flight.squadron.player.opponent
            if self.model.ew_enabled and self.model.doctrine(defender).gps_jamming:
                # Jammed GPS: the weapon falls back on its INS.
                factor *= 0.6
            return factor
        if guidance is Guidance.ATGM:
            return 0.65 + 0.35 * env.visual_factor
        if guidance is Guidance.ANTISHIP:
            return 1.0
        if guidance is Guidance.ANTI_RADIATION:
            return (
                0.8
                if point.unit is not None and point.unit.type in UNITS_WITH_RADAR
                else 0.1
            )
        # Visual delivery.
        modern = airframe.profile.generation >= 4 or airframe.has_tgp
        sight = (
            (0.75 + 0.25 * env.visual_factor)
            if modern
            else (0.35 + 0.65 * env.visual_factor)
        )
        factor = sight * env.line_of_sight_through_cloud(altitude)
        if point.moving:
            factor *= 0.8
        return factor

    def _pick(self, points: list[AimPoint], spread: bool) -> Optional[AimPoint]:
        alive = [p for p in points if p.alive and self._still_alive(p)]
        if not alive:
            return None
        if spread:
            top = max(p.priority for p in alive)
            best = [p for p in alive if p.priority == top]
            return self.rng.choice(best)
        weights = [p.priority for p in alive]
        return self.rng.choices(alive, weights=weights, k=1)[0]

    def _still_alive(self, point: AimPoint) -> bool:
        if point.unit is not None:
            return point.unit.alive
        if point.kind == "front":
            return point.group.size > 0  # type: ignore[attr-defined]
        return True

    def _deliver(self, airframe: AirframeState, points: list[AimPoint]) -> None:
        flight_type = self.flight.flight_type
        defended = (
            bool(self._point_defenses(self._target_position()))
            and not self._is_front_line()
        )
        for store in list(airframe.a2g_stores(self._roles())):
            weapon = store.profile
            altitude = self._attack_altitude(airframe, store)
            rounds = store.remaining
            store.remaining = 0
            for _ in range(rounds):
                self.report.released += 1
                if flight_type is FlightType.OCA_RUNWAY:
                    self._runway_hit(airframe, weapon, altitude, defended)
                    continue
                precision = weapon.guidance not in VISUAL_DELIVERY
                point = self._pick(points, spread=precision)
                if point is None:
                    break
                p_hit = weapon.accuracy * airframe.skill * self._fuel_factor
                p_hit *= self._guidance_factor(
                    airframe, weapon.guidance, altitude, point
                )
                if defended and not weapon.standoff:
                    p_hit *= 0.8
                if weapon.guidance is Guidance.ANTISHIP:
                    p_hit *= self._ship_defense(point)
                if self._fac and (
                    weapon.guidance in VISUAL_DELIVERY
                    or weapon.guidance is Guidance.LASER
                ):
                    p_hit *= FAC_BONUS
                if weapon.guidance in VISUAL_DELIVERY and self._roe_caution:
                    # Careful release near towns: higher, slower, fewer hits.
                    p_hit *= 0.8
                if self.rng.random() >= clamp(p_hit, 0.02, 0.95):
                    self._collateral(weapon, point, hit=False)
                    continue
                self.report.hits += 1
                self._collateral(weapon, point, hit=True)
                self._apply_hit(point, weapon.warhead, airframe)
                if weapon.warhead is Warhead.CLUSTER or weapon.guidance in (
                    Guidance.UNGUIDED,
                    Guidance.ROCKET,
                ):
                    # Area effect: neighbours of the aim point.
                    extra = 2 if weapon.warhead is Warhead.CLUSTER else 1
                    for _ in range(extra):
                        neighbour = self._pick(points, spread=False)
                        if (
                            neighbour is not None
                            and neighbour.target_class
                            in (TargetClass.SOFT, TargetClass.AIRCRAFT)
                            and self.rng.random() < 0.35
                        ):
                            self._apply_hit(neighbour, weapon.warhead, airframe)

    def _ship_defense(self, point: AimPoint) -> float:
        if point.unit is None:
            return 0.9
        tgo = point.unit.ground_object
        defenders = sum(
            1
            for u in tgo.units
            if u.alive and u.is_ship and u.threat_range.kilometers > 5
        )
        return 0.6 ** min(defenders, 3)

    def _runway_hit(
        self, airframe: AirframeState, weapon: object, altitude: float, defended: bool
    ) -> None:
        guidance = weapon.guidance  # type: ignore[attr-defined]
        p_hit = weapon.accuracy * airframe.skill  # type: ignore[attr-defined]
        point = AimPoint("runway", TargetClass.STRUCTURE, 1.0)
        p_hit *= self._guidance_factor(airframe, guidance, altitude, point)
        if defended and not weapon.standoff:  # type: ignore[attr-defined]
            p_hit *= 0.8
        # A runway is a big target.
        p_hit = clamp(p_hit * 1.5, 0.05, 0.95)
        if self.rng.random() < p_hit:
            self.report.hits += 1
            self.report.runway_score += RUNWAY_DAMAGE.get(weapon.warhead, 0.05)  # type: ignore[attr-defined]

    def _apply_hit(
        self, point: AimPoint, warhead: Warhead, airframe: AirframeState
    ) -> None:
        if not point.alive or not self._still_alive(point):
            return
        if point.target_class is TargetClass.SHIP:
            self._damage_ship(point, warhead)
            return
        p_kill = KILL_MATRIX.get(warhead, KILL_MATRIX[Warhead.MEDIUM])[
            point.target_class
        ]
        if self.rng.random() >= p_kill:
            return
        killed = False
        results = self.model.results
        if point.kind == "unit" and point.unit is not None:
            killed = results.kill_theater_unit(point.unit, self.events)
        elif point.kind == "front":
            killed = results.kill_front_line_unit(point.group, point.origin) > 0  # type: ignore[arg-type]
            if killed:
                self.model.credit(self.flight, "cas_kill")
        elif point.kind == "parked":
            results.kill_parked_aircraft(point.squadron)  # type: ignore[arg-type]
            self.model_kills("parked", point.squadron)[None] += 1
            killed = True
        elif point.kind == "convoy":
            from game.unitmap import ConvoyUnit

            results.kill_convoy_unit(ConvoyUnit(point.unit_type, point.convoy))  # type: ignore[arg-type]
            self.model_kills("convoy", point.convoy)[point.unit_type] += 1
            killed = True
        if killed:
            point.alive = False
            self.report.kills += 1

    def _damage_ship(self, point: AimPoint, warhead: Warhead) -> None:
        damage = SHIP_DAMAGE.get(warhead, 0.05)
        if point.kind == "cargo_ship":
            totals = self.model_kills("ship", point.convoy)
            totals[None] += damage
            if totals[None] >= 2 and point.alive:
                point.alive = False
                self.model.results.kill_cargo_ship(point.convoy)  # type: ignore[arg-type]
                self.report.kills += 1
            return
        unit = point.unit
        if unit is None:
            return
        unit_class = (
            unit.unit_type.unit_class
            if unit.unit_type is not None
            else UnitClass.FRIGATE
        )
        hit_points = SHIP_HIT_POINTS.get(unit_class, 2)
        totals = self.model_kills("ship", unit)
        totals[None] += damage
        if totals[None] >= hit_points and self.model.results.kill_theater_unit(
            unit, self.events
        ):
            point.alive = False
            self.report.kills += 1

    # ------------------------------------------------------------------ SEAD

    def _sead(self, airframes: list[AirframeState]) -> None:
        targets: list[TheaterGroundObject] = []
        if hasattr(self.target, "groups") and self.target.has_aa:  # type: ignore[attr-defined]
            targets.append(self.target)  # type: ignore[arg-type]
        targets.extend(
            t for t in self._point_defenses(self.target.position) if t not in targets
        )
        if not targets:
            return
        for tgo in targets:
            site = site_for(self.model, tgo)
            if site.is_dark(self.time) or not site.emits:
                continue
            shooters = []
            for airframe in airframes:
                if not airframe.alive:
                    continue
                stores = [
                    s
                    for s in airframe.stores
                    if s.profile.role is WeaponRole.ARM and s.remaining > 0
                ]
                if stores:
                    shooters.append(
                        (airframe, max(stores, key=lambda s: s.profile.range_km))
                    )
            if not shooters:
                break
            fire_arms(self.model, site, shooters, self.time, self.events, self.rng)

    # ------------------------------------------------------------------ report

    def _summarize(self) -> None:
        report = self.report
        if self.flight.flight_type is FlightType.OCA_RUNWAY:
            from game.theater import ControlPoint

            target = self.target
            if (
                isinstance(target, ControlPoint)
                and target.runway_is_destroyable
                and report.runway_score >= 3.0
            ):
                self.model.results.damage_runway(target)
                report.notes.append("runway closed")
            elif report.runway_score > 0:
                report.notes.append("runway damaged but still usable")
        notes = f" ({', '.join(report.notes)})" if report.notes else ""
        self.model.log(
            self.time,
            CombatDomain.STRIKE,
            self.side,
            f"{self.flight} attacks {self.target.name}: {report.released} weapons released, "
            f"{report.hits} hits, {report.kills} destroyed, {report.losses} aircraft lost{notes}",
        )
