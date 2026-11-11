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
