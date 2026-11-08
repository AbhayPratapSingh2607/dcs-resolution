"""Air-to-air engagements, resolved in phases over simulated time.

Each engagement runs in 10 second rounds:

1. **Detection.** Each side builds a picture of the other from onboard radar
   (range scales with target RCS^1/4, look-down capability matters against low
   targets), IRST, eyeballs, and the off-board picture (AWACS, EWR/GCI). The
   side that sees first shoots first, and a target that has not seen the
   shooter is far more likely to die.
2. **BVR.** Committed fighters pick targets by role (escorts protect their
   package, CAP goes for the strikers) and fire when the target is inside the
   range their skill and the geometry allow. Missiles fly for real time; SARH
   missiles need their shooter alive and supporting until impact.
3. **Defense.** Targets that are aware of the shot (RWR, MAWS, visual) defend:
   chaff, flares, notching, ECM, and their own skill and agility. Defending
   costs initiative: a defending airframe cannot press its own attack.
4. **Merge.** Once the range closes inside visual range the fight becomes a
   series of close-in duels decided by agility, skill, high off-boresight
   missiles, numbers and light conditions.
5. **Decisions.** After each round flights decide whether to keep fighting:
   CAP and escorts break off when out of missiles, after heavy losses or when
   badly outnumbered; strikers that are engaged without cover abort, jettison
   and go home (mission failed); support aircraft run.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from game.sim.combatlog import CombatDomain
from .airframe import AirframeState, GUN, WeaponStore, flight_role
from .engine import CombatModel, clamp, distance_km
from .profiles import Guidance, WeaponCombatProfile

if TYPE_CHECKING:
    from game.ato import Flight
    from game.sim.gameupdateevents import GameUpdateEvents

ROUND_SECONDS = 10.0
MAX_DURATION_SECONDS = 420.0
WVR_KM = 9.0

#: Average speed of a missile over its flight, km/s.
MISSILE_SPEED = {
    Guidance.ARH: 0.95,
    Guidance.SARH: 0.85,
    Guidance.IR: 0.7,
    Guidance.BEAM: 0.6,
    Guidance.GUN: 1.0,
}

#: How good a well-flown, aware target is at defeating each guidance type.
BASE_EVASION = {
    Guidance.ARH: 0.42,
    Guidance.SARH: 0.48,
    Guidance.IR: 0.4,
    Guidance.BEAM: 0.6,
    Guidance.GUN: 0.35,
}


@dataclass
class EngagedFlight:
    flight: Flight
    role: str
    side: str
    airframes: list[AirframeState]
    initial_count: int
    committed: bool = True
    disengaging_rounds: int = 0
    aborted: bool = False
    losses: int = 0

    @property
    def alive(self) -> list[AirframeState]:
        return [a for a in self.airframes if a.alive]

    @property
    def fighting(self) -> list[AirframeState]:
        if not self.committed or self.role != "fighter":
            return []
        return [a for a in self.airframes if a.can_fight_air]

    @property
    def present(self) -> bool:
        """Still in the fight area and targetable."""
        return bool(self.alive) and (self.committed or self.disengaging_rounds > 0)


@dataclass
class MissileInFlight:
    shooter: AirframeState
    target: AirframeState
    weapon: WeaponCombatProfile
    impact_at: float
    pk: float
    target_aware: bool
    launch_range_km: float
    #: Kinematic range of the shot when fired (geometry-adjusted).
    effective_range_km: float = 0.0


@dataclass
class AirEngagement:
    model: CombatModel
    start_time: datetime
    rng: random.Random
    flights: list[EngagedFlight] = field(default_factory=list)
    elapsed: float = 0.0
    range_km: float = 60.0
    merged: bool = False
    missiles: list[MissileInFlight] = field(default_factory=list)
    #: Airframes each side has a track on.
    known: dict[str, set[int]] = field(
        default_factory=lambda: {"blue": set(), "red": set()}
    )
    _since_round: float = 0.0
    _rounds_without_action: int = 0
    shots: int = 0

    @staticmethod
    def create(
        model: CombatModel, flights: list[Flight], time: datetime
    ) -> AirEngagement:
        engagement = AirEngagement(model, time, model.rng())
        for flight in flights:
            engagement.add_flight(flight)
        engagement.range_km = engagement._initial_range()
        return engagement

    # ------------------------------------------------------------------ setup

    def add_flight(self, flight: Flight) -> None:
        if any(e.flight is flight for e in self.flights):
            return
        airframes = self.model.airframes(flight)
        role = flight_role(flight)
        if role == "fighter" and not any(a.can_fight_air for a in airframes):
            # A fighter with nothing left to shoot behaves like anything else
            # caught in the fight: it tries to leave.
            role = "striker"
        side = self.model.side_name(flight.squadron.player)
        self.flights.append(
            EngagedFlight(
                flight,
                role,
                side,
                airframes,
                len(airframes),
                committed=role == "fighter",
            )
        )
        if role != "fighter":
            entry = self.flights[-1]
            entry.disengaging_rounds = 0
            entry.committed = True  # Present in the fight, but does not shoot.

    def _side(self, side: str) -> list[EngagedFlight]:
        return [f for f in self.flights if f.side == side]

    @staticmethod
    def _enemy(side: str) -> str:
        return "red" if side == "blue" else "blue"

    def _initial_range(self) -> float:
        blue = [a.position for f in self._side("blue") for a in f.alive]
        red = [a.position for f in self._side("red") for a in f.alive]
        if not blue or not red:
            return 60.0
        bx = sum(p.x for p in blue) / len(blue)
        by = sum(p.y for p in blue) / len(blue)
        rx = sum(p.x for p in red) / len(red)
        ry = sum(p.y for p in red) / len(red)
        separation = math.hypot(bx - rx, by - ry) / 1000
        return clamp(separation, 15.0, 120.0)

    # ------------------------------------------------------------------ helpers

    def _present_airframes(self, side: str) -> list[AirframeState]:
        return [a for f in self._side(side) if f.present for a in f.alive]

    def _entry_for(self, airframe: AirframeState) -> EngagedFlight:
        return next(f for f in self.flights if f.flight is airframe.flight)

    def _fighters(self, side: str) -> list[AirframeState]:
        return [a for f in self._side(side) for a in f.fighting]

    def _mean(self, values: list[float], default: float) -> float:
        return sum(values) / len(values) if values else default

    def _pair_range(self) -> float:
        return max(0.5, self.range_km * self.rng.uniform(0.8, 1.2))

    def _jamming_against(self, side: str) -> float:
        """Stand-off jamming support enjoyed by the *enemy* of ``side``."""
        jammers = 0
        for entry in self._side(self._enemy(side)):
            for airframe in entry.alive:
                if airframe.offensive_jammer:
                    jammers += 1
                for other in self.model.iter_package_airframes(entry.flight, 120):
                    if other.offensive_jammer:
                        jammers += 1
        return clamp(0.2 * jammers, 0.0, 0.45)

    # ------------------------------------------------------------------ detection

    def _detect(self, side: str, now: datetime) -> None:
        own = [a for f in self._side(side) for a in f.alive]
        if not own:
            return
        player = own[0].flight.squadron.player
        awareness = self.model.awareness(player, now)
        quality = self.model.quality(player)
        jam = self._jamming_against(side)
        env = self.model.env
        for target in self._present_airframes(self._enemy(side)):
            if id(target) in self.known[side]:
                continue
            target_alt = target.altitude_m
            rcs = target.effective_rcs
            p_detect = 0.0
            covered = awareness.covers(target.position, target_alt, rcs)
            if covered:
                p_detect = 0.85 * (1 - jam * 0.5)
            # Pilots trained to fly under ground control are lost without it.
            autonomy = 0.6 if quality.gci_dependent and not covered else 1.0
            for sensor in own:
                rng_km = self._pair_range()
                radar = sensor.profile.radar_detection_range_km(rcs) * (1 - jam)
                if (
                    target_alt < sensor.altitude_m - 1500
                    and not sensor.profile.look_down
                ):
                    radar *= 0.3
                if target.profile.helicopter:
                    radar *= 0.5
                if radar > 0 and rng_km <= radar:
                    p_detect = max(
                        p_detect,
                        (0.5 + 0.45 * (1 - rng_km / radar)) * sensor.skill * autonomy,
                    )
                if sensor.profile.irst and rng_km <= 35 * env.ir_seeker_factor:
                    p_detect = max(p_detect, 0.45)
                visual_km = 8.0 * env.visual_factor * (1.5 if rcs > 20 else 1.0)
                if rng_km <= visual_km:
                    p_detect = max(p_detect, 0.65 * env.visual_factor * sensor.skill)
            if self.rng.random() < p_detect:
                self.known[side].add(id(target))

    def _knows(self, side: str, airframe: AirframeState) -> bool:
        return id(airframe) in self.known[side]

    # ------------------------------------------------------------------ shooting

    def _choose_target(
        self, shooter: AirframeState, side: str
    ) -> Optional[AirframeState]:
        enemy_side = self._enemy(side)
        candidates = [
            a for a in self._present_airframes(enemy_side) if self._knows(side, a)
        ]
        if not candidates:
            return None
        in_flight: dict[int, int] = {}
        for missile in self.missiles:
            in_flight[id(missile.target)] = in_flight.get(id(missile.target), 0) + 1

        shooter_role = shooter.flight.flight_type
        own_package = shooter.flight.package
        threatening = {
            id(m.shooter)
            for m in self.missiles
            if m.target.flight.package is own_package
        }

        def priority(target: AirframeState) -> float:
            entry = self._entry_for(target)
            score = 0.0
            if shooter_role.is_escort_type and id(target) in threatening:
                score += 5.0
            if entry.role == "fighter":
                score += 2.0 if shooter_role.is_escort_type else 1.0
            elif entry.role == "striker":
                score += 3.0 if not shooter_role.is_escort_type else 0.5
            else:
                score += 3.5  # AWACS and tankers are prize targets.
            score -= 1.5 * in_flight.get(id(target), 0)
            if target.damaged:
                score -= 1.0
            return score + self.rng.random() * 0.5

        best = max(candidates, key=priority)
        if in_flight.get(id(best), 0) >= 2:
            return None
        return best

    def _aspect(self, target: AirframeState) -> tuple[str, float]:
        entry = self._entry_for(target)
        if not entry.committed or entry.disengaging_rounds > 0:
            weights = (0.15, 0.3, 0.55)
        elif entry.role == "fighter":
            weights = (0.6, 0.3, 0.1)
        else:
            weights = (0.35, 0.35, 0.3)
        roll = self.rng.random()
        if roll < weights[0]:
            return "hot", 1.0
        if roll < weights[0] + weights[1]:
            return "beam", 0.65
        return "cold", 0.38

    def _effective_range(
        self,
        store: WeaponStore,
        shooter: AirframeState,
        target: AirframeState,
        aspect_factor: float,
    ) -> float:
        weapon = store.profile
        altitude = self.model.target_altitude_factor(shooter.altitude_m)
        energy = 1 + 0.15 * clamp(
            (shooter.altitude_m - target.altitude_m) / 3000, -1, 1
        )
        rng_km = weapon.range_km * aspect_factor * altitude * energy
        if weapon.guidance is Guidance.IR:
            seeker = 10.0 if weapon.all_aspect else 4.0
            if not weapon.all_aspect and aspect_factor > 0.5:
                return 0.0  # Rear aspect only.
            rng_km = min(
                rng_km,
                max(seeker, weapon.range_km * 0.6) * self.model.env.ir_seeker_factor,
            )
        return rng_km

    def _can_lock(
        self,
        shooter: AirframeState,
        target: AirframeState,
        weapon: WeaponCombatProfile,
        pair_range: float,
    ) -> tuple[bool, float]:
        """Whether the shooter can guide this weapon, and a quality multiplier."""
        rcs = target.effective_rcs
        if weapon.guidance in (Guidance.SARH, Guidance.BEAM):
            radar = shooter.profile.radar_detection_range_km(rcs) * 0.85
            if (
                target.altitude_m < shooter.altitude_m - 1500
                and not shooter.profile.look_down
            ):
                radar *= 0.3
            return pair_range <= radar, 1.0
        if weapon.guidance is Guidance.ARH:
            radar = shooter.profile.radar_detection_range_km(rcs)
            if (
                target.altitude_m < shooter.altitude_m - 1500
                and not shooter.profile.look_down
            ):
                radar *= 0.3
            if pair_range <= radar:
                return True, 1.0
            # Datalink shot on an off-board track.
            if shooter.profile.datalink:
                return True, 0.8
            return False, 0.0
        if weapon.guidance in (Guidance.IR, Guidance.GUN):
            return True, 1.0
        return False, 0.0

    def _choose_weapon(
        self,
        shooter: AirframeState,
        target: AirframeState,
        pair_range: float,
        aspect_factor: float,
    ) -> Optional[tuple[WeaponStore, float, float]]:
        """Picks the weapon to fire now, or None to hold fire. Returns
        (store, effective range, guidance quality)."""
        # Disciplined pilots let the target come inside the no-escape zone;
        # nervous ones fire at the edge of the envelope.
        discipline = clamp((shooter.skill - 0.8) / 0.3, 0.0, 1.0)
        best: Optional[tuple[WeaponStore, float, float, float]] = None
        stores = list(shooter.a2a_stores())
        if shooter.has_gun and shooter.gun_rounds > 0:
            stores.append(WeaponStore(GUN, shooter.gun_rounds))
        for store in stores:
            weapon = store.profile
            eff = self._effective_range(store, shooter, target, aspect_factor)
            if eff <= 0 or pair_range > eff:
                continue
            ok, quality = self._can_lock(shooter, target, weapon, pair_range)
            if not ok:
                continue
            threshold = eff * (0.85 - 0.3 * discipline)
            nez = weapon.nez_km * aspect_factor**-0.5
            if pair_range > max(threshold, nez) and self.rng.random() > 0.25:
                continue
            rf = self._range_factor(weapon, pair_range, eff, aspect_factor)
            value = weapon.pk * rf * quality
            # Don't waste missiles on hopeless shots: the bar rises with discipline
            # and with how few missiles are left.
            remaining = sum(s.remaining for s in shooter.a2a_stores())
            minimum = 0.12 + 0.1 * discipline + (0.08 if remaining <= 2 else 0.0)
            if weapon is not GUN and value < minimum:
                continue
            if best is None or value > best[3]:
                best = (store, eff, quality, value)
        if best is None:
            return None
        return best[0], best[1], best[2]

    @staticmethod
    def _range_factor(
        weapon: WeaponCombatProfile, pair_range: float, eff: float, aspect_factor: float
    ) -> float:
        nez = weapon.nez_km * (aspect_factor**-0.5)
        if pair_range <= nez:
            return 1.0
        span = max(eff - nez, 0.1)
        return clamp(1.0 - 0.65 * (pair_range - nez) / span, 0.3, 1.0)

    def _fire(self, shooter: AirframeState, side: str) -> bool:
        target = self._choose_target(shooter, side)
        if target is None:
            return False
        pair_range = self._pair_range()
        aspect, aspect_factor = self._aspect(target)
        choice = self._choose_weapon(shooter, target, pair_range, aspect_factor)
        if choice is None:
            return False
        store, eff, quality = choice
        weapon = store.profile
        if weapon is GUN:
            shooter.gun_rounds -= 1
        else:
            for real in shooter.stores:
                if real.profile is weapon:
                    real.remaining -= 1
                    break

        pk = weapon.pk * self._range_factor(weapon, pair_range, eff, aspect_factor)
        pk *= quality * shooter.skill
        if weapon.radar_guided:
            pk *= 1 - target.profile.ecm * (
                0.6 if shooter.profile.generation >= 4.5 else 1.0
            )
        if weapon.guidance is Guidance.IR:
            pk *= self.model.env.ir_seeker_factor
        if weapon.guidance is Guidance.GUN:
            pk *= 0.5 + 0.5 * self.model.env.visual_factor
        pk *= self.model.lethality

        target_side = self._enemy(side)
        aware = self._target_aware(target, shooter, weapon, target_side)
        speed = MISSILE_SPEED.get(weapon.guidance, 0.8)
        tof = pair_range / speed
        self.missiles.append(
            MissileInFlight(
                shooter,
                target,
                weapon,
                self.elapsed + tof,
                clamp(pk, 0.01, 0.97),
                aware,
                pair_range,
                eff,
            )
        )
        if aware:
            target.go_defensive(self.elapsed, self.elapsed + tof)
        self.shots += 1
        self.model.log(
            self.start_time_plus(),
            CombatDomain.AIR,
            side,
            f"{shooter.name} fires {weapon.name} at {target.name} ({pair_range:.0f} km, {aspect})",
        )
        # Salvo doctrine (Soviet practice: a radar and an IR missile, or two of
        # the same, at each target to beat its countermeasures).
        if (
            weapon is not GUN
            and self.model.doctrine(shooter.flight.squadron.player).a2a_salvo >= 2
        ):
            second = next(
                (
                    s
                    for s in shooter.a2a_stores()
                    if s.profile is not weapon
                    and self._effective_range(s, shooter, target, aspect_factor)
                    >= pair_range
                ),
                None,
            ) or next((s for s in shooter.a2a_stores() if s.profile is weapon), None)
            if second is not None:
                second.remaining -= 1
                follow = second.profile
                follow_pk = (
                    pk if follow is weapon else pk * follow.pk / max(weapon.pk, 0.01)
                )
                self.missiles.append(
                    MissileInFlight(
                        shooter,
                        target,
                        follow,
                        self.elapsed + tof + 2,
                        clamp(follow_pk, 0.01, 0.97),
                        aware,
                        pair_range,
                        eff,
                    )
                )
                self.shots += 1
        return True

    def _target_aware(
        self,
        target: AirframeState,
        shooter: AirframeState,
        weapon: WeaponCombatProfile,
        target_side: str,
    ) -> bool:
        knows_shooter = self._knows(target_side, shooter)
        guidance = weapon.guidance
        if guidance in (Guidance.SARH, Guidance.BEAM):
            p = max(target.profile.rwr, 0.3 if knows_shooter else 0.0)
        elif guidance is Guidance.ARH:
            # Launched in track-while-scan: often only the pitbull warning.
            p = max(target.profile.rwr * 0.85, 0.5 if knows_shooter else 0.0)
        elif guidance is Guidance.IR:
            p = 0.85 if target.profile.maws else (0.45 if knows_shooter else 0.1)
            p *= (
                0.5 + 0.5 * self.model.env.visual_factor
                if not target.profile.maws
                else 1.0
            )
        else:
            p = 0.5 if knows_shooter else 0.15
        # Good pilots keep their head on a swivel and read the RWR.
        p *= clamp(0.55 + 0.45 * target.skill, 0.6, 1.05)
        return self.rng.random() < p

    # ------------------------------------------------------------------ impacts

    def _resolve_missiles(self, now: datetime, events: GameUpdateEvents) -> None:
        remaining = []
        for missile in self.missiles:
            if missile.impact_at > self.elapsed:
                remaining.append(missile)
                continue
            self._resolve_impact(missile, now, events)
        self.missiles = remaining

    def _resolve_impact(
        self, missile: MissileInFlight, now: datetime, events: GameUpdateEvents
    ) -> None:
        target = missile.target
        shooter = missile.shooter
        side = self.model.side_name(shooter.flight.squadron.player)
        if not target.alive:
            return
        pk = missile.pk
        weapon = missile.weapon
        if weapon.guidance in (Guidance.SARH, Guidance.BEAM):
            if not shooter.alive or shooter.is_defensive(missile.impact_at - 3):
                pk *= 0.1  # Shooter had to break lock.
        elif weapon.guidance is Guidance.ARH and not shooter.alive:
            pk *= 0.6 if missile.launch_range_km > 20 else 1.0

        if missile.target_aware and missile.effective_range_km > 0:
            # A warned target outside the no-escape zone turns cold and runs
            # the missile out of energy. Long shots against fighters rarely
            # worked in combat (AIM-54, R-27ER and AIM-120 max-range shots).
            fraction = missile.launch_range_km / missile.effective_range_km
            outrun = clamp((fraction - 0.4) * 1.5, 0.0, 0.85)
            outrun *= clamp(0.6 + 0.4 * target.profile.agility, 0.3, 1.1)
            pk *= 1 - outrun
        if missile.target_aware:
            radar = weapon.guidance in (Guidance.ARH, Guidance.SARH, Guidance.BEAM)
            countermeasures = (
                target.use_countermeasures(radar)
                if weapon.guidance is not Guidance.GUN
                else True
            )
            evade = BASE_EVASION.get(weapon.guidance, 0.4)
            evade *= target.skill * (0.55 + 0.45 * target.profile.agility)
            if not countermeasures:
                evade *= 0.55
            if weapon.hobs:
                evade *= 0.8
            # Several missiles at once overwhelm the defense.
            simultaneous = sum(
                1
                for m in self.missiles
                if m.target is target and abs(m.impact_at - missile.impact_at) < 6
            )
            evade *= 0.85 ** max(0, simultaneous - 1)
            pk *= 1 - clamp(evade, 0.0, 0.85)
        else:
            pk *= 0.97
        if target.damaged:
            pk = min(0.97, pk * 1.3)

        stats = self.model.shot_stats
        keys = (f"a2a:{weapon.name}", "a2a", f"a2a:{side}")
        for key in keys:
            stats[key][0] += 1
        if self.rng.random() < pk:
            for key in keys:
                stats[key][1] += 1
            if self.rng.random() < 0.8 or target.damaged:
                entry = self._entry_for(target)
                if self.model.kill_airframe(
                    target,
                    now,
                    events,
                    CombatDomain.AIR,
                    f"{weapon.name} from {shooter.name}",
                ):
                    entry.losses += 1
                    self.model.credit(shooter.flight, "air_kill")
            else:
                target.damaged = True
                self.model.log(
                    now,
                    CombatDomain.AIR,
                    side,
                    f"{weapon.name} from {shooter.name} damages {target.name}",
                )
        else:
            self.model.log(
                now,
                CombatDomain.AIR,
                side,
                f"{weapon.name} from {shooter.name} misses {target.name}"
                + (" (defeated)" if missile.target_aware else ""),
            )

    # ------------------------------------------------------------------ WVR

    def _dogfight(self, now: datetime, events: GameUpdateEvents) -> int:
        actions = 0
        env = self.model.env
        blue = [a for a in self._present_airframes("blue")]
        red = [a for a in self._present_airframes("red")]
        if not blue or not red:
            return 0
        ratio = {"blue": len(blue) / len(red), "red": len(red) / len(blue)}
        for side, own, enemy in (("blue", blue, red), ("red", red, blue)):
            for fighter in [a for f in self._side(side) for a in f.fighting]:
                if not fighter.alive or fighter.is_defensive(self.elapsed):
                    continue
                opponents = [e for e in enemy if e.alive]
                if not opponents:
                    break
                opponent = self.rng.choice(opponents)
                # Finding and tracking the bandit: eyeballs, helped by radar.
                sight = env.visual_factor
                if fighter.profile.radar_km > 0:
                    sight = max(sight, 0.65)
                if fighter.profile.irst:
                    sight = max(sight, 0.75)
                if self.rng.random() > 0.35 * (0.2 + 0.8 * sight):
                    continue
                score = self._bfm_score(fighter, ratio[side]) - self._bfm_score(
                    opponent, ratio[self._enemy(side)]
                )
                if self.rng.random() < 1 / (1 + math.exp(-1.6 * score)):
                    attacker, defender, att_side = fighter, opponent, side
                else:
                    opponent_entry = self._entry_for(opponent)
                    if opponent_entry.role != "fighter" or not opponent.can_fight_air:
                        continue  # Defender escaped but cannot shoot back.
                    attacker, defender, att_side = opponent, fighter, self._enemy(side)
                actions += 1
                self._wvr_shot(attacker, defender, att_side, now, events)
        return actions

    def _bfm_score(self, airframe: AirframeState, numbers: float) -> float:
        score = airframe.profile.agility * 1.5 + (airframe.skill - 1.0) * 4.0
        if airframe.profile.hmcs and any(s.profile.hobs for s in airframe.a2a_stores()):
            score += 0.5
        if not airframe.can_fight_air:
            score -= 1.0
        if self._entry_for(airframe).role != "fighter":
            score -= 0.8
        score += 0.4 * math.log(max(numbers, 0.1))
        if airframe.damaged:
            score -= 0.5
        return score

    def _wvr_shot(
        self,
        attacker: AirframeState,
        defender: AirframeState,
        side: str,
        now: datetime,
        events: GameUpdateEvents,
    ) -> None:
        ir = [s for s in attacker.a2a_stores() if s.profile.guidance is Guidance.IR]
        if ir:
            store = max(
                ir,
                key=lambda s: s.profile.pk
                + (0.2 if s.profile.hobs and attacker.profile.hmcs else 0),
            )
            store.remaining -= 1
            weapon = store.profile
            pk = weapon.pk * self.model.env.ir_seeker_factor
            if weapon.hobs and attacker.profile.hmcs:
                pk *= 1.1
        elif attacker.has_gun and attacker.gun_rounds > 0:
            attacker.gun_rounds -= 1
            weapon = GUN
            pk = GUN.pk * (0.5 + 0.5 * self.model.env.visual_factor)
        else:
            return
        pk *= attacker.skill * self.model.lethality
        aware = self.rng.random() < (0.6 + 0.3 * self.model.env.visual_factor)
        self.model.log(
            now,
            CombatDomain.AIR,
            side,
            f"{attacker.name} gets a shot on {defender.name} in the merge ({weapon.name})",
        )
        self.missiles.append(
            MissileInFlight(
                attacker,
                defender,
                weapon,
                self.elapsed,
                clamp(pk, 0.01, 0.95),
                aware,
                2.0,
            )
        )
        self._resolve_missiles(now, events)

    # ------------------------------------------------------------------ decisions

    def _decide(self, now: datetime) -> None:
        for entry in self.flights:
            if not entry.alive:
                continue
            if entry.disengaging_rounds > 0:
                entry.disengaging_rounds -= 1
                if entry.disengaging_rounds == 0:
                    entry.committed = False
                continue
            if not entry.committed:
                continue
            own_fighters = len(self._fighters(entry.side))
            enemy_fighters = len(self._fighters(self._enemy(entry.side)))
            threatened = any(
                m.target.flight is entry.flight for m in self.missiles
            ) or any(self._knows(self._enemy(entry.side), a) for a in entry.alive)

            if entry.role == "support":
                if threatened:
                    self._disengage(entry, now, "turns away from the threat")
                continue

            if entry.role == "striker":
                if not threatened or enemy_fighters == 0:
                    continue
                if own_fighters >= enemy_fighters and entry.losses == 0:
                    continue  # Escorts are handling it; press on.
                p_abort = 0.25 + 0.3 * entry.losses / max(entry.initial_count, 1)
                p_abort *= self.model.abort_factor(entry.flight)
                if own_fighters == 0:
                    p_abort += 0.2
                if self.rng.random() < p_abort:
                    entry.aborted = True
                    self.model.credit(entry.flight, "abort")
                    for airframe in entry.alive:
                        airframe.jettison_air_to_ground()
                    self._disengage(
                        entry, now, "jettisons stores and aborts the mission"
                    )
                continue

            # Fighters.
            alive = entry.alive
            if not any(a.can_fight_air for a in alive):
                entry.aborted = True
                self._disengage(entry, now, "is out of weapons and disengages")
                continue
            loss_fraction = entry.losses / max(entry.initial_count, 1)
            protecting = entry.flight.flight_type.is_escort_type and any(
                f.role == "striker" and f.alive and f.committed
                for f in self.flights
                if f.flight.package is entry.flight.package
            )
            if (
                not self.merged
                and not any(a.has_bvr_missiles for a in alive)
                and enemy_fighters > 0
                and not protecting
            ):
                # Outranged: keep pressing for the merge until it starts costing
                # aircraft, then run.
                under_fire = sum(
                    1 for m in self.missiles if m.target.flight is entry.flight
                )
                if (
                    entry.losses > 0 or under_fire >= len(alive) + 1
                ) and self.rng.random() < 0.5:
                    self._disengage(entry, now, "is outranged and breaks off")
                    continue
            outnumbered = enemy_fighters > max(own_fighters, 1) * 1.8
            if (loss_fraction >= 0.5 or outnumbered) and not protecting:
                p_break = (0.4 + loss_fraction * 0.4) * self.model.abort_factor(
                    entry.flight
                )
                if self.rng.random() < p_break:
                    self._disengage(entry, now, "is losing the fight and breaks off")
                    continue
            if self.elapsed > self._bingo_after(entry, now) and self.rng.random() < 0.2:
                self._disengage(entry, now, "is at bingo fuel and breaks off")

    def _bingo_after(self, entry: EngagedFlight, now: datetime) -> float:
        """Fighters far from home reach bingo sooner; a tanker in reach keeps
        them in the fight longer (see fuel.py). Checked each time, so losing
        the tanker shortens the fight."""
        from .fuel import bingo_after_s

        return bingo_after_s(self.model, entry.flight, now)

    def _disengage(self, entry: EngagedFlight, now: datetime, reason: str) -> None:
        # Running away takes time; pursuers get shots at a cold target meanwhile.
        entry.disengaging_rounds = 2 if entry.role == "fighter" else 3
        self.model.log(now, CombatDomain.AIR, entry.side, f"{entry.flight} {reason}")

    # ------------------------------------------------------------------ main loop

    def start_time_plus(self) -> datetime:
        from datetime import timedelta

        return self.start_time + timedelta(seconds=self.elapsed)

    def step(self, seconds: float, events: GameUpdateEvents) -> bool:
        """Advances the engagement. Returns True when it is over."""
        self.elapsed += seconds
        self._since_round += seconds
        while self._since_round >= ROUND_SECONDS:
            self._since_round -= ROUND_SECONDS
            if self._round(events):
                return True
        return False

    def _round(self, events: GameUpdateEvents) -> bool:
        now = self.start_time_plus()
        for side in ("blue", "red"):
            self._detect(side, now)

        actions = 0
        if self.merged:
            actions += self._dogfight(now, events)
        else:
            order = [a for f in self.flights for a in f.fighting]
            self.rng.shuffle(order)
            for shooter in order:
                if not shooter.alive or shooter.is_defensive(self.elapsed):
                    continue
                side = self.model.side_name(shooter.flight.squadron.player)
                if self._fire(shooter, side):
                    actions += 1
        self._resolve_missiles(now, events)
        self._decide(now)
        self._close_range()

        if actions or self.missiles:
            self._rounds_without_action = 0
        else:
            self._rounds_without_action += 1

        blue_fighters = self._fighters("blue")
        red_fighters = self._fighters("red")
        blue_present = self._present_airframes("blue")
        red_present = self._present_airframes("red")
        if not self.missiles:
            if not blue_present or not red_present:
                return True
            if not blue_fighters and not red_fighters:
                return True
            if self._rounds_without_action >= 4 and (self.merged or self.range_km < 5):
                return True
            if self._rounds_without_action >= 9:
                return True
        return self.elapsed >= MAX_DURATION_SECONDS

    def _close_range(self) -> None:
        blue = self._fighters("blue")
        red = self._fighters("red")
        speeds = [a.speed_kmh for a in blue + red] or [800.0]
        speed_kms = self._mean(speeds, 800.0) / 3600
        if blue and red:
            closure = speed_kms * 2 * 0.65
        elif blue or red:
            closure = speed_kms * 0.5  # Chasing strikers or support.
        else:
            closure = -speed_kms
        self.range_km = max(1.0, self.range_km - closure * ROUND_SECONDS)
        if self.range_km <= WVR_KM and (blue or red):
            if not self.merged:
                self.merged = True
                self.model.log(
                    self.start_time_plus(),
                    CombatDomain.AIR,
                    "",
                    "The fight closes to visual range",
                )

    # ------------------------------------------------------------------ summary

    def summary(self) -> str:
        parts = []
        for side in ("blue", "red"):
            losses = sum(e.losses for e in self._side(side))
            lost = [e for e in self._side(side) if e.losses]
            text = (
                ", ".join(f"{e.losses}x {e.flight.unit_type}" for e in lost)
                or "no losses"
            )
            parts.append(f"{side} {text}" if losses else f"{side} no losses")
        return (
            f"Air engagement over after {self.elapsed:.0f}s, {self.shots} shots: "
            + "; ".join(parts)
        )

    def aborted_flights(self) -> list[Flight]:
        return [e.flight for e in self.flights if e.aborted and e.alive]
