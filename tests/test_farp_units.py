"""Tests for choosing the units that dress player FARPs."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Type, cast

from dcs import helicopters, planes, vehicles
from dcs.unittype import FlyingType, UnitType as DcsUnitType

from game.data.units import UnitClass
from game.missiongenerator.farpunits import (
    DESERT,
    WOODLAND,
    FarpUnitSet,
    scenery_for,
)
from game.theater import Player
from game.theater.farpterrain import SiteTerrain, UNKNOWN_SITE
from pydcs_extensions.usamilitaryassetspack.usamilitaryassetspack import (
    CH_USInfantry_FIM92,
    CH_USInfantry_M4,
)


def ground(dcs_type: Type[DcsUnitType], unit_class: UnitClass) -> Any:
    return SimpleNamespace(
        dcs_unit_type=dcs_type, unit_class=unit_class, variant_id=dcs_type.id
    )


def aircraft(dcs_type: Type[FlyingType], transport: bool = True) -> Any:
    return SimpleNamespace(
        dcs_unit_type=dcs_type,
        variant_id=dcs_type.id,
        helicopter=dcs_type.helicopter,
        capable_of=lambda task: transport,
    )


def make_coalition(
    player: Player,
    ground_units: list[Any],
    aircraft_types: list[Any],
    squadrons: list[Any] | None = None,
) -> Any:
    faction = SimpleNamespace(accessible_units=ground_units, aircraft=aircraft_types)
    air_wing = SimpleNamespace(iter_squadrons=lambda: iter(squadrons or []))
    return cast(Any, SimpleNamespace(player=player, faction=faction, air_wing=air_wing))


def test_mod_units_are_preferred_when_the_faction_has_them() -> None:
    coalition = make_coalition(
        Player.BLUE,
        [
            ground(vehicles.Infantry.Soldier_M4, UnitClass.INFANTRY),
            ground(CH_USInfantry_M4, UnitClass.INFANTRY),
            ground(vehicles.AirDefence.Soldier_stinger, UnitClass.MANPAD),
            ground(CH_USInfantry_FIM92, UnitClass.MANPAD),
        ],
        [],
    )
    units = FarpUnitSet(coalition, WOODLAND)

    assert units.unit_for("soldier").dcs_type is CH_USInfantry_M4
    assert units.unit_for("manpad").dcs_type is CH_USInfantry_FIM92


def test_scenery_picks_matching_variant() -> None:
    coalition = make_coalition(
        Player.BLUE,
        [
            ground(vehicles.Infantry.Soldier_M4_GRG, UnitClass.INFANTRY),
            ground(vehicles.Infantry.Soldier_M4, UnitClass.INFANTRY),
        ],
        [],
    )

    desert = FarpUnitSet(coalition, DESERT).unit_for("soldier")
    woodland = FarpUnitSet(coalition, WOODLAND).unit_for("soldier")

    assert desert.dcs_type is vehicles.Infantry.Soldier_M4
    assert woodland.dcs_type is vehicles.Infantry.Soldier_M4_GRG


def test_red_faction_uses_its_own_transports() -> None:
    coalition = make_coalition(
        Player.RED,
        [ground(vehicles.AirDefence.SA_18_Igla_manpad, UnitClass.MANPAD)],
        [aircraft(planes.IL_76MD), aircraft(helicopters.Mi_26)],
    )
    units = FarpUnitSet(coalition, WOODLAND)

    assert units.unit_for("transport_plane").dcs_type is planes.IL_76MD
    assert units.unit_for("fatcow_helicopter").dcs_type is helicopters.Mi_26
    assert units.unit_for("manpad").dcs_type is vehicles.AirDefence.SA_18_Igla_manpad


def test_falls_back_to_side_defaults() -> None:
    blue = FarpUnitSet(make_coalition(Player.BLUE, [], []), WOODLAND)
    red = FarpUnitSet(make_coalition(Player.RED, [], []), WOODLAND)

    assert blue.unit_for("transport_plane").dcs_type is planes.C_130
    assert blue.unit_for("fatcow_helicopter").dcs_type is helicopters.CH_47Fbl1
    assert blue.unit_for("soldier").dcs_type is vehicles.Infantry.Soldier_M4
    assert blue.unit_for("manpad").dcs_type is vehicles.AirDefence.Soldier_stinger
    assert red.unit_for("soldier").dcs_type is vehicles.Infantry.Paratrooper_AKS_74
    assert red.unit_for("manpad").dcs_type is vehicles.AirDefence.SA_18_Igla_S_manpad


def test_unlisted_faction_transport_is_used() -> None:
    # A transport helicopter not in the candidate list, and a non-transport one.
    coalition = make_coalition(
        Player.BLUE,
        [],
        [aircraft(helicopters.AH_64D_BLK_II, False), aircraft(helicopters.UH_1H)],
    )

    unit = FarpUnitSet(coalition, WOODLAND).unit_for("fatcow_helicopter")

    assert unit.dcs_type is helicopters.UH_1H


def test_aircraft_use_squadron_livery() -> None:
    squadron = SimpleNamespace(
        aircraft=SimpleNamespace(dcs_unit_type=planes.C_130), livery="RAF"
    )
    coalition = make_coalition(
        Player.BLUE, [], [aircraft(planes.C_130)], squadrons=[squadron]
    )

    unit = FarpUnitSet(coalition, WOODLAND).unit_for("transport_plane")

    assert unit.dcs_type is planes.C_130
    assert unit.livery == "RAF"


def test_scenery_from_site_or_theater() -> None:
    arid = SiteTerrain(known=True, steep=False, built_up=False, arid=True)
    green = SiteTerrain(known=True, steep=False, built_up=False, arid=False)

    assert scenery_for(arid, WOODLAND) == DESERT
    assert scenery_for(green, DESERT) == WOODLAND
    assert scenery_for(UNKNOWN_SITE, DESERT) == DESERT
