"""Tests for choosing the units that dress a player FARP."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Type, cast

from dcs import helicopters, planes, vehicles
from dcs.unittype import FlyingType, UnitType as DcsUnitType

from game.data.units import UnitClass
from game.missiongenerator.farpunits import FarpUnitSet
from game.theater import Player
from pydcs_extensions.usamilitaryassetspack.usamilitaryassetspack import (
    CH_USInfantry_FIM92,
    CH_USInfantry_M2,
    CH_USInfantry_M4,
    CH_USInfantry_M120,
    CH_USInfantry_M249,
)


def ground(
    dcs_type: Type[DcsUnitType], unit_class: UnitClass, spawn_weight: int = 1
) -> Any:
    return SimpleNamespace(
        dcs_unit_type=dcs_type,
        unit_class=unit_class,
        variant_id=dcs_type.id,
        spawn_weight=spawn_weight,
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
    infantry: list[Any],
    aircraft_types: list[Any],
    squadrons: list[Any] | None = None,
    liveries: dict[str, list[str]] | None = None,
) -> Any:
    faction = SimpleNamespace(
        infantry_with_class=lambda unit_class: (
            u for u in infantry if u.unit_class is unit_class
        ),
        aircraft=aircraft_types,
        liveries_overrides_ground_forces=liveries or {},
    )
    air_wing = SimpleNamespace(iter_squadrons=lambda: iter(squadrons or []))
    return cast(Any, SimpleNamespace(player=player, faction=faction, air_wing=air_wing))


def test_infantry_comes_from_the_faction_including_mod_units() -> None:
    coalition = make_coalition(
        Player.BLUE,
        [
            ground(CH_USInfantry_M4, UnitClass.INFANTRY),
            ground(CH_USInfantry_FIM92, UnitClass.MANPAD),
        ],
        [],
    )
    units = FarpUnitSet(coalition)
    assert units.unit_for("soldier", "a").dcs_type is CH_USInfantry_M4
    assert units.unit_for("manpad", "a").dcs_type is CH_USInfantry_FIM92


def test_soldiers_are_a_weighted_mix_that_is_stable_per_position() -> None:
    coalition = make_coalition(
        Player.BLUE,
        [
            ground(CH_USInfantry_M4, UnitClass.INFANTRY, spawn_weight=9),
            ground(CH_USInfantry_M249, UnitClass.INFANTRY, spawn_weight=1),
        ],
        [],
    )
    units = FarpUnitSet(coalition)
    picks = [units.unit_for("soldier", f"crew {i}").dcs_type for i in range(50)]
    again = [units.unit_for("soldier", f"crew {i}").dcs_type for i in range(50)]

    assert picks == again
    assert picks.count(CH_USInfantry_M4) > picks.count(CH_USInfantry_M249) > 0


def test_falls_back_to_defaults_for_either_side() -> None:
    for player in (Player.BLUE, Player.RED):
        units = FarpUnitSet(make_coalition(player, [], []))

        assert units.unit_for("transport_plane").dcs_type is planes.C_130
        assert units.unit_for("fatcow_helicopter").dcs_type is helicopters.CH_47Fbl1
        assert units.unit_for("soldier").dcs_type is vehicles.Infantry.Soldier_M4_GRG
        assert units.unit_for("manpad").dcs_type is vehicles.Infantry.Soldier_M4_GRG


def test_transport_aircraft_come_from_the_faction() -> None:
    coalition = make_coalition(
        Player.BLUE,
        [],
        [aircraft(helicopters.AH_64D_BLK_II, False), aircraft(helicopters.UH_1H)],
    )

    unit = FarpUnitSet(coalition).unit_for("fatcow_helicopter")

    assert unit.dcs_type is helicopters.UH_1H


def test_transport_prefers_a_type_the_coalition_flies() -> None:
    squadron = SimpleNamespace(
        aircraft=SimpleNamespace(dcs_unit_type=planes.C_130), livery="RAF"
    )
    coalition = make_coalition(
        Player.BLUE,
        [],
        [aircraft(planes.An_26B), aircraft(planes.C_130)],
        squadrons=[squadron],
    )

    unit = FarpUnitSet(coalition).unit_for("transport_plane")

    assert unit.dcs_type is planes.C_130
    assert unit.livery == "RAF"


def test_faction_ground_liveries_take_precedence() -> None:
    coalition = make_coalition(
        Player.BLUE,
        [ground(vehicles.AirDefence.Soldier_stinger, UnitClass.MANPAD)],
        [],
        liveries={"Soldier stinger": ["desert"]},
    )
    assert FarpUnitSet(coalition).unit_for("manpad").livery == "desert"


def test_seasonal_us_soldiers_are_replaced_by_the_georgian_m4() -> None:
    coalition = make_coalition(
        Player.BLUE,
        [
            ground(vehicles.Infantry.Soldier_M4, UnitClass.INFANTRY),
            ground(vehicles.Infantry.Soldier_M249, UnitClass.INFANTRY),
        ],
        [],
    )
    units = FarpUnitSet(coalition)
    picks = {units.unit_for("soldier", f"crew {i}").dcs_type for i in range(20)}

    assert picks == {vehicles.Infantry.Soldier_M4_GRG}


def test_only_soldiers_on_foot_crew_the_farp() -> None:
    coalition = make_coalition(
        Player.BLUE,
        [
            ground(CH_USInfantry_M4, UnitClass.INFANTRY),
            ground(CH_USInfantry_M120, UnitClass.INFANTRY, spawn_weight=50),
            ground(CH_USInfantry_M2, UnitClass.INFANTRY, spawn_weight=50),
            ground(
                vehicles.Artillery.x_2B11_mortar, UnitClass.INFANTRY, spawn_weight=50
            ),
        ],
        [],
    )
    units = FarpUnitSet(coalition)
    picks = {units.unit_for("soldier", f"crew {i}").dcs_type for i in range(30)}

    assert picks == {CH_USInfantry_M4}


def test_a_faction_with_only_mortars_falls_back_to_the_georgian_m4() -> None:
    coalition = make_coalition(
        Player.RED,
        [ground(vehicles.Artillery.x_2B11_mortar, UnitClass.INFANTRY)],
        [],
    )
    unit = FarpUnitSet(coalition).unit_for("soldier", "crew")

    assert unit.dcs_type is vehicles.Infantry.Soldier_M4_GRG


def test_country_lists_its_own_infantry_only() -> None:
    from dcs.countries import USA, CombinedJointTaskForcesBlue, Georgia

    from game.missiongenerator.farpunits import country_lists

    georgian_m4 = vehicles.Infantry.Soldier_M4_GRG
    assert not country_lists(USA(), georgian_m4)
    assert country_lists(USA(), vehicles.Infantry.Soldier_M4)
    assert country_lists(Georgia(), georgian_m4)
    assert country_lists(CombinedJointTaskForcesBlue(), georgian_m4)


def test_mod_infantry_counts_as_listed() -> None:
    from dcs.countries import USA

    from game.missiongenerator.farpunits import country_lists

    assert country_lists(USA(), CH_USInfantry_M4)
