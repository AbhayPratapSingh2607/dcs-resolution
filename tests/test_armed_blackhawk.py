"""The optional Armed Blackhawk submod for the UH-60L mod."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from game import persistency

from game.ato.loadouts import Loadout
from game.data.weapons import Weapon
from game.dcs.aircrafttype import AircraftType
from game.dcs.pylonrules import PylonRules
from pydcs_extensions.uh60l.armedblackhawk import (
    adapt_payload,
    eject_armed_blackhawk,
    inject_armed_blackhawk,
)
from pydcs_extensions.uh60l.uh60l import UH_60L, UH_60L_DAP


@pytest.fixture(autouse=True)
def _persistency(tmp_path: Path) -> None:
    # AircraftType reads the unit data files, which need the saved-games folder.
    persistency.setup(str(tmp_path), prefer_liberation_payloads=False, port=16884)


@pytest.fixture
def submod() -> Iterator[None]:
    inject_armed_blackhawk()
    try:
        yield
    finally:
        eject_armed_blackhawk()


def weapon(clsid: str) -> Weapon:
    found = Weapon.with_clsid(clsid)
    assert found is not None, clsid
    return found


def test_submod_adds_airframe_and_wing_stations_and_removes_them_again() -> None:
    base = {aircraft: set(aircraft.pylons) for aircraft in (UH_60L, UH_60L_DAP)}
    inject_armed_blackhawk()
    try:
        for aircraft in (UH_60L, UH_60L_DAP):
            assert set(aircraft.pylons) == base[aircraft] | {8, 9}
            assert hasattr(aircraft, "Pylon8")
            assert PylonRules.has_rules(aircraft.id)
    finally:
        eject_armed_blackhawk()
    for aircraft in (UH_60L, UH_60L_DAP):
        assert set(aircraft.pylons) == base[aircraft]
        assert not hasattr(aircraft, "Pylon8")
        assert not PylonRules.has_rules(aircraft.id)


def test_base_mod_wing_removal_moves_to_the_esss_station() -> None:
    transport = {1: "<CLEAN>", 2: "<CLEAN>", 4: "{UH60_SEAT_CARGO_ALL}", 6: "<CLEAN>"}

    assert adapt_payload(transport) == {4: "{UH60_SEAT_CARGO_ALL}", 9: "<CLEAN>"}
    armed = {2: "{UH60_M230_LEFT}", 6: "{UH60_M230_RIGHT}"}
    assert adapt_payload(armed) == armed


def test_stores_whose_rules_are_not_met_are_dropped(submod: None) -> None:
    # Seahawk tanks need the MH-60R airframe and each other.
    payload = {
        2: "{SEAHAWK_FUEL_TANK_120}",
        6: "{SEAHAWK_FUEL_TANK_120}",
        8: "{AB_MH60J}",
        9: "<CLEAN>",
    }
    assert PylonRules.apply(UH_60L.id, payload) == {8: "{AB_MH60J}", 9: "<CLEAN>"}

    payload[8] = "{AB_60R}"
    assert PylonRules.apply(UH_60L.id, payload) == payload

    # Dropping one tank breaks the other's rule too.
    del payload[6]
    assert PylonRules.apply(UH_60L.id, payload) == {8: "{AB_60R}", 9: "<CLEAN>"}


def test_airframe_is_an_ordinary_station_choice(submod: None) -> None:
    uh60 = AircraftType.named("UH-60L")
    seahawk = Loadout(
        "MH-60R Seahawk",
        {
            2: weapon("{SEAHAWK_FUEL_TANK_120}"),
            6: weapon("{SEAHAWK_FUEL_TANK_120}"),
            8: weapon("{AB_60R}"),
            9: weapon("<CLEAN>"),
        },
        date=None,
    )

    final = seahawk.for_aircraft(uh60)

    assert {n: w.clsid for n, w in final.pylons.items() if w is not None} == {
        2: "{SEAHAWK_FUEL_TANK_120}",
        6: "{SEAHAWK_FUEL_TANK_120}",
        8: "{AB_60R}",
        9: "<CLEAN>",
    }


def test_stores_another_airframe_needs_are_dropped(submod: None) -> None:
    uh60 = AircraftType.named("UH-60L")
    loadout = Loadout(
        "test",
        {
            2: weapon("{SEAHAWK_FUEL_TANK_120}"),
            6: weapon("{SEAHAWK_FUEL_TANK_120}"),
            3: weapon("{UH60L_M134_GUNNER}"),
            8: weapon("{AB_MH60J}"),
            9: weapon("<CLEAN>"),
        },
        date=None,
    )

    final = loadout.for_aircraft(uh60)

    assert {n: w.clsid for n, w in final.pylons.items() if w is not None} == {
        3: "{UH60L_M134_GUNNER}",
        8: "{AB_MH60J}",
        9: "<CLEAN>",
    }


def test_submod_stations_are_dropped_while_it_is_disabled() -> None:
    uh60 = AircraftType.named("UH-60L")
    assert PylonRules.mod_stations(UH_60L.id) == {8, 9}
    loadout = Loadout(
        "MH-60J Jayhawk",
        {3: weapon("{UH60L_M134_GUNNER}"), 8: weapon("{AB_MH60J}")},
        date=None,
    )

    final = loadout.for_aircraft(uh60)

    assert {n: w.clsid for n, w in final.pylons.items() if w is not None} == {
        3: "{UH60L_M134_GUNNER}"
    }


def test_loading_a_store_loads_what_it_needs_like_the_mission_editor(
    submod: None,
) -> None:
    uh60 = AircraftType.named("UH-60L")
    loadout = Loadout("Custom", {3: weapon("{UH60L_M134_GUNNER}")}, date=None)

    changed = loadout.load_store(uh60, 2, weapon("{SEAHAWK_FUEL_TANK_120}"))

    # The other tank, the MH-60R airframe, and (for the airframe) no stub wings.
    assert changed == {6, 8, 9}
    assert {n: w.clsid for n, w in loadout.pylons.items() if w is not None} == {
        2: "{SEAHAWK_FUEL_TANK_120}",
        3: "{UH60L_M134_GUNNER}",
        6: "{SEAHAWK_FUEL_TANK_120}",
        8: "{AB_60R}",
        9: "<CLEAN>",
    }


def test_changing_a_store_removes_the_ones_that_needed_it(submod: None) -> None:
    uh60 = AircraftType.named("UH-60L")
    loadout = Loadout("Custom", {}, date=None)
    loadout.load_store(uh60, 2, weapon("{SEAHAWK_FUEL_TANK_120}"))
    loadout.pylon_settings[6] = {"some": "setting"}

    changed = loadout.load_store(uh60, 8, weapon("{AB_MH60J}"))

    assert changed == {2, 6}
    assert {n: w.clsid for n, w in loadout.pylons.items() if w is not None} == {
        8: "{AB_MH60J}",
        9: "<CLEAN>",
    }
    assert 6 not in loadout.pylon_settings

    # Emptying a tank's station takes the other tank with it too.
    loadout.load_store(uh60, 2, weapon("{SEAHAWK_FUEL_TANK_120}"))
    assert loadout.load_store(uh60, 6, None) == {2}
    assert loadout.pylons[2] is None


def test_loading_stores_without_rules_changes_nothing_else() -> None:
    uh60 = AircraftType.named("UH-60L")
    loadout = Loadout("Custom", {3: weapon("{UH60L_M134_GUNNER}")}, date=None)

    assert loadout.load_store(uh60, 7, weapon("{UH60L_M134_GUNNER}")) == set()
    assert loadout.pylons[3] == weapon("{UH60L_M134_GUNNER}")
