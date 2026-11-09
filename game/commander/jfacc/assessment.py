"""Campaign assessment: measures of effectiveness (MOEs) from what a side knows.

Everything here is judged through the side's own intelligence picture, the
way a JFACC strategy cell would assess the campaign. Enemy force counts are
ISR estimates, enemy sites only count when known, and BDA is what the side
believes it destroyed, not ground truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterator, Optional, TYPE_CHECKING

from game.theater.player import Player

if TYPE_CHECKING:
    from game import Game
    from game.squadrons import Squadron
    from game.theater import ControlPoint, FrontLine
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.warfare.intel import IntelPicture


@dataclass
class FrontAssessment:
    front: FrontLine
    friendly_cp: ControlPoint
    enemy_cp: ControlPoint
    friendly_units: float
    enemy_units: float
    troops_in_contact: bool
    enemy_offensive_warning: bool
    base_threatened: bool

    @property
    def force_ratio(self) -> float:
        if self.enemy_units <= 0:
            return math.inf
        return self.friendly_units / self.enemy_units


@dataclass
class CampaignAssessment:
    turn: int
    #: Share of the enemy IADS command, comms and power nodes believed down.
    c2_degraded: float
    #: Quality-weighted own fighters against the estimated enemy fighters.
    air_superiority: float
    own_fighters: float
    enemy_fighters: float
    #: Known enemy MERAD/LORAD sites believed alive in the battle area.
    battle_area_sams: int
    #: Enemy deployable front-line strength (estimate).
    enemy_ground_strength: float
    fronts: list[FrontAssessment] = field(default_factory=list)
    #: True once the shooting has started.
    war_started: bool = True
    #: Control points (bases, FOBs, carriers) the side holds.
    own_bases: int = 0

    @property
    def main_effort(self) -> Optional[FrontAssessment]:
        """The front where the side's main effort lies: the most threatened
        front when defending, the most favourable one when attacking."""
        if not self.fronts:
            return None
        threatened = [f for f in self.fronts if f.enemy_offensive_warning]
        if threatened:
            return min(threatened, key=lambda f: f.force_ratio)
        weakest = min(self.fronts, key=lambda f: f.force_ratio)
        if weakest.force_ratio < 0.8:
            return weakest
        return max(self.fronts, key=lambda f: min(f.force_ratio, 100.0))

    @property
    def min_force_ratio(self) -> float:
        if not self.fronts:
            return math.inf
        return min(f.force_ratio for f in self.fronts)

    @property
    def main_effort_force_ratio(self) -> float:
        effort = self.main_effort
        return math.inf if effort is None else effort.force_ratio

    @property
    def any_offensive_warning(self) -> bool:
        return any(f.enemy_offensive_warning for f in self.fronts)

    @property
    def any_base_threatened(self) -> bool:
        return any(f.base_threatened for f in self.fronts)

    def as_dict(self) -> dict[str, float]:
        return {
            "c2_degraded": self.c2_degraded,
            "air_superiority": min(self.air_superiority, 99.0),
            "own_fighters": self.own_fighters,
            "enemy_fighters": self.enemy_fighters,
            "battle_area_sams": float(self.battle_area_sams),
            "enemy_ground_strength": self.enemy_ground_strength,
            "min_force_ratio": min(self.min_force_ratio, 99.0),
            "main_effort_force_ratio": min(self.main_effort_force_ratio, 99.0),
            "own_bases": float(self.own_bases),
        }


def _picture(game: Game, player: Player) -> Optional[IntelPicture]:
    war_state = getattr(game, "war_state", None)
    if war_state is None or not war_state.intel_enabled(game):
        return None
    return war_state.picture(game, player)


def enemy_tgos(game: Game, player: Player) -> Iterator[TheaterGroundObject]:
    for cp in game.theater.controlpoints:
        if cp.captured is player or cp.captured.is_neutral:
            continue
        yield from cp.ground_objects


def known(game: Game, player: Player, tgo: TheaterGroundObject) -> bool:
    picture = _picture(game, player)
    if picture is None:
        return True
    return picture.knows(tgo)


def believed_alive(game: Game, player: Player, tgo: TheaterGroundObject) -> bool:
    picture = _picture(game, player)
    if picture is None:
        return not tgo.is_dead
    return picture.believed_alive(tgo)


def believed_destroyed_fraction(
    game: Game, player: Player, tgo: TheaterGroundObject
) -> tuple[float, float]:
    """Share of the target's units the side believes destroyed, and how
    confident it is in that assessment."""
    units = list(tgo.units)
    if not units:
        return 0.0, 1.0
    picture = _picture(game, player)
    if picture is None:
        dead = sum(1 for u in units if not u.alive)
        return dead / len(units), 1.0
    contact = picture.contact(tgo)
    if contact is None:
        return 0.0, 0.0
    believed = sum(1 for u in units if u.id in contact.believed_dead)
    return believed / len(units), contact.confidence


def fighter_strength(squadrons: Iterator[Squadron], quality: float) -> float:
    from game.sim.combat.model.profiles import CombatProfiles

    total = 0.0
    profiles = CombatProfiles.instance()
    for squadron in squadrons:
        if squadron.owned_aircraft <= 0:
            continue
        profile = profiles.aircraft(squadron.aircraft)
        if not profile.fighter:
            continue
        # Fourth generation = 1.0; each generation step is worth ~40%.
        generation = max(0.4, 1.0 + 0.4 * (profile.generation - 4.0))
        total += squadron.owned_aircraft * generation * quality
    return total


def _aircrew_quality(game: Game, player: Player) -> float:
    from game.sim.combat.model.forcequality import for_faction

    try:
        return for_faction(game.coalition_for(player).faction.name).aircrew
    except Exception:
        return 1.0


def assess(game: Game, player: Player) -> CampaignAssessment:
    from game.data.groups import GroupTask
    from game.theater.iadsnetwork.iadsrole import IadsRole
    from game.theater.theatergroundobject import SamGroundObject
    from game.warfare.intel import estimate_count

    coalition = game.coalition_for(player)
    enemy = coalition.opponent
    picture = _picture(game, player)
    war_state = getattr(game, "war_state", None)

    # --- C2: enemy IADS command, comms and power nodes.
    c2_total = 0
    c2_down = 0
    c2_roles = (
        IadsRole.COMMAND_CENTER,
        IadsRole.CONNECTION_NODE,
        IadsRole.POWER_SOURCE,
    )
    for tgo in enemy_tgos(game, player):
        if not any(
            getattr(g, "iads_role", None) in c2_roles for g in tgo.groups
        ):
            continue
        if not known(game, player, tgo):
            continue
        c2_total += 1
        if not believed_alive(game, player, tgo):
            c2_down += 1
    c2_degraded = 1.0 if c2_total == 0 else c2_down / c2_total

    # --- Air superiority.
    own = fighter_strength(
        coalition.air_wing.iter_squadrons(), _aircrew_quality(game, player)
    )
    enemy_true = fighter_strength(
        enemy.air_wing.iter_squadrons(), _aircrew_quality(game, player.opponent)
    )
    if picture is not None and war_state is not None and enemy_true > 0:
        rng = war_state.rng(game, f"jfacc:fighters:{player}")
        enemy_est = float(estimate_count(round(enemy_true), picture.isr, rng))
    else:
        enemy_est = enemy_true
    air_superiority = math.inf if enemy_est <= 0 else own / enemy_est

    # --- Battle-area SAMs: known MERAD/LORAD within reach of friendly bases.
    friendly_cps = [
        cp for cp in game.theater.controlpoints if cp.captured is player
    ]
    battle_area_sams = 0
    for tgo in enemy_tgos(game, player):
        if not isinstance(tgo, SamGroundObject):
            continue
        if tgo.task not in (GroupTask.LORAD, GroupTask.MERAD):
            continue
        if not known(game, player, tgo) or not believed_alive(game, player, tgo):
            continue
        if not tgo.has_live_radar_sam:
            # Believed alive but its radars are down: suppressed.
            continue
        if any(
            cp.position.distance_to_point(tgo.position) < 150 * 1852
            for cp in friendly_cps
        ):
            battle_area_sams += 1

    # --- Fronts.
    fronts: list[FrontAssessment] = []
    enemy_ground = 0.0
    for front in game.theater.conflicts():
        if front.blue_cp.captured is player:
            friendly_cp, enemy_cp = front.blue_cp, front.red_cp
        else:
            friendly_cp, enemy_cp = front.red_cp, front.blue_cp
        friendly_units = float(friendly_cp.deployable_front_line_units)
        enemy_units = float(enemy_cp.deployable_front_line_units)
        if picture is not None and war_state is not None and enemy_units > 0:
            rng = war_state.rng(game, f"jfacc:front:{player}:{enemy_cp.id}")
            enemy_units = float(estimate_count(int(enemy_units), picture.isr, rng))
        enemy_ground += enemy_units
        warning = False
        if war_state is not None and war_state.intel_enabled(game):
            try:
                from game.warfare.agencies import expects_offensive

                warning = expects_offensive(
                    game, war_state, player, enemy_cp, friendly_cp
                )
            except Exception:
                warning = False
        fronts.append(
            FrontAssessment(
                front=front,
                friendly_cp=friendly_cp,
                enemy_cp=enemy_cp,
                friendly_units=friendly_units,
                enemy_units=enemy_units,
                troops_in_contact=friendly_units > 0 and enemy_units > 0,
                enemy_offensive_warning=warning,
                base_threatened=friendly_units < 0.5 * enemy_units
                and enemy_units > 0,
            )
        )

    return CampaignAssessment(
        turn=game.turn,
        c2_degraded=c2_degraded,
        air_superiority=air_superiority,
        own_fighters=own,
        enemy_fighters=enemy_est,
        battle_area_sams=battle_area_sams,
        enemy_ground_strength=enemy_ground,
        fronts=fronts,
        war_started=game.turn >= 1,
        own_bases=len(friendly_cps),
    )
