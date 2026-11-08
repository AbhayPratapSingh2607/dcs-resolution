"""Front-line ground combat while fast forwarding.

Each front line fights a round every few simulated minutes, using the combat
groups the ground planner deployed for this turn. Losses follow a modified
Lanchester square law: each side's killing power grows with how many weapons
it brings and what they are good against (anti-armor vs. soft targets), and
is spread across the enemy weighted by exposure and protection.

On top of that:

* **Stance** decides who is attacking. Attackers are exposed in the open;
  defenders in prepared positions take far fewer losses per shot fired (the
  classic 3:1 rule falls out of this). Ambushes hit hard in the first round.
  Retreating forces barely shoot back and lose ground.
* **Artillery** fires from behind the line against everything, and only
  counter-battery fire touches it.
* **Air support** comes from the attack model: CAS kills land on the same
  combat groups, so a front with air superiority grinds the enemy down.
* **Night and weather** blunt direct fire unless the unit has thermal sights.
* **Breakpoint.** Units stop fighting long before they are wiped out: an
  attack culminates after losing about a quarter of its strength, a defense
  breaks after about a third (historically 20-40% for both). A broken defense
  withdraws under pressure and a culminated attack digs in, so contact drops
  off sharply instead of fighting to the last vehicle.

Losses are recorded as front-line casualties, so the existing turn-end logic
moves the front line according to who won.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from game.ground_forces.combat_stance import CombatStance
from game.sim.combatlog import CombatDomain
from .engine import CombatModel, poisson

if TYPE_CHECKING:
    from game.ground_forces.ai_ground_planner import CombatGroup
    from game.theater import ControlPoint
    from game.theater.frontline import FrontLine

#: Expected kills per unit of effective firepower per 10 minutes of fighting.
#: Calibrated so a turn of even fighting costs an attacker 15-25% and a
#: defender about half that (resources/tools/combat_calibration.py).
LETHALITY = 0.045

#: Stances that fight from prepared positions.
DUG_IN = {CombatStance.DEFENSIVE, CombatStance.AMBUSH}
#: Anti-armor bonus for ATGM teams fighting from prepared positions.
ATGM_DEFENSE = 1.5

#: Fighting intensity while a broken defense withdraws under pursuit.
PURSUIT = 0.35
#: Fighting intensity once both sides are spent.
SPENT = 0.15

ATTACKING = {
    CombatStance.AGGRESSIVE,
    CombatStance.BREAKTHROUGH,
    CombatStance.ELIMINATION,
}

#: Fire intensity by stance.
STANCE_FIRE = {
    CombatStance.AGGRESSIVE: 1.0,
    CombatStance.BREAKTHROUGH: 1.25,
    CombatStance.ELIMINATION: 1.15,
    CombatStance.DEFENSIVE: 0.8,
    CombatStance.AMBUSH: 0.9,
    CombatStance.RETREAT: 0.25,
}

#: How exposed a side is to incoming fire, by its own stance.
STANCE_EXPOSURE = {
    CombatStance.AGGRESSIVE: 1.0,
    CombatStance.BREAKTHROUGH: 1.15,
    CombatStance.ELIMINATION: 0.95,
    CombatStance.DEFENSIVE: 0.5,
    CombatStance.AMBUSH: 0.45,
    CombatStance.RETREAT: 0.7,
}


@dataclass
class SideState:
    control_point: ControlPoint
    stance: CombatStance
    groups: list[CombatGroup]
    initial_strength: int
    losses: int = 0
    broken: bool = False
    rounds: int = 0

    @property
    def strength(self) -> int:
        return sum(g.size for g in self.groups)

    @property
    def attacking(self) -> bool:
        return self.stance in ATTACKING and not self.broken

    #: Front morale (game.warfare) and doctrine's defense-in-depth bonus.
    morale: float = 0.75
    depth: float = 0.0

    @property
    def breakpoint(self) -> float:
        base = 0.25 if self.attacking else 0.35 + self.depth
        # Confident troops hold on longer; demoralised ones break early.
        return base * (0.55 + 0.6 * self.morale)


@dataclass
class FrontState:
    front_line: FrontLine
    blue: SideState
    red: SideState
    rng: random.Random


@dataclass
class GroundWar:
    model: CombatModel
    interval: timedelta
    fronts: dict[int, FrontState] = field(default_factory=dict)
    last_round: Optional[datetime] = None

    def on_game_tick(self, time: datetime) -> None:
        if self.last_round is None:
            self.last_round = time
            return
        if time - self.last_round < self.interval:
            return
        dt = time - self.last_round
        self.last_round = time
        for front_line in self.model.game.theater.conflicts():
            front = self._front(front_line)
            if front is not None:
                self._round(front, time, dt.total_seconds() / 600)

    def _front(self, front_line: FrontLine) -> Optional[FrontState]:
        key = id(front_line)
        if key in self.fronts:
            return self.fronts[key]
        planners = self.model.game.ground_planners
        blue_cp = front_line.blue_cp
        red_cp = front_line.red_cp
        blue_planner = planners.get(blue_cp.id)
        red_planner = planners.get(red_cp.id)
        if blue_planner is None or red_planner is None:
            return None
        blue_groups = blue_planner.units_per_cp.get(red_cp.id, [])
        red_groups = red_planner.units_per_cp.get(blue_cp.id, [])
        blue_stance = blue_cp.stances.get(red_cp.id, CombatStance.DEFENSIVE)
        red_stance = red_cp.stances.get(blue_cp.id, CombatStance.DEFENSIVE)
        front = FrontState(
            front_line,
            self._side(blue_cp, blue_stance, blue_groups),
            self._side(red_cp, red_stance, red_groups),
            self.model.rng(),
        )
        self.fronts[key] = front
        return front

    def _side(
        self,
        control_point: ControlPoint,
        stance: CombatStance,
        groups: list[CombatGroup],
    ) -> SideState:
        deployed = sum(g.size for g in groups)
        doctrine = self.model.doctrine(control_point.captured)
        # Defense in depth needs something behind the line.
        reserves = control_point.base.total_armor - deployed
        depth = doctrine.depth if reserves >= deployed * 0.5 else 0.0
        return SideState(
            control_point,
            stance,
            groups,
            deployed,
            morale=self.model.front_morale(control_point),
            depth=depth,
        )

    @staticmethod
    def _arms(groups: list[CombatGroup]) -> dict[str, int]:
        """Vehicles per arm: armor, infantry (IFV/APC/infantry), artillery,
        air defense, anti-tank."""
        from game.ground_forces.ai_ground_planner import CombatGroupRole as Role

        mapping = {
            Role.TANK: "armor",
            Role.IFV: "infantry",
            Role.APC: "infantry",
            Role.INFANTRY: "infantry",
            Role.RECON: "infantry",
            Role.ARTILLERY: "artillery",
            Role.SHORAD: "air_defense",
            Role.ATGM: "anti_tank",
        }
        counts: dict[str, int] = {}
        for group in groups:
            arm = mapping.get(group.role)
            if arm is not None and group.size > 0:
                counts[arm] = counts.get(arm, 0) + group.size
        return counts

    def _tactics(
        self, side: SideState, enemy: SideState, first_round: bool
    ) -> tuple[float, float]:
        """(direct, indirect) multipliers from doctrine and force composition."""
        doctrine = self.model.doctrine(side.control_point.captured)
        arms = self._arms(side.groups)
        enemy_arms = self._arms(enemy.groups)
        total = max(sum(arms.values()), 1)
        direct = 1.0
        indirect = 1.0
        # Combined arms: each arm that is meaningfully present covers the others'
        # weaknesses (infantry screens tanks from ATGMs, air defense keeps
        # helicopters off, artillery suppresses).
        present = [a for a, n in arms.items() if n / total >= 0.1]
        direct *= 1 + 0.08 * max(len(present) - 1, 0) * doctrine.combined_arms
        enemy_total = max(sum(enemy_arms.values()), 1)
        enemy_infantry = (
            enemy_arms.get("infantry", 0) + enemy_arms.get("anti_tank", 0)
        ) / enemy_total
        if present == ["armor"] and enemy_infantry > 0.2:
            direct *= 0.85  # Unsupported tanks against infantry and ATGMs.
        # Artillery preparation before the assault.
        if first_round and side.attacking and arms.get("artillery"):
            indirect *= doctrine.artillery_prep
        # Manoeuvre: with superior numbers and mobility the attacker flanks.
        mobile = (arms.get("armor", 0) + arms.get("infantry", 0)) / total
        if (
            side.attacking
            and side.strength > 2 * max(enemy.strength, 1)
            and mobile > 0.5
        ):
            direct *= doctrine.maneuver
        return direct, indirect

    # ------------------------------------------------------------------

    def _firepower(
        self, side: SideState, enemy: SideState, first_round: bool
    ) -> tuple[float, float]:
        """(direct, indirect) firepower of ``side`` against ``enemy``'s mix."""
        env = self.model.env
        enemy_units = [
            (g, self.model.profiles.ground_unit(g.unit_type))
            for g in enemy.groups
            if g.size > 0
        ]
        total_enemy = sum(g.size for g, _ in enemy_units) or 1
        armor_fraction = sum(g.size for g, p in enemy_units if p.armored) / total_enemy

        from game.ground_forces.ai_ground_planner import CombatGroupRole as Role

        direct = 0.0
        indirect = 0.0
        for group in side.groups:
            if group.size <= 0:
                continue
            profile = self.model.profiles.ground_unit(group.unit_type)
            anti_armor = profile.anti_armor
            if group.role is Role.ATGM and side.stance in DUG_IN:
                # Missiles from prepared positions, at long range, into armor
                # crossing open ground: the defender's main tank killer.
                anti_armor *= ATGM_DEFENSE
            power = anti_armor * armor_fraction + profile.anti_soft * (
                1 - armor_fraction
            )
            if profile.indirect:
                indirect += (
                    group.size * power * (0.85 if not env.precipitation else 0.7)
                )
            else:
                direct += group.size * power * env.ground_fire_factor(profile.thermal)
        fire = STANCE_FIRE[side.stance] * (0.7 + 0.4 * side.morale)
        if side.broken:
            fire *= 0.35
        if first_round and side.stance is CombatStance.AMBUSH:
            fire *= 1.8
        # Fighting far from home: under-strength reserves mean poorer support.
        reserves = side.control_point.base.total_armor
        supply = 1.0 if reserves >= side.initial_strength * 0.5 else 0.85
        direct_tactics, indirect_tactics = self._tactics(side, enemy, first_round)
        return (
            direct * fire * supply * direct_tactics,
            indirect * fire * supply * indirect_tactics,
        )

    def _round(self, front: FrontState, time: datetime, tempo: float) -> None:
        blue, red = front.blue, front.red
        if blue.strength == 0 or red.strength == 0:
            return
        intensity = 1.0
        if blue.broken and red.broken:
            intensity = SPENT
        elif any(
            (side.broken or side.stance is CombatStance.RETREAT) and enemy.attacking
            for side, enemy in ((blue, red), (red, blue))
        ):
            # One side is falling back (broken, or a deliberate withdrawal);
            # the other follows up, but contact is patchy.
            intensity = PURSUIT
        elif not blue.attacking and not red.attacking:
            # Nobody is attacking: patrols, raids and artillery duels only.
            intensity = 0.3
        first = blue.rounds == 0
        blue_fire = self._firepower(blue, red, first)
        red_fire = self._firepower(red, blue, first)

        red_losses = self._inflict(front, blue, red, blue_fire, intensity * tempo)
        blue_losses = self._inflict(front, red, blue, red_fire, intensity * tempo)
        blue.rounds += 1
        red.rounds += 1

        if blue_losses or red_losses:
            self.model.log(
                time,
                CombatDomain.GROUND,
                "",
                f"{front.front_line.name}: blue ({blue.stance.name.lower()}) loses {blue_losses}, "
                f"red ({red.stance.name.lower()}) loses {red_losses}",
            )
        for side, name in ((blue, "blue"), (red, "red")):
            if side.broken or side.initial_strength == 0:
                continue
            if side.losses / side.initial_strength >= side.breakpoint:
                side.broken = True
                verb = (
                    "attack culminates" if side.stance in ATTACKING else "line breaks"
                )
                self.model.log(
                    time,
                    CombatDomain.GROUND,
                    name,
                    f"{front.front_line.name}: the {name} {verb} after losing "
                    f"{side.losses} of {side.initial_strength} vehicles",
                )

    def _inflict(
        self,
        front: FrontState,
        shooter: SideState,
        target: SideState,
        fire: tuple[float, float],
        scale: float,
    ) -> int:
        direct, indirect = fire
        exposure = STANCE_EXPOSURE[target.stance]
        if target.broken:
            if target.stance in ATTACKING:
                # A culminated attack falls back onto the defensive.
                exposure = STANCE_EXPOSURE[CombatStance.DEFENSIVE] * 1.2
            elif shooter.attacking:
                exposure *= 1.1  # Withdrawing under fire, out of its positions.
        weights = []
        groups = [g for g in target.groups if g.size > 0]
        if not groups:
            return 0
        protection_weighted = 0.0
        for group in groups:
            profile = self.model.profiles.ground_unit(group.unit_type)
            vulnerability = 1 / max(profile.protection, 0.1)
            if profile.indirect:
                vulnerability *= 0.15  # Out of direct fire range.
            protection_weighted += group.size * min(vulnerability, 4.0)
            weights.append(group.size * min(vulnerability, 4.0))
        mean_vulnerability = protection_weighted / sum(g.size for g in groups)

        expected = LETHALITY * scale * exposure * self.model.lethality
        expected *= (direct + indirect * 0.6) * min(mean_vulnerability, 3.0) / 1.5
        kills = min(poisson(front.rng, expected), target.strength)
        dealt = 0
        for _ in range(kills):
            alive = [(g, w) for g, w in zip(groups, weights) if g.size > 0]
            if not alive:
                break
            group = front.rng.choices(
                [g for g, _ in alive], weights=[w for _, w in alive], k=1
            )[0]
            dealt += self.model.results.kill_front_line_unit(
                group, target.control_point
            )
        target.losses += dealt
        return dealt

    def summary(self) -> list[str]:
        lines = []
        for front in self.fronts.values():
            lines.append(
                f"{front.front_line.name}: blue lost {front.blue.losses}/{front.blue.initial_strength}, "
                f"red lost {front.red.losses}/{front.red.initial_strength}"
            )
        return lines
