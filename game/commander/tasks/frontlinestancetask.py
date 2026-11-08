from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from game.commander.tasks.theatercommandertask import TheaterCommanderTask
from game.commander.theaterstate import TheaterState
from game.ground_forces.combat_stance import CombatStance
from game.theater import FrontLine

if TYPE_CHECKING:
    from game.coalition import Coalition
    from game.theater.player import Player


class FrontLineStanceTask(TheaterCommanderTask, ABC):
    def __init__(self, front_line: FrontLine, player: Player) -> None:
        self.front_line = front_line
        self.friendly_cp = self.front_line.control_point_friendly_to(player)
        self.enemy_cp = self.front_line.control_point_hostile_to(player)

    @property
    @abstractmethod
    def stance(self) -> CombatStance: ...

    @staticmethod
    def management_allowed(state: TheaterState) -> bool:
        return (
            not state.context.coalition.player.is_blue
            or state.context.settings.automate_front_line_stance
        )

    def better_stance_already_set(self, state: TheaterState) -> bool:
        current_stance = state.front_line_stances[self.front_line]
        if current_stance is None:
            return False
        preference = (
            CombatStance.RETREAT,
            CombatStance.DEFENSIVE,
            CombatStance.AMBUSH,
            CombatStance.AGGRESSIVE,
            CombatStance.ELIMINATION,
            CombatStance.BREAKTHROUGH,
        )
        current_rating = preference.index(current_stance)
        new_rating = preference.index(self.stance)
        return current_rating >= new_rating

    @property
    @abstractmethod
    def have_sufficient_front_line_advantage(self) -> bool: ...

    @property
    def ground_force_balance(self) -> float:
        # TODO: Planned CAS missions should reduce the expected opposing force size.
        friendly_forces = float(self.friendly_cp.deployable_front_line_units)
        enemy_forces = float(self.enemy_cp.deployable_front_line_units)
        game = self.friendly_cp.coalition.game
        war_state = getattr(game, "war_state", None)
        if war_state is not None:
            # Commanders judge the enemy from intelligence estimates, and their
            # own troops by how well they will actually fight.
            if war_state.intel_enabled(game) and enemy_forces > 0:
                from game.warfare.intel import estimate_count

                player = self.friendly_cp.captured
                picture = war_state.picture(game, player)
                rng = war_state.rng(game, f"stance:{self.enemy_cp.id}")
                enemy_forces = float(
                    estimate_count(int(enemy_forces), picture.isr, rng)
                )
            if war_state.morale_enabled(game):
                friendly_forces *= 0.5 + 0.67 * war_state.morale.front(self.friendly_cp)
                enemy_forces *= 0.5 + 0.67 * war_state.morale.front(self.enemy_cp)
        if enemy_forces == 0:
            return math.inf
        return friendly_forces / enemy_forces

    def preconditions_met(self, state: TheaterState) -> bool:
        if not self.management_allowed(state):
            return False
        if self.better_stance_already_set(state):
            return False
        if self.friendly_cp.deployable_front_line_units == 0:
            return False
        if self.warned_of_offensive() and self.stance in (
            CombatStance.AGGRESSIVE,
            CombatStance.ELIMINATION,
            CombatStance.BREAKTHROUGH,
        ):
            # Intelligence warns of an enemy attack: unless overwhelmingly
            # stronger, receive it from prepared positions.
            if self.ground_force_balance < 2.0:
                return False
        return self.have_sufficient_front_line_advantage

    def warned_of_offensive(self) -> bool:
        game = self.friendly_cp.coalition.game
        war_state = getattr(game, "war_state", None)
        if war_state is None or not war_state.intel_enabled(game):
            return False
        from game.warfare.agencies import expects_offensive

        return expects_offensive(
            game, war_state, self.friendly_cp.captured, self.enemy_cp, self.friendly_cp
        )

    def apply_effects(self, state: TheaterState) -> None:
        state.front_line_stances[self.front_line] = self.stance

    def execute(self, coalition: Coalition) -> None:
        self.friendly_cp.stances[self.enemy_cp.id] = self.stance
