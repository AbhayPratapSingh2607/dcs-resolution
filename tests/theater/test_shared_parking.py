"""Helicopters may park on jet spots: jets can't overfill a base by counting
only the jets (Gudauta at 40/31)."""

from types import SimpleNamespace
from typing import Any

from game.theater.controlpoint import ControlPoint, ParkingType


class _Base:
    """31 spots: 25 for jets, 6 helipads; 24 jets and 16 helicopters."""

    unclaimed_parking = ControlPoint.unclaimed_parking

    def total_aircraft_parking(self, parking_type: ParkingType) -> int:
        spots = 0
        if parking_type.include_fixed_wing:
            spots += 25
        if parking_type.include_rotary_wing:
            spots += 6
        return spots

    def allocated_aircraft(self, parking_type: ParkingType) -> Any:
        total = 0 if not self.helicopters_placed else 16
        if not parking_type.include_rotary_wing:
            total = 0
        return SimpleNamespace(total=total + self.jets)

    def __init__(self, jets: int, helicopters_placed: bool) -> None:
        self.jets = jets
        self.helicopters_placed = helicopters_placed


JETS = ParkingType(fixed_wing=True, fixed_wing_stol=True)


def test_jets_see_the_spots_the_helicopters_took() -> None:
    base: Any = _Base(jets=12, helicopters_placed=True)
    # 25 jet spots less 12 jets is 13, but the base holds 31 and has 28.
    assert base.unclaimed_parking(JETS) == 3


def test_without_helicopters_the_jet_spots_count() -> None:
    base: Any = _Base(jets=12, helicopters_placed=False)
    assert base.unclaimed_parking(JETS) == 13
