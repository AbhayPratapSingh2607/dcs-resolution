"""Surface-to-air engagements.

A SAM site is modelled as a set of launchers (with magazines and fire
channels) that depend on their tracking radars. For each 10 second round a
site that can see the target fires salvos, the target defends, and any SEAD
support in the package hunts the radar. Long-range radar SAMs are limited by
the radar horizon and their altitude envelope, so low flying gets you close
before you're seen and high flying keeps you out of MANPADS and AAA.

Sites keep their state for the whole simulation: missiles fired are gone,
radars destroyed by ARMs stay dead, and a site that went dark to avoid an ARM
stays suppressed for a while.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Optional, TYPE_CHECKING

from dcs.unittype import VehicleType

from game.data.radar_db import (
    LAUNCHER_TRACKER_PAIRS,
    TELARS,
    TRACK_RADARS,
    UNITS_WITH_RADAR,
)
from game.sim.combatlog import CombatDomain
from .aircrew import LossCause
from .airframe import AirframeState, WeaponStore
from .engine import CombatModel, clamp, distance_km, radar_horizon_km
from .profiles import AirDefenseGuidance, AirDefenseProfile, WeaponRole

if TYPE_CHECKING:
    from game.ato import Flight
    from game.sim.gameupdateevents import GameUpdateEvents
    from game.theater import TheaterGroundObject
    from game.theater.theatergroup import TheaterGroup, TheaterUnit

ROUND_SECONDS = 10.0


@dataclass
class Launcher:
    unit: TheaterUnit
    group: TheaterGroup
    profile: AirDefenseProfile
    missiles: int

    def guidance_ready(self) -> bool:
        if not self.unit.alive:
            return False
        if self.profile.guidance is not AirDefenseGuidance.RADAR:
            return True
        if not (
            issubclass(self.unit.type, VehicleType)
            and self.unit.type in LAUNCHER_TRACKER_PAIRS
        ):
            # Radar SAM we know nothing about the pairing of; any live radar will do.
            return any(u.alive and u.type in UNITS_WITH_RADAR for u in self.group.units)
        trackers = LAUNCHER_TRACKER_PAIRS[self.unit.type]
        return any(u.alive and u.type in trackers for u in self.group.units)


@dataclass
class SamSiteState:
    tgo: TheaterGroundObject
    launchers: list[Launcher]
    dark_until: Optional[datetime] = None
    first_track: dict[int, float] = field(default_factory=dict)
    #: Airframe ids currently being guided on, with the time the channel frees.
    channels: dict[int, datetime] = field(default_factory=dict)
    shots: int = 0
    _outage_bucket: int = -1
    _outage: bool = False
    #: Targets this site has already fired on (surprise is spent).
    surprised: set[int] = field(default_factory=set)

    @staticmethod
    def build(model: CombatModel, tgo: TheaterGroundObject) -> SamSiteState:
        launchers = []
        for group in tgo.groups:
            for unit in group.units:
                if not unit.alive or not unit.is_anti_air or unit.type in TRACK_RADARS:
                    continue
                if float(getattr(unit.type, "threat_range", 0) or 0) <= 0:
                    continue
                profile = model.profiles.air_defense(unit)
                if profile is None:
                    continue
                launchers.append(Launcher(unit, group, profile, profile.missiles))
        return SamSiteState(tgo, launchers)

    def radar_units(self) -> list[TheaterUnit]:
        radars = []
        for unit in self.tgo.units:
            if unit.alive and (
                unit.type in TRACK_RADARS
                or unit.type in TELARS
                or unit.type in UNITS_WITH_RADAR
            ):
                radars.append(unit)
        return radars

    def power_outage(self, now: datetime, rng: random.Random) -> bool:
        """A site without mains power runs on generators and is sometimes off
        the air. Decided once per minute."""
        bucket = int(now.timestamp() // 60)
        if self._outage_bucket != bucket:
            self._outage_bucket = bucket
            self._outage = rng.random() < 0.3
        return self._outage

    def is_dark(self, now: datetime) -> bool:
        return self.dark_until is not None and now < self.dark_until

    def ready_launchers(self) -> list[Launcher]:
        return [l for l in self.launchers if l.missiles > 0 and l.guidance_ready()]

    @property
    def emits(self) -> bool:
        return any(l.profile.emitter for l in self.launchers if l.unit.alive)

    def free_channels(self, now: datetime, profile: AirDefenseProfile) -> int:
        self.channels = {k: v for k, v in self.channels.items() if v > now}
        launchers = (
            len({id(l.group) for l in self.ready_launchers() if l.profile is profile})
            or 1
        )
        return max(0, profile.channels * launchers - len(self.channels))


def site_for(model: CombatModel, tgo: TheaterGroundObject) -> SamSiteState:
    key = str(tgo.id)
    site = model.sam_sites.get(key)
    if site is None:
        site = SamSiteState.build(model, tgo)
        model.sam_sites[key] = site
    return site


def package_jamming(model: CombatModel, flight: Flight) -> float:
    """Stand-off and escort jamming protecting this flight, 0..0.6."""
    jam = 0.0
    for airframe in model.airframes(flight):
        if airframe.offensive_jammer:
            jam += 0.25
    for airframe in model.iter_package_airframes(flight, 100):
        if airframe.offensive_jammer:
            jam += 0.25
    return clamp(jam, 0.0, 0.6)


def sead_shooters(
    model: CombatModel, flight: Flight, site: SamSiteState
) -> list[tuple[AirframeState, WeaponStore]]:
    """Package members with ARMs in range of the site."""
    from game.ato.flighttype import FlightType

    shooters = []
    candidates = list(model.airframes(flight)) + list(
        model.iter_package_airframes(flight, 120)
    )
    for airframe in candidates:
        if (
            airframe.flight.flight_type
            not in (
                FlightType.SEAD,
                FlightType.SEAD_ESCORT,
                FlightType.DEAD,
                FlightType.SEAD_SWEEP,
            )
            and airframe.flight is not flight
        ):
            continue
        stores = [
            s
            for s in airframe.stores
            if s.profile.role is WeaponRole.ARM and s.remaining > 0
        ]
        if not stores:
            continue
        rng_km = distance_km(airframe.position, site.tgo.position)
        store = max(stores, key=lambda s: s.profile.range_km)
        if rng_km <= store.profile.range_km * model.target_altitude_factor(
            airframe.altitude_m
        ):
            shooters.append((airframe, store))
    return shooters


@dataclass
class AirDefenseEngagement:
    """One flight transiting the engagement zones of one or more SAM sites."""

    model: CombatModel
    flight: Flight
    sites: list[SamSiteState]
    start_time: datetime
    rng: random.Random
    window_seconds: float = 60.0
    elapsed: float = 0.0
    shots_at_flight: int = 0
    losses: int = 0
    _since_round: float = 0.0
    aborted: bool = False
    sites_engaged: set[str] = field(default_factory=set)
    _decoys_launched: bool = False

    @staticmethod
    def create(
        model: CombatModel,
        flight: Flight,
        tgos: Iterable[TheaterGroundObject],
        time: datetime,
        window: timedelta,
    ) -> AirDefenseEngagement:
        sites = [site_for(model, tgo) for tgo in tgos]
        return AirDefenseEngagement(
            model, flight, sites, time, model.rng(), window.total_seconds()
        )

    def now(self) -> datetime:
        return self.start_time + timedelta(seconds=self.elapsed)

    def step(self, seconds: float, events: GameUpdateEvents) -> bool:
        self.elapsed += seconds
        self._since_round += seconds
        while self._since_round >= ROUND_SECONDS:
            self._since_round -= ROUND_SECONDS
            self._round(events)
            if not self.model.airframes(self.flight):
                return True
        if self.elapsed >= self.window_seconds:
            self._decide()
            return True
        return False

    # --------------------------------------------------------------------

    def _avoid_engaged_sites(self) -> None:
        """Trained aircrews that survive an engagement are vectored out of that
        envelope (AWACS, RWR, re-routing) instead of loitering in it."""
        quality = self.model.quality(self.flight.squadron.player)
        if (
            not quality.standoff_doctrine
            or self.flight.flight_type.name in SEAD_HUNTERS
        ):
            return
        until = self.now() + timedelta(minutes=5)
        for site_key in self.sites_engaged:
            self.model.sam_avoidance[(id(self.flight), site_key)] = until

    def _round(self, events: GameUpdateEvents) -> None:
        now = self.now()
        if not self._decoys_launched:
            self._decoys_launched = True
            # Package sequencing: SEAD goes in first against the sites it knows,
            # then decoys, and only then the strikers.
            for site in self.sites:
                key = (id(self.flight.package), str(site.tgo.id))
                if key in self.model.preempted or site.is_dark(now):
                    continue
                if site.emits and self.model.knows_site(
                    self.flight.squadron.player, site.tgo
                ):
                    shooters = sead_shooters(self.model, self.flight, site)
                    if shooters:
                        self.model.preempted.add(key)
                        fire_arms(self.model, site, shooters[:2], now, events, self.rng)
            if self.model.ew_enabled:
                for site in self.sites:
                    launch_decoys(self.model, site, self.flight, now, events, self.rng)
        altitude = self._penetration_altitude()
        for site in self.sites:
            engage_site(
                self.model,
                self,
                site,
                self.flight,
                now,
                events,
                self.rng,
                attack_altitude_m=altitude,
            )

    def _penetration_altitude(self) -> Optional[float]:
        """Low-level doctrine: strikers come in under the radar horizon."""
        from .airframe import flight_role

        if flight_role(self.flight) != "striker":
            return None
        if not self.model.doctrine(self.flight.squadron.player).low_level_strikes:
            return None
        airframes = self.model.airframes(self.flight)
        if not airframes or airframes[0].profile.helicopter:
            return None
        return 250.0

    def _decide(self) -> None:
        from .airframe import flight_role

        self._avoid_engaged_sites()
        airframes = self.model.airframes(self.flight)
        if not airframes or flight_role(self.flight) != "striker":
            return
        from game.ato.flighttype import FlightType

        if self.flight.flight_type in (
            FlightType.SEAD,
            FlightType.DEAD,
            FlightType.SEAD_ESCORT,
        ):
            return
        initial = len(airframes) + self.losses
        p_abort = 0.0
        if self.losses:
            p_abort += 0.25 + 0.35 * self.losses / max(initial, 1)
        if self.shots_at_flight >= 4:
            p_abort += 0.15
        p_abort *= self.model.abort_factor(self.flight)
        if self.rng.random() < p_abort:
            self.aborted = True
            self.model.credit(self.flight, "abort")
            for airframe in airframes:
                airframe.jettison_air_to_ground()
            self.model.log(
                self.now(),
                CombatDomain.AIR_DEFENSE,
                self.model.side_name(self.flight.squadron.player),
                f"{self.flight} aborts under heavy SAM fire",
            )


def launch_decoys(
    model: CombatModel,
    site: SamSiteState,
    flight: Flight,
    now: datetime,
    events: GameUpdateEvents,
    rng: random.Random,
) -> int:
    """Air-launched decoys (TALD, MALD) fly into the site's coverage ahead of
    the package. Sites that can't tell them from aircraft light up their radars
    and spend missiles on them, which is when the HARM shooters get them
    (Bekaa 1982, Desert Storm night one). Returns decoys engaged."""
    if site.is_dark(now) or not site.emits:
        return 0
    stores = [
        (airframe, store)
        for airframe in list(model.airframes(flight))
        + list(model.iter_package_airframes(flight, 80))
        for store in airframe.decoys()
    ]
    if not stores:
        return 0
    owner = site.tgo.control_point.captured
    defender = model.quality(owner)
    discrimination = model.doctrine(owner).decoy_discrimination * (
        0.5 + 0.5 * defender.sam_crew
    )
    engaged = 0
    for airframe, store in stores:
        while store.remaining > 0:
            store.remaining -= 1
            if rng.random() < discrimination:
                continue  # Recognised as a decoy and ignored.
            launchers = [
                l
                for l in site.ready_launchers()
                if l.profile.emitter and l.missiles > 0
            ]
            if not launchers:
                return engaged
            launcher = rng.choice(launchers)
            salvo = min(launcher.profile.salvo, launcher.missiles)
            launcher.missiles -= salvo
            site.shots += salvo
            site.channels[id(store) * 1000 + store.remaining] = now + timedelta(
                seconds=30
            )
            engaged += 1
    if engaged:
        model.log(
            now,
            CombatDomain.AIR_DEFENSE,
            model.tgo_side(site.tgo),
            f"{site.tgo.name} engages {engaged} decoys",
        )
        # The radars are on now: HARM shooters take their chance.
        _sead_response(model, site, flight, now, events, rng)
    return engaged


def under_arm_threat(model: CombatModel, site: SamSiteState, now: datetime) -> bool:
    """Whether the crew has reason to fear anti-radiation missiles: an ARM was
    fired at the site recently, or enemy SEAD aircraft with ARMs are airborne
    within reach of it."""
    key = str(site.tgo.id)
    last = model.arm_launches.get(key)
    if last is not None and (now - last).total_seconds() < 300:
        return True
    bucket = int(now.timestamp() // 30)
    cached = model.arm_threat_cache.get(key)
    if cached is not None and cached[0] == bucket:
        return cached[1]
    enemy = site.tgo.control_point.captured.opponent
    threatened = False
    for package in model.game.coalition_for(enemy).ato.packages:
        for flight in package.flights:
            if threatened:
                break
            if flight.flight_type.name not in SEAD_HUNTERS:
                continue
            if not flight.alive or not flight.state.in_flight:
                continue
            for airframe in model.airframes(flight):
                reach = max(
                    (
                        st.profile.range_km
                        for st in airframe.stores
                        if st.profile.role is WeaponRole.ARM and st.remaining > 0
                    ),
                    default=0.0,
                )
                if (
                    reach
                    and distance_km(airframe.position, site.tgo.position) <= reach * 1.2
                ):
                    threatened = True
                    break
        if threatened:
            break
    model.arm_threat_cache[key] = (bucket, threatened)
    return threatened


def engage_site(
    model: CombatModel,
    engagement: Optional[AirDefenseEngagement],
    site: SamSiteState,
    flight: Flight,
    now: datetime,
    events: GameUpdateEvents,
    rng: random.Random,
    attack_altitude_m: Optional[float] = None,
    only: Optional[list[AirframeState]] = None,
    range_km: Optional[float] = None,
) -> int:
    """One round of a site shooting at a flight. Returns the number of shots fired.

    The kill chain follows what decided real SAM engagements:

    * **Cueing.** A site tied into a working IADS gets early, accurate tracks
      from the network. An autonomous site has to find targets with its own
      radar: shorter reach, poorer tracks, slower reaction.
    * **Crew proficiency** (force quality) sets track quality and how often a
      launch is made properly.
    * **SEAD deterrence.** Under ARM threat, crews radiate only briefly or fire
      without guidance to survive (Serbia 1999: hundreds of launches, two
      kills). That costs track quality and makes many launches ballistic.
    * **Threat avoidance.** Aircrews trained to stay out of known envelopes are
      vectored away once engaged, so repeat engagements are harder.
    """
    if site.is_dark(now):
        return 0
    launchers = site.ready_launchers()
    if not launchers:
        return 0
    env = model.env
    side = model.tgo_side(site.tgo)
    defender = model.quality(site.tgo.control_point.captured)
    # Crews that watched neighbouring sites die, or were hunted by ARMs, are
    # timid: worse at their job and quicker to hide.
    crew_morale = model.sam_crew_morale(site.tgo)
    crew_skill = defender.sam_crew * (0.7 + 0.4 * crew_morale)
    arm_fear = min(0.95, defender.arm_fear + 0.5 * max(0.0, 0.75 - crew_morale))
    site_key = str(site.tgo.id)
    covered = site.tgo.is_iads and model.awareness(
        site.tgo.control_point.captured, now
    ).covers(flight.state.estimate_position(), attack_altitude_m or 3000, 5)
    # In an advanced IADS the site also needs its command chain: early warning
    # through live comms and command centres. Power loss means generators.
    network = model.site_network(site.tgo)
    networked = covered and (network is None or network.networked)
    unpowered = network is not None and not network.has_power
    if unpowered and site.power_outage(now, rng):
        return 0
    cued = networked and rng.random() < defender.iads_integration
    # Communications jamming breaks the link between the network and the site.
    jam_comms = package_jamming(model, flight) if model.ew_enabled else 0.0
    if cued and jam_comms and rng.random() < jam_comms * 0.6:
        cued = False
    arm_threat = under_arm_threat(model, site, now)
    # Short-emission tactics: the crew radiates in bursts and may fire blind.
    hiding = arm_threat and rng.random() < arm_fear
    jam = package_jamming(model, flight)
    avoid_until = model.sam_avoidance.get((id(flight), site_key))
    avoiding = avoid_until is not None and now < avoid_until
    # A site the attackers didn't know about gets surprise: nobody routed
    # around it, and the first shots come out of nowhere.
    surprise = not model.knows_site(flight.squadron.player, site.tgo)
    if surprise:
        avoiding = False
    # Ambush tactics: radars stay dark until the target is close, then a short,
    # unexpected shot.
    ambush_doctrine = (
        model.doctrine(site.tgo.control_point.captured).sam_ambush and not cued
    )
    shots_this_round = 0
    targets = [
        a for a in (only if only is not None else model.airframes(flight)) if a.alive
    ]
    rng.shuffle(targets)

    for airframe in targets:
        altitude = (
            attack_altitude_m if attack_altitude_m is not None else airframe.altitude_m
        )
        if range_km is not None:
            rng_km = range_km
        else:
            rng_km = distance_km(airframe.position, site.tgo.position)
        for launcher in launchers:
            profile = launcher.profile
            if launcher.missiles <= 0 or not launcher.guidance_ready():
                continue
            if not (profile.min_alt_m <= max(altitude, 1.0) <= profile.max_alt_m):
                continue
            reach = profile.range_km
            # Ambushes are a tactic of mobile short and medium range systems.
            ambush = ambush_doctrine and profile.emitter and profile.range_km <= 60
            if profile.emitter:
                reach = min(reach, radar_horizon_km(profile.mast_m, altitude))
                burn = 1 - jam * (1 - profile.eccm)
                reach *= burn
                if ambush:
                    # Radars dark until the target is close.
                    reach *= 0.6
                elif not cued and profile.guidance is AirDefenseGuidance.RADAR:
                    # Own acquisition radar only: late detection, short shots.
                    reach *= 0.65
                if hiding:
                    reach *= 0.7
            else:
                # Optical systems need to see the target.
                reach = min(reach, 8.0 * env.visual_factor + 1)
            if altitude < 1200 and profile.emitter:
                reach *= 0.75  # Terrain masking and clutter.
            if avoiding:
                reach *= 0.6
            if rng_km > reach:
                continue
            key = id(airframe)
            if key in site.channels and site.channels[key] > now:
                # Shoot-look-shoot: missiles already on the way to this target.
                break
            if site.free_channels(now, profile) <= 0:
                continue

            # Detection and track.
            if profile.emitter:
                p_track = 0.9 if cued else 0.6
                p_track *= 1 - jam * (1 - profile.eccm) * 0.5
                if airframe.profile.rcs < 0.1:
                    p_track *= 0.35
                if hiding:
                    p_track *= 0.6
            else:
                p_track = 0.75 * env.visual_factor
            p_track *= 0.5 + 0.5 * crew_skill
            if avoiding:
                p_track *= 0.5
            if key not in site.first_track:
                if rng.random() > p_track:
                    continue
                site.first_track[key] = 0.0
                # The lock-up lights up the RWR/HTS of any ARM shooters nearby:
                # they get to shoot while the site works through its kill chain.
                if profile.emitter and _sead_response(
                    model, site, flight, now, events, rng
                ):
                    return shots_this_round
                if not launcher.guidance_ready():
                    continue
                reaction = profile.reaction_s * (1.0 if cued else 1.5)
                if unpowered:
                    reaction *= 1.5
                reaction /= 0.5 + 0.5 * crew_skill
                if reaction > ROUND_SECONDS:
                    # Acquired this round; still working through the kill chain.
                    site.first_track[key] = reaction - ROUND_SECONDS
                    continue
            elif site.first_track[key] > 0:
                site.first_track[key] = max(0.0, site.first_track[key] - ROUND_SECONDS)
                if site.first_track[key] > 0:
                    continue

            # SEAD reaction: ARMs come in as soon as the site radiates.
            if profile.emitter and _sead_response(
                model, site, flight, now, events, rng
            ):
                return shots_this_round
            if not launcher.guidance_ready():
                continue  # The radar was just destroyed by an ARM.

            salvo = min(profile.salvo, launcher.missiles)
            if profile.guidance is AirDefenseGuidance.GUN:
                salvo = 2
            launcher.missiles -= (
                1 if profile.guidance is AirDefenseGuidance.GUN else salvo
            )
            speed = 0.6 if profile.guidance is AirDefenseGuidance.IR else 1.1
            time_of_flight = (
                3.0 if profile.guidance is AirDefenseGuidance.GUN else rng_km / speed
            )
            # The channel is tied up guiding until impact, then the crew assesses.
            site.channels[key] = now + timedelta(seconds=time_of_flight + 8)
            site.shots += salvo
            shots_this_round += salvo
            if engagement is not None:
                engagement.shots_at_flight += salvo
                engagement.sites_engaged.add(site_key)
            # Firing gives the site away. Surprise only works once per target.
            first_shot = (surprise or ambush) and key not in site.surprised
            site.surprised.add(key)
            model.record_intel(flight.squadron.player, site.tgo, 0.6, "ENGAGEMENT")
            ballistic = (
                profile.emitter and hiding and rng.random() < 0.5 + 0.3 * arm_fear
            )
            unit = (
                "bursts" if profile.guidance is AirDefenseGuidance.GUN else "missiles"
            )
            model.log(
                now,
                CombatDomain.AIR_DEFENSE,
                side,
                f"{profile.system} at {site.tgo.name} engages {airframe.name} "
                f"({rng_km:.0f} km, {salvo} {unit}"
                + (", fired without guidance" if ballistic else "")
                + ")",
            )
            if _resolve_salvo(
                model,
                airframe,
                profile,
                salvo,
                rng_km,
                altitude,
                jam,
                rng,
                cued=cued,
                ballistic=ballistic,
                crew=crew_skill,
                readiness=defender.readiness,
                surprise=first_shot,
            ):
                model.shot_stats[f"sam:{profile.system}"][1] += 1
                model.shot_stats["sam"][1] += 1
                if model.kill_airframe(
                    airframe,
                    now,
                    events,
                    CombatDomain.AIR_DEFENSE,
                    f"{profile.system} from {site.tgo.name}",
                    (
                        LossCause.AAA
                        if profile.guidance is AirDefenseGuidance.GUN
                        else LossCause.SAM
                    ),
                ):
                    if engagement is not None:
                        engagement.losses += 1
            break  # One launcher per target per round.
    return shots_this_round


def _resolve_salvo(
    model: CombatModel,
    airframe: AirframeState,
    profile: AirDefenseProfile,
    salvo: int,
    rng_km: float,
    altitude: float,
    jam: float,
    rng: random.Random,
    cued: bool = True,
    ballistic: bool = False,
    crew: float = 1.0,
    readiness: float = 0.9,
    surprise: bool = False,
) -> bool:
    """Resolves a salvo with combat (not test-range) kill probability.

    p_kill = valid launch x reliability x not defeated x lethal hit.

    Historically, missiles fired at warned, manoeuvring, ECM-protected aircraft
    rarely hit: roughly 1% per SA-2 over Hanoi in 1972, ~0.3% per SAM over
    Serbia in 1999. Most of the gap from test Pk is missiles that never had a
    valid solution, failed, were decoyed or jammed, or were out-flown.
    """
    env = model.env
    stats_key = f"sam:{profile.system}"
    for _ in range(salvo):
        if not airframe.alive:
            return False
        model.shot_stats[stats_key][0] += 1
        model.shot_stats["sam"][0] += 1
        pk = profile.pk
        # Launch made properly, by a crew that knows its system, with working kit.
        pk *= readiness * (0.6 + 0.4 * crew) * profile.reliability
        # Long shots leave the missile slow and the target time to react.
        pk *= clamp(1.2 - 0.85 * rng_km / max(profile.range_km, 0.1), 0.3, 1.0)
        if not cued and profile.emitter:
            pk *= 0.8  # Poorer track from the site's own radar.
        if ballistic:
            pk *= 0.05  # Fired without guidance to avoid an ARM.
        if profile.emitter:
            ecm = airframe.profile.ecm + jam * 0.6
            pk *= 1 - clamp(ecm, 0.0, 0.9) * (1 - profile.eccm)
            if airframe.profile.towed_decoy:
                pk *= 0.6
        if profile.guidance is AirDefenseGuidance.IR:
            pk *= env.ir_seeker_factor
        if profile.guidance is AirDefenseGuidance.GUN:
            pk *= (0.6 + 0.4 * env.visual_factor) * clamp(
                1.4 - altitude / 2500, 0.2, 1.4
            )
        # Awareness and defense.
        if profile.guidance is AirDefenseGuidance.IR:
            aware = rng.random() < (
                0.85 if airframe.profile.maws else 0.3 * env.visual_factor
            )
        elif profile.guidance is AirDefenseGuidance.GUN:
            aware = rng.random() < 0.5
        else:
            aware = rng.random() < airframe.profile.rwr
        if surprise and aware and rng.random() < 0.4:
            aware = False  # Unexpected: the warning comes too late to react.
        if aware:
            radar = profile.emitter
            cm = (
                airframe.use_countermeasures(radar)
                if profile.guidance is not AirDefenseGuidance.GUN
                else True
            )
            # A warned, well-flown aircraft defeats most SAM shots: break turns
            # at the right moment, chaff/flares, notching, terrain.
            if profile.guidance is AirDefenseGuidance.GUN:
                evade = 0.4 * airframe.skill
            else:
                evade = 0.75 * airframe.skill * (0.4 + 0.6 * airframe.profile.agility)
            if not cm:
                evade *= 0.6
            pk *= 1 - clamp(evade, 0.0, 0.9)
        pk = clamp(pk * model.lethality, 0.001, 0.95)
        if rng.random() < pk:
            if rng.random() < 0.8 or airframe.damaged:
                return True
            airframe.damaged = True
    return False


def _sead_response(
    model: CombatModel,
    site: SamSiteState,
    flight: Flight,
    now: datetime,
    events: GameUpdateEvents,
    rng: random.Random,
) -> bool:
    """SEAD aircraft fire on the emitting site. Returns True if the site shut down
    its radar before it could shoot."""
    shooters = sead_shooters(model, flight, site)
    if not shooters:
        return False
    return fire_arms(model, site, shooters[:2], now, events, rng)


def fire_arms(
    model: CombatModel,
    site: SamSiteState,
    shooters: list[tuple[AirframeState, WeaponStore]],
    now: datetime,
    events: GameUpdateEvents,
    rng: random.Random,
) -> bool:
    """Fires anti-radiation missiles at a site. Returns True if the site went dark."""
    went_dark = False
    emcon = max(
        (l.profile.emcon for l in site.launchers if l.profile.emitter), default=0.4
    )
    for airframe, store in shooters:
        if store.remaining <= 0:
            continue
        store.remaining -= 1
        weapon = store.profile
        model.arm_launches[str(site.tgo.id)] = now
        model.record_intel(airframe.flight.squadron.player, site.tgo, 0.7, "ELINT")
        model.credit(airframe.flight, "arm_attack", site.tgo)
        side = model.side_name(airframe.flight.squadron.player)
        model.log(
            now,
            CombatDomain.AIR_DEFENSE,
            side,
            f"{airframe.name} fires {weapon.name} at {site.tgo.name}",
        )
        if not went_dark and rng.random() < emcon:
            went_dark = True
            site.dark_until = now + timedelta(seconds=rng.uniform(60, 180))
            model.log(
                now,
                CombatDomain.AIR_DEFENSE,
                model.tgo_side(site.tgo),
                f"{site.tgo.name} shuts down its radars to defeat the ARM",
            )
            continue
        if went_dark:
            continue
        radars = site.radar_units()
        if not radars:
            continue
        p_hit = weapon.accuracy * airframe.skill * model.lethality
        if rng.random() < clamp(p_hit, 0.05, 0.9):
            radar = rng.choice(radars)
            if model.results.kill_theater_unit(radar, events):
                model.log(
                    now,
                    CombatDomain.AIR_DEFENSE,
                    side,
                    f"{weapon.name} destroys {radar.unit_type or radar.type.id} at {site.tgo.name}",
                )
        else:
            model.log(
                now,
                CombatDomain.AIR_DEFENSE,
                side,
                f"{weapon.name} misses {site.tgo.name}",
            )
    return went_dark


SEAD_HUNTERS = ("SEAD", "SEAD_ESCORT", "SEAD_SWEEP", "DEAD")
HUNT_INTERVAL_SECONDS = 45.0


def sead_hunt(model: CombatModel, now: datetime, events: GameUpdateEvents) -> None:
    """SEAD flights hunt emitters on their own.

    Search and tracking radars radiate whether or not they are shooting at
    anybody; a SEAD flight with ARMs left fires at any it can reach. The site
    either shuts down (suppressed for a while) or loses its radar.
    """
    from game.theater.player import Player

    last_hunt = model.sead_hunts
    for player in (Player.BLUE, Player.RED):
        coalition = model.game.coalition_for(player)
        enemy_sites = None
        for package in coalition.ato.packages:
            for flight in package.flights:
                if flight.flight_type.name not in SEAD_HUNTERS:
                    continue
                if not flight.alive or not flight.state.in_flight:
                    continue
                previous = last_hunt.get(id(flight))
                if (
                    previous is not None
                    and (now - previous).total_seconds() < HUNT_INTERVAL_SECONDS
                ):
                    continue
                last_hunt[id(flight)] = now
                shooters = []
                for airframe in model.airframes(flight):
                    stores = [
                        st
                        for st in airframe.stores
                        if st.profile.role is WeaponRole.ARM and st.remaining > 0
                    ]
                    if stores:
                        shooters.append(
                            (airframe, max(stores, key=lambda st: st.profile.range_km))
                        )
                if not shooters:
                    continue
                if enemy_sites is None:
                    enemy_sites = [
                        tgo
                        for cp in model.game.theater.control_points_for(player.opponent)
                        for tgo in cp.ground_objects
                        if not tgo.is_dead and tgo.has_aa
                    ]
                position = flight.state.estimate_position()
                best = None
                for tgo in enemy_sites:
                    site = site_for(model, tgo)
                    if site.is_dark(now) or not site.emits or not site.radar_units():
                        continue
                    reach = shooters[0][
                        1
                    ].profile.range_km * model.target_altitude_factor(
                        shooters[0][0].altitude_m
                    )
                    distance = distance_km(position, tgo.position)
                    if not model.knows_site(player, tgo) and model.rng().random() > 0.5:
                        continue  # The emitter wasn't located this time.
                    if distance <= reach and (best is None or distance < best[0]):
                        best = (distance, site)
                if best is not None:
                    fire_arms(model, best[1], shooters[:2], now, events, model.rng())
