"""Fire missions in the DCS mission (game.warfare.firemissions).

Each fire mission timed inside the mission gets a FireAtPoint task on its
launcher's group, pushed by a trigger at the mission's time: ships fire
Tomahawks, missile sites their Scuds, and the front line's artillery groups
their rounds (split over the side's artillery groups at that front). The
mission is then marked IN_MISSION, so the combat model leaves it to DCS.

Missions before the mission start were already resolved by the combat model.
Missions after the mission window, or whose launcher isn't in the mission
(culled, not generated), stay PLANNED and are resolved by the combat model.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING

from dcs.action import AITaskPush
from dcs.condition import TimeAfter
from dcs.mapping import Point as DcsPoint
from dcs.task import FireAtPoint, WeaponType
from dcs.triggers import Event, TriggerOnce

from game.warfare.firemissions import (
    FireMission,
    FireStatus,
    LauncherKind,
    enabled,
    missions_this_turn,
    target_of,
)

if TYPE_CHECKING:
    from dcs import Mission
    from dcs.unitgroup import Group

    from game import Game

#: Spread of the impact points around the target, meters.
CRUISE_RADIUS = 30
BALLISTIC_RADIUS = 150
ARTILLERY_RADIUS = 120


class FireMissionGenerator:
    def __init__(
        self,
        mission: Mission,
        game: Game,
        start: datetime,
        artillery: Optional[dict[tuple[str, bool], list[Group]]] = None,
    ) -> None:
        self.mission = mission
        self.game = game
        self.start = start
        #: The front lines' artillery groups, by (front line name, is blue).
        self.artillery = artillery or {}

    @property
    def end(self) -> datetime:
        from game.sim.atoperiod import window

        bounds = window(self.game)
        if bounds is not None:
            return max(bounds[1], self.start)
        return self.start + self.game.settings.desired_player_mission_duration

    def generate(self) -> list[FireMission]:
        if not enabled(self.game):
            return []
        given: list[FireMission] = []
        for mission in missions_this_turn(self.game):
            if mission.status is FireStatus.IN_MISSION:
                # A regenerated mission (Take off again after an abort).
                mission.status = FireStatus.PLANNED
            if mission.status is not FireStatus.PLANNED:
                continue
            if not self.start <= mission.time <= self.end:
                continue
            target = target_of(self.game, mission)
            if target is None:
                continue
            try:
                if self._give(mission, target):
                    mission.status = FireStatus.IN_MISSION
                    given.append(mission)
            except Exception:
                logging.exception(f"Could not give fire mission {mission.id} to DCS")
        if given:
            logging.info(f"{len(given)} fire missions given to the DCS mission")
        return given

    def _groups(self, mission: FireMission) -> list[Group]:
        if mission.kind is LauncherKind.ARTILLERY:
            key = mission.launcher_key
            front = key[len("front:") : key.rindex(":")]
            return list(self.artillery.get((front, mission.player_blue), []))
        name = mission.launcher_key.split(":", 1)[1]
        group = self.mission.find_group(name)
        return [group] if group is not None else []

    def _give(self, mission: FireMission, target: Any) -> bool:
        groups = self._groups(mission)
        if not groups:
            return False
        delay = max(1, int((mission.time - self.start).total_seconds()))
        point = DcsPoint(target.position.x, target.position.y, self.mission.terrain)
        if mission.kind is LauncherKind.ARTILLERY:
            per_group = max(1, mission.rounds // len(groups))
            for group in groups:
                self._fire(
                    group, point, per_group, ARTILLERY_RADIUS, None, delay, mission
                )
            return True
        if mission.kind is LauncherKind.SHIP:
            self._fire(
                groups[0],
                point,
                mission.rounds,
                CRUISE_RADIUS,
                WeaponType.CruiseMissile,
                delay,
                mission,
            )
        else:
            self._fire(
                groups[0], point, mission.rounds, BALLISTIC_RADIUS, None, delay, mission
            )
        return True

    def _fire(
        self,
        group: Group,
        point: DcsPoint,
        rounds: int,
        radius: int,
        weapon: Optional[WeaponType],
        delay: int,
        mission: FireMission,
    ) -> None:
        task = FireAtPoint(point, rounds, radius)
        if weapon is not None:
            task.params["weaponType"] = weapon.value
        group.add_trigger_action(task)
        trigger = TriggerOnce(
            Event.NoEvent, f"Fire mission {mission.target_name} #{group.id}"
        )
        trigger.add_condition(TimeAfter(seconds=delay))
        trigger.add_action(AITaskPush(group.id, len(group.tasks)))
        self.mission.triggerrules.triggers.append(trigger)


def planned_missile_groups(game: Game) -> set[str]:
    """Missile site groups with a fire mission this turn: their random fire
    task (TgoGenerator) is replaced by the planned one."""
    return {
        m.launcher_key.split(":", 1)[1]
        for m in missions_this_turn(game)
        if m.kind is LauncherKind.MISSILE and m.status is not FireStatus.CANCELLED
    }


def fires_in_mission(game: Game, tgo: Any) -> bool:
    """Whether one of the ground object's groups has a fire mission timed
    inside the DCS window: it is kept in the mission (not culled) to fire it."""
    from game.sim.atoperiod import window
    from game.warfare.firemissions import FirePlan

    if not isinstance(getattr(game, "fire_plan", None), FirePlan):
        return False
    if not enabled(game) or not missions_this_turn(game):
        return False
    bounds = window(game)
    if bounds is None:
        return False
    names = {f"group:{g.group_name}" for g in tgo.groups}
    return any(
        m.launcher_key in names
        and m.status in (FireStatus.PLANNED, FireStatus.IN_MISSION)
        and bounds[0] <= m.time <= bounds[1]
        for m in missions_this_turn(game)
    )
