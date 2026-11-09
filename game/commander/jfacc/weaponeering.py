"""Weaponeering: how many aircraft a target needs, and with which weapons.

Aim points (DMPIs) come from the target class and the number of live
elements. Weapons per aim point come from hardness. Guidance must suit the
conditions: laser and TV guided weapons need a clear line of sight from
medium altitude, so under a low cloud deck planners switch to GPS/INS or
unguided weapons, and at night only aircraft with a targeting pod or radar
ground mapping are tasked for attack.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, TYPE_CHECKING

from game.ato.flighttype import FlightType
from .profile import PlanningProfile
from .targetclass import HARDNESS

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight
    from game.ato.loadouts import Loadout
    from game.dcs.aircrafttype import AircraftType
    from game.theater import MissionTarget

ATTACK_TASKS = {
    FlightType.STRIKE,
    FlightType.BAI,
    FlightType.CAS,
    FlightType.DEAD,
    FlightType.OCA_RUNWAY,
    FlightType.OCA_AIRCRAFT,
    FlightType.ARMED_RECON,
    FlightType.ANTISHIP,
}

#: Tasks whose loadouts can stand in for each other when the default one
#: carries weapons the conditions rule out.
RELATED_TASKS = {
    FlightType.STRIKE: (FlightType.STRIKE, FlightType.OCA_RUNWAY, FlightType.BAI),
    FlightType.OCA_RUNWAY: (FlightType.OCA_RUNWAY, FlightType.STRIKE),
    FlightType.BAI: (FlightType.BAI, FlightType.CAS, FlightType.STRIKE),
    FlightType.CAS: (FlightType.CAS, FlightType.BAI),
    FlightType.DEAD: (FlightType.DEAD, FlightType.BAI, FlightType.STRIKE),
    FlightType.OCA_AIRCRAFT: (FlightType.OCA_AIRCRAFT, FlightType.BAI),
    FlightType.ARMED_RECON: (FlightType.ARMED_RECON, FlightType.CAS),
    FlightType.ANTISHIP: (FlightType.ANTISHIP,),
}


@dataclass(frozen=True)
class Conditions:
    night: bool
    low_cloud: bool
    visibility_km: float

    @property
    def key(self) -> str:
        if self.low_cloud:
            return "under_cloud"
        return "clear_night" if self.night else "clear_day"

    def describe(self) -> str:
        parts = ["night" if self.night else "day"]
        if self.low_cloud:
            parts.append("low cloud")
        return ", ".join(parts)


def conditions_for(game: Game, profile: PlanningProfile) -> Conditions:
    from game.sim.combat.model.environment import CombatEnvironment

    try:
        env = CombatEnvironment.from_conditions(game.conditions)
    except Exception:
        env = CombatEnvironment.clear_day()
    min_base_ft = float(profile.get("conditions", "min_cloud_base_for_lgb_ft", 12000))
    low_cloud = (
        env.cloud_base_m is not None
        and env.cloud_cover >= 0.6
        and env.cloud_base_m * 3.28084 < min_base_ft
    )
    return Conditions(
        night=env.night, low_cloud=low_cloud, visibility_km=env.visibility_km
    )


# ------------------------------------------------------------------ sizing


def aircraft_needed(
    profile: PlanningProfile,
    target_class: str,
    live_elements: int,
) -> int:
    """Attack aircraft needed for the desired effect against one target."""
    cfg = profile.section("weaponeering")
    dmpis = min(profile.dmpis_for(target_class), max(1, live_elements))
    hardness = HARDNESS.get(target_class, "medium")
    weapons = dmpis * int(cfg.get("weapons_per_dmpi", {}).get(hardness, 2))
    per_aircraft = max(1, int(cfg.get("weapons_per_aircraft", 2)))
    aircraft = math.ceil(weapons / per_aircraft)
    # Fly in elements of two.
    aircraft = max(2, aircraft + (aircraft % 2))
    return min(aircraft, int(profile.get("packages", "max_strikers", 8)))


# ---------------------------------------------------------------- guidance


def _a2g_guidance(loadout: Loadout) -> set[str]:
    from game.sim.combat.model.profiles import CombatProfiles, WeaponRole

    profiles = CombatProfiles.instance()
    kinds: set[str] = set()
    for weapon in loadout.pylons.values():
        if weapon is None:
            continue
        try:
            profile = profiles.weapon(weapon)
        except Exception:
            continue
        if profile.role in (WeaponRole.A2G, WeaponRole.ARM, WeaponRole.ANTISHIP):
            kinds.add(profile.guidance.value)
    return kinds


def _has_tgp(loadout: Loadout) -> bool:
    from game.sim.combat.model.profiles import CombatProfiles, WeaponRole

    profiles = CombatProfiles.instance()
    for weapon in loadout.pylons.values():
        if weapon is None:
            continue
        try:
            if profiles.weapon(weapon).role is WeaponRole.TGP:
                return True
        except Exception:
            continue
    return False


@lru_cache(maxsize=None)
def night_capable(aircraft: AircraftType) -> bool:
    """Whether the aircraft can find and attack targets at night: a targeting
    pod in any of its loadouts, a ground-mapping radar strike aircraft, or a
    night-attack helicopter."""
    from game.ato.loadouts import Loadout
    from game.sim.combat.model.profiles import CombatProfiles, RadarType

    year = 1980
    try:
        from game.sim.combat.model.profiles import parse_year

        year = parse_year(aircraft.year_introduced)
    except Exception:
        pass
    if aircraft.helicopter:
        return year >= 1984
    try:
        for loadout in Loadout.iter_for_aircraft(aircraft):
            if _has_tgp(loadout):
                return True
    except Exception:
        pass
    profile = CombatProfiles.instance().aircraft(aircraft)
    # Radar-bombing strike aircraft (F-111/Tornado/Su-24 class) work at night.
    return (
        profile.radar is not RadarType.NONE
        and not profile.fighter
        and year >= 1975
    )


def allowed_guidance(profile: PlanningProfile, conditions: Conditions) -> list[str]:
    table = profile.section("weaponeering").get("guidance_preference", {})
    return list(table.get(conditions.key, ["gps", "laser", "unguided"]))


def _loadout_ok(guidance: set[str], allowed: Iterable[str], conditions: Conditions) -> bool:
    if not guidance:
        return False
    usable = set(allowed) | {"anti_radiation", "antiship", "atgm", "rocket", "cluster", "runway", "iir", "ir"}
    if conditions.low_cloud:
        usable -= {"laser", "tv"}
    return bool(guidance & usable)


def _candidate_loadouts(flight: Flight) -> list[Loadout]:
    from game.ato.loadouts import Loadout
    from game.data.weapons import Weapon

    dcs_type = flight.unit_type.dcs_unit_type
    names: list[str] = []
    for task in RELATED_TASKS.get(flight.flight_type, (flight.flight_type,)):
        for name in Loadout.default_loadout_names_for(task):
            if name not in names:
                names.append(name)
    dcs_type.load_payloads()
    loadouts: list[Loadout] = []
    for name in names:
        payload = dcs_type.loadout_by_name(name)
        if payload is None:
            continue
        payload = Loadout.adjust_payload_for_target(payload, flight.package.target)
        try:
            loadouts.append(
                Loadout(
                    name,
                    {i: Weapon.with_clsid(d["clsid"]) for i, d in payload},
                    date=None,
                    pylon_settings={i: d.get("settings", {}) for i, d in payload},
                )
            )
        except Exception:
            continue
    return loadouts


def apply(flight: Flight, profile: PlanningProfile, conditions: Conditions) -> tuple[bool, str]:
    """Check (and if needed fix) the flight's weapons for the conditions.

    Returns whether the flight can attack, and a note for the rationale.
    """
    if flight.flight_type not in ATTACK_TASKS:
        return True, ""
    if conditions.night and profile.get("conditions", "night_requires_sensor", True):
        if not night_capable(flight.unit_type):
            return False, f"{flight.unit_type} is not night-attack capable"
    allowed = allowed_guidance(profile, conditions)
    members = list(flight.iter_members())
    if not members:
        return True, ""
    current = members[0].loadout
    if _loadout_ok(_a2g_guidance(current), allowed, conditions):
        return True, ""
    for candidate in _candidate_loadouts(flight):
        if _loadout_ok(_a2g_guidance(candidate), allowed, conditions):
            for member in members:
                if member.is_player:
                    continue
                member.loadout = candidate.clone()
            return True, f"weapons changed to {candidate.name} ({conditions.describe()})"
    return False, f"no {flight.unit_type} weapons suit {conditions.describe()}"


def carries_standoff(flight: Flight) -> bool:
    """Whether the flight's air-to-ground weapons are released outside the
    reach of target-area defenses (JSOW, JASSM, Maverick and the like)."""
    from game.sim.combat.model.profiles import CombatProfiles, WeaponRole

    profiles = CombatProfiles.instance()
    for member in flight.iter_members():
        for weapon in member.loadout.pylons.values():
            if weapon is None:
                continue
            try:
                profile = profiles.weapon(weapon)
            except Exception:
                continue
            if profile.role in (WeaponRole.A2G, WeaponRole.ANTISHIP) and profile.standoff:
                return True
        break
    return False


def live_elements(target: MissionTarget) -> int:
    from game.theater.theatergroundobject import TheaterGroundObject

    if isinstance(target, TheaterGroundObject):
        return max(1, target.alive_unit_count)
    units = getattr(target, "units", None)
    if units is not None:
        try:
            return max(1, len(list(units)))
        except TypeError:
            pass
    return 4
