"""Per-aircraft combat state: what each airframe is carrying and how well it is flown."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional, TYPE_CHECKING

from dcs.unit import Skill

from game.ato.flighttype import FlightType
from .profiles import (
    AircraftCombatProfile,
    CombatProfiles,
    Guidance,
    WeaponCombatProfile,
    WeaponRole,
)

if TYPE_CHECKING:
    from dcs import Point

    from .forcequality import ForceQuality

    from game.ato import Flight
    from game.ato.flightmember import FlightMember


SKILL_FACTOR = {
    Skill.Average: 0.76,
    Skill.Good: 0.88,
    Skill.High: 1.0,
    Skill.Excellent: 1.12,
    Skill.Player: 1.05,
    Skill.Client: 1.05,
}

#: Internal gun used when no better weapon is available, close in.
GUN = WeaponCombatProfile(
    name="Gun",
    role=WeaponRole.A2A,
    guidance=Guidance.GUN,
    count=6,
    range_km=1.2,
    nez_km=0.8,
    pk=0.25,
    all_aspect=False,
)


@dataclass
class WeaponStore:
    profile: WeaponCombatProfile
    remaining: int


@dataclass(eq=False)
class AirframeState:
    flight: Flight
    member: FlightMember
    profile: AircraftCombatProfile
    skill: float
    stores: list[WeaponStore]
    has_gun: bool
    has_tgp: bool
    self_jammer: bool
    offensive_jammer: bool
    chaff: int
    flares: int
    alive: bool = True
    damaged: bool = False
    #: Engagement-local window (seconds) during which the airframe is busy
    #: defending a missile and cannot press its own attack. Pilots only go
    #: defensive in the last seconds of a missile's flight; better pilots
    #: leave it later and recover sooner.
    defensive_from: float = 0.0
    defensive_until: float = -1.0
    gun_rounds: int = field(default=GUN.count)
    label: str = ""

    def is_defensive(self, at: float) -> bool:
        return self.defensive_from <= at <= self.defensive_until

    def go_defensive(self, now: float, impact: float) -> None:
        lead = 22.0 * (2.0 - self.skill)
        start = max(now, impact - lead)
        end = impact + 6.0 * (2.0 - self.skill)
        if self.defensive_until < now:
            self.defensive_from, self.defensive_until = start, end
        else:
            self.defensive_from = min(self.defensive_from, start)
            self.defensive_until = max(self.defensive_until, end)

    @property
    def is_player(self) -> bool:
        return self.member.is_player

    @property
    def name(self) -> str:
        return self.label

    @property
    def position(self) -> Point:
        return self.flight.state.estimate_position()

    @property
    def altitude_m(self) -> float:
        try:
            altitude, _ = self.flight.state.estimate_altitude()  # type: ignore[attr-defined]
            return float(altitude.meters)
        except Exception:
            return 3000.0

    @property
    def speed_kmh(self) -> float:
        try:
            return float(self.flight.state.estimate_speed().kph)  # type: ignore[attr-defined]
        except Exception:
            return 800.0

    @property
    def effective_rcs(self) -> float:
        rcs = self.profile.rcs
        # External stores roughly double the frontal RCS of a fighter.
        if self.stores and not self.profile.rcs < 0.1:
            rcs *= 1.0 + 0.15 * min(6, sum(1 for s in self.stores if s.remaining > 0))
        return rcs

    def a2a_stores(self) -> Iterator[WeaponStore]:
        for store in self.stores:
            if store.profile.role is WeaponRole.A2A and store.remaining > 0:
                yield store

    def a2g_stores(
        self, roles: tuple[WeaponRole, ...] = (WeaponRole.A2G,)
    ) -> Iterator[WeaponStore]:
        for store in self.stores:
            if store.profile.role in roles and store.remaining > 0:
                yield store

    def decoys(self) -> Iterator[WeaponStore]:
        for store in self.stores:
            if store.profile.role is WeaponRole.DECOY and store.remaining > 0:
                yield store

    @property
    def has_a2a_missiles(self) -> bool:
        return any(True for _ in self.a2a_stores())

    @property
    def has_bvr_missiles(self) -> bool:
        return any(s.profile.range_km > 25 for s in self.a2a_stores())

    @property
    def can_fight_air(self) -> bool:
        return (
            self.alive
            and not self.damaged
            and (self.has_a2a_missiles or (self.has_gun and self.gun_rounds > 0))
        )

    def jettison_air_to_ground(self) -> None:
        for store in self.stores:
            if store.profile.role in (WeaponRole.A2G, WeaponRole.ANTISHIP):
                store.remaining = 0

    def use_countermeasures(self, radar: bool) -> bool:
        """Expends a program of chaff or flares. Returns False if none were left."""
        if radar:
            if self.chaff <= 0:
                return False
            self.chaff = max(0, self.chaff - 6)
            return True
        if self.flares <= 0:
            return False
        self.flares = max(0, self.flares - 4)
        return True


def build_airframe(
    flight: Flight,
    member: FlightMember,
    profiles: CombatProfiles,
    quality: Optional[ForceQuality] = None,
) -> AirframeState:
    aircraft = flight.unit_type
    profile = profiles.aircraft(aircraft)
    stores: dict[str, WeaponStore] = {}
    has_tgp = aircraft.has_built_in_target_pod
    self_jammer = aircraft.has_built_in_ecm
    offensive_jammer = aircraft.has_built_in_jamming
    for weapon in member.loadout.pylons.values():
        if weapon is None:
            continue
        try:
            weapon_profile = profiles.weapon(weapon)
        except Exception:
            continue
        if weapon_profile.role is WeaponRole.TGP:
            has_tgp = True
            continue
        if weapon_profile.role is WeaponRole.JAMMER:
            self_jammer = True
            continue
        if weapon_profile.role is WeaponRole.OFFENSIVE_JAMMER:
            offensive_jammer = True
            continue
        if weapon_profile.role is WeaponRole.OTHER:
            continue
        store = stores.get(weapon_profile.name)
        if store is None:
            stores[weapon_profile.name] = WeaponStore(
                weapon_profile, weapon_profile.count
            )
        else:
            store.remaining += weapon_profile.count

    if member.pilot is None:
        skill = SKILL_FACTOR[flight.squadron.base_skill]
    elif member.pilot.player:
        skill = SKILL_FACTOR[Skill.Player]
    else:
        skill = SKILL_FACTOR.get(flight.squadron.pilot_skill(member.pilot), 1.0)
        # Combat experience beyond what the skill tiers capture.
        skill *= 1.0 + min(0.05, member.pilot.record.missions_flown * 0.005)

    from dataclasses import replace

    # Self-protection pods were worth a great deal historically (Linebacker,
    # Bekaa, Desert Storm); how much depends on threat libraries and tactics.
    ew_support = quality.ew_support if quality is not None else 1.0
    ecm = max(profile.ecm, 0.3) if self_jammer else profile.ecm
    ecm_profile = replace(profile, ecm=min(0.6, ecm * ew_support))
    if quality is not None:
        skill *= quality.aircrew

    has_gun = (
        aircraft.always_keeps_gun
        or aircraft.gunfighter
        or (profile.fighter and not profile.helicopter)
    )
    index = flight.roster.members.index(member) + 1
    callsign = getattr(flight, "callsign", None)
    if callsign is not None and getattr(callsign, "name", None):
        label = f"{aircraft.display_name} {callsign.name} {callsign.nr or 1}-{index}"
    else:
        label = f"{aircraft.display_name} #{index}"
    return AirframeState(
        label=label,
        flight=flight,
        member=member,
        profile=ecm_profile,
        skill=skill,
        stores=sorted(stores.values(), key=lambda s: -s.profile.range_km),
        has_gun=has_gun,
        has_tgp=has_tgp,
        self_jammer=self_jammer,
        offensive_jammer=offensive_jammer,
        chaff=ecm_profile.chaff,
        flares=ecm_profile.flares,
    )


def flight_role(flight: Flight) -> str:
    """fighter | striker | support"""
    flight_type = flight.flight_type
    if flight_type.is_air_to_air:
        return "fighter"
    if flight_type in (
        FlightType.AEWC,
        FlightType.REFUELING,
        FlightType.TRANSPORT,
        FlightType.FERRY,
        FlightType.PRETENSE_CARGO,
        FlightType.RECOVERY,
        FlightType.RESCUE_KING,
    ):
        return "support"
    return "striker"


def first_alive(airframes: list[AirframeState]) -> Optional[AirframeState]:
    return next((a for a in airframes if a.alive), None)
