"""Categories and grouping for the mission editor-style weapon menu."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.data.weapons import WeaponType
from qt_ui.windows.mission.flight.payload.weaponmenu import (
    AA_MISSILES,
    AG_MISSILES,
    BOMBS,
    FUEL_TANKS,
    GUIDED_BOMBS,
    PODS,
    _group_key,
    category,
    display_name,
    store_name,
)


def weapon(name: str, kind: WeaponType = WeaponType.UNKNOWN) -> Any:
    return SimpleNamespace(name=name, weapon_group=SimpleNamespace(type=kind))


def test_mod_station_prefix_and_count_are_dropped() -> None:
    atflir = weapon(
        " [ STA 05\t  | CHEEK  | TGPMNT ] - 1x AN/ASQ-228 ATFLIR - Targeting Pod"
    )

    assert display_name(atflir) == (
        "[ STA 05 | CHEEK | TGPMNT ] - 1x AN/ASQ-228 ATFLIR - Targeting Pod"
    )
    assert store_name(atflir) == "AN/ASQ-228 ATFLIR - Targeting Pod"


def test_categories() -> None:
    assert category(weapon("[ STA 01 | WNGTP ] - 1x AIM-9X Sidewinder - IR AAM")) == (
        AA_MISSILES
    )
    assert category(weapon("[ STA 04 ] - 1x FPU-12/A (480 GAL)")) == FUEL_TANKS
    assert category(weapon("AN/ASQ-228 ATFLIR - Targeting Pod")) == PODS
    assert category(weapon("[ STA 02 ] - 1x CBU-99 - 490lbs")) == BOMBS
    assert category(weapon("[ STA 03 ] - 1x GBU-38 - JDAM")) == GUIDED_BOMBS
    assert category(weapon("CATM-65K - Captive Trg Round for Mav K")) == AG_MISSILES
    # Retribution's own weapon data wins over the name.
    assert category(weapon("Some jammer", WeaponType.JAMMER)) == PODS


def test_variants_of_a_store_group_together() -> None:
    mod = weapon(
        " [ STA 05\t | CHEEK | TGPMNT ] - 1x AN/ASQ-228 ATFLIR - Targeting Pod"
    )
    stock = weapon("AN/ASQ-228 ATFLIR - Targeting Pod")
    assert _group_key(mod) == _group_key(stock)

    plain = weapon("[ STA 05 ] - 1x AIM-7P Sparrow - Semi-Active Radar")
    other = weapon("AIM-7P Sparrow Semi-Active Radar")
    assert _group_key(plain) == _group_key(other)

    ai_only = weapon("[ STA 03 ] - 1x AIM-120D AMRAAM - Active Radar AAM, (AI Only)")
    modded = weapon(
        "[ STA 03 ] - 1x AIM-120D AMRAAM - Active Radar AAM, (Mod Required)"
    )
    assert _group_key(ai_only) == _group_key(modded)
