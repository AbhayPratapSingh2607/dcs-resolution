"""Folding a 6 hour plan to one screen (W4, qt_ui.atopresentation.folds) and
the map's station symbols for routine lines (game.server.flights.models)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from game.ato.flighttype import FlightType
from game.server.flights.models import routine_station
from qt_ui import atopresentation as ap

START = datetime(2020, 6, 1, 6, 0)
PUSH = (START + timedelta(hours=2), START + timedelta(hours=3))


def _package(
    task: FlightType, target: str, tot_min: int, players: bool = False, n: int = 2
) -> Any:
    flight = SimpleNamespace(
        flight_type=task, count=n, client_count=1 if players else 0, alert=False
    )
    package = SimpleNamespace(
        primary_task=task,
        flights=[flight],
        target=SimpleNamespace(name=target),
        time_over_target=START + timedelta(minutes=tot_min),
        has_players=players,
        package_description=task.value,
        custom_name=None,
    )
    flight.package = package
    return package


def test_routine_lines_fold_with_their_reliefs() -> None:
    caps = [_package(FlightType.BARCAP, "CAP 040", m) for m in (30, 90, 150, 210)]
    awacs = [_package(FlightType.AEWC, "AWACS Alpha", m) for m in (20, 200)]
    lone = [_package(FlightType.REFUELING, "Texaco", 40)]
    table = ap.folds(caps + awacs + lone, PUSH)
    assert {table[id(p)].key for p in caps} == {"line:BARCAP:CAP 040"}
    assert table[id(caps[0])].representative is caps[0]
    assert table[id(caps[0])].count == 4
    assert table[id(awacs[0])].label == "AEW&C — AWACS Alpha"
    # One package is no fold.
    assert id(lone[0]) not in table


def test_waves_outside_the_push_fold_per_category() -> None:
    before = [_package(FlightType.STRIKE, f"T{i}", 45 + i) for i in range(3)]
    inside = [_package(FlightType.STRIKE, f"P{i}", 125 + i) for i in range(4)]
    after = [_package(FlightType.DEAD, f"S{i}", 250 + i) for i in range(2)]
    players = _package(FlightType.STRIKE, "You", 50, players=True)
    table = ap.folds(before + inside + after + [players], PUSH)
    assert {table[id(p)].key for p in before} == {"wave:strike:before"}
    assert table[id(before[0])].label == "Strike before the main push"
    assert {table[id(p)].key for p in after} == {"wave:sead:after"}
    # The main push stays open, and so does a package with players.
    assert all(id(p) not in table for p in inside)
    assert id(players) not in table
    # Without a push nothing but the lines folds.
    assert ap.folds(before + after, None) == {}


def test_folded_rows_fit_a_screen() -> None:
    caps = [_package(FlightType.BARCAP, f"CAP {s}", m) for s in ("040", "120") for m in (30, 90, 150, 210, 270)]
    strikes = [_package(FlightType.STRIKE, f"T{i}", 40 + 3 * i) for i in range(6)]
    push = [_package(FlightType.STRIKE, f"P{i}", 125 + 3 * i) for i in range(5)]
    late = [_package(FlightType.STRIKE, f"L{i}", 240 + 3 * i) for i in range(6)]
    packages = caps + strikes + push + late
    assert len(packages) == 27
    # Two CAP lines, one row each; the waves before and after the push, one
    # row each; the five push packages open.
    assert ap.folded_rows(packages, PUSH) == 2 + 1 + 1 + 5


def test_main_push_comes_from_the_side_state() -> None:
    side = SimpleNamespace(push=PUSH)
    game = SimpleNamespace(air_campaign=SimpleNamespace(maybe_side=lambda blue: side))
    assert ap.main_push(game, True) == PUSH  # type: ignore[arg-type]
    none = SimpleNamespace(air_campaign=SimpleNamespace(maybe_side=lambda blue: None))
    assert ap.main_push(none, True) is None  # type: ignore[arg-type]
    assert ap.main_push(SimpleNamespace(), True) is None  # type: ignore[arg-type]


def _flight(task: FlightType, players: bool = False, alert: bool = False, station: Any = None) -> Any:
    layout = SimpleNamespace(patrol_start=SimpleNamespace(position=station)) if station else SimpleNamespace()
    flight = SimpleNamespace(
        flight_type=task,
        alert=alert,
        flight_plan=SimpleNamespace(layout=layout),
        departure=SimpleNamespace(name="Kutaisi"),
    )
    flight.package = SimpleNamespace(
        has_players=players,
        flights=[flight],
        target=SimpleNamespace(name="CAP 040", position="target"),
    )
    return flight


def test_routine_station_for_lines_only() -> None:
    cap = _flight(FlightType.BARCAP, station="racetrack")
    assert routine_station(cap) == ("BARCAP CAP 040", "racetrack")
    # No racetrack position: the station is the package target.
    assert routine_station(_flight(FlightType.AEWC)) == ("AEW&C CAP 040", "target")
    alert = _flight(FlightType.BARCAP, alert=True)
    assert routine_station(alert) == ("Ground alert Kutaisi", "target")
    assert routine_station(_flight(FlightType.STRIKE)) is None
    assert routine_station(_flight(FlightType.BARCAP, players=True)) is None
    # A tanker inside a strike package is not a line.
    tanker = _flight(FlightType.REFUELING)
    tanker.package.flights.append(SimpleNamespace(flight_type=FlightType.STRIKE, alert=False))
    assert routine_station(tanker) is None


def test_packages_outside_the_bubble_fold_by_group() -> None:
    inside = [_package(FlightType.STRIKE, f"P{i}", 125 + i) for i in range(3)]
    away = [_package(FlightType.STRIKE, f"A{i}", 130 + i) for i in range(3)]
    elsewhere = {id(p) for p in away}
    table = ap.folds(inside + away, PUSH, elsewhere)
    assert {table[id(p)].key for p in away} == {"elsewhere:strike"}
    assert table[id(away[0])].label == "Strike elsewhere (combat model)"
    # The main push packages in the mission stay open.
    assert all(id(p) not in table for p in inside)
    assert ap.folded_rows(inside + away, PUSH, elsewhere) == 4
