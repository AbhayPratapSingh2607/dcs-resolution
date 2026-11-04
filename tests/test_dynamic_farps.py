"""Tests for player-established FARPs and helicopter detachments."""

from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from typing import Any, Iterator, cast
from unittest.mock import MagicMock

import pytest
from dcs.mapping import Point
from dcs.terrain import Caucasus

from game.ato import FlightType
from game.farps import FarpManager
from game.settings import Settings
from game.sim import GameUpdateEvents
from game.squadrons import Pilot, Squadron
from game.squadrons.detachments import (
    create_detachment,
    destroy_detachment,
    detachment_errors,
    detachments_at,
    max_detachment_size,
    recall_detachment,
)
from game.theater import ParkingType, Player
from game.theater.dynamicfarp import DynamicFarp, FarpKind
from game.point_with_heading import PointWithHeading
from game.utils import Heading

TERRAIN = Caucasus()
ALL_PARKING = ParkingType(True, True, True)


class FakeAirWing:
    def __init__(self) -> None:
        self.squadrons: dict[Any, list[Squadron]] = defaultdict(list)

    def add_squadron(self, squadron: Squadron) -> None:
        self.squadrons[squadron.aircraft].append(squadron)

    def iter_squadrons(self) -> Iterator[Squadron]:
        for squadrons in list(self.squadrons.values()):
            yield from list(squadrons)


def make_world() -> SimpleNamespace:
    settings = Settings()
    # These tests cover detachments arriving instantly, which is what the instant
    # transfer cheat does; without it they fly to the FARP over a turn.
    settings.enable_transfer_cheat = True
    game = SimpleNamespace(settings=settings, turn=1, messages=[])
    game.message = lambda title, text="": game.messages.append(title)
    coalition = SimpleNamespace(
        player=Player.BLUE,
        game=game,
        air_wing=FakeAirWing(),
        ato=SimpleNamespace(packages=[]),
        budget=1000.0,
    )
    coalition.adjust_budget = lambda amount: setattr(
        coalition, "budget", coalition.budget + amount
    )
    game.blue = coalition
    game.red = SimpleNamespace(ato=SimpleNamespace(packages=[]))
    return SimpleNamespace(game=game, coalition=coalition, settings=settings)


def make_farp(
    world: SimpleNamespace,
    kind: FarpKind = FarpKind.WET_WING,
    capacity: int = 4,
    name: str = "FARP Viper",
) -> DynamicFarp:
    farp = DynamicFarp(
        name,
        Point(0, 0, TERRAIN),
        Heading.from_degrees(90),
        cast(Any, MagicMock()),
        Player.BLUE,
        kind,
        capacity,
        established_turn=1,
    )
    farp._coalition = cast(Any, world.coalition)
    return farp


def make_helicopter_type() -> Any:
    aircraft: Any = MagicMock()
    aircraft.helicopter = True
    aircraft.lha_capable = False
    aircraft.capable_of.return_value = True
    aircraft.__str__.return_value = "AH-64D"
    return aircraft


def make_squadron(
    world: SimpleNamespace, location: Any, aircraft: Any, owned: int = 8
) -> Squadron:
    squadron = Squadron(
        name="1-227th",
        nickname=None,
        country=cast(Any, MagicMock()),
        role="Attack",
        aircraft=aircraft,
        max_size=12,
        livery=None,
        livery_set=[],
        primary_task=FlightType.CAS,
        auto_assignable_mission_types={FlightType.CAS, FlightType.TRANSPORT},
        radio_presets={},
        operating_bases=cast(Any, MagicMock()),
        female_pilot_percentage=0,
        pilot_pool=[],
        coalition=cast(Any, world.coalition),
        flight_db=cast(Any, MagicMock()),
        settings=world.settings,
        location=location,
    )
    pilots = [Pilot(f"Pilot {i}") for i in range(owned)]
    squadron.current_roster.extend(pilots)
    squadron.available_pilots.extend(pilots)
    squadron.owned_aircraft = owned
    squadron.untasked_aircraft = owned
    world.coalition.air_wing.add_squadron(squadron)
    return squadron


def make_home_base() -> Any:
    base = MagicMock()
    base.is_dynamic_farp = False
    base.unclaimed_parking.return_value = 100
    return base


# DynamicFarp


def test_wet_wing_layout() -> None:
    world = make_world()
    farp = make_farp(world, capacity=4)
    assert len(farp.helipads_quad) == 1
    assert not farp.helipads_invisible
    assert farp.total_aircraft_parking(ALL_PARKING) == 4
    assert not farp.can_deploy_ground_units
    assert farp.is_dynamic_farp
    assert not farp.is_fat_cow


def test_wet_wing_extra_capacity_uses_single_pads() -> None:
    world = make_world()
    farp = make_farp(world, capacity=6)
    assert len(farp.helipads_quad) == 1
    assert len(farp.helipads_invisible) == 2
    assert farp.total_aircraft_parking(ALL_PARKING) == 6


def test_fat_cow_layout() -> None:
    from game.theater.dynamicfarp import FATCOW_LAYOUT

    world = make_world()
    farp = make_farp(world, FarpKind.FAT_COW, capacity=2)
    assert farp.is_fat_cow
    assert not farp.helipads_quad
    # Fat Cow layout (FARP faces east): the two pads sit side by side 100m aft,
    # 35m left (north) and 35m right (south) of the centerline.
    pads = farp.helipads_invisible
    assert (round(pads[0].x), round(pads[0].y)) == (35, -100)
    assert (round(pads[1].x), round(pads[1].y)) == (-35, -100)
    assert pads[0].heading == pads[1].heading
    assert farp.total_aircraft_parking(ALL_PARKING) == 2
    # Like the Wet Wing, it can rearm as well as refuel.
    assert any(obj.role == "ammo" for obj in FATCOW_LAYOUT)


def test_wet_wing_costs_more_than_fat_cow() -> None:
    world = make_world()
    manager = manager_with_farp(world, make_farp(world))
    settings = world.settings
    assert manager.deploy_cost(FarpKind.WET_WING) > manager.deploy_cost(
        FarpKind.FAT_COW
    )
    wet_wing = make_farp(world, FarpKind.WET_WING)
    fat_cow = make_farp(world, FarpKind.FAT_COW, capacity=2)
    assert wet_wing.upkeep_per_turn == settings.wet_wing_farp_upkeep
    assert fat_cow.upkeep_per_turn == settings.fat_cow_farp_upkeep
    assert wet_wing.upkeep_per_turn > fat_cow.upkeep_per_turn
    # The only other difference is how many helicopters they hold.
    assert manager.capacity(FarpKind.WET_WING) > manager.capacity(FarpKind.FAT_COW)


# Detachments


def test_create_detachment_moves_aircraft_and_pilots() -> None:
    world = make_world()
    farp = make_farp(world)
    parent = make_squadron(world, make_home_base(), make_helicopter_type())

    det = create_detachment(parent, farp, 2)

    assert det.parent is parent
    assert det.location is farp
    assert det.owned_aircraft == det.untasked_aircraft == 2
    assert parent.owned_aircraft == parent.untasked_aircraft == 6
    assert len(det.current_roster) == 2
    assert len(parent.current_roster) == 6
    assert detachments_at(farp) == [det]
    assert farp.unclaimed_parking(ALL_PARKING) == 2


def test_detachment_prefers_player_pilots() -> None:
    world = make_world()
    farp = make_farp(world)
    parent = make_squadron(world, make_home_base(), make_helicopter_type())
    player_pilot = parent.available_pilots[-1]
    player_pilot.player = True

    det = create_detachment(parent, farp, 1)

    assert det.current_roster == [player_pilot]


def test_second_detachment_from_same_parent_reinforces() -> None:
    world = make_world()
    farp = make_farp(world)
    parent = make_squadron(world, make_home_base(), make_helicopter_type())

    first = create_detachment(parent, farp, 1)
    second = create_detachment(parent, farp, 2)

    assert first is second
    assert first.owned_aircraft == 3
    assert len(detachments_at(farp)) == 1


def test_detachment_limits() -> None:
    world = make_world()
    farp = make_farp(world, FarpKind.FAT_COW, capacity=2)
    parent = make_squadron(world, make_home_base(), make_helicopter_type())

    assert max_detachment_size(parent, farp) == 2
    assert detachment_errors(parent, farp, 3)
    with pytest.raises(ValueError):
        create_detachment(parent, farp, 3)

    # Any helicopter can go to any FARP, whatever tasks it flies.
    gunship = make_helicopter_type()
    gunship.capable_of.side_effect = lambda task: task is FlightType.CAS
    apaches = make_squadron(world, make_home_base(), gunship)
    assert max_detachment_size(apaches, farp) == 2

    # FARPs are still helicopter-only.
    plane = make_helicopter_type()
    plane.helicopter = False
    jets = make_squadron(world, make_home_base(), plane)
    assert max_detachment_size(jets, farp) == 0


def test_detachment_cannot_buy_and_keeps_its_tasks() -> None:
    world = make_world()
    farp = make_farp(world, FarpKind.FAT_COW, capacity=2)
    parent = make_squadron(world, make_home_base(), make_helicopter_type())

    det = create_detachment(parent, farp, 2)

    assert not det.has_aircraft_capacity_for(1)
    assert det.replenish_count == 0
    assert det.capable_of(FlightType.CAS)
    assert det.capable_of(FlightType.TRANSPORT)
    assert det.auto_assignable_mission_types == parent.auto_assignable_mission_types


def test_recall_detachment_restores_parent() -> None:
    world = make_world()
    farp = make_farp(world)
    parent = make_squadron(world, make_home_base(), make_helicopter_type())
    det = create_detachment(parent, farp, 3)

    recall_detachment(det)

    assert parent.owned_aircraft == parent.untasked_aircraft == 8
    assert len(parent.current_roster) == 8
    assert len(parent.available_pilots) == 8
    assert det not in list(world.coalition.air_wing.iter_squadrons())


def test_destroyed_detachment_loses_aircraft_but_pilots_return() -> None:
    world = make_world()
    farp = make_farp(world)
    parent = make_squadron(world, make_home_base(), make_helicopter_type())
    det = create_detachment(parent, farp, 3)

    destroy_detachment(det)

    assert parent.owned_aircraft == 5
    assert parent.destroyed_aircraft == 3
    assert len(parent.current_roster) == 8


def test_cannot_relocate_squadron_to_farp() -> None:
    world = make_world()
    farp = make_farp(world)
    parent = make_squadron(world, make_home_base(), make_helicopter_type())
    with pytest.raises(RuntimeError):
        parent.plan_relocation(farp, MagicMock())


# FarpManager


def manager_with_farp(world: SimpleNamespace, farp: DynamicFarp) -> FarpManager:
    world.game.theater = SimpleNamespace(controlpoints=[farp])
    world.game.compute_threat_zones = lambda events: None
    return FarpManager(cast(Any, world.coalition))


def test_dismantle_returns_detachments_and_emits_delete() -> None:
    world = make_world()
    farp = make_farp(world)
    manager = manager_with_farp(world, farp)
    parent = make_squadron(world, make_home_base(), make_helicopter_type())
    create_detachment(parent, farp, 2)

    events = GameUpdateEvents()
    manager.dismantle(farp, events)

    assert farp not in world.game.theater.controlpoints
    assert farp.id in events.deleted_control_points
    assert parent.owned_aircraft == 8


def test_end_turn_charges_upkeep_and_fat_cows_do_not_expire() -> None:
    world = make_world()
    farp = make_farp(world, FarpKind.FAT_COW, capacity=2)
    manager = manager_with_farp(world, farp)

    for turn in range(2, 12):
        world.game.turn = turn
        manager.end_turn(GameUpdateEvents())

    assert world.coalition.budget == 1000 - 10 * world.settings.fat_cow_farp_upkeep
    assert farp in world.game.theater.controlpoints


def make_base(position: Point, friendly: bool) -> Any:
    base = MagicMock()
    base.is_dynamic_farp = False
    base.is_offmap = False
    base.is_fleet = False
    base.captured.is_neutral = False
    base.position = position
    base.is_friendly.return_value = friendly
    return base


def test_end_turn_evacuates_overrun_farps_of_both_types() -> None:
    for kind in FarpKind:
        world = make_world()
        farp = make_farp(world, kind, capacity=2)
        manager = manager_with_farp(world, farp)
        # The nearest base is now an enemy one: the FARP has been overrun.
        world.game.theater.controlpoints.append(
            make_base(Point(1000, 0, TERRAIN), friendly=False)
        )

        manager.end_turn(GameUpdateEvents())

        assert farp not in world.game.theater.controlpoints, kind


def test_farp_limit_is_shared_by_both_types() -> None:
    world = make_world()
    world.settings.max_farps = 2
    wet_wing = make_farp(world, FarpKind.WET_WING)
    fat_cow = make_farp(world, FarpKind.FAT_COW, capacity=2, name="FARP Cobra")
    manager = manager_with_farp(world, wet_wing)
    world.game.theater.controlpoints.append(fat_cow)
    world.game.theater.is_on_land = lambda point: True
    world.game.theater.ground_objects = []
    world.game.theater.conflicts = lambda: []

    for kind in FarpKind:
        reasons = manager.check_site(Point(100_000, 0, TERRAIN), kind).reasons
        assert "Limit of 2 FARP(s) reached." in reasons, kind


def test_end_turn_abandons_farps_when_broke() -> None:
    world = make_world()
    farp = make_farp(world, FarpKind.FAT_COW, capacity=2)
    manager = manager_with_farp(world, farp)
    world.coalition.budget = 5

    manager.end_turn(GameUpdateEvents())

    assert farp not in world.game.theater.controlpoints


def test_farp_destroyed_when_all_fuel_depots_killed() -> None:
    world = make_world()
    farp = make_farp(world, capacity=6)
    manager = manager_with_farp(world, farp)
    depots = FarpManager.fuel_depot_names(farp)
    assert depots == {
        "FARP Viper FARP 0_fuel object",
        "FARP Viper Invisible FARP 0_fuel object",
        "FARP Viper Invisible FARP 1_fuel object",
    }

    manager.commit_losses(list(depots)[:2], GameUpdateEvents())
    assert farp in world.game.theater.controlpoints

    manager.commit_losses(list(depots), GameUpdateEvents())
    assert farp not in world.game.theater.controlpoints


def test_fat_cow_destroyed_when_its_fuel_is_killed() -> None:
    world = make_world()
    farp = make_farp(world, FarpKind.FAT_COW, capacity=2)
    manager = manager_with_farp(world, farp)
    assert FarpManager.fuel_depot_names(farp) == {
        "FARP Viper fatcow apfc_fuel object",
        "FARP Viper fatcow fuel object",
    }

    manager.commit_losses(["FARP Viper fatcow fuel object"], GameUpdateEvents())
    assert farp in world.game.theater.controlpoints

    manager.commit_losses(
        ["FARP Viper fatcow fuel object", "FARP Viper fatcow apfc_fuel object"],
        GameUpdateEvents(),
    )
    assert farp not in world.game.theater.controlpoints


# Real aircraft data


@pytest.fixture
def _real_aircraft_data(tmp_path: Any) -> None:
    from game import persistency

    import pydcs_extensions  # noqa: F401  (registers modded aircraft with pydcs)

    persistency.setup(str(tmp_path), prefer_liberation_payloads=False, port=16884)


def test_every_helicopter_can_go_to_either_farp(_real_aircraft_data: None) -> None:
    from game.dcs.aircrafttype import AircraftType

    helicopters = [a for a in AircraftType.iter_all() if a.helicopter]
    names = {a.display_name for a in helicopters}
    # Stock and modded helicopters, including attack helicopters.
    assert {"AH-64D Apache Longbow", "UH-60L", "OH-6A Cayuse"} <= names

    for kind in FarpKind:
        for aircraft in helicopters:
            world = make_world()
            farp = make_farp(world, kind, capacity=2)
            parent = make_squadron(world, make_home_base(), aircraft)
            errors = detachment_errors(parent, farp, 1)
            assert errors == [], f"{kind} {aircraft.display_name}: {errors}"
            det = create_detachment(parent, farp, 1)
            for task in FlightType:
                assert det.capable_of(task) == aircraft.capable_of(task)


def test_loading_rederives_pads_from_current_layout() -> None:
    """A FARP saved with an older pad layout gets pads matching the current
    layout (and so its props) when the save is loaded."""
    world = make_world()
    farp = make_farp(world, FarpKind.FAT_COW, capacity=2)
    expected = [(round(p.x), round(p.y)) for p in farp.helipads_invisible]

    state = dict(farp.__dict__)
    # Older saves: stale pad positions, no stored capacity, and a Fat Cow expiry.
    state["helipads_invisible"] = [
        PointWithHeading.from_point(Point(0, 0, TERRAIN), Heading.from_degrees(90)),
        PointWithHeading.from_point(Point(0, -100, TERRAIN), Heading.from_degrees(90)),
    ]
    del state["capacity"]
    state["expires_on_turn"] = 4

    loaded = DynamicFarp.__new__(DynamicFarp)
    loaded.__setstate__(state)

    assert loaded.capacity == 2
    assert [(round(p.x), round(p.y)) for p in loaded.helipads_invisible] == expected
    assert not hasattr(loaded, "expires_on_turn")


def test_lua_string_quotes_farp_names() -> None:
    from game.missiongenerator.tgogenerator import _lua_string

    assert _lua_string("FARP Viper manpad") == '"FARP Viper manpad"'
    # A quote and a backslash in the name are both escaped.
    assert _lua_string(r'a"b\c') == r'"a\"b\\c"'


def test_detachment_is_listed_after_its_parent() -> None:
    world = make_world()
    farp = make_farp(world)
    aircraft = make_helicopter_type()
    parent = make_squadron(world, make_home_base(), aircraft)
    other = make_squadron(world, make_home_base(), aircraft)

    det = create_detachment(parent, farp, 2)

    assert list(world.coalition.air_wing.iter_squadrons()) == [parent, det, other]
