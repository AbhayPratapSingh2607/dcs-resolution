"""Campaign start (M4): the opening of the war, resolved at Begin Campaign.

The player makes the opening choices at turn 0 (T7: H-hour and the opening
emphasis) and spends the pre-war reconnaissance tasks (T5); red's commander
spends its own. The new-campaign setting for strategic surprise (T8) sets red's
posture at H-hour. Begin Campaign then, in order:

1. starts the war at H-hour;
2. puts red in its posture: radar SAMs moved off their known sites, emission
   control, decoys, aircraft dispersed or parked in the open, fighters on alert;
3. fills each side's pre-war picture and flies the reconnaissance (T5); the
   strategic intel round runs right after, in WarState.end_turn (T6);
4. fires blue's opening missile salvo at fixed targets from the target list,
   weighted by the emphasis (T9, decision 5: blue only, turn 0 only);
5. writes the turn 1 BDA report (T10): what was fired at and what intelligence
   assesses was hit, with the picture's uncertainty.

Everything here runs once. The damage is applied to the game, so it shows on the
map and in the first mission as wrecks and craters.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from datetime import time
from enum import Enum
from typing import Any, Iterable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game import Game
    from game.sim.gameupdateevents import GameUpdateEvents
    from game.theater import ControlPoint, MissionTarget
    from game.theater.player import Player
    from game.theater.theatergroundobject import TheaterGroundObject

NM = 1852.0


class Emphasis(Enum):
    BALANCED = "Balanced"
    AIR_DEFENSES = "Air defenses"
    AIRFIELDS = "Airfields"
    C2 = "Command and control"


class Surprise(Enum):
    NONE = "None: the enemy expects the war"
    PARTIAL = "Partial"
    FULL = "Full: the enemy is caught unprepared"


#: Target classes (game.commander.jfacc.targetclass) each emphasis favours.
EMPHASIS_CLASSES: dict[Emphasis, set[str]] = {
    Emphasis.AIR_DEFENSES: {"sam_lorad", "sam_merad", "ewr"},
    Emphasis.AIRFIELDS: {"airfield"},
    Emphasis.C2: {"c2_node", "power"},
}
#: How much an emphasis multiplies its classes' weight, on turn 1 and for the
#: missile strikes.
EMPHASIS_WEIGHT = 2.5

#: The four 6 hour periods of the day H-hour can open (hour of day).
H_HOURS = (0, 6, 12, 18)

#: Pre-war reconnaissance: radius around each chosen area.
RECON_RADIUS_M = 40 * NM


# ------------------------------------------------------------------ state


@dataclass
class SalvoShot:
    target: str
    target_class: str
    missiles: int
    hits: int
    #: Units destroyed (true), and what intelligence assesses (believed).
    destroyed: int
    assessed: int
    runway_cut: bool = False
    aircraft_destroyed: int = 0


@dataclass
class OpeningPlan:
    """The opening choices and what Begin Campaign did with them."""

    #: Hour of day the first period opens, or None for the campaign's time.
    h_hour: Optional[int] = None
    emphasis: Emphasis = Emphasis.BALANCED
    #: Pre-war reconnaissance areas: enemy control point names, by side
    #: (True = blue). Missing: the commander picks.
    recon: dict[bool, list[str]] = field(default_factory=dict)
    begun: bool = False
    surprise: Optional[Surprise] = None
    shots: list[SalvoShot] = field(default_factory=list)
    #: The turn 1 report (T10) and the opening estimate (T6), as lines.
    report: list[str] = field(default_factory=list)
    recon_flown: dict[bool, list[str]] = field(default_factory=dict)
    moved_sams: int = 0

    def __setstate__(self, state: dict[str, Any]) -> None:
        defaults = OpeningPlan().__dict__
        self.__dict__.update({**defaults, **state})


def opening_of(game: Game) -> OpeningPlan:
    plan = getattr(game, "opening", None)
    if plan is None:
        plan = OpeningPlan()
        game.opening = plan  # type: ignore[attr-defined]
    return plan


def surprise_of(game: Game) -> Surprise:
    plan = getattr(game, "opening", None)
    if plan is not None and plan.surprise is not None:
        return plan.surprise
    value = getattr(game.settings, "strategic_surprise", Surprise.PARTIAL)
    return value if isinstance(value, Surprise) else Surprise.PARTIAL


def opening_turn(game: Game) -> bool:
    """True on turn 1, the turn the opening shapes."""
    return getattr(game, "turn", 0) == 1 and opening_of(game).begun


# ---------------------------------------------------------- red's posture


#: Share of red's mobile radar SAMs off their known sites at H-hour.
MOVED_SHARE = {Surprise.NONE: 0.6, Surprise.PARTIAL: 0.3, Surprise.FULL: 0.0}
#: Extra (or fewer) ground alert pairs per base on turn 1.
ALERT_BONUS = {Surprise.NONE: 1, Surprise.PARTIAL: 0, Surprise.FULL: -1}
#: Share of red's aircraft parked in the open (the rest dispersed or in
#: shelters) on turn 1.
PARKED_IN_OPEN = {Surprise.NONE: 0.3, Surprise.PARTIAL: 0.6, Surprise.FULL: 1.0}
#: Cruise missile hit chance multiplier.
SURPRISE_HIT = {Surprise.NONE: 0.75, Surprise.PARTIAL: 0.9, Surprise.FULL: 1.0}
#: Turns until a runway the salvo cratered is open again. Engineers standing
#: by with repair kits reopen a strip within one 6 hour turn; caught by
#: surprise, the repair takes the usual four.
SALVO_REPAIR_TURNS = {Surprise.NONE: 1, Surprise.PARTIAL: 2, Surprise.FULL: 4}
#: Share of red's missile launchers (Scud sites, artillery) that fire back on
#: turn 1 (game.warfare.firemissions): ready when the war was expected,
#: silent when caught by surprise.
COUNTER_STRIKE_SHARE = {Surprise.NONE: 1.0, Surprise.PARTIAL: 0.5, Surprise.FULL: 0.0}


def _red_turn_1(game: Game, player: Any) -> bool:
    return opening_turn(game) and not player.is_blue


def alert_pairs_bonus(game: Game, player: Any) -> int:
    """Turn 1: red's fighters on alert follow its posture (T8)."""
    if not _red_turn_1(game, player):
        return 0
    return ALERT_BONUS[surprise_of(game)]


def mobile_emcon(game: Game, player: Any) -> Optional[str]:
    """Turn 1: red's mobile radar SAMs' emission control (T8): in ambush when
    the war was expected, radiating when caught by surprise; None leaves the
    doctrine's order."""
    if not _red_turn_1(game, player):
        return None
    from game.commander.jfacc.iads import ACTIVE, AMBUSH

    return {Surprise.NONE: AMBUSH, Surprise.PARTIAL: None, Surprise.FULL: ACTIVE}[
        surprise_of(game)
    ]


def decoys_allowed(game: Game, player: Any) -> bool:
    """Red caught by full surprise has had no time to set out decoys."""
    if player.is_blue or getattr(game, "turn", 0) > 1:
        return True
    plan = getattr(game, "opening", None)
    if plan is None or not plan.begun:
        return True
    return surprise_of(game) is not Surprise.FULL


def parked_in_open(game: Game, player: Any) -> float:
    if player.is_blue:
        return 1.0
    return PARKED_IN_OPEN[surprise_of(game)]


def _mobile_radar_sams(game: Game, player: Any) -> list[TheaterGroundObject]:
    from game.commander.jfacc.iads import _radar_sams
    from game.warfare.intel import is_mobile

    return [t for t in _radar_sams(game, player) if is_mobile(t)]


def apply_posture(game: Game, rng: random.Random) -> int:
    """Red's posture at H-hour (T8). Returns how many SAM sites moved."""
    from game.commander.jfacc.iads import _radar_sams, shift_site
    from game.theater.player import Player
    from game.warfare.intel import IntelSource

    surprise = surprise_of(game)
    picture = game.war_state.picture(game, Player.BLUE)
    moved = 0
    share = MOVED_SHARE[surprise]
    for tgo in _mobile_radar_sams(game, Player.RED):
        if rng.random() >= share:
            continue
        distance = rng.uniform(3000, 8000)
        bearing = rng.uniform(0, 2 * math.pi)
        try:
            shift_site(game, tgo, distance * math.sin(bearing), distance * math.cos(bearing))
        except Exception:
            logging.exception(f"Could not move {tgo} for red's posture")
            continue
        picture.scooted(tgo)
        moved += 1
    if surprise is Surprise.FULL:
        # Caught at its peacetime sites: what was known is confirmed.
        for tgo in _radar_sams(game, Player.RED):
            if picture.knows(tgo):
                picture.observe(tgo, 0.5, IntelSource.PREWAR, 0, rng)
    return moved


# ------------------------------------------------------- reconnaissance (T5)


def recon_tasks(game: Game, player: Player) -> int:
    """How many areas the side can reconnoitre before the war."""
    isr = game.war_state.doctrine(game, player).isr
    return 2 + round(4 * isr)


def recon_candidates(game: Game, player: Player) -> list[ControlPoint]:
    """Enemy bases to reconnoitre, nearest to the side's own first."""
    from game.theater.controlpoint import ControlPointType

    own = [
        cp
        for cp in game.theater.control_points_for(player)
        if cp.cptype is not ControlPointType.OFF_MAP
    ]
    enemy = [
        cp
        for cp in game.theater.control_points_for(player.opponent)
        if cp.cptype is not ControlPointType.OFF_MAP
    ]

    def distance(cp: ControlPoint) -> float:
        return min((cp.position.distance_to_point(o.position) for o in own), default=0.0)

    return sorted(enemy, key=distance)


def commander_recon(game: Game, player: Player) -> list[str]:
    """The commander's own choice: the nearest enemy bases."""
    return [cp.name for cp in recon_candidates(game, player)[: recon_tasks(game, player)]]


def fly_recon(game: Game, player: Player, names: Iterable[str], rng: random.Random) -> int:
    """Raise what the side knows within RECON_RADIUS_M of each area.
    Returns how many enemy sites were seen."""
    from game.warfare.intel import IntelSource, enemy_ground_objects

    picture = game.war_state.picture(game, player)
    isr = picture.isr
    wanted = set(names)
    areas = [cp for cp in recon_candidates(game, player) if cp.name in wanted]
    seen = 0
    for cp in areas:
        picture.airbase_quality[cp.id] = max(picture.airbase_quality.get(cp.id, 0.0), 0.85)
        for tgo in enemy_ground_objects(game, player):
            if tgo.position.distance_to_point(cp.position) > RECON_RADIUS_M:
                continue
            picture.observe(tgo, 0.55 + 0.35 * isr, IntelSource.RECON, 0, rng)
            seen += 1
    return seen


# ----------------------------------------------------------- missiles (T9)

#: Weight of each fixed target class for the opening salvo.
SALVO_WEIGHT = {
    "c2_node": 3.0,
    "ewr": 2.5,
    "sam_lorad": 2.5,
    "power": 2.0,
    "airfield": 2.0,
    "fuel": 1.5,
    "ammo": 1.5,
    "factory": 1.0,
    "building": 0.7,
}
#: Missiles per target, by class.
MISSILES_PER_TARGET = {"airfield": 4, "sam_lorad": 3}
BASE_HIT = 0.8

CRUISE_SHIP_KEYS = ("TICONDEROG", "USS_Arleigh_Burke", "CG_", "Arleigh", "MOSCOW", "PIOTR", "NEUSTRASH", "REZKY")
BOMBER_KEYS = ("B-52", "B-1B", "B_1", "Tu-95", "Tu-160", "Tu-22")


def _doctrine_name(game: Game, player: Player) -> str:
    try:
        from game.commander.jfacc.planner import profile_for

        profile = profile_for(game, player)
        return str(getattr(profile, "name", "") or "").lower()
    except Exception:
        return ""


def salvo_size(game: Game) -> tuple[int, str]:
    """(missiles, how it was sized) for blue's opening salvo: from the faction
    and its era, raised by the cruise missile ships and bomber detachments."""
    from game.theater.controlpoint import ControlPointType
    from game.theater.player import Player

    year = game.current_day.year
    faction = game.blue.faction
    doctrine = _doctrine_name(game, Player.BLUE)
    country = str(getattr(faction, "country", "") or "")
    western = "west" in doctrine or "nato" in doctrine or country in ("USA", "UK", "France")
    russian = "russia" in doctrine or "soviet" in doctrine or country in ("Russia", "USSR")
    if western:
        base = 24 if year >= 2003 else 16 if year >= 1991 else 8 if year >= 1983 else 0
    elif russian:
        base = 12 if year >= 2015 else 0
    else:
        base = 0
    if base == 0:
        return 0, f"no cruise missiles in {country or 'the faction'}'s {year} arsenal"
    ships = 0
    for cp in game.theater.control_points_for(Player.BLUE):
        for tgo in cp.ground_objects:
            for unit in tgo.units:
                name = str(getattr(unit.type, "id", unit.type) if hasattr(unit, "type") else "")
                if unit.alive and any(k in name for k in CRUISE_SHIP_KEYS):
                    ships += 1
    bombers = 0
    for squadron in game.blue.air_wing.iter_squadrons():
        if squadron.location.cptype is not ControlPointType.OFF_MAP:
            continue
        if any(k in squadron.aircraft.variant_id for k in BOMBER_KEYS):
            bombers += squadron.owned_aircraft
    total = base + 8 * min(ships, 4) + 2 * bombers
    parts = [f"{base} from the {year} arsenal"]
    if ships:
        parts.append(f"{8 * min(ships, 4)} from {min(ships, 4)} cruise missile ships")
    if bombers:
        parts.append(f"{2 * bombers} from {bombers} bombers")
    return total, ", ".join(parts)


def missile_strikes_enabled(game: Game) -> bool:
    """Whether blue fires the opening salvo (the Opening missile strikes
    setting, also in the Begin Campaign window)."""
    return bool(getattr(game.settings, "opening_missile_strikes", True))


@dataclass(frozen=True)
class PlannedShot:
    """One target of the opening salvo, before it is fired."""

    target: MissionTarget
    target_class: str
    missiles: int

    @property
    def name(self) -> str:
        return self.target.name


def planned_salvo(
    game: Game, emphasis: Optional[Emphasis] = None
) -> list[PlannedShot]:
    """The opening salvo's targets and missiles, against blue's current picture,
    as fire_salvo will fire it. Pre-war reconnaissance flown at Begin Campaign
    can still add or reorder targets. Empty when the side has no missiles; the
    plan ignores whether the strikes are turned off."""
    missiles, _ = salvo_size(game)
    planned: list[PlannedShot] = []
    if missiles <= 0:
        return planned
    for _, target, target_class in _salvo_candidates(game, emphasis):
        if missiles <= 0:
            break
        n = min(missiles, MISSILES_PER_TARGET.get(target_class, 2))
        missiles -= n
        planned.append(PlannedShot(target, target_class, n))
    return planned


def _salvo_candidates(
    game: Game, emphasis: Optional[Emphasis] = None
) -> list[tuple[float, MissionTarget, str]]:
    from game.commander.jfacc.targetclass import classify
    from game.theater.controlpoint import ControlPointType
    from game.theater.player import Player
    from game.warfare.intel import is_mobile

    picture = game.war_state.picture(game, Player.BLUE)
    if emphasis is None:
        emphasis = opening_of(game).emphasis
    favoured = EMPHASIS_CLASSES.get(emphasis, set())
    found: list[tuple[float, MissionTarget, str]] = []
    for cp in game.theater.control_points_for(Player.RED):
        if cp.cptype is ControlPointType.OFF_MAP:
            continue
        if not cp.is_fleet and cp.runway_is_operational():
            weight = SALVO_WEIGHT["airfield"] * (EMPHASIS_WEIGHT if "airfield" in favoured else 1.0)
            found.append((weight, cp, "airfield"))
        for tgo in cp.ground_objects:
            if tgo.is_dead or is_mobile(tgo) or not picture.knows(tgo):
                continue
            _, target_class = classify(tgo)
            base = SALVO_WEIGHT.get(target_class)
            if base is None:
                continue
            weight = base * (EMPHASIS_WEIGHT if target_class in favoured else 1.0)
            weight *= 0.5 + 0.5 * min(1.0, picture.contact(tgo).confidence if picture.contact(tgo) else 0.5)
            found.append((weight, tgo, target_class))
    found.sort(key=lambda f: -f[0])
    return found


def _defended(game: Game, target: MissionTarget) -> float:
    """Hit chance multiplier for red's air defenses around the target."""
    from game.commander.jfacc.iads import _radar_sams
    from game.theater.player import Player

    factor = 1.0
    for sam in _radar_sams(game, Player.RED):
        if sam is target or sam.is_dead:
            continue
        try:
            reach = sam.max_threat_range().meters
        except Exception:
            continue
        if sam.position.distance_to_point(target.position) <= reach:
            factor = min(factor, 0.85)
    return factor


def fire_salvo(game: Game, events: GameUpdateEvents, rng: random.Random) -> list[SalvoShot]:
    """Blue's opening missile strikes (T9), resolved now."""
    from game.theater import ControlPoint
    from game.theater.player import Player

    if not missile_strikes_enabled(game):
        return []
    planned = planned_salvo(game)
    if not planned:
        return []
    surprise = SURPRISE_HIT[surprise_of(game)]
    picture = game.war_state.picture(game, Player.BLUE)
    shots: list[SalvoShot] = []
    for planned_shot in planned:
        target = planned_shot.target
        target_class = planned_shot.target_class
        n = planned_shot.missiles
        p = BASE_HIT * surprise * _defended(game, target)
        if target_class == "sam_lorad":
            p *= 0.85  # point defense
        hits = sum(1 for _ in range(n) if rng.random() < p)
        shot = SalvoShot(target.name, target_class, n, hits, 0, 0)
        if isinstance(target, ControlPoint):
            _hit_airfield(game, target, hits, shot, rng)
        else:
            _hit_site(game, target, hits, shot, events, picture, rng)
        shots.append(shot)
    return shots


def _hit_site(
    game: Game,
    tgo: TheaterGroundObject,
    hits: int,
    shot: SalvoShot,
    events: GameUpdateEvents,
    picture: Any,
    rng: random.Random,
) -> None:
    from game.warfare.intel import IntelSource

    alive = [u for u in tgo.units if u.alive]
    # Radars and command posts first: what a planner aims at.
    alive.sort(key=lambda u: 0 if "radar" in str(getattr(u, "name", "")).lower() or "sr" in str(getattr(u, "name", "")).lower() else 1)
    for unit in alive[:hits]:
        unit.kill(events)
        shot.destroyed += 1
        picture.report_kill(tgo, unit.id, 0.5 + 0.4 * picture.isr, rng)
    # Damage claims from missiles are uncertain: some misses are claimed.
    picture.overclaim(tgo, 0.15 * (1 - picture.isr), rng)
    picture.observe(tgo, 0.3, IntelSource.STRIKE, 1, rng)
    contact = picture.contact(tgo)
    believed = contact.believed_dead if contact is not None else set()
    shot.assessed = sum(1 for u in tgo.units if u.id in believed)


def _hit_airfield(
    game: Game, cp: ControlPoint, hits: int, shot: SalvoShot, rng: random.Random
) -> None:
    if hits >= 2 and cp.runway_status is not None:
        cp.runway_status.damage()
        # The repair starts at once; how long it takes follows the surprise.
        # Turn 0's own end ticks it once more (ControlPoint.process_turn runs
        # after Begin Campaign), hence the extra turn.
        cp.runway_status.repair_turns_remaining = (
            SALVO_REPAIR_TURNS[surprise_of(game)] + 1
        )
        shot.runway_cut = True
    exposure = parked_in_open(game, cp.captured)
    for _ in range(hits):
        if rng.random() >= 0.5 * exposure:
            continue
        squadrons = [s for s in cp.squadrons if s.owned_aircraft > 0]
        if not squadrons:
            break
        squadron = rng.choice(squadrons)
        squadron.owned_aircraft -= 1
        squadron.destroyed_aircraft += 1
        shot.aircraft_destroyed += 1
    # Aircraft kills on a ramp are hard to count from imagery.
    noise = rng.uniform(0.6, 1.4)
    shot.assessed = max(0, round(shot.aircraft_destroyed * noise)) + (1 if shot.runway_cut else 0)
    shot.destroyed = shot.aircraft_destroyed + (1 if shot.runway_cut else 0)


# ------------------------------------------------------------ the report (T10)


def bda_report(game: Game, shots: list[SalvoShot], sized: str) -> list[str]:
    from game.theater.player import Player

    if not shots:
        if not missile_strikes_enabled(game) and salvo_size(game)[0] > 0:
            return ["No opening missile strikes: they were turned off."]
        return [f"No opening missile strikes: {sized}."]
    isr = game.war_state.picture(game, Player.BLUE).isr
    fired = sum(s.missiles for s in shots)
    lines = [
        f"Opening salvo: {fired} cruise missiles at {len(shots)} targets "
        f"({sized}); emphasis: {opening_of(game).emphasis.value.lower()}, "
        f"surprise: {surprise_of(game).name.lower()}."
    ]
    hit_targets = [s for s in shots if s.assessed > 0]
    lines.append(
        f"Intelligence assesses {len(hit_targets)} of {len(shots)} targets hit "
        f"(confidence {'high' if isr >= 0.75 else 'moderate' if isr >= 0.5 else 'low'}; "
        "battle damage is uncertain until reconnaissance confirms it)."
    )
    for shot in shots:
        if shot.target_class == "airfield":
            effect = []
            if shot.runway_cut:
                effect.append("runway cratered")
            if shot.assessed - (1 if shot.runway_cut else 0) > 0:
                effect.append(f"about {shot.assessed - (1 if shot.runway_cut else 0)} aircraft destroyed on the ground")
            text = ", ".join(effect) if effect else "no effect seen"
        else:
            text = (
                f"{shot.assessed} element{'s' if shot.assessed != 1 else ''} assessed destroyed"
                if shot.assessed
                else "no effect seen"
            )
        lines.append(f"  {shot.target} ({shot.target_class.replace('_', ' ')}): {shot.missiles} missiles, {text}")
    lines.extend(reaction_lines(game, shots))
    return lines


def reaction_lines(game: Game, shots: list[SalvoShot]) -> list[str]:
    """What intelligence expects the enemy to do about the salvo, which the
    strategic surprise decides: how soon its runways reopen, how much of its
    air force flies from road bases meanwhile, and whether it fires back."""
    from game.warfare.roadbases import OPENING_SHARE, enabled

    surprise = surprise_of(game)
    lines: list[str] = []
    cut = [s for s in shots if s.runway_cut]
    if cut:
        turns = SALVO_REPAIR_TURNS[surprise]
        lines.append(
            f"Enemy reaction: {len(cut)} runway{'s' if len(cut) != 1 else ''} cut; "
            + (
                "repair crews were standing by and should reopen them next turn"
                if turns == 1
                else f"repairs should take about {turns} turns"
            )
            + "."
        )
        if enabled(game):
            share = OPENING_SHARE.get(surprise.name, 0.0)
            lines.append(
                f"  Until then about {round(share * 100)}% of their fighters and "
                "attack aircraft there fly from road bases"
                + (
                    " (dispersed before H-hour)"
                    if surprise is Surprise.NONE
                    else " (caught at their main bases)"
                    if surprise is Surprise.FULL
                    else ""
                )
                + "; helicopters fly on."
            )
    from game.warfare.firemissions import enabled as fire_missions_enabled

    # Red fires back only through fire missions (the Fire missions setting).
    counter = COUNTER_STRIKE_SHARE[surprise] if fire_missions_enabled(game) else 0.0
    if counter >= 1.0:
        lines.append(
            "Expect a counter-strike on turn 1: the enemy's missile units were ready."
        )
    elif counter > 0:
        lines.append("Expect a limited counter-strike from the enemy's missile units.")
    return lines


def opening_estimate(game: Game) -> list[str]:
    """The picture at H-hour (T6): what blue knows of the enemy."""
    from game.commander.jfacc.intelview import enemy_squadrons
    from game.theater.player import Player
    from game.warfare.intel import enemy_ground_objects

    picture = game.war_state.picture(game, Player.BLUE)
    sites = list(enemy_ground_objects(game, Player.BLUE))
    known = [t for t in sites if picture.knows(t)]
    confirmed = [t for t in known if picture.confirmed(t)]
    from game.commander.jfacc.iads import _radar_sams

    sams = [t for t in _radar_sams(game, Player.RED) if picture.knows(t)]
    aircraft = sum(n for _, n in enemy_squadrons(game, Player.BLUE))
    plan = opening_of(game)
    recon = plan.recon_flown.get(True, [])
    lines = [
        f"Opening estimate: {len(known)} enemy sites located ({len(confirmed)} "
        f"confirmed), {len(sams)} radar SAM sites, about {aircraft} enemy aircraft."
    ]
    if recon:
        lines.append("Pre-war reconnaissance over " + ", ".join(recon) + ".")
    if plan.moved_sams:
        lines.append(
            "Expect SAM sites away from their known positions: the enemy has moved "
            "some of its air defenses."
            if surprise_of(game) is not Surprise.FULL
            else ""
        )
    return [l for l in lines if l]


# ---------------------------------------------------------------- begin


def apply_h_hour(game: Game) -> None:
    plan = opening_of(game)
    if plan.h_hour is None:
        return
    from game.weather.conditions import TimeOfDay

    start = time(hour=int(plan.h_hour) % 24)
    game.time_of_day_offset_for_start_time = list(TimeOfDay).index(
        game.theater.daytime_map.best_guess_time_of_day_at(start)
    )
    game.conditions = game.generate_conditions(forced_time=start)


def begin_campaign(game: Game, events: GameUpdateEvents) -> None:
    """Runs once, when turn 0 ends (Begin Campaign)."""
    from game.theater.player import Player

    plan = opening_of(game)
    if plan.begun:
        return
    plan.surprise = surprise_of(game)
    rng = game.war_state.rng(game, "opening")
    try:
        apply_h_hour(game)
    except Exception:
        logging.exception("Could not set H-hour")
    plan.begun = True
    if not game.war_state.intel_enabled(game):
        plan.report = ["Intelligence is off: no pre-war picture or reconnaissance."]
    else:
        # The pre-war picture, then red's posture (which may move sites blue
        # knows), then the reconnaissance.
        for player in (Player.BLUE, Player.RED):
            game.war_state.picture(game, player)
        try:
            plan.moved_sams = apply_posture(game, rng)
        except Exception:
            logging.exception("Could not apply red's posture")
        for player in (Player.BLUE, Player.RED):
            names = plan.recon.get(player.is_blue)
            if not names:
                names = commander_recon(game, player)
            names = names[: recon_tasks(game, player)]
            fly_recon(game, player, names, rng)
            plan.recon_flown[player.is_blue] = list(names)
    try:
        sized = salvo_size(game)[1]
        plan.shots = fire_salvo(game, events, rng)
        plan.report = plan.report + bda_report(game, plan.shots, sized)
    except Exception:
        logging.exception("Opening missile strikes failed")
    for line in plan.report[:2]:
        game.message("Opening", line)


def turn_one_lines(game: Game) -> list[str]:
    """The opening estimate and the BDA report, for the turn 1 briefing."""
    if not opening_turn(game):
        return []
    plan = opening_of(game)
    try:
        estimate = opening_estimate(game) if game.war_state.intel_enabled(game) else []
    except Exception:
        logging.exception("Could not build the opening estimate")
        estimate = []
    return estimate + plan.report
