"""The Rescue King: placed from the FARPs menu, a C-130 orbit that stages two
rescue helicopters for one turn."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, Optional, cast
from unittest.mock import MagicMock

from dcs.mapping import Point
from dcs.terrain import Caucasus
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon

from game.ato.flightplans.rescueking import KingOrbit
from game.ato.flighttype import FlightType
from game.ato.flightwaypointtype import FlightWaypointType
from game.ato.starttype import StartType
from game.farps import FarpManager
from game.settings import Settings
from game.sim import GameUpdateEvents
from game.squadrons import Pilot, Squadron
from game.squadrons.detachments import create_detachment, detachments_at
from game.theater import ParkingType, Player
from game.theater.dynamicfarp import (
    RESCUE_KING_CAPACITY,
    DynamicFarp,
    FarpKind,
    is_rescue_king,
)
from game.utils import Heading, feet, nautical_miles

TERRAIN = Caucasus()
NOW = datetime(2026, 1, 1, 12)
NM = 1852.0
HELICOPTERS = ParkingType(False, False, True)
JETS = ParkingType(True, False, False)


class FakeAirWing:
    def __init__(self) -> None:
        self.squadrons: dict[Any, list[Squadron]] = defaultdict(list)

    def add_squadron(self, squadron: Squadron) -> None:
        self.squadrons[squadron.aircraft].append(squadron)

    def iter_squadrons(self) -> Iterator[Squadron]:
        for squadrons in list(self.squadrons.values()):
            yield from list(squadrons)


def _p(x_nm: float, y_nm: float = 0.0) -> Point:
    return Point(x_nm * NM, y_nm * NM, TERRAIN)


def _world(defenses: Any = None) -> SimpleNamespace:
    settings = Settings()
    settings.enable_dynamic_farps = True
    # The King's helicopters are stationed at once even without the cheat.
    settings.enable_transfer_cheat = False
    game = SimpleNamespace(settings=settings, turn=1, messages=[])
    game.message = lambda title, text="": game.messages.append(title)
    coalition = SimpleNamespace(
        player=Player.BLUE,
        game=game,
        air_wing=FakeAirWing(),
        ato=SimpleNamespace(packages=[]),
        budget=1000.0,
        opponent=SimpleNamespace(
            threat_zone=SimpleNamespace(
                air_defenses=defenses if defenses is not None else Polygon()
            )
        ),
    )
    coalition.adjust_budget = lambda amount: setattr(
        coalition, "budget", coalition.budget + amount
    )
    game.blue = coalition
    game.red = SimpleNamespace(ato=SimpleNamespace(packages=[]))
    game.theater = SimpleNamespace(
        controlpoints=[], conflicts=lambda: iter([]), landmap=None
    )
    game.compute_threat_zones = lambda events: None
    return SimpleNamespace(game=game, coalition=coalition, settings=settings)


def _king(world: SimpleNamespace, at: Optional[Point] = None) -> DynamicFarp:
    king = DynamicFarp(
        "King 1",
        at or _p(0),
        Heading.from_degrees(90),
        cast(Any, MagicMock()),
        Player.BLUE,
        FarpKind.RESCUE_KING,
        RESCUE_KING_CAPACITY,
        established_turn=1,
    )
    king._coalition = cast(Any, world.coalition)
    world.game.theater.controlpoints.append(king)
    return king


def _aircraft(helicopter: bool, tasks: set[FlightType]) -> Any:
    aircraft: Any = MagicMock()
    aircraft.helicopter = helicopter
    aircraft.lha_capable = False
    aircraft.capable_of.side_effect = lambda task: task in tasks
    return aircraft


def _base(x_nm: float) -> Any:
    base = MagicMock()
    base.is_dynamic_farp = False
    base.unclaimed_parking.return_value = 100
    base.position = _p(x_nm)
    return base


def _squadron(
    world: SimpleNamespace,
    aircraft: Any,
    x_nm: float,
    owned: int,
    tasks: set[FlightType],
) -> Squadron:
    squadron = Squadron(
        name="Rescue",
        nickname=None,
        country=cast(Any, MagicMock()),
        role="Rescue",
        aircraft=aircraft,
        max_size=12,
        livery=None,
        livery_set=[],
        primary_task=FlightType.TRANSPORT,
        auto_assignable_mission_types=tasks,
        radio_presets={},
        operating_bases=cast(Any, MagicMock()),
        female_pilot_percentage=0,
        pilot_pool=[],
        coalition=cast(Any, world.coalition),
        flight_db=cast(Any, MagicMock()),
        settings=world.settings,
        location=_base(x_nm),
    )
    pilots = [Pilot(f"Pilot {i}") for i in range(owned)]
    squadron.current_roster.extend(pilots)
    squadron.available_pilots.extend(pilots)
    squadron.owned_aircraft = owned
    squadron.untasked_aircraft = owned
    world.coalition.air_wing.add_squadron(squadron)
    return squadron


def _helicopters(world: SimpleNamespace, x_nm: float = 50, owned: int = 4) -> Squadron:
    tasks = {FlightType.CSAR, FlightType.TRANSPORT}
    return _squadron(world, _aircraft(True, tasks), x_nm, owned, set(tasks))


def _c130(
    world: SimpleNamespace, x_nm: float = 100, enabled: bool = True, owned: int = 2
) -> Squadron:
    tasks = {FlightType.TRANSPORT}
    if enabled:
        tasks.add(FlightType.RESCUE_KING)
    return _squadron(
        world,
        _aircraft(False, {FlightType.RESCUE_KING, FlightType.TRANSPORT}),
        x_nm,
        owned,
        tasks,
    )


# ------------------------------------------------------------- the King


def test_king_is_an_airborne_base_for_two_helicopters() -> None:
    king = _king(_world())
    assert is_rescue_king(king)
    assert king.total_aircraft_parking(HELICOPTERS) == RESCUE_KING_CAPACITY
    assert king.total_aircraft_parking(JETS) == 0
    assert king.can_operate(_aircraft(True, set()))
    assert not king.can_operate(_aircraft(False, set()))
    assert king.required_aircraft_start_type is StartType.IN_FLIGHT
    assert king.runway_is_operational()
    # No pads on the ground and nothing to pay for.
    assert not (king.helipads or king.helipads_quad or king.helipads_invisible)
    assert king.upkeep_per_turn == 0


def test_only_the_king_orbit_is_planned_against_it() -> None:
    king = _king(_world())
    assert list(king.mission_types(Player.BLUE)) == [FlightType.RESCUE_KING]
    assert list(king.mission_types(Player.RED)) == []


def test_ground_farps_are_not_kings() -> None:
    world = _world()
    farp = DynamicFarp(
        "FARP Viper",
        _p(10),
        Heading.from_degrees(90),
        cast(Any, MagicMock()),
        Player.BLUE,
        FarpKind.FAT_COW,
        2,
        established_turn=1,
    )
    farp._coalition = cast(Any, world.coalition)
    assert not is_rescue_king(farp)
    assert not is_rescue_king(_base(0))


# ------------------------------------------------------------- placement


def test_king_site_needs_a_c130_and_a_pair_of_helicopters() -> None:
    world = _world()
    manager = FarpManager(cast(Any, world.coalition))
    reasons = manager.check_site(_p(0), FarpKind.RESCUE_KING).reasons
    assert any("C-130" in r for r in reasons)
    assert any("helicopter" in r for r in reasons)

    _c130(world)
    _helicopters(world)
    check = manager.check_site(_p(0), FarpKind.RESCUE_KING)
    assert check.valid, check.reasons
    assert check.cost == 0


def test_king_site_must_be_outside_enemy_air_defenses() -> None:
    sam = ShapelyPoint(0, 0).buffer(20 * NM)
    world = _world(sam)
    _c130(world)
    _helicopters(world)
    manager = FarpManager(cast(Any, world.coalition))
    assert not manager.check_site(_p(5), FarpKind.RESCUE_KING).valid
    # Anywhere else is fine, land or sea, as long as no SAM covers it.
    assert manager.check_site(_p(30), FarpKind.RESCUE_KING).valid


def test_kings_keep_apart() -> None:
    world = _world()
    _c130(world)
    _helicopters(world, owned=6)
    _king(world)
    manager = FarpManager(cast(Any, world.coalition))
    assert not manager.check_site(_p(1), FarpKind.RESCUE_KING).valid


def test_a_single_helicopter_will_do() -> None:
    world = _world()
    _c130(world)
    _helicopters(world, owned=1)
    manager = FarpManager(cast(Any, world.coalition))
    assert manager.check_site(_p(0), FarpKind.RESCUE_KING).valid


def test_without_transport_needed_no_c130_is_needed() -> None:
    world = _world()
    _helicopters(world)
    manager = FarpManager(cast(Any, world.coalition))
    assert not manager.check_site(_p(0), FarpKind.RESCUE_KING).valid
    world.settings.farps_need_no_transport = True
    assert manager.check_site(_p(0), FarpKind.RESCUE_KING).valid
    # Ground FARPs are set up at once: nothing flies their equipment in.
    assert manager.instant_setup


def test_only_csar_helicopters_go_to_a_king() -> None:
    world = _world()
    king = _king(world)
    attack = _squadron(
        world, _aircraft(True, {FlightType.CAS}), 10, 4, {FlightType.CAS}
    )
    manager = FarpManager(cast(Any, world.coalition))
    assert manager.rescue_squadron(_p(0)) is None
    try:
        manager.station_king_helicopters(king, attack, 2)
    except ValueError:
        pass
    else:
        raise AssertionError("an attack helicopter was sent to the King")


def test_a_full_pair_goes_before_a_nearer_single() -> None:
    world = _world()
    _helicopters(world, x_nm=10, owned=1)
    pair = _helicopters(world, x_nm=60, owned=4)
    manager = FarpManager(cast(Any, world.coalition))
    assert manager.rescue_squadron(_p(0)) is pair


def test_only_kc130s_are_tanker_kings(tmp_path: Path) -> None:
    from dcs import planes

    from game import persistency
    from game.ato.flightplans.rescueking import is_tanker_king
    from game.dcs.aircrafttype import AircraftType

    persistency.setup(str(tmp_path), prefer_liberation_payloads=False, port=16884)

    def flight(unit: Any) -> Any:
        return SimpleNamespace(unit_type=next(AircraftType.for_dcs_type(unit)))

    assert is_tanker_king(flight(planes.KC130))
    assert not is_tanker_king(flight(planes.C_130))
    # pydcs lists Refueling among the C-130J-30's DCS tasks, but Retribution
    # doesn't fly it as a tanker.
    assert not is_tanker_king(flight(planes.C_130J_30))


# ------------------------------------------------------ the King aircraft


def test_squadrons_with_rescue_king_off_are_never_picked_automatically() -> None:
    world = _world()
    off = _c130(world, x_nm=10, enabled=False)
    on = _c130(world, x_nm=200)
    manager = FarpManager(cast(Any, world.coalition))
    assert manager.king_squadron(_p(0)) is on
    # Both are listed for the player, nearest first; the one turned off says why.
    listed = manager.king_squadrons(_p(0))
    assert [s for s, _ in listed] == [off, on]
    assert listed[0][1] is not None and "turned off" in listed[0][1]
    assert listed[1][1] is None


def test_no_king_site_when_every_c130_has_rescue_king_off() -> None:
    world = _world()
    _c130(world, enabled=False)
    _helicopters(world)
    manager = FarpManager(cast(Any, world.coalition))
    reasons = manager.check_site(_p(0), FarpKind.RESCUE_KING).reasons
    assert any("turned on" in r for r in reasons)


def test_busy_squadrons_are_listed_with_the_reason() -> None:
    world = _world()
    busy = _c130(world, owned=1)
    busy.untasked_aircraft = 0
    manager = FarpManager(cast(Any, world.coalition))
    assert manager.king_squadrons(_p(0)) == [(busy, "no aircraft free")]
    # Unless it is the one already flying the orbit.
    assert manager.king_squadrons(_p(0), current=busy) == [(busy, None)]


def _planned(manager: FarpManager) -> list[Any]:
    """Stubs plan_king_flight: records who would fly the orbit."""
    calls: list[Any] = []

    def plan(king: Any, now: Any, events: Any = None) -> Any:
        squadron = manager._king_orbit_squadron(king)
        calls.append(squadron)
        return SimpleNamespace(squadron=squadron)

    manager.plan_king_flight = plan  # type: ignore[method-assign]
    return calls


def test_the_player_picks_the_king_aircraft() -> None:
    world = _world()
    king = _king(world)
    near = _c130(world, x_nm=10)
    far = _c130(world, x_nm=200)
    manager = FarpManager(cast(Any, world.coalition))
    calls = _planned(manager)
    assert manager._king_orbit_squadron(king) is near
    manager.set_king_aircraft(king, far, NOW)
    assert king.king_squadron_choice is far and not king.king_outside_tanker
    assert calls == [far]
    # The choice stands when the orbit is planned again (a replan).
    assert manager._king_orbit_squadron(king) is far
    # If the chosen squadron can't go any more, the nearest one goes.
    far.untasked_aircraft = 0
    assert manager._king_orbit_squadron(king) is near


def test_a_squadron_with_rescue_king_off_or_busy_cant_be_picked() -> None:
    world = _world()
    king = _king(world)
    off = _c130(world, enabled=False)
    manager = FarpManager(cast(Any, world.coalition))
    _planned(manager)
    for squadron in (off, _helicopters(world)):
        try:
            manager.set_king_aircraft(king, squadron, NOW)
        except ValueError:
            continue
        raise AssertionError(f"{squadron} was accepted as the King aircraft")


def test_the_outside_kc130_needs_the_no_transport_setting() -> None:
    world = _world()
    king = _king(world)
    own = _c130(world)
    manager = FarpManager(cast(Any, world.coalition))
    _planned(manager)
    try:
        manager.set_king_aircraft(king, None, NOW)
    except ValueError:
        pass
    else:
        raise AssertionError("the outside KC-130 was allowed without the setting")

    world.settings.farps_need_no_transport = True
    # With the setting on, the outside KC-130 is the default (None) ...
    assert manager._king_orbit_squadron(king) is None
    # ... the player can pick their own squadron instead ...
    manager.set_king_aircraft(king, own, NOW)
    assert manager._king_orbit_squadron(king) is own
    # ... and go back to the outside KC-130.
    manager.set_king_aircraft(king, None, NOW)
    assert king.king_outside_tanker
    assert manager._king_orbit_squadron(king) is None


def test_rescue_helicopters_come_from_the_nearest_csar_squadron() -> None:
    world = _world()
    far = _helicopters(world, x_nm=200)
    near = _helicopters(world, x_nm=40)
    manager = FarpManager(cast(Any, world.coalition))
    assert manager.rescue_squadron(_p(0)) is near
    # A squadron with CSAR turned off is the last resort.
    near.auto_assignable_mission_types.discard(FlightType.CSAR)
    assert manager.rescue_squadron(_p(0)) is far


def test_king_helicopters_arrive_at_once_without_the_cheat() -> None:
    world = _world()
    king = _king(world)
    parent = _helicopters(world)
    det = create_detachment(parent, king, 2, instant=True)
    assert det.location is king
    assert det.destination is None
    assert parent.owned_aircraft == 2


def test_king_is_over_at_the_end_of_the_turn() -> None:
    world = _world()
    king = _king(world)
    parent = _helicopters(world)
    create_detachment(parent, king, 2, instant=True)
    manager = FarpManager(cast(Any, world.coalition))
    assert manager.kings == [king]
    assert manager.ground_farps == []

    manager.end_turn(GameUpdateEvents())
    assert king not in world.game.theater.controlpoints
    assert not detachments_at(king)
    assert parent.owned_aircraft == 4
    # It cost nothing, and nothing is refunded.
    assert world.coalition.budget == 1000


# ------------------------------------------------------- flights from it


def _builder() -> Any:
    return SimpleNamespace(get_cruise_altitude=feet(500), is_helo=True)


def test_king_flights_start_and_end_in_the_air_over_it() -> None:
    from game.ato.flightplans.waypointbuilder import WaypointBuilder

    king = _king(_world())
    takeoff = WaypointBuilder.takeoff(_builder(), king)
    landing = WaypointBuilder.land(_builder(), king)
    for waypoint in (takeoff, landing):
        assert waypoint.waypoint_type is FlightWaypointType.NAV
        assert waypoint.position == king.position
        assert waypoint.alt == feet(500)
    # Nowhere to divert to in the sky.
    assert WaypointBuilder.divert(_builder(), king) is None


def _despawns(arrival: Any, player: bool) -> bool:
    from game.missiongenerator.aircraft.waypoints.pydcswaypointbuilder import (
        PydcsWaypointBuilder,
    )

    builder = SimpleNamespace(
        flight=SimpleNamespace(
            roster=SimpleNamespace(members=[SimpleNamespace(is_player=player)]),
            arrival=arrival,
            start_type=StartType.IN_FLIGHT,
            coalition=SimpleNamespace(
                game=SimpleNamespace(
                    settings=SimpleNamespace(perf_ai_despawn_airstarted=False)
                )
            ),
        )
    )
    waypoint = SimpleNamespace(position=arrival.position)
    return PydcsWaypointBuilder.ai_despawn(builder, waypoint)  # type: ignore[arg-type]


def test_ai_helicopters_leave_the_mission_back_at_the_king() -> None:
    king = _king(_world())
    assert _despawns(king, player=False)
    # A player flies on.
    assert not _despawns(king, player=True)
    # An ordinary base isn't a despawn point (with the setting off).
    assert not _despawns(SimpleNamespace(position=_p(0)), player=False)


def test_king_orbit_runs_across_the_line_to_the_fight() -> None:
    orbit = KingOrbit(_p(0), 90)
    start, end = orbit.racetrack
    assert abs(start.distance_to_point(end) - nautical_miles(15).meters) < 1
    # Heading 90 (east): the racetrack runs north-south, centred on the King.
    assert abs(start.y - end.y) < 1
    assert abs(start.x + end.x) < 1


def test_lua_credits_king_rescues_at_boarding() -> None:
    lua = Path("resources/plugins/opscsar/OpsCSAR.lua").read_text(encoding="utf-8")
    assert "kingUnits" in lua
    boarded = lua[lua.index("OnAfterBoarded") :]
    boarded = boarded[: boarded.index("OnAfterRescued")]
    assert "king" in boarded.lower()
    assert "king_units[Heliname]" in boarded
    assert "table.insert(csar_rescued, entry.id)" in boarded


def test_both_king_helicopters_are_ready_to_fly() -> None:
    from datetime import datetime

    from game.commander.jfacc.sorties import SortieLedger

    world = _world()
    king = _king(world)
    det = create_detachment(_helicopters(world), king, 2, instant=True)
    profile = SimpleNamespace(mc_rate=0.5, max_sorties_per_airframe=2)
    ledger = SortieLedger(
        cast(Any, profile), datetime(2020, 1, 1), datetime(2020, 1, 2), 1
    )
    # Unlike an ordinary squadron, none of the pair is down for maintenance.
    assert ledger.mission_capable(det) == 2
