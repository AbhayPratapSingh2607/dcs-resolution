"""Deception: camouflage and decoy sites.

Forces with a deception doctrine (Soviet maskirovka, Serbian practice in 1999)
set up decoys next to their mobile air defenses and vehicle groups: inflatable
launchers, dummy radars, burnt-out wrecks dressed as live vehicles. Imagery and
agents are easily fooled by them; ELINT much less so (most decoys don't
radiate); a close look by reconnaissance or a strike crew may see through them.

A side whose picture of a site has latched onto a decoy believes the decoy's
position with high confidence. Strikes against it hit the decoy, the crews
report the site destroyed, and the real site lives to fight.
"""

from __future__ import annotations

import math
import random
from typing import Optional, TYPE_CHECKING

from .intel import EXPOSING_SOURCES, IntelPicture, IntelSource, is_mobile

if TYPE_CHECKING:
    from game import Game
    from game.theater import TheaterGroundObject
    from .warstate import WarState

#: How easily each source is taken in by a decoy, relative to doctrine.
FOOLED_BY = {
    IntelSource.SATELLITE: 0.55,
    IntelSource.AGENT: 0.6,
    IntelSource.VISUAL: 0.4,
    IntelSource.PREWAR: 0.3,
    IntelSource.ELINT: 0.1,
    IntelSource.SIGINT: 0.1,
    IntelSource.RECON: 0.12,
    IntelSource.STRIKE: 0.0,
    IntelSource.ENGAGEMENT: 0.0,
}


def enabled(game: Game) -> bool:
    return bool(getattr(game.settings, "deception_enabled", True))


def place_decoys(game: Game, war_state: WarState) -> int:
    """Gives each side's mobile sites their decoys, per doctrine. Returns how
    many decoys were placed this turn."""
    from game.theater.player import Player

    if not enabled(game):
        return 0
    placed = 0
    for player in (Player.BLUE, Player.RED):
        doctrine = war_state.doctrine(game, player)
        if doctrine.deception <= 0:
            continue
        from game.opening import decoys_allowed

        if not decoys_allowed(game, player):
            # Caught by full surprise (T8): no time to set out decoys.
            continue
        rng = war_state.rng(game, f"decoys{player}")
        from game.commander.jfacc.iads import decoy_plan

        plan = decoy_plan(game, player)
        for cp in game.theater.control_points_for(player):
            for tgo in cp.ground_objects:
                if tgo.is_dead:
                    war_state.deception.pop(tgo.id, None)
                    continue
                if plan is not None and _is_radar_sam(tgo):
                    placed += _planned_decoys(game, war_state, tgo, plan, rng)
                    continue
                if not is_mobile(tgo) or tgo.id in war_state.deception:
                    continue
                count = 0
                if rng.random() < doctrine.deception:
                    count = 2 if rng.random() < doctrine.deception * 0.5 else 1
                war_state.deception[tgo.id] = [
                    _decoy_offset(game, tgo, rng) for _ in range(count)
                ]
                placed += count
    return placed


def _is_radar_sam(tgo: TheaterGroundObject) -> bool:
    from game.theater.theatergroundobject import SamGroundObject

    return isinstance(tgo, SamGroundObject) and any(
        getattr(u, "is_anti_air", False) for u in tgo.units if u.alive
    )


def _planned_decoys(
    game: Game,
    war_state: WarState,
    tgo: TheaterGroundObject,
    plan: tuple[object, int],
    rng: random.Random,
) -> int:
    """The side's IADS management keeps per_site decoys beside each radar
    SAM site, toward the threat axis (game.commander.jfacc.iads)."""
    from game.commander.jfacc.iads import near_decoys, planned_decoy_offset

    side, per_site = plan
    decoys = war_state.deception.setdefault(tgo.id, [])
    added = 0
    for _ in range(max(0, per_site - near_decoys(decoys))):
        offset = planned_decoy_offset(game, tgo, side, rng)  # type: ignore[arg-type]
        if offset is None:
            break
        decoys.append(offset)
        added += 1
    return added


def _decoy_offset(
    game: Game, tgo: TheaterGroundObject, rng: random.Random
) -> tuple[float, float]:
    for _ in range(8):
        distance = rng.uniform(1500, 5000)
        bearing = rng.uniform(0, 2 * math.pi)
        dx, dy = distance * math.sin(bearing), distance * math.cos(bearing)
        point = tgo.position.point_from_heading(math.degrees(bearing), distance)
        try:
            if game.theater.is_on_land(point):
                return dx, dy
        except Exception:
            return dx, dy
    return dx, dy


def maybe_fooled(
    game: Game,
    war_state: WarState,
    picture: IntelPicture,
    tgo: TheaterGroundObject,
    source: IntelSource,
    rng: random.Random,
) -> bool:
    """After an observation: does the observer latch onto a decoy, or does a
    close look expose one? Returns True if the picture now holds a decoy."""
    if not enabled(game):
        return False
    decoys = war_state.deception.get(tgo.id) or []
    contact = picture.contact(tgo)
    if contact is not None and contact.decoy_index is not None:
        if source in EXPOSING_SOURCES and rng.random() < 0.3 + 0.5 * picture.isr:
            picture.expose(tgo, rng)
            return False
        return True
    if not decoys:
        return False
    owner = tgo.control_point.captured
    deception = war_state.doctrine(game, owner).deception
    if rng.random() < FOOLED_BY.get(source, 0.2) * deception * (
        1.2 - 0.5 * picture.isr
    ):
        index = rng.randrange(len(decoys))
        picture.latch_decoy(tgo, index, decoys[index])
        return True
    return False


def decoyed(picture: IntelPicture, tgo: TheaterGroundObject) -> Optional[int]:
    contact = picture.contact(tgo)
    return None if contact is None else contact.decoy_index


def consume_decoy(war_state: WarState, tgo: TheaterGroundObject, index: int) -> None:
    decoys = war_state.deception.get(tgo.id)
    if decoys and 0 <= index < len(decoys):
        decoys.pop(index)
