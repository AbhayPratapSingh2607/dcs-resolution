"""Fire missions: cruise missile, ballistic missile and artillery strikes planned
for a regular turn (after the opening salvo of turn 0).

A fire mission is a launcher, a target, a number of rounds and a time in the
turn's 6 hour period. Launchers come from what the side has in the campaign:

* **cruise missile ships**: Ticonderoga cruisers and Arleigh Burke destroyers
  fire Tomahawks, 8 a ship per turn, out to 1000 km;
* **missile sites**: Scud launchers (300 km) and V-1 ramps (250 km), one
  round a launcher per turn;
* **artillery**: the side's artillery on a front line, 10 rounds a gun per
  turn, at targets within reach of its firing positions behind the front.

There is no stock to track: each launcher fires up to its capacity each turn.

A mission whose time falls inside the DCS mission is fired by DCS: the mission
generator gives the launcher's group a timed FireAtPoint and marks the mission
IN_MISSION (game.missiongenerator.firemissiongenerator). Every other mission
(before the DCS window, after it, the whole turn fought by the combat model, or
a launcher not in the mission) is resolved by the combat model at its time
(``FireMissionSimulation``), and whatever is still pending when the turn's
results are committed is resolved then (``resolve_pending``).

The player plans blue's in the Fire Missions window; red's commander plans its
own each turn (``plan_ai_fire_missions``). On turn 1 red's counter-strike
follows the strategic surprise (game.opening.COUNTER_STRIKE_SHARE).
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Iterator, Optional, TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from game import Game
    from game.sim.gameupdateevents import GameUpdateEvents
    from game.sim.simulationresults import SimulationResults
    from game.theater import ControlPoint, MissionTarget
    from game.theater.frontline import FrontLine
    from game.theater.player import Player
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.theater.theatergroup import TheaterGroup


class LauncherKind(Enum):
    SHIP = "Cruise missile ship"
    MISSILE = "Missile site"
    ARTILLERY = "Artillery"


class FireStatus(Enum):
    PLANNED = "Planned"
    #: Given to DCS: the mission generator gave the launcher its fire task.
    IN_MISSION = "In the DCS mission"
    FIRED = "Fired"
    #: The launcher was gone (destroyed, out of range) when it was due.
    CANCELLED = "Cancelled"


#: DCS unit type id: (rounds per unit per turn, range in meters, weapon).
SHIP_LAUNCHERS = {
    "TICONDEROG": (8, 1_000_000, "Tomahawk"),
    "USS_Arleigh_Burke_IIa": (8, 1_000_000, "Tomahawk"),
}
MISSILE_LAUNCHERS = {
    "Scud_B": (1, 300_000, "Scud"),
    "v1_launcher": (1, 250_000, "V-1"),
}
#: Rounds a front-line artillery piece fires per turn.
ARTILLERY_ROUNDS_PER_GUN = 10

#: Hit chance per missile against a point target, before air defenses.
CRUISE_HIT = 0.8
#: Scuds are inaccurate (CEP of hundreds of meters).
BALLISTIC_HIT = 0.3
#: Expected units killed per artillery round against a site.
ARTILLERY_KILL_PER_ROUND = 0.05
#: Hits that close a runway.
RUNWAY_HITS = 2

#: Default time of a new mission: this long after the DCS window opens, so
#: it is fired in the mission you fly.
DEFAULT_DELAY = timedelta(minutes=10)

#: Weight of each target class for the commander's choice
#: (game.opening.SALVO_WEIGHT plus front-line targets for artillery).
TARGET_WEIGHT = {
    "c2_node": 3.0,
    "ewr": 2.5,
    "sam_lorad": 2.5,
    "sam_merad": 2.2,
    "airfield": 2.0,
    "power": 2.0,
    "sam_shorad": 1.6,
    "fuel": 1.5,
    "ammo": 1.5,
    "armor": 1.4,
    "factory": 1.0,
    "building": 0.7,
}


# ----------------------------------------------------------------- launchers


@dataclass(frozen=True)
class Launcher:
    """Something that can fire this turn. Derived from the game each time."""

    key: str
    kind: LauncherKind
    name: str
    position: Any
    range_m: float
    #: Rounds it can fire per turn.
    capacity: int
    weapon: str
    player: Any
    #: The DCS group that fires (ships and missile sites).
    group_name: Optional[str] = None
    #: Artillery: the front line and the side's artillery types there.
    front: Any = None

    @property
    def label(self) -> str:
        return f"{self.name} ({self.kind.value}, {self.capacity} {self.weapon})"


def _alive_units(group: TheaterGroup, table: dict[str, tuple[int, int, str]]) -> list:
    return [u for u in group.units if u.alive and getattr(u.type, "id", None) in table]


def _group_launchers(
    game: Game,
    player: Player,
    kind: LauncherKind,
    table: dict[str, tuple[int, int, str]],
) -> Iterator[Launcher]:
    for cp in game.theater.control_points_for(player):
        for tgo in cp.ground_objects:
            if tgo.is_dead:
                continue
            for group in tgo.groups:
                units = _alive_units(group, table)
                if not units:
                    continue
                per, reach, weapon = table[units[0].type.id]
                yield Launcher(
                    key=f"group:{group.group_name}",
                    kind=kind,
                    name=tgo.name if len(tgo.groups) == 1 else group.name,
                    position=units[0].position,
                    range_m=float(reach),
                    capacity=per * len(units),
                    weapon=weapon,
                    player=player,
                    group_name=group.group_name,
                )


def artillery_reach(threat_range: float) -> float:
    """How far past the front an artillery piece reaches from where the front
    line generator places it (game.missiongenerator.flotgenerator: 16-18 km
    back when its range allows, else with the tanks, about 3 km back)."""
    placed = 17_000 if threat_range - 7500 > 18_000 else 3_000
    return max(0.0, threat_range - placed)


def _artillery_launchers(game: Game, player: Player) -> Iterator[Launcher]:
    from game.data.units import UnitClass

    for front in game.theater.conflicts():
        cp = front.blue_cp if player.is_blue else front.red_cp
        if cp is None or cp.captured != player:
            continue
        guns = 0
        reach = 0.0
        for unit_type, count in cp.base.armor.items():
            if unit_type.unit_class is not UnitClass.ARTILLERY or count <= 0:
                continue
            threat = float(getattr(unit_type.dcs_unit_type, "threat_range", 0) or 0)
            guns += count
            reach = max(reach, artillery_reach(threat))
        if guns <= 0 or reach <= 0:
            continue
        yield Launcher(
            key=f"front:{front.name}:{'blue' if player.is_blue else 'red'}",
            kind=LauncherKind.ARTILLERY,
            name=f"Artillery at {front.name}",
            position=front.position,
            range_m=reach,
            capacity=guns * ARTILLERY_ROUNDS_PER_GUN,
            weapon="rounds",
            player=player,
            front=front,
        )


def launchers(game: Game, player: Player) -> list[Launcher]:
    found: list[Launcher] = []
    found.extend(_group_launchers(game, player, LauncherKind.SHIP, SHIP_LAUNCHERS))
    found.extend(
        _group_launchers(game, player, LauncherKind.MISSILE, MISSILE_LAUNCHERS)
    )
    found.extend(_artillery_launchers(game, player))
    return found


def launcher_by_key(game: Game, player: Player, key: str) -> Optional[Launcher]:
    for launcher in launchers(game, player):
        if launcher.key == key:
            return launcher
    return None


# ------------------------------------------------------------------- missions


@dataclass
class FireMission:
    player_blue: bool
    turn: int
    launcher_key: str
    launcher_name: str
    kind: LauncherKind
    weapon: str
    #: The target: a ground object or an airfield, by id.
    target_id: Any
    target_name: str
    rounds: int
    time: datetime
    status: FireStatus = FireStatus.PLANNED
    #: Planned by the commander rather than the player.
    auto: bool = False
    id: UUID = field(default_factory=uuid4)
    #: What happened, once resolved.
    result: str = ""

    @property
    def side(self) -> str:
        return "blue" if self.player_blue else "red"


@dataclass
class FirePlan:
    missions: list[FireMission] = field(default_factory=list)

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update({"missions": [], **state})


def fire_plan_of(game: Game) -> FirePlan:
    plan = getattr(game, "fire_plan", None)
    if plan is None:
        plan = FirePlan()
        game.fire_plan = plan  # type: ignore[attr-defined]
    return plan


def missions_this_turn(
    game: Game, player: Optional[Player] = None
) -> list[FireMission]:
    turn = getattr(game, "turn", 0)
    return [
        m
        for m in fire_plan_of(game).missions
        if m.turn == turn and (player is None or m.player_blue == player.is_blue)
    ]


def drop_old_missions(game: Game) -> None:
    plan = fire_plan_of(game)
    turn = getattr(game, "turn", 0)
    plan.missions = [m for m in plan.missions if m.turn >= turn]


def rounds_planned(
    game: Game, launcher_key: str, exclude: Optional[FireMission] = None
) -> int:
    return sum(
        m.rounds
        for m in missions_this_turn(game)
        if m.launcher_key == launcher_key
        and m is not exclude
        and m.status is not FireStatus.CANCELLED
    )


def rounds_left(
    game: Game, launcher: Launcher, exclude: Optional[FireMission] = None
) -> int:
    return max(0, launcher.capacity - rounds_planned(game, launcher.key, exclude))


def enabled(game: Game) -> bool:
    return bool(getattr(game.settings, "fire_missions", True))


def period_bounds(game: Game) -> tuple[datetime, datetime]:
    from game.sim.atoperiod import period

    bounds = period(game)
    if bounds is not None:
        return bounds
    start = game.conditions.start_time
    return start, start + game.settings.desired_player_mission_duration


def default_time(game: Game) -> datetime:
    from game.sim.atoperiod import window

    bounds = window(game)
    start = bounds[0] if bounds is not None else game.conditions.start_time
    return start + DEFAULT_DELAY


# -------------------------------------------------------------------- targets


def _find_target(game: Game, target_id: Any) -> Optional[MissionTarget]:
    for cp in game.theater.controlpoints:
        if cp.id == target_id:
            return cp
        for tgo in cp.ground_objects:
            if tgo.id == target_id:
                return tgo
    return None


def target_class_of(target: MissionTarget) -> str:
    from game.theater import ControlPoint

    if isinstance(target, ControlPoint):
        return "airfield"
    try:
        from game.commander.jfacc.targetclass import classify

        return classify(target)[1]
    except Exception:
        return "building"


def _knows(game: Game, player: Player, tgo: TheaterGroundObject) -> bool:
    try:
        if not game.war_state.intel_enabled(game):
            return True
        return bool(game.war_state.picture(game, player).knows(tgo))
    except Exception:
        return True


def targets_for(game: Game, launcher: Launcher) -> list[tuple[float, MissionTarget]]:
    """Enemy targets the launcher can reach, nearest first, as (distance, target).
    Only what the side's intelligence knows of; artillery doesn't fire at
    airfields."""
    from game.theater import ControlPoint
    from game.theater.controlpoint import ControlPointType
    from game.warfare.intel import is_mobile

    player = launcher.player
    found: list[tuple[float, MissionTarget]] = []
    for cp in game.theater.control_points_for(player.opponent):
        if cp.cptype is ControlPointType.OFF_MAP:
            continue
        if (
            launcher.kind is not LauncherKind.ARTILLERY
            and isinstance(cp, ControlPoint)
            and not cp.is_fleet
            and cp.runway_is_destroyable
        ):
            distance = launcher.position.distance_to_point(cp.position)
            if distance <= launcher.range_m:
                found.append((distance, cp))
        for tgo in cp.ground_objects:
            if tgo.is_dead or tgo.sea_object:
                # Land attack weapons: ships are left to anti-ship strikes.
                continue
            if launcher.kind is not LauncherKind.ARTILLERY and is_mobile(tgo):
                # Missiles are fired at fixed points; mobile sites move.
                continue
            if not _knows(game, player, tgo):
                continue
            distance = launcher.position.distance_to_point(tgo.position)
            if distance <= launcher.range_m:
                found.append((distance, tgo))
    found.sort(key=lambda f: f[0])
    return found


def unreachable_reason(
    game: Game, player: Player, target: MissionTarget
) -> Optional[str]:
    """Why no launcher of the side can fire at the target, or None when one can."""
    from game.theater import ControlPoint
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.warfare.intel import is_mobile

    found = launchers(game, player)
    if not found:
        return (
            "Your side has no cruise missile ships, missile sites or front-line "
            "artillery."
        )
    if any(t is target for l in found for _, t in targets_for(game, l)):
        return None
    name = getattr(target, "name", "This target")
    if isinstance(target, TheaterGroundObject):
        if target.sea_object:
            return f"{name} is at sea: fire missions are land attack only."
        if not _knows(game, player, target):
            return f"Intelligence hasn't located {name}, so nothing can be aimed at it."
    artillery = [l for l in found if l.kind is LauncherKind.ARTILLERY]
    missiles = [l for l in found if l.kind is not LauncherKind.ARTILLERY]

    def nearest(group: list[Launcher]) -> str:
        best = min(group, key=lambda l: l.position.distance_to_point(target.position))
        km = best.position.distance_to_point(target.position) / 1000
        return f"{best.name} is {km:.0f} km away (reach {best.range_m / 1000:.0f} km)"

    if isinstance(target, TheaterGroundObject) and is_mobile(target):
        reason = (
            f"{name} is a mobile site: cruise missiles and ballistic missiles are "
            "fired at fixed points, so only front-line artillery can hit it"
        )
        if artillery:
            return f"{reason}, and none is in reach: {nearest(artillery)}."
        return f"{reason}, and your side has no artillery at a front line."
    if isinstance(target, ControlPoint) and not missiles:
        return "Artillery doesn't fire at airfields, and your side has no missiles."
    return f"Out of reach: {nearest(found)}."


def plan_mission(
    game: Game,
    launcher: Launcher,
    target: MissionTarget,
    rounds: int,
    time: Optional[datetime] = None,
    auto: bool = False,
) -> FireMission:
    rounds = max(1, min(rounds, rounds_left(game, launcher)))
    mission = FireMission(
        player_blue=launcher.player.is_blue,
        turn=game.turn,
        launcher_key=launcher.key,
        launcher_name=launcher.name,
        kind=launcher.kind,
        weapon=launcher.weapon,
        target_id=target.id,
        target_name=target.name,
        rounds=rounds,
        time=time if time is not None else default_time(game),
        auto=auto,
    )
    fire_plan_of(game).missions.append(mission)
    return mission


def remove_mission(game: Game, mission: FireMission) -> None:
    plan = fire_plan_of(game)
    if mission in plan.missions:
        plan.missions.remove(mission)


def target_of(game: Game, mission: FireMission) -> Optional[MissionTarget]:
    return _find_target(game, mission.target_id)


def strike_labels(game: Game) -> dict[Any, list[str]]:
    """Planned strikes by target id, for the map: the opening salvo on turn 0,
    this turn's blue fire missions after that (red's are not shown)."""
    labels: dict[Any, list[str]] = {}
    if getattr(game, "turn", 0) == 0:
        from game.opening import missile_strikes_enabled, planned_salvo

        if missile_strikes_enabled(game):
            for shot in planned_salvo(game):
                labels.setdefault(shot.target.id, []).append(
                    f"Opening salvo: {shot.missiles} cruise missiles"
                )
        return labels
    for mission in missions_this_turn(game):
        if not mission.player_blue or mission.status is FireStatus.CANCELLED:
            continue
        verb = "Fired" if mission.status is FireStatus.FIRED else "Fire mission"
        labels.setdefault(mission.target_id, []).append(
            f"{verb} {mission.time:%H:%M}: {mission.rounds} {mission.weapon} "
            f"from {mission.launcher_name}"
        )
    return labels


# ----------------------------------------------------------- the commander


#: Share of red's launcher capacity it fires each turn after the first.
AI_SHARE = 1.0


def plan_ai_fire_missions(
    game: Game, player: Player, share: Optional[float] = None
) -> list[FireMission]:
    """The commander's fire missions: the highest value targets in reach, the
    capacity spread over the period. Red on turn 1 fires its counter-strike,
    sized by the strategic surprise."""
    if not enabled(game) or getattr(game, "turn", 0) < 1:
        return []
    if share is None:
        share = AI_SHARE
        if game.turn == 1 and not player.is_blue:
            from game.opening import COUNTER_STRIKE_SHARE, opening_of, surprise_of

            if opening_of(game).begun:
                share = COUNTER_STRIKE_SHARE[surprise_of(game)]
    if share <= 0:
        return []
    rng = random.Random(f"fire:{game.turn}:{player.is_blue}")
    start, end = period_bounds(game)
    span = max(60.0, (end - start).total_seconds() - 1800)
    planned: list[FireMission] = []
    for launcher in launchers(game, player):
        budget = int(rounds_left(game, launcher) * share)
        if budget <= 0:
            continue
        options = []
        for distance, target in targets_for(game, launcher):
            weight = TARGET_WEIGHT.get(target_class_of(target), 0.5)
            # Nearer targets first among similar ones.
            options.append((weight * (1.0 - 0.3 * distance / launcher.range_m), target))
        options.sort(key=lambda o: -o[0])
        for _, target in options:
            if budget <= 0:
                break
            if any(m.target_id == target.id for m in planned):
                continue
            rounds = min(budget, rounds_for(launcher, target))
            when = start + timedelta(seconds=rng.uniform(600, span))
            planned.append(
                plan_mission(game, launcher, target, rounds, when, auto=True)
            )
            budget -= rounds
    return planned


def rounds_for(launcher: Launcher, target: MissionTarget) -> int:
    """A sensible number of rounds at the target: two missiles a unit up to
    four (an airfield gets four, enough to cut the runway), one Scud, and up
    to 40 artillery rounds."""
    from game.theater import ControlPoint

    if launcher.kind is LauncherKind.ARTILLERY:
        return min(launcher.capacity, 40)
    if launcher.kind is LauncherKind.MISSILE:
        return 1
    if isinstance(target, ControlPoint):
        return 4
    units = sum(1 for u in getattr(target, "units", []) if u.alive)
    return max(2, min(4, units + 1))


# ------------------------------------------------------------- resolution


def _air_defense(game: Game, target: MissionTarget, player: Player) -> float:
    """Hit chance multiplier for the defender's SAMs around the target."""
    try:
        from game.commander.jfacc.iads import _radar_sams
    except Exception:
        return 1.0
    factor = 1.0
    for sam in _radar_sams(game, player.opponent):
        if sam is target or sam.is_dead:
            continue
        try:
            reach = sam.max_threat_range().meters
        except Exception:
            continue
        if sam.position.distance_to_point(target.position) <= reach:
            factor = min(factor, 0.85)
    return factor


def resolve(
    game: Game,
    mission: FireMission,
    results: SimulationResults,
    events: GameUpdateEvents,
    rng: random.Random,
) -> str:
    """Fires the mission in the combat model and records the damage in
    ``results`` (so it is committed with the turn, and undone if the turn is
    reset). Returns what happened."""
    from game.sim.combatlog import CombatDomain
    from game.theater import ControlPoint
    from game.theater.player import Player as PlayerEnum
    from game.warfare.intel import IntelSource
    from game.warfare.warstate import IntelEvent

    player = PlayerEnum.BLUE if mission.player_blue else PlayerEnum.RED
    launcher = launcher_by_key(game, player, mission.launcher_key)
    target = target_of(game, mission)
    if launcher is None or target is None:
        mission.status = FireStatus.CANCELLED
        mission.result = (
            "cancelled: the launcher is gone"
            if launcher is None
            else "cancelled: the target is gone"
        )
        _undo_status(results, mission)
        return mission.result
    if launcher.position.distance_to_point(target.position) > launcher.range_m * 1.05:
        mission.status = FireStatus.CANCELLED
        mission.result = "cancelled: out of range"
        _undo_status(results, mission)
        return mission.result

    if launcher.kind is LauncherKind.ARTILLERY:
        text = _resolve_artillery(target, mission.rounds, results, events, rng)
    else:
        p = CRUISE_HIT if launcher.kind is LauncherKind.SHIP else BALLISTIC_HIT
        if launcher.kind is LauncherKind.SHIP:
            p *= _air_defense(game, target, player)
        hits = sum(1 for _ in range(mission.rounds) if rng.random() < p)
        if isinstance(target, ControlPoint):
            text = _resolve_airfield(game, target, hits, results, rng)
        else:
            text = _resolve_site(target, hits, results, events)
        text = f"{hits} of {mission.rounds} hit; {text}"
    if not isinstance(target, ControlPoint):
        results.intel_events.append(
            IntelEvent(mission.player_blue, target.id, 0.3, IntelSource.STRIKE)
        )
    mission.status = FireStatus.FIRED
    mission.result = text
    _undo_status(results, mission)
    results.log.add(
        mission.time,
        CombatDomain.STRIKE,
        mission.side,
        f"{mission.launcher_name} fired {mission.rounds} {mission.weapon} at "
        f"{mission.target_name}: {text}",
    )
    return text


def _undo_status(results: SimulationResults, mission: FireMission) -> None:
    def restore(_events: Any) -> None:
        mission.status = FireStatus.PLANNED
        mission.result = ""

    results._undo.append(restore)


def _resolve_site(
    tgo: Any, hits: int, results: SimulationResults, events: GameUpdateEvents
) -> str:
    alive = [u for u in tgo.units if u.alive]

    def priority(unit: Any) -> int:
        name = str(getattr(unit, "name", "")).lower()
        return 0 if "radar" in name or " sr" in name or "str" in name else 1

    alive.sort(key=priority)
    killed = 0
    for unit in alive[:hits]:
        if results.kill_theater_unit(unit, events):
            killed += 1
    return f"{killed} destroyed" if killed else "no damage"


def _resolve_artillery(
    tgo: Any,
    rounds: int,
    results: SimulationResults,
    events: GameUpdateEvents,
    rng: random.Random,
) -> str:
    from game.theater import ControlPoint

    if isinstance(tgo, ControlPoint):
        return "no effect"
    alive = [u for u in tgo.units if u.alive]
    if not alive:
        return "no damage"
    expected = rounds * ARTILLERY_KILL_PER_ROUND
    kills = int(expected) + (1 if rng.random() < expected - int(expected) else 0)
    rng.shuffle(alive)
    killed = 0
    for unit in alive[: min(kills, len(alive))]:
        if results.kill_theater_unit(unit, events):
            killed += 1
    return f"{killed} destroyed" if killed else "no damage"


def _resolve_airfield(
    game: Game,
    cp: ControlPoint,
    hits: int,
    results: SimulationResults,
    rng: random.Random,
) -> str:
    from game.opening import parked_in_open

    notes = []
    if hits >= RUNWAY_HITS and cp.runway_is_destroyable and cp.runway_is_operational():
        results.damage_runway(cp)
        notes.append("runway cut")
    exposure = parked_in_open(game, cp.captured)
    parked = 0
    for _ in range(hits):
        if rng.random() >= 0.4 * exposure:
            continue
        squadrons = [s for s in cp.squadrons if s.owned_aircraft > parked]
        if not squadrons:
            break
        results.kill_parked_aircraft(rng.choice(squadrons))
        parked += 1
    if parked:
        notes.append(f"{parked} aircraft destroyed on the ground")
    return ", ".join(notes) if notes else "no damage"


class FireMissionSimulation:
    """Resolves the fire missions due in a combat model pass, at their time."""

    def __init__(self, game: Game, results: SimulationResults) -> None:
        self.game = game
        self.results = results
        self.rng = random.Random(results.seed ^ 0x5F1)

    def tick(self, time: datetime, events: GameUpdateEvents) -> None:
        if not enabled(self.game):
            return
        for mission in missions_this_turn(self.game):
            if mission.status is FireStatus.PLANNED and mission.time <= time:
                try:
                    resolve(self.game, mission, self.results, events, self.rng)
                except Exception:
                    logging.exception(f"Fire mission {mission.id} failed")
                    mission.status = FireStatus.CANCELLED


def reset_in_mission(game: Game) -> None:
    """The DCS mission was aborted: what it would have fired is planned again."""
    for mission in missions_this_turn(game):
        if mission.status is FireStatus.IN_MISSION:
            mission.status = FireStatus.PLANNED


def resolve_pending(
    game: Game, events: GameUpdateEvents, quit: Optional[datetime] = None
) -> list[FireMission]:
    """Fires what is still pending when the turn's results are committed: the
    missions after the combat model's last pass and, when the player quit DCS
    before their time (``quit``), the ones given to the mission. The damage is
    committed at once."""
    if not enabled(game):
        return []
    due = []
    for mission in missions_this_turn(game):
        if mission.status is FireStatus.PLANNED:
            due.append(mission)
        elif (
            mission.status is FireStatus.IN_MISSION
            and quit is not None
            and mission.time > quit
        ):
            mission.status = FireStatus.PLANNED
            due.append(mission)
    for mission in missions_this_turn(game):
        if mission.status is FireStatus.IN_MISSION:
            # DCS fired it; the mission's own results have the damage.
            mission.status = FireStatus.FIRED
            mission.result = "fired in the DCS mission"
    if not due:
        return []
    from game.debriefing import Debriefing
    from game.sim.missionresultsprocessor import MissionResultsProcessor
    from game.sim.simulationresults import SimulationResults
    from game.unitmap import UnitMap

    results = SimulationResults()
    rng = random.Random(results.seed ^ 0x5F2)
    for mission in sorted(due, key=lambda m: m.time):
        try:
            resolve(game, mission, results, events, rng)
        except Exception:
            logging.exception(f"Fire mission {mission.id} failed")
            mission.status = FireStatus.CANCELLED
    debriefing = Debriefing({"mission_ended": True}, game, UnitMap())
    debriefing.merge_simulation_results(results)
    MissionResultsProcessor(game).commit_resolved_period(debriefing, events)
    results.forget_undo()
    for mission in due:
        logging.info(f"Fire mission at {mission.target_name}: {mission.result}")
    return due


def summary_message(game: Game) -> None:
    """One message with what blue's fire missions did this turn."""
    from game.theater.player import Player as PlayerEnum

    lines = report_lines(game, PlayerEnum.BLUE)
    if lines:
        game.message("Fire missions", "; ".join(lines))


def report_lines(game: Game, player: Player) -> list[str]:
    """This turn's fire missions of a side, for the debrief."""
    lines = []
    for mission in sorted(missions_this_turn(game, player), key=lambda m: m.time):
        status = (
            mission.result
            if mission.status in (FireStatus.FIRED, FireStatus.CANCELLED)
            else mission.status.value.lower()
        )
        lines.append(
            f"{mission.time:%H:%M} {mission.launcher_name}: {mission.rounds} "
            f"{mission.weapon} at {mission.target_name} — {status}"
        )
    return lines
