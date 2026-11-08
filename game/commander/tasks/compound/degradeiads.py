from collections.abc import Iterator
from dataclasses import dataclass
from typing import Union

from game.commander.tasks.primitive.antiship import PlanAntiShip
from game.commander.tasks.primitive.dead import PlanDead
from game.commander.tasks.primitive.strike import PlanStrike
from game.commander.theaterstate import TheaterState
from game.data.groups import GroupTask
from game.htn import CompoundTask, Method
from game.theater.theatergroundobject import IadsGroundObject, NavalGroundObject
from game.warfare.iads import dependency_targets


@dataclass(frozen=True)
class DegradeIads(CompoundTask[TheaterState]):
    #: Only the opening rollback: the network's nodes and the long and medium
    #: range SAMs nearest the main effort.
    rollback_only: bool = False

    def each_valid_method(self, state: TheaterState) -> Iterator[Method[TheaterState]]:
        # Doctrines that practise decapitation go for the network first: command
        # centres, comms and power that the threatening SAMs depend on.
        if self.decapitation(state):
            game = state.context.coalition.game
            sites = [
                s
                for s in state.threatening_air_defenses
                if isinstance(s, IadsGroundObject)
            ] or [
                s
                for s in state.enemy_air_defenses
                if s.task in [GroupTask.LORAD, GroupTask.MERAD]
            ]
            for node in dependency_targets(game, sites):
                if node in state.strike_targets:
                    yield [PlanStrike(node)]

        for air_defense in state.threatening_air_defenses:
            yield [self.plan_against(air_defense)]

        if self.rollback_only:
            rollback = sorted(
                [
                    tgo
                    for tgo in state.enemy_air_defenses
                    if tgo.task in [GroupTask.LORAD, GroupTask.MERAD]
                ],
                key=lambda x: (
                    state.priority_cp.distance_to(x) if state.priority_cp else 0
                ),
            )
            for air_defense in rollback[:2]:
                yield [self.plan_against(air_defense)]
            return

        prioritized_air_defenses = sorted(
            [
                tgo
                for tgo in state.enemy_air_defenses
                if tgo.task in [GroupTask.LORAD, GroupTask.MERAD]
            ],
            key=lambda x: (state.priority_cp.distance_to(x) if state.priority_cp else 0)
            - x.max_threat_range().meters,
        )

        for air_defense in prioritized_air_defenses:
            yield [self.plan_against(air_defense)]
        for detector in state.detecting_air_defenses:
            yield [self.plan_against(detector)]

    @staticmethod
    def decapitation(state: TheaterState) -> bool:
        from game.warfare.doctrine import for_faction_obj

        coalition = state.context.coalition
        return for_faction_obj(coalition.faction).decapitation

    @staticmethod
    def plan_against(
        target: Union[IadsGroundObject, NavalGroundObject],
    ) -> Union[PlanDead, PlanAntiShip]:
        if isinstance(target, IadsGroundObject):
            return PlanDead(target)
        return PlanAntiShip(target)
