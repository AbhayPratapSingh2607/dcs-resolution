from collections.abc import Iterator
from dataclasses import dataclass

from game.commander.tasks.primitive.recon import PlanRecon
from game.commander.theaterstate import TheaterState
from game.htn import CompoundTask, Method


@dataclass(frozen=True)
class ReconnoiterTargets(CompoundTask[TheaterState]):
    def each_valid_method(self, state: TheaterState) -> Iterator[Method[TheaterState]]:
        for target in state.recon_targets:
            yield [PlanRecon(target)]
