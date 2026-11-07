"""Loadout rules mods put on their pylons.

DCS mods can declare that a store on one station needs particular stores on
others (the mission editor's "required" rule), e.g. the Armed Blackhawk
submod's Seahawk fuel tanks only fit the MH-60R airframe. pydcs doesn't export
these rules, so mods that need them register them here, together with an
optional adapter that rewrites payloads made for an older version of the mod.

Payloads here are plain station -> CLSID maps.
"""

from __future__ import annotations

from typing import Callable, ClassVar, Optional

Requirement = tuple[int, str]
Payload = dict[int, str]


class PylonRules:
    _rules: ClassVar[dict[str, dict[tuple[int, str], list[Requirement]]]] = {}
    _adapters: ClassVar[dict[str, Callable[[Payload], Payload]]] = {}
    _mod_stations: ClassVar[dict[str, set[int]]] = {}

    @classmethod
    def declare_mod_stations(cls, aircraft_id: str, stations: set[int]) -> None:
        """Stations the aircraft only has while an optional mod is enabled.
        Payloads using them are hidden, and the stations dropped, while it isn't."""
        cls._mod_stations.setdefault(aircraft_id, set()).update(stations)

    @classmethod
    def mod_stations(cls, aircraft_id: str) -> set[int]:
        return cls._mod_stations.get(aircraft_id, set())

    @classmethod
    def register(
        cls,
        aircraft_id: str,
        rules: dict[tuple[int, str], list[Requirement]],
        adapter: Optional[Callable[[Payload], Payload]] = None,
    ) -> None:
        cls._rules[aircraft_id] = rules
        if adapter is not None:
            cls._adapters[aircraft_id] = adapter

    @classmethod
    def unregister(cls, aircraft_id: str) -> None:
        cls._rules.pop(aircraft_id, None)
        cls._adapters.pop(aircraft_id, None)

    @classmethod
    def has_rules(cls, aircraft_id: str) -> bool:
        return aircraft_id in cls._rules or aircraft_id in cls._adapters

    @classmethod
    def requirements(
        cls, aircraft_id: str, station: int, clsid: str
    ) -> list[Requirement]:
        return cls._rules.get(aircraft_id, {}).get((station, clsid), [])

    @classmethod
    def apply(cls, aircraft_id: str, payload: Payload) -> Payload:
        """Adapts the payload, then drops stores whose rules aren't met (which can
        in turn break others' rules, so until nothing changes)."""
        adapter = cls._adapters.get(aircraft_id)
        if adapter is not None:
            payload = adapter(dict(payload))
        return cls._drop_unmet(aircraft_id, payload)

    @classmethod
    def select(
        cls, aircraft_id: str, payload: Payload, station: int, clsid: Optional[str]
    ) -> Payload:
        """Loads a store the way the mission editor does: the stores it needs are
        loaded with it (and those stores' own needs), and stores elsewhere whose
        needs are no longer met are removed. None empties the station."""
        payload = dict(payload)
        if clsid is None:
            payload.pop(station, None)
            return cls._drop_unmet(aircraft_id, payload)
        payload[station] = clsid
        pending = [(station, clsid)]
        while pending:
            loaded_station, loaded = pending.pop()
            for required_station, required in cls.requirements(
                aircraft_id, loaded_station, loaded
            ):
                if payload.get(required_station) != required:
                    payload[required_station] = required
                    pending.append((required_station, required))
        return cls._drop_unmet(aircraft_id, payload)

    @classmethod
    def _drop_unmet(cls, aircraft_id: str, payload: Payload) -> Payload:
        """Drops stores whose rules aren't met (which can in turn break others'
        rules, so until nothing changes)."""
        rules = cls._rules.get(aircraft_id)
        if not rules:
            return payload
        payload = dict(payload)
        changed = True
        while changed:
            changed = False
            for station, clsid in list(payload.items()):
                for required_station, required in rules.get((station, clsid), []):
                    loaded = payload.get(required_station, "<CLEAN>")
                    if loaded != required:
                        del payload[station]
                        changed = True
                        break
        return payload
