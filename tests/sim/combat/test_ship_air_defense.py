"""Short-ranged ships (fast attack craft, patrol boats) have guns and MANPADS,
not a radar SAM: as TELARs they were HARM targets, and in fast forward the
Growlers sank the IRGCN boats an anti-ship package was planned against."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dcs.ships import REZKY

from game.sim.combat.model.profiles import AirDefenseGuidance, _derive_air_defense
from pydcs_extensions.iranmilitaryassetspack.iranmilitaryassetspack import (
    IranFAC_MG,
    IranFAC_MG_AShM,
)


def _unit(dcs_type: Any) -> Any:
    return SimpleNamespace(type=dcs_type, unit_type=None)


def test_fast_attack_craft_are_not_emitters() -> None:
    manpads = _derive_air_defense(_unit(IranFAC_MG), None)
    gun = _derive_air_defense(_unit(IranFAC_MG_AShM), None)
    assert manpads is not None and manpads.guidance is AirDefenseGuidance.IR
    assert gun is not None and gun.guidance is AirDefenseGuidance.GUN
    assert not manpads.emitter and not gun.emitter


def test_a_frigate_keeps_its_radar_sam() -> None:
    frigate = _derive_air_defense(_unit(REZKY), None)
    assert frigate is not None and frigate.emitter


class _Rng:
    """Doesn't shut down for the ARM (0.9 > emcon), then hits (0.0)."""

    def __init__(self) -> None:
        self.draws = iter([0.9, 0.0])

    def random(self) -> float:
        return next(self.draws)

    def choice(self, items: list[Any]) -> Any:
        return items[0]


def test_an_arm_silences_a_ship_without_sinking_it() -> None:
    from datetime import datetime
    from unittest.mock import MagicMock

    from game.sim.combat.model.airdefense import SHIP_RADAR_OUT, fire_arms

    now = datetime(2005, 4, 26, 19, 30)
    ship = SimpleNamespace(type=REZKY, unit_type="REZKY")
    site = SimpleNamespace(
        launchers=[],
        tgo=SimpleNamespace(id=1, name="LOBSTER"),
        dark_until=None,
        radar_units=lambda: [ship],
    )
    model = MagicMock()
    model.lethality = 1.0
    airframe = SimpleNamespace(skill=1.0, flight=MagicMock(), name="Growler 1")
    store = SimpleNamespace(
        remaining=1, profile=SimpleNamespace(accuracy=1.0, name="AGM-88C")
    )
    assert fire_arms(model, site, [(airframe, store)], now, MagicMock(), _Rng())  # type: ignore[arg-type]
    model.results.kill_theater_unit.assert_not_called()
    assert site.dark_until == now + SHIP_RADAR_OUT
