"""Intelligence agencies: human and signals intelligence.

Each side's agencies produce a few products per turn:

* Order of battle: estimates of aircraft and armour at enemy bases improve.
* Site tips: agents report enemy sites. Many are vague, some point at decoys,
  some are simply wrong and create phantom threats the planner has to route
  around until imagery or recon clears them.
* Warnings: signals intelligence reads enemy preparations. An expected
  offensive makes the AI dig in; the player gets reports stating how sure the
  agency is. Warnings can be false alarms, and real offensives can be missed.
* Battle damage: agencies confirm (or contradict) strike reports.

Balance: reliability is the agency's capability reduced by the enemy's
counter-intelligence, and everything an agency produces is uncertain.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .deception import maybe_fooled
from .intel import IntelSource, enemy_ground_objects

if TYPE_CHECKING:
    from game import Game
    from game.theater import ControlPoint
    from game.theater.player import Player
    from .warstate import WarState


@dataclass(frozen=True)
class AgencyReport:
    tips_true: int
    tips_false: int
    bda_resolved: int


def reliability(game: Game, war_state: WarState, viewer: Player, kind: str) -> float:
    own = war_state.doctrine(game, viewer)
    enemy = war_state.doctrine(game, viewer.opponent)
    base = own.humint if kind == "humint" else own.sigint
    value = base * (1 - 0.5 * enemy.counterintel)
    return max(
        0.0,
        min(0.95, value * float(getattr(game.settings, "intel_source_strength", 1.0))),
    )


def run_agencies(
    game: Game, war_state: WarState, viewer: Player, rng: random.Random
) -> AgencyReport:
    picture = war_state.picture(game, viewer)
    humint = reliability(game, war_state, viewer, "humint")
    own = war_state.doctrine(game, viewer)

    # Order of battle at enemy bases.
    for cp in game.theater.control_points_for(viewer.opponent):
        previous = picture.airbase_quality.get(cp.id, 0.0)
        picture.airbase_quality[cp.id] = max(previous * 0.85, humint * 0.6)

    # Site tips.
    tips = round(1 + 3 * own.humint)
    unknown = [
        tgo
        for tgo in enemy_ground_objects(game, viewer)
        if not tgo.is_dead and not picture.knows(tgo)
    ]
    rng.shuffle(unknown)
    true_tips = false_tips = 0
    enemy_cps = list(game.theater.control_points_for(viewer.opponent))
    for _ in range(tips):
        if rng.random() < humint and unknown:
            tgo = unknown.pop()
            picture.observe(tgo, 0.2 + 0.25 * humint, IntelSource.AGENT, game.turn, rng)
            maybe_fooled(game, war_state, picture, tgo, IntelSource.AGENT, rng)
            true_tips += 1
        elif enemy_cps and rng.random() < 0.6:
            # A false report: a SAM that isn't there.
            cp = rng.choice(enemy_cps)
            point = cp.position.point_from_heading(
                rng.uniform(0, 360), rng.uniform(5_000, 30_000)
            )
            picture.add_phantom(point.x, point.y, game.turn, rng)
            false_tips += 1

    # Battle damage: settle some of last turn's strike claims.
    resolved = 0
    for contact in picture.contacts.values():
        if (
            contact.source is not IntelSource.STRIKE
            or contact.last_seen_turn < game.turn - 1
        ):
            continue
        if rng.random() >= humint * 0.5:
            continue
        from .intel import tgo_by_id

        struck = tgo_by_id(game, contact.tgo_id)
        if struck is None:
            continue
        contact.believed_dead = {u.id for u in struck.units if not u.alive}
        resolved += 1
    return AgencyReport(true_tips, false_tips, resolved)


# ---------------------------------------------------------------------- warnings


def expects_offensive(
    game: Game,
    war_state: WarState,
    viewer: Player,
    enemy_cp: ControlPoint,
    friendly_cp: ControlPoint,
) -> bool:
    """Whether the viewer's agencies warn of an enemy offensive from enemy_cp
    this turn. Deterministic per turn so repeated planning passes agree."""
    from game.ground_forces.combat_stance import CombatStance

    if not getattr(game.settings, "space_and_agency_intel", True):
        return False
    stance = enemy_cp.stances.get(friendly_cp.id)
    attacking = stance in (
        CombatStance.AGGRESSIVE,
        CombatStance.BREAKTHROUGH,
        CombatStance.ELIMINATION,
    )
    rng = war_state.rng(game, f"warning:{viewer}:{enemy_cp.id}")
    sigint = reliability(game, war_state, viewer, "sigint")
    if attacking:
        return rng.random() < sigint
    return rng.random() < (1 - sigint) * 0.2  # False alarm.


def warn_player(game: Game, war_state: WarState) -> None:
    """Agency reports for the player after both sides have planned the turn:
    expected enemy offensives and strikes."""
    from game.theater import ControlPoint, TheaterGroundObject
    from game.theater.player import Player

    if not getattr(game.settings, "space_and_agency_intel", True):
        return
    if war_state.warnings_turn == game.turn:
        return
    war_state.warnings_turn = game.turn
    sigint = reliability(game, war_state, Player.BLUE, "sigint")
    if sigint <= 0:
        return

    def confidence(p: float) -> str:
        return "highly likely" if p > 0.7 else "likely" if p > 0.45 else "possible"

    for front_line in game.theater.conflicts():
        if expects_offensive(
            game, war_state, Player.BLUE, front_line.red_cp, front_line.blue_cp
        ):
            game.message(
                "Agency report",
                f"Enemy offensive {confidence(sigint)} at {front_line.blue_cp.name}.",
            )

    rng = war_state.rng(game, "strike-warnings")
    regions: dict[str, int] = {}
    for package in game.red.ato.packages:
        target = package.target
        if isinstance(target, (TheaterGroundObject, ControlPoint)) and (
            target.is_friendly(Player.BLUE)
        ):
            name = (
                target.control_point.name
                if isinstance(target, TheaterGroundObject)
                else target.name
            )
            regions[name] = regions.get(name, 0) + 1
    for name, count in regions.items():
        if rng.random() < sigint:
            game.message(
                "Agency report",
                f"Enemy air strike {confidence(sigint)} in the {name} area"
                + (f" ({count} packages)" if count > 1 else "")
                + ".",
            )
    if rng.random() < (1 - sigint) * 0.3:
        own = list(game.theater.control_points_for(Player.BLUE))
        if own:
            game.message(
                "Agency report",
                f"Enemy air strike possible in the {rng.choice(own).name} area.",
            )
