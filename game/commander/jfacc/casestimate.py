"""Expected front-line kills of a CAS flight, from its actual loadout.

CAS is sized to a desired effect on the enemy in contact. How many aircraft
that takes depends a great deal on the aircraft and what it carries: an
A-10C with Mavericks and cluster bombs kills several vehicles per sortie, an
F-16 with two GBU-12s far fewer, and a helicopter with ATGMs somewhere in
between. This mirrors the fast-forward attack model (game.sim.combat.model.
attack): every round is a delivery with the weapon's accuracy, a guidance
factor for moving vehicles, and the kill matrix for the warhead against the
front's mix of armor and soft vehicles; cluster and unguided weapons also
hit neighbours. Each aircraft makes FRONT_LINE_PASSES deliveries at most,
the most effective weapons first. Weather, defenses and crew skill are left out: it is a
planning figure, not a simulation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight
    from game.theater.frontline import FrontLine
    from game.theater.player import Player

#: Share of the ideal deliveries that turn into kills once flak, weather,
#: crew skill and overkill on vehicles already destroyed are counted. Fitted
#: to the combat model: A-10C two-ships (Maverick, CBU) estimated at ~17
#: kills, measured 9-14 per vul window.
DELIVERY_FACTOR = 0.7
#: Kills assumed for a flight whose loadout can't be read.
FALLBACK_KILLS_PER_AIRCRAFT = 2.0
#: Share of a front assumed armored when the enemy formation is unknown.
DEFAULT_ARMOR_SHARE = 0.5


def front_armor_share(game: Game, front: FrontLine, player: Player) -> float:
    """Share of the enemy vehicles at this front that are armored."""
    from game.sim.combat.model.profiles import CombatProfiles

    own_cp, enemy_cp = (
        (front.blue_cp, front.red_cp) if player.is_blue else (front.red_cp, front.blue_cp)
    )
    planner = game.ground_planners.get(enemy_cp.id)
    if planner is None:
        return DEFAULT_ARMOR_SHARE
    profiles = CombatProfiles.instance()
    armored = total = 0
    for group in planner.units_per_cp.get(own_cp.id, []):
        try:
            is_armored = profiles.ground_unit(group.unit_type).armored
        except Exception:
            is_armored = True
        total += group.size
        armored += group.size if is_armored else 0
    return armored / total if total else DEFAULT_ARMOR_SHARE


def expected_front_kills(flight: Flight, armor_share: float = DEFAULT_ARMOR_SHARE) -> float:
    """Vehicles the flight is expected to destroy in one CAS sortie."""
    from game.sim.combat.model.attack import (
        FRONT_LINE_PASSES,
        KILL_MATRIX,
        TargetClass,
        front_line_value,
    )
    from game.sim.combat.model.profiles import CombatProfiles, Guidance, Warhead, WeaponRole

    profiles = CombatProfiles.instance()
    try:
        aircraft = profiles.aircraft(flight.unit_type)
        modern = aircraft.generation >= 4 or flight.unit_type.has_built_in_target_pod
    except Exception:
        modern = True
    soft_share = 1.0 - armor_share

    def p_kill(warhead: Warhead) -> float:
        row = KILL_MATRIX.get(warhead, KILL_MATRIX[Warhead.MEDIUM])
        return armor_share * row[TargetClass.ARMOR] + soft_share * row[TargetClass.SOFT]

    total = 0.0
    for member in flight.iter_members():
        try:
            weapons = [w for w in member.loadout.pylons.values() if w is not None]
        except Exception:
            total += FALLBACK_KILLS_PER_AIRCRAFT
            continue
        profiles_on_board = []
        has_tgp = getattr(flight.unit_type, "has_built_in_target_pod", False)
        for weapon in weapons:
            try:
                profile = profiles.weapon(weapon)
            except Exception:
                continue
            if profile.role is WeaponRole.TGP:
                has_tgp = True
            elif profile.role in (WeaponRole.A2G, WeaponRole.ANTISHIP):
                profiles_on_board.append(profile)
        # The model's order over the front: most effective first.
        profiles_on_board.sort(key=lambda profile: -front_line_value(profile))
        passes = FRONT_LINE_PASSES
        for profile in profiles_on_board:
            if passes <= 0:
                break
            rounds = min(profile.count, passes)
            passes -= rounds
            guidance = profile.guidance
            if guidance is Guidance.LASER:
                factor = 0.9 if has_tgp else 0.3
            elif guidance in (Guidance.TV, Guidance.IIR, Guidance.ATGM):
                factor = 0.9
            elif guidance is Guidance.GPS:
                # Front-line vehicles move: coordinate-seeking weapons miss.
                factor = 0.25
            elif guidance is Guidance.ANTI_RADIATION:
                factor = 0.1
            else:
                factor = (0.9 if modern or has_tgp else 0.6) * 0.8
            p_hit = min(0.95, max(0.02, profile.accuracy * factor))
            kills = p_hit * p_kill(profile.warhead)
            if profile.warhead is Warhead.CLUSTER:
                kills += p_hit * 2 * 0.35 * soft_share * p_kill(profile.warhead)
            elif guidance in (Guidance.UNGUIDED, Guidance.ROCKET):
                kills += p_hit * 0.35 * soft_share * p_kill(profile.warhead)
            total += rounds * kills
    return total * DELIVERY_FACTOR


def flight_kills_or_fallback(flight: Flight, armor_share: float) -> float:
    try:
        return expected_front_kills(flight, armor_share)
    except Exception:
        logging.exception("JFACC: could not estimate CAS kills")
        return FALLBACK_KILLS_PER_AIRCRAFT * flight.count
