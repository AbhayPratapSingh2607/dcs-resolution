"""Focused turns (settings.focused_turns): a turn plans one mission window
plus a short lead-in, every strike TOT falls inside the window, lines don't
relieve for the last few minutes, and the package guidance stops further
offensive packages."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from dcs.mapping import Point

from game.ato.flighttype import FlightType
from game.commander.jfacc.campaignstate import AirCampaignState
from game.commander.jfacc.planner import (
    counts_toward_target,
    focused_lead_in,
    period_hours,
)
from game.commander.jfacc.profile import load_profile
from game.commander.jfacc.scheduler import Timeline
from game.sim import atoperiod

START = datetime(2026, 6, 1, 12, 0)


@pytest.fixture
def profile():  # type: ignore[no-untyped-def]
    loaded = load_profile("western")
    assert loaded is not None
    return loaded


def _game(focused: bool, minutes: int = 60, lead_in: int = 30) -> Any:
    settings = SimpleNamespace(
        focused_turns=focused,
        focused_lead_in_min=lead_in,
        desired_player_mission_duration=timedelta(minutes=minutes),
        ato_period_hours=6,
    )
    return SimpleNamespace(settings=settings, air_campaign=AirCampaignState(), turn=1)


def test_focused_period_is_lead_in_plus_window(profile) -> None:  # type: ignore[no-untyped-def]
    assert period_hours(_game(True, 60, 30), profile) == pytest.approx(1.5)
    assert period_hours(_game(True, 150, 0), profile) == pytest.approx(2.5)
    assert focused_lead_in(_game(False)) is None
    assert period_hours(_game(False), profile) == pytest.approx(6)


def test_focused_window_is_fixed_after_the_lead_in() -> None:
    game = _game(True)
    game.air_campaign.note_period(1, START, START + timedelta(minutes=90), 30)
    assert atoperiod.is_focused(game)
    assert atoperiod.window(game) == (
        START + timedelta(minutes=30),
        START + timedelta(minutes=90),
    )
    # Nothing to pick, and picking doesn't move it.
    assert atoperiod.max_window_offset_min(game) == 0
    atoperiod.set_window_offset(game, 0)
    assert atoperiod.window(game)[0] == START + timedelta(minutes=30)  # type: ignore[index]


def test_theater_period_keeps_the_picker() -> None:
    game = _game(False)
    game.air_campaign.note_period(1, START, START + timedelta(hours=6))
    assert not atoperiod.is_focused(game)
    assert atoperiod.max_window_offset_min(game) == 300


def test_strike_tots_fall_inside_the_window(profile) -> None:  # type: ignore[no-untyped-def]
    window = (START + timedelta(minutes=30), START + timedelta(minutes=90))
    timeline = Timeline(profile, START, window[1], window=window)
    assert timeline.earliest >= window[0]
    assert timeline.latest <= window[1] - timedelta(minutes=10)
    tots = []
    for i in range(40):
        tot = timeline.strike_tot(Point(i * 1000.0, 0, None))  # type: ignore[arg-type]
        if tot is None:
            break
        timeline.reserve(tot, Point(i * 1000.0, 0, None))  # type: ignore[arg-type]
        tots.append(tot)
    assert tots
    assert all(timeline.earliest <= t <= timeline.latest for t in tots)


def _package(*tasks: FlightType, alert: bool = False, name: str = "T") -> Any:
    flights = [SimpleNamespace(flight_type=t, alert=alert) for t in tasks]
    return SimpleNamespace(flights=flights, target=SimpleNamespace(name=name))


def test_package_guidance_counts_combat_packages_only() -> None:
    assert counts_toward_target(_package(FlightType.STRIKE, FlightType.ESCORT))
    assert counts_toward_target(_package(FlightType.BARCAP, name="CAP Kutaisi 320"))
    assert not counts_toward_target(_package(FlightType.BARCAP, alert=True))
    assert not counts_toward_target(_package(FlightType.AEWC))
    assert not counts_toward_target(_package(FlightType.REFUELING))
    assert not counts_toward_target(_package(FlightType.BARCAP, name="HVAA CAP AEW&C"))


def test_cap_patrol_covers_the_window(profile) -> None:  # type: ignore[no-untyped-def]
    from game.commander.jfacc.composer import PackageComposer

    composer = cast(Any, PackageComposer.__new__(PackageComposer))
    composer.profile = profile
    composer.game = SimpleNamespace(
        settings=SimpleNamespace(
            desired_barcap_mission_duration=timedelta(minutes=60),
            desired_awacs_mission_duration=timedelta(hours=2),
            desired_tanker_on_station_time=timedelta(minutes=60),
        )
    )
    composer.patrol_until = START + timedelta(minutes=90)
    tot = START + timedelta(minutes=25)
    assert composer.patrol_override(FlightType.BARCAP, tot) == timedelta(minutes=65)
    # Capped: a long window still gets a relief.
    composer.patrol_until = START + timedelta(hours=4)
    assert composer.patrol_override(FlightType.BARCAP, tot) == timedelta(minutes=90)
    # A tanker stretches up to half again its usual time, never shortens.
    assert composer.patrol_override(FlightType.REFUELING, tot) == timedelta(minutes=90)
    composer.patrol_until = START + timedelta(minutes=60)
    assert composer.patrol_override(FlightType.REFUELING, tot) is None
    # Theater period: no override.
    composer.patrol_until = None
    assert composer.patrol_override(FlightType.BARCAP, tot) is None


def test_no_relief_for_the_last_minutes_of_the_window(profile) -> None:  # type: ignore[no-untyped-def]
    from game.commander.jfacc.planner import JfaccPlanner

    planner = cast(Any, JfaccPlanner.__new__(JfaccPlanner))
    planner.profile = profile
    end = START + timedelta(minutes=90)
    planner.timeline = Timeline(profile, START, end, window=(START, end))
    assert not planner._relief_needed(end - timedelta(minutes=10), end)
    assert planner._relief_needed(end - timedelta(minutes=30), end)
    # Theater period: every gap is covered.
    planner.timeline = Timeline(profile, START, end)
    assert planner._relief_needed(end - timedelta(minutes=10), end)
