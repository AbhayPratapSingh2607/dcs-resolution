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

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING
from uuid import UUID

from .intel import EXPOSING_SOURCES, IntelPicture, IntelSource, is_mobile

if TYPE_CHECKING:
    from dcs.mapping import Point

    from game import Game
    from game.ato import Package
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


# ============================================================ the decoy call
#
# A package sent against a site whose picture is a decoy may see through it
# on the way in: the crews' sensors, ELINT from the SEAD element (most decoys
# don't radiate), or a real site close enough to be found from the decoy.
# The call is made once, before the mission is flown (at Take off, when the
# fast forward reaches the DCS window, or when the combat model's strike
# arrives), and both DCS and the combat model follow it: a package that sees
# through it attacks the real site, one that doesn't bombs the decoy.

#: Beyond this from the decoy the real site isn't found on the attack run.
SPOT_RANGE_M = 20_000.0
#: The chance to see through a decoy: base, per unit of the side's ISR, and
#: with a SEAD element in the package; capped.
SPOT_BASE = 0.15
SPOT_PER_ISR = 0.35
SPOT_SEAD_BONUS = 0.2
SPOT_MAX = 0.85


@dataclass
class DecoyCall:
    """One package's call on a decoyed target, rolled before the mission."""

    tgo_id: UUID
    decoy_index: int
    #: The decoy's position (the believed position of the site), DCS axes.
    x: float
    y: float
    chance: float
    spotted: bool
    reasons: list[str] = field(default_factory=list)

    def summary(self) -> str:
        what = (
            "sees through the decoy and attacks the real site"
            if self.spotted
            else "takes the decoy for the site"
        )
        why = "; ".join(self.reasons)
        return f"{what} ({round(self.chance * 100)}% chance: {why})"


def _attack_types() -> set[Any]:
    from game.ato.flighttype import FlightType

    return {FlightType.DEAD, FlightType.STRIKE, FlightType.BAI}


def _sead_types() -> set[Any]:
    from game.ato.flighttype import FlightType

    return {FlightType.SEAD, FlightType.SEAD_ESCORT, FlightType.SEAD_SWEEP}


def see_through_chance(
    package: Package, picture: IntelPicture, tgo: TheaterGroundObject, decoy: Point
) -> tuple[float, list[str]]:
    """The chance the package spots the decoy, and why."""
    distance = decoy.distance_to_point(tgo.position)
    if distance >= SPOT_RANGE_M:
        return 0.0, [f"the real site is {distance / 1000:.0f} km from the decoy"]
    chance = SPOT_BASE + SPOT_PER_ISR * picture.isr
    reasons = [f"ISR {round(picture.isr * 100)}%"]
    if any(f.flight_type in _sead_types() for f in package.flights):
        chance += SPOT_SEAD_BONUS
        reasons.append("ELINT from the SEAD element")
    # The farther the real site, the less likely the crews find it.
    chance *= 1.0 - 0.5 * distance / SPOT_RANGE_M
    reasons.append(f"real site {distance / 1000:.0f} km away")
    return min(SPOT_MAX, chance), reasons


def decoy_call(game: Game, package: Package) -> Optional[DecoyCall]:
    """The package's call on its target, made the first time it is asked
    and kept (the same decoy gives the same call). None when the package's
    picture of its target isn't a decoy or it has no attack flights."""
    from game.theater import TheaterGroundObject

    target = package.target
    if not isinstance(target, TheaterGroundObject) or not enabled(game):
        return None
    if not any(f.flight_type in _attack_types() for f in package.flights):
        return None
    war_state = getattr(game, "war_state", None)
    if war_state is None or not war_state.intel_enabled(game):
        return None
    if not package.flights:
        return None
    viewer = package.flights[0].squadron.player
    if target.control_point.captured == viewer:
        return None
    picture = war_state.picture(game, viewer)
    index = decoyed(picture, target)
    existing: Optional[DecoyCall] = getattr(package, "decoy_call", None)
    if index is None:
        package.decoy_call = None  # type: ignore[attr-defined]
        return None
    if (
        existing is not None
        and existing.tgo_id == target.id
        and existing.decoy_index == index
    ):
        return existing
    point = picture.estimated_position(target)
    chance, reasons = see_through_chance(package, picture, target, point)
    rng = war_state.rng(game, f"decoycall:{target.id}:{package.time_over_target}")
    call = DecoyCall(
        target.id, index, point.x, point.y, chance, rng.random() < chance, reasons
    )
    package.decoy_call = call  # type: ignore[attr-defined]
    return call


def decide_decoy_calls(game: Game) -> list[tuple[Package, DecoyCall]]:
    """Makes the call for every package in the ATOs (the packages flown in
    DCS), before the mission is generated."""
    calls: list[tuple[Package, DecoyCall]] = []
    for coalition in (game.blue, game.red):
        for package in coalition.ato.packages:
            try:
                call = decoy_call(game, package)
            except Exception:
                logging.exception(f"Could not make the decoy call for {package}")
                continue
            if call is not None:
                calls.append((package, call))
                logging.info(f"{package}: {call.summary()}")
    return calls


def strike_on_decoy(
    war_state: WarState,
    picture: IntelPicture,
    tgo: TheaterGroundObject,
    index: int,
    rng: random.Random,
) -> str:
    """The weapons hit the decoy: it is gone, and the crews either realise
    it was a dummy or report the site destroyed. Returns the note."""
    consume_decoy(war_state, tgo, index)
    contact = picture.contact(tgo)
    if rng.random() < 0.25 + 0.4 * picture.isr:
        picture.expose(tgo, rng)
        return "the crews report a decoy"
    if contact is not None:
        contact.decoy_index = None
        contact.believed_dead = {u.id for u in tgo.units}
    return "reported destroyed"


def apply_dcs_calls(game: Game, calls: list[tuple[Package, DecoyCall]]) -> None:
    """After the DCS mission: what the calls of the AI packages flown there
    did to the picture. A package that saw through the decoy has found the
    real site; one that didn't has bombed the decoy. Packages with players
    are left to what the players did."""
    war_state = getattr(game, "war_state", None)
    if war_state is None:
        return
    for package, call in calls:
        if package.has_players:
            continue
        target = package.target
        if getattr(target, "id", None) != call.tgo_id or not package.flights:
            continue
        viewer = package.flights[0].squadron.player
        picture = war_state.picture(game, viewer)
        if decoyed(picture, target) != call.decoy_index:  # type: ignore[arg-type]
            continue
        rng = war_state.rng(game, f"decoydcs:{call.tgo_id}")
        if call.spotted:
            picture.expose(target, rng)
        else:
            strike_on_decoy(
                war_state, picture, target, call.decoy_index, rng  # type: ignore[arg-type]
            )
