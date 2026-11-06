"""Support for the Armed Blackhawk submod (v7.1.4) of the UH-60L mod.

The submod, with the ANDR0ID Weapon Pack it needs, changes both UH-60L types:

- station 8 ("ARMED BLACKHAWK") selects the airframe: MH-60J/K/R/S, HH-60G...
  It's an ordinary station in the loadout editor, and the submod's own payloads
  ("MH-60R Seahawk"...) are ordinary loadouts;
- station 9 ("ESSS") carries the stub wings; loading it with <CLEAN> removes
  them, which the base mod did with <CLEAN> on stations 1, 2, 6 and 7;
- many more stores on the other stations, some only allowed with a given
  airframe (the submod's "required" rules).

It's optional, so the stations and rules are only swapped in while a game has the
mod enabled. The pack's stores are always known to pydcs, which is harmless.
"""

from __future__ import annotations

import inspect
from typing import Any

from dcs.helicopters import HelicopterType
from dcs.weapons_data import weapon_ids

from game.dcs.pylonrules import PylonRules
from pydcs_extensions.weapon_injector import inject_weapons
from .armedblackhawk_data import REQUIREMENTS, STATIONS, WeaponsArmedBlackhawk
from .uh60l import UH_60L, UH_60L_DAP

inject_weapons(WeaponsArmedBlackhawk)

AIRCRAFT: dict[str, type[HelicopterType]] = {
    UH_60L.id: UH_60L,
    UH_60L_DAP.id: UH_60L_DAP,
}

#: Stations where the base mod used <CLEAN> to remove the stub wings.
BASE_MOD_WING_STATIONS = (1, 2, 6, 7)
AIRFRAME_STATION = 8
ESSS_STATION = 9

_base_pylons: dict[str, tuple[set[int], dict[str, Any]]] = {}

for _aircraft_id in AIRCRAFT:
    PylonRules.declare_mod_stations(_aircraft_id, {AIRFRAME_STATION, ESSS_STATION})


def _pylon_classes(aircraft: type[HelicopterType]) -> dict[str, Any]:
    return {
        name: value
        for name, value in aircraft.__dict__.items()
        if inspect.isclass(value) and name.startswith("Pylon")
    }


def _make_pylon(number: int, clsids: list[str]) -> type:
    members = {}
    for clsid in clsids:
        weapon = weapon_ids.get(clsid)
        if weapon is None:
            continue
        key = "".join(c if c.isalnum() else "_" for c in clsid).strip("_")
        members[key] = (number, weapon)
    return type(f"Pylon{number}", (), members)


def adapt_payload(pylons: dict[int, str]) -> dict[int, str]:
    """Moves the base mod's "no stub wings" (<CLEAN> on 1, 2, 6, 7) to station 9,
    the submod's equivalent. Takes and returns station -> CLSID."""
    if not any(pylons.get(n) == "<CLEAN>" for n in BASE_MOD_WING_STATIONS):
        return pylons
    adapted = {
        n: c
        for n, c in pylons.items()
        if not (n in BASE_MOD_WING_STATIONS and c == "<CLEAN>")
    }
    adapted.setdefault(ESSS_STATION, "<CLEAN>")
    return adapted


def is_injected() -> bool:
    return bool(_base_pylons)


def inject_armed_blackhawk() -> None:
    """Gives both UH-60L types the submod's stations and loadout rules."""
    if is_injected():
        return
    for aircraft_id, aircraft in AIRCRAFT.items():
        classes = _pylon_classes(aircraft)
        _base_pylons[aircraft_id] = (set(aircraft.pylons), classes)
        for name in classes:
            delattr(aircraft, name)
        for number, clsids in STATIONS[aircraft_id].items():
            setattr(aircraft, f"Pylon{number}", _make_pylon(number, clsids))
        aircraft.pylons = set(STATIONS[aircraft_id])
        PylonRules.register(
            aircraft_id,
            {
                (int(key.split(":", 1)[0]), key.split(":", 1)[1]): reqs
                for key, reqs in REQUIREMENTS[aircraft_id].items()
            },
            adapt_payload,
        )


def eject_armed_blackhawk() -> None:
    """Restores the base UH-60L mod's stations."""
    for aircraft_id, (pylons, classes) in _base_pylons.items():
        aircraft = AIRCRAFT[aircraft_id]
        for name in _pylon_classes(aircraft):
            delattr(aircraft, name)
        for name, value in classes.items():
            setattr(aircraft, name, value)
        aircraft.pylons = pylons
        PylonRules.unregister(aircraft_id)
    _base_pylons.clear()
