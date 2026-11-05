"""Chooses the units that dress a player FARP.

The soldiers, MANPAD team and the transport aircraft that set up the FARP come
from the owning faction, so they match its nationality and any enabled mods
(mod units are only in a faction's lists while that mod is enabled). Where there
is a choice, units suiting the scenery at the FARP site (desert or woodland) are
preferred. The candidates are listed in resources/farp_units.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Iterable, Optional, TYPE_CHECKING, Type

import yaml
from dcs import helicopters, planes, vehicles
from dcs.unittype import FlyingType, UnitType as DcsUnitType, VehicleType

from game.ato.flighttype import FlightType
from game.data.units import UnitClass
from game.theater.farpterrain import SiteTerrain

if TYPE_CHECKING:
    from game.coalition import Coalition
    from game.dcs.aircrafttype import AircraftType
    from game.factions.faction import Faction

FARP_UNITS_PATH = Path("resources/farp_units.yaml")

DESERT = "desert"
WOODLAND = "woodland"
ANY = "any"

#: Used when the faction has none of the candidates.
SIDE_DEFAULTS: dict[str, tuple[Type[DcsUnitType], Type[DcsUnitType]]] = {
    # role: (blue, red)
    "soldier": (vehicles.Infantry.Soldier_M4, vehicles.Infantry.Paratrooper_AKS_74),
    "manpad": (
        vehicles.AirDefence.Soldier_stinger,
        vehicles.AirDefence.SA_18_Igla_S_manpad,
    ),
    "transport_plane": (planes.C_130, planes.C_130),
    "fatcow_helicopter": (helicopters.CH_47Fbl1, helicopters.CH_47Fbl1),
}

#: Roles filled by aircraft, and whether that aircraft is a helicopter.
AIRCRAFT_ROLES = {"transport_plane": False, "fatcow_helicopter": True}


@dataclass(frozen=True)
class Candidate:
    type_id: str
    scenery: str = ANY
    livery: Optional[str] = None


@dataclass(frozen=True)
class FarpUnit:
    dcs_type: Type[DcsUnitType]
    livery: Optional[str] = None


@cache
def load_candidates(path: Path = FARP_UNITS_PATH) -> dict[str, tuple[Candidate, ...]]:
    with path.open(encoding="utf-8") as f:
        data: dict[str, list[dict[str, Any]]] = yaml.safe_load(f)
    return {
        role: tuple(
            Candidate(
                str(entry["type"]),
                str(entry.get("scenery", ANY)),
                entry.get("livery"),
            )
            for entry in entries
        )
        for role, entries in data.items()
    }


def scenery_for(site: SiteTerrain, theater_scenery: str) -> str:
    """Desert or woodland, from the site's land cover when known."""
    if site.known:
        return DESERT if site.arid else WOODLAND
    return theater_scenery


def _ranked(candidates: Iterable[Candidate], scenery: str) -> list[Candidate]:
    """Candidates in listed order, with those meant for the other scenery moved
    to the end (used only when nothing else fits)."""

    def rank(candidate: Candidate) -> int:
        return 0 if candidate.scenery in (scenery, ANY) else 1

    return sorted(candidates, key=rank)


def _faction_ground_types(faction: Faction) -> dict[str, Type[VehicleType]]:
    return {
        unit.dcs_unit_type.id: unit.dcs_unit_type
        for unit in faction.accessible_units
        if issubclass(unit.dcs_unit_type, VehicleType)
    }


def _faction_aircraft(faction: Faction) -> dict[str, AircraftType]:
    return {aircraft.dcs_unit_type.id: aircraft for aircraft in faction.aircraft}


def _squadron_livery(
    coalition: Coalition, dcs_type: Type[DcsUnitType]
) -> Optional[str]:
    """The livery of a squadron in the coalition flying this aircraft type."""
    for squadron in coalition.air_wing.iter_squadrons():
        if squadron.aircraft.dcs_unit_type is dcs_type and squadron.livery:
            return squadron.livery
    return None


class FarpUnitSet:
    def __init__(self, coalition: Coalition, scenery: str) -> None:
        self.coalition = coalition
        self.faction = coalition.faction
        self.scenery = scenery
        self.candidates = load_candidates()

    def unit_for(self, role: str) -> FarpUnit:
        if role in AIRCRAFT_ROLES:
            return self._aircraft_for(role)
        return self._ground_unit_for(role)

    def _side_default(self, role: str) -> Type[DcsUnitType]:
        blue, red = SIDE_DEFAULTS[role]
        return blue if self.coalition.player.is_blue else red

    def _ground_unit_for(self, role: str) -> FarpUnit:
        available = _faction_ground_types(self.faction)
        for candidate in _ranked(self.candidates.get(role, ()), self.scenery):
            dcs_type = available.get(candidate.type_id)
            if dcs_type is not None:
                livery = candidate.livery if candidate.scenery == self.scenery else None
                return FarpUnit(dcs_type, livery)
        if role == "manpad":
            # Any MANPAD team the faction has will do.
            for unit in sorted(
                self.faction.accessible_units, key=lambda u: u.variant_id
            ):
                if unit.unit_class is UnitClass.MANPAD and issubclass(
                    unit.dcs_unit_type, VehicleType
                ):
                    return FarpUnit(unit.dcs_unit_type)
        return FarpUnit(self._side_default(role))

    def _aircraft_for(self, role: str) -> FarpUnit:
        available = _faction_aircraft(self.faction)
        dcs_type: Optional[Type[FlyingType]] = None
        livery: Optional[str] = None
        for candidate in _ranked(self.candidates.get(role, ()), self.scenery):
            aircraft = available.get(candidate.type_id)
            if aircraft is not None:
                dcs_type = aircraft.dcs_unit_type
                livery = candidate.livery
                break
        if dcs_type is None:
            # Any transport aircraft of the right kind the faction flies.
            helicopter = AIRCRAFT_ROLES[role]
            for aircraft in sorted(available.values(), key=lambda a: a.variant_id):
                if aircraft.helicopter == helicopter and aircraft.capable_of(
                    FlightType.TRANSPORT
                ):
                    dcs_type = aircraft.dcs_unit_type
                    break
        if dcs_type is None:
            return FarpUnit(self._side_default(role))
        return self.aircraft_unit(dcs_type, livery)

    def aircraft_unit(
        self, dcs_type: Type[FlyingType], livery: Optional[str] = None
    ) -> FarpUnit:
        """A static aircraft of this type, in a coalition squadron's livery."""
        return FarpUnit(dcs_type, _squadron_livery(self.coalition, dcs_type) or livery)
