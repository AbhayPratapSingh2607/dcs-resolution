"""Chooses the units that dress a player FARP.

Everything comes from the owning faction's unit lists, so the FARP matches its
nationality and whatever mod units the faction lists:

* Soldiers and the MANPAD team are picked from the faction's infantry like the
  front line's infantry squads: at random, weighted by each unit's spawn weight.
  A faction without any falls back to the Georgian M4.
* The parked transport is one of the faction's transport aircraft, preferring a
  type the coalition has a squadron of. (Usually it's the aircraft that actually
  flew the equipment in; see TgoGenerator._layout_types.)

Ground units use the faction's ground unit liveries, like everywhere else.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Type

from dcs import helicopters, planes, vehicles
from dcs.unittype import FlyingType, UnitType as DcsUnitType, VehicleType

from game.ato.flighttype import FlightType
from game.data.units import UnitClass

if TYPE_CHECKING:
    from game.coalition import Coalition

#: Used when the faction lists nothing that fits the role.
DEFAULTS: dict[str, Type[DcsUnitType]] = {
    "soldier": vehicles.Infantry.Soldier_M4_GRG,
    "manpad": vehicles.Infantry.Soldier_M4_GRG,
    "transport_plane": planes.C_130,
    "fatcow_helicopter": helicopters.CH_47Fbl1,
}

#: FARP soldiers swapped for a look-alike. Soldier M4 and M249 have DCS's
#: seasonal liveries, which DCS picks by the mission date alone (winter camo in a
#: snowless December desert); the Georgian M4 ("Infantry M4 Georgia") has none.
SOLDIER_SUBSTITUTES: dict[Type[DcsUnitType], Type[DcsUnitType]] = {
    vehicles.Infantry.Soldier_M4: vehicles.Infantry.Soldier_M4_GRG,
    vehicles.Infantry.Soldier_M249: vehicles.Infantry.Soldier_M4_GRG,
}

#: Infantry roles and the faction unit class that fills them.
INFANTRY_ROLES = {"soldier": UnitClass.INFANTRY, "manpad": UnitClass.MANPAD}

#: Roles filled by aircraft, and whether that aircraft is a helicopter.
AIRCRAFT_ROLES = {"transport_plane": False, "fatcow_helicopter": True}


@dataclass(frozen=True)
class FarpUnit:
    dcs_type: Type[DcsUnitType]
    livery: Optional[str] = None


class FarpUnitSet:
    def __init__(self, coalition: Coalition) -> None:
        self.coalition = coalition
        self.faction = coalition.faction

    def unit_for(self, role: str, key: str = "") -> FarpUnit:
        """The unit for a role. For infantry, key seeds the random pick, so
        each position of a FARP gets the same soldier every mission."""
        if role in AIRCRAFT_ROLES:
            return self._aircraft_for(role)
        return self._infantry_for(role, key)

    def _infantry_for(self, role: str, key: str) -> FarpUnit:
        choices = sorted(
            (
                unit
                for unit in self.faction.infantry_with_class(INFANTRY_ROLES[role])
                if issubclass(unit.dcs_unit_type, VehicleType)
            ),
            key=lambda u: u.variant_id,
        )
        if not choices:
            dcs_type = DEFAULTS[role]
        else:
            weights = [unit.spawn_weight for unit in choices]
            if not any(weights):
                weights = [1] * len(choices)
            pick = random.Random(key).choices(choices, weights=weights)[0]
            dcs_type = pick.dcs_unit_type
        if role == "soldier":
            dcs_type = SOLDIER_SUBSTITUTES.get(dcs_type, dcs_type)
        return FarpUnit(dcs_type, self._ground_livery(dcs_type))

    def _ground_livery(self, dcs_type: Type[DcsUnitType]) -> Optional[str]:
        overrides = self.faction.liveries_overrides_ground_forces.get(dcs_type.id)
        if overrides:
            return overrides[0]
        return None

    def _aircraft_for(self, role: str) -> FarpUnit:
        helicopter = AIRCRAFT_ROLES[role]
        transports = [
            aircraft
            for aircraft in self.faction.aircraft
            if aircraft.helicopter == helicopter
            and aircraft.capable_of(FlightType.TRANSPORT)
        ]
        flown = {
            squadron.aircraft.dcs_unit_type
            for squadron in self.coalition.air_wing.iter_squadrons()
        }
        transports.sort(key=lambda a: (a.dcs_unit_type not in flown, a.variant_id))
        if not transports:
            return FarpUnit(DEFAULTS[role])
        return self.aircraft_unit(transports[0].dcs_unit_type)

    def aircraft_unit(self, dcs_type: Type[FlyingType]) -> FarpUnit:
        """A static aircraft of this type, in a coalition squadron's livery."""
        for squadron in self.coalition.air_wing.iter_squadrons():
            if squadron.aircraft.dcs_unit_type is dcs_type and squadron.livery:
                return FarpUnit(dcs_type, squadron.livery)
        return FarpUnit(dcs_type)
