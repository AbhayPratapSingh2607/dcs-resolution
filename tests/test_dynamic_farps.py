"""Tests for player-established FARPs and helicopter detachments."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, cast
from unittest.mock import MagicMock

import numpy as np
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
    free_farp_slots,
    max_detachment_size,
    recall_detachment,
)
from game.theater import ParkingType, Player
from game.theater.dynamicfarp import DynamicFarp, FarpKind, farp_footprint_radius
from game.theater.farpterrain import FarpTerrain
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
    settings.enable_dynamic_farps = True
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
    world.game.theater.farp_terrain = None

    for kind in FarpKind:
        reasons = manager.check_site(Point(100_000, 0, TERRAIN), kind).reasons
        assert "Limit of 2 FARP(s) reached." in reasons, kind


def make_terrain_grid(
    steep: list[tuple[int, int]] = [],
    built_up: list[tuple[int, int]] = [],
    arid: bool = False,
) -> FarpTerrain:
    """A 20x20 grid of 200m cells from (0, 0), flagging the given cells."""
    shape = (20, 20)
    steep_grid = np.zeros(shape, dtype=bool)
    built_grid = np.zeros(shape, dtype=bool)
    for cell in steep:
        steep_grid[cell] = True
    for cell in built_up:
        built_grid[cell] = True
    return FarpTerrain(
        0, 0, 200, steep_grid, built_grid, np.full(shape, arid, dtype=bool)
    )


def test_terrain_survey_flags_cells_within_radius() -> None:
    grid = make_terrain_grid(steep=[(10, 10)], built_up=[(2, 2)], arid=True)

    near_steep = grid.survey(Point(2_100, 2_100, TERRAIN), 150)
    assert near_steep.known and near_steep.steep and not near_steep.built_up
    assert near_steep.arid

    # Two cells (400m) away from the steep cell is clear with a 150m radius.
    clear = grid.survey(Point(2_500, 2_900, TERRAIN), 150)
    assert clear.known and not clear.steep and not clear.built_up

    town = grid.survey(Point(500, 500, TERRAIN), 150)
    assert town.built_up


def test_terrain_survey_outside_grid_is_unknown() -> None:
    grid = make_terrain_grid(steep=[(0, 0)])

    outside = grid.survey(Point(-10_000, -10_000, TERRAIN), 150)

    assert not outside.known and not outside.steep


def test_terrain_grid_round_trips_through_file(tmp_path: Path) -> None:
    grid = make_terrain_grid(steep=[(1, 2), (19, 19)], built_up=[(5, 6)], arid=True)
    path = tmp_path / "farpterrain.npz"

    grid.save(path)
    loaded = FarpTerrain.load(path)

    assert loaded is not None
    assert (loaded.origin_x, loaded.origin_y, loaded.cell) == (0, 0, 200)
    assert (loaded.steep == grid.steep).all()
    assert (loaded.built_up == grid.built_up).all()
    assert loaded.arid.all()


def test_site_check_rejects_uneven_and_built_up_terrain() -> None:
    world = make_world()
    world.game.theater = SimpleNamespace(
        controlpoints=[],
        ground_objects=[],
        is_on_land=lambda point: True,
        conflicts=lambda: [],
        farp_terrain=make_terrain_grid(steep=[(10, 10)], built_up=[(3, 3)]),
    )
    manager = FarpManager(cast(Any, world.coalition))

    hill = manager.check_site(Point(2_100, 2_100, TERRAIN), FarpKind.WET_WING)
    town = manager.check_site(Point(700, 700, TERRAIN), FarpKind.FAT_COW)
    flat = manager.check_site(Point(1_000, 3_500, TERRAIN), FarpKind.WET_WING)

    assert "Terrain too uneven for a FARP." in hill.reasons
    assert "Too close to a built-up area." in town.reasons
    assert "Terrain too uneven for a FARP." not in flat.reasons
    assert "Too close to a built-up area." not in flat.reasons


def test_footprint_covers_layout_and_pads() -> None:
    # The Wet Wing's MANPAD team stands ~150m from the FARP point, the Fat Cow's
    # pads ~105m.
    assert farp_footprint_radius(FarpKind.WET_WING, 4) > 150
    assert farp_footprint_radius(FarpKind.FAT_COW, 2) > 105
    # Extra Wet Wing pads extend the footprint.
    assert farp_footprint_radius(FarpKind.WET_WING, 8) > farp_footprint_radius(
        FarpKind.WET_WING, 4
    )


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
    # A save made with an older layout: stale pad positions.
    state["helipads_invisible"] = [
        PointWithHeading.from_point(Point(0, 0, TERRAIN), Heading.from_degrees(90)),
        PointWithHeading.from_point(Point(0, -100, TERRAIN), Heading.from_degrees(90)),
    ]

    loaded = DynamicFarp.__new__(DynamicFarp)
    loaded.__setstate__(state)

    assert loaded.capacity == 2
    assert [(round(p.x), round(p.y)) for p in loaded.helipads_invisible] == expected


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


def make_pending_farp(
    world: SimpleNamespace, kind: FarpKind = FarpKind.WET_WING
) -> DynamicFarp:
    farp = DynamicFarp(
        "FARP Hammer",
        Point(0, 0, TERRAIN),
        Heading.from_degrees(90),
        cast(Any, MagicMock()),
        Player.BLUE,
        kind,
        4 if kind is FarpKind.WET_WING else 2,
        established_turn=1,
        established=False,
    )
    farp._coalition = cast(Any, world.coalition)
    return farp


def make_transport_squadron(helicopter: bool, x: float = 50_000) -> Any:
    return SimpleNamespace(
        is_detachment=False,
        untasked_aircraft=2,
        has_available_pilots=True,
        aircraft=SimpleNamespace(
            helicopter=helicopter, capable_of=lambda task: task is FlightType.TRANSPORT
        ),
        location=SimpleNamespace(position=Point(x, 0, TERRAIN)),
    )


def test_pending_farp_has_no_pads_or_upkeep_until_set_up() -> None:
    world = make_world()
    farp = make_pending_farp(world)
    manager = manager_with_farp(world, farp)

    assert not farp.helipads_quad and not farp.helipads_invisible
    assert free_farp_slots(farp) == 0
    assert manager.total_upkeep == 0
    parent = make_squadron(world, make_home_base(), make_helicopter_type())
    assert any("isn't set up yet" in e for e in detachment_errors(parent, farp, 1))

    farp.establish()

    assert farp.established and farp.helipads_quad
    assert free_farp_slots(farp) == 4
    assert manager.total_upkeep == farp.upkeep_per_turn


def test_pending_farp_survives_save_load_without_pads() -> None:
    world = make_world()
    farp = make_pending_farp(world)

    loaded = DynamicFarp.__new__(DynamicFarp)
    loaded.__setstate__(dict(farp.__dict__))

    assert not loaded.established
    assert not loaded.helipads_quad and not loaded.helipads_invisible


def test_older_saves_load_as_established() -> None:
    world = make_world()
    state = dict(make_farp(world).__dict__)
    del state["established"]
    del state["setup_aircraft"]

    loaded = DynamicFarp.__new__(DynamicFarp)
    loaded.__setstate__(state)

    assert loaded.established and loaded.setup_aircraft is None
    assert loaded.helipads_quad


def test_commit_setups_establishes_delivered_farps_only() -> None:
    world = make_world()
    delivered = make_pending_farp(world)
    waiting = make_pending_farp(world, FarpKind.FAT_COW)
    manager = manager_with_farp(world, delivered)
    world.game.theater.controlpoints.append(waiting)
    setup_type = MagicMock()
    world.coalition.ato.packages = [
        SimpleNamespace(
            target=delivered, flights=[SimpleNamespace(unit_type=setup_type)]
        )
    ]
    events = GameUpdateEvents()

    manager.commit_setups([str(delivered.id), "unrelated"], events)

    assert delivered.established and delivered.setup_aircraft is setup_type
    assert delivered in events.updated_control_points
    assert not waiting.established


def test_cancelling_pending_farp_refunds_deploy_cost() -> None:
    world = make_world()
    farp = make_pending_farp(world)
    manager = manager_with_farp(world, farp)
    budget = world.coalition.budget

    manager.dismantle(farp, GameUpdateEvents())

    assert world.coalition.budget == budget + manager.deploy_cost(FarpKind.WET_WING)


def test_setup_squadron_matches_farp_type() -> None:
    world = make_world()
    manager = manager_with_farp(world, make_pending_farp(world))
    plane = make_transport_squadron(helicopter=False)
    helicopter = make_transport_squadron(helicopter=True, x=10_000)
    world.coalition.air_wing = SimpleNamespace(
        iter_squadrons=lambda: iter([plane, helicopter])
    )
    site = Point(0, 0, TERRAIN)

    # Wet Wings are airdropped by a plane, Fat Cows flown in by helicopter.
    assert manager.setup_squadron(FarpKind.WET_WING, site) is plane
    assert manager.setup_squadron(FarpKind.FAT_COW, site) is helicopter

    # Without a plane, a helicopter flies the Wet Wing in.
    world.coalition.air_wing = SimpleNamespace(
        iter_squadrons=lambda: iter([helicopter])
    )
    assert manager.setup_squadron(FarpKind.WET_WING, site) is helicopter


def test_site_check_needs_a_transport_unless_instant_cheat() -> None:
    world = make_world()
    world.settings.enable_transfer_cheat = False
    world.game.theater = SimpleNamespace(
        controlpoints=[],
        ground_objects=[],
        is_on_land=lambda point: True,
        conflicts=lambda: [],
        farp_terrain=None,
    )
    world.coalition.air_wing = SimpleNamespace(iter_squadrons=lambda: iter([]))
    manager = FarpManager(cast(Any, world.coalition))
    site = Point(100_000, 0, TERRAIN)

    reasons = manager.check_site(site, FarpKind.FAT_COW).reasons
    assert "No transport helicopter available to fly the equipment in." in reasons

    world.settings.enable_instant_farp_cheat = True
    reasons = manager.check_site(site, FarpKind.FAT_COW).reasons
    assert not any("transport" in r for r in reasons)


def test_instant_cheat_sets_up_waiting_farps() -> None:
    world = make_world()
    world.settings.enable_instant_farp_cheat = True
    farp = make_pending_farp(world)
    manager = manager_with_farp(world, farp)

    manager.plan_setup_flights(datetime(2020, 1, 1))

    assert farp.established and farp.helipads_quad


# AI planning and player-only FARPs


def test_ai_planner_uses_helicopters_stationed_at_established_farps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game.ato.closestairfields import ObjectiveDistanceCache
    from game.dcs.aircrafttype import AircraftType
    from game.squadrons.airwing import AirWing

    from game.utils import nautical_miles

    world = make_world()
    farp = make_farp(world)
    helicopter = make_helicopter_type()
    helicopter.max_mission_range = nautical_miles(100)
    parent = make_squadron(world, make_home_base(), helicopter)
    det = create_detachment(parent, farp, 2)
    monkeypatch.setattr(
        AircraftType, "priority_list_for_task", classmethod(lambda cls, task: [])
    )
    ObjectiveDistanceCache.set_theater(cast(Any, SimpleNamespace(controlpoints=[farp])))
    target = SimpleNamespace(
        name="Target", position=Point(5_000, 0, TERRAIN), distance_to=lambda o: 5_000
    )
    air_wing = SimpleNamespace(player=Player.BLUE, settings=world.settings)

    def best() -> list[Squadron]:
        ObjectiveDistanceCache.invalidate()
        return AirWing.best_squadrons_for(
            cast(Any, air_wing), cast(Any, target), FlightType.CAS, 2, False, True
        )

    try:
        assert farp.runway_is_operational()
        assert best() == [det]

        # A FARP still waiting for its equipment has no pads to fly from.
        farp.established = False
        farp.helipads_quad = []
        farp.helipads_invisible = []
        assert not farp.runway_is_operational()
        assert best() == []
    finally:
        ObjectiveDistanceCache.theater = None
        ObjectiveDistanceCache.invalidate()


def test_only_the_player_can_establish_farps() -> None:
    world = make_world()
    world.coalition.player = Player.RED
    manager = manager_with_farp(world, make_farp(world))

    check = manager.check_site(Point(50_000, 50_000, TERRAIN), FarpKind.FAT_COW)

    assert check.reasons == ["Only the player can establish FARPs."]


def test_pretense_leaves_dynamic_farps_out_and_restores_them() -> None:
    from game.pretense.pretensemissiongenerator import (
        remove_dynamic_farps,
        restore_dynamic_farps,
    )

    world = make_world()
    farp = make_farp(world)
    base, other = make_home_base(), make_home_base()
    controlpoints = [base, farp, other]
    game: Any = SimpleNamespace(theater=SimpleNamespace(controlpoints=controlpoints))

    removed = remove_dynamic_farps(game)

    assert game.theater.controlpoints == [base, other]
    assert game.theater.controlpoints is controlpoints

    restore_dynamic_farps(game, removed)

    assert game.theater.controlpoints == [base, farp, other]
