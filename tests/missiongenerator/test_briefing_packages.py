"""The DCS briefing's friendly package list: combat packages by time over
target with clock times, routine lines one line each, and plain text (no
HTML escaping: "AEW&C", not "AEW&amp;C")."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from game.ato.flighttype import FlightType
from game.missiongenerator.briefinggenerator import BriefingGenerator
from game.theater.player import Player

START = datetime(2005, 4, 26, 13, 0)


def _package(name: str, task: FlightType, tot_min: int) -> Any:
    return SimpleNamespace(
        target=SimpleNamespace(name=name),
        primary_task=task,
        time_over_target=START + timedelta(minutes=tot_min),
    )


def _flight(
    package: Any,
    task: FlightType,
    size: int,
    type_id: str,
    delay_min: int,
    base: str = "CVN-75",
) -> Any:
    return SimpleNamespace(
        package=package,
        flight_type=task,
        size=size,
        units=[SimpleNamespace(type=type_id)],
        departure_delay=timedelta(minutes=delay_min),
        departure=SimpleNamespace(airfield_name=base),
        client_units=[],
        friendly=Player.BLUE,
    )


def _generator(flights: list[Any]) -> BriefingGenerator:
    gen: Any = object.__new__(BriefingGenerator)
    gen.mission = SimpleNamespace(start_time=START)
    gen.flights = flights
    return gen


def test_packages_by_tot_and_routine_lines() -> None:
    dead = _package("ELEPHANT", FlightType.DEAD, 65)
    early = _package("SHOEBILL", FlightType.DEAD, 50)
    cap = [_package("CAP LHA-3 329", FlightType.BARCAP, m) for m in (5, 60, 115)]
    awacs = _package("CVN-75", FlightType.AEWC, 20)
    flights = [
        _flight(dead, FlightType.DEAD, 4, "EA-18G", 20),
        _flight(dead, FlightType.SEAD_ESCORT, 4, "FA-18F", 22),
        _flight(early, FlightType.DEAD, 4, "FA-18E", 0),
        _flight(awacs, FlightType.AEWC, 1, "E-2C", 0),
    ] + [_flight(p, FlightType.BARCAP, 2, "FA-18F", 0) for p in cap]
    packages, lines = _generator(flights)._ally_packages()
    assert packages == [
        "13:50 SHOEBILL: DEAD 4x FA-18E\n      from CVN-75, airborne or starting up at mission start",
        "14:05 ELEPHANT: DEAD 4x EA-18G, SEAD Escort 4x FA-18F\n      from CVN-75, takes off 13:20",
    ]
    assert lines == [
        "CAP LHA-3 329: BARCAP 2x FA-18F, on station 13:05, 14:00, 14:55",
        "CVN-75: AEW&C 1x E-2C, on station 13:20",
    ]


def test_the_template_is_plain_text() -> None:
    gen: Any = object.__new__(BriefingGenerator)
    BriefingGenerator.__init__(gen, SimpleNamespace(), SimpleNamespace())  # type: ignore[arg-type]
    assert gen.template.environment.autoescape is False
