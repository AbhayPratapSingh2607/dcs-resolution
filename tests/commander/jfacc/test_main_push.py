"""The main push (W2): the turn's main effort in one block as long as the
mission, with smaller waves before and after it, and about half of the
offensive sorties aimed into it."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from dcs.mapping import Point

from game.commander.jfacc.campaignstate import AirCampaignState, SideCampaign
from game.commander.jfacc.planner import JfaccPlanner, is_offensive_package
from game.commander.jfacc.profile import Category, load_profile
from game.commander.jfacc.scheduler import Timeline
from game.ato.flighttype import FlightType

START = datetime(2026, 6, 1, 6, 0)
END = START + timedelta(hours=6)


@pytest.fixture
def profile():  # type: ignore[no-untyped-def]
    loaded = load_profile("western")
    assert loaded is not None
    return loaded


def _point(i: int) -> Any:
    return Point(i * 50_000.0, 0, None)  # type: ignore[arg-type]


def test_push_waves_run_sead_then_strikes_then_follow_up(profile) -> None:  # type: ignore[no-untyped-def]
    push = (START + timedelta(hours=2), START + timedelta(hours=3))
    timeline = Timeline(profile, START, END, push=push)
    waves = timeline.push_wave_times()
    assert len(waves) == 3
    assert waves[0] == push[0] + timedelta(minutes=5)
    assert waves[1] - waves[0] == timedelta(minutes=8)
    assert all(push[0] <= w < push[1] for w in waves)


def test_at_least_one_wave_before_the_push(profile) -> None:  # type: ignore[no-untyped-def]
    push = (START + timedelta(hours=2), START + timedelta(hours=3))
    timeline = Timeline(profile, START, END, push=push)
    outer = timeline.outer_wave_times()
    assert any(t < push[0] for t in outer)
    assert not any(timeline.in_push(t) for t in outer)
    # Even when the push opens early.
    early = (START + timedelta(minutes=40), START + timedelta(minutes=100))
    timeline = Timeline(profile, START, END, push=early)
    assert any(t < early[0] for t in timeline.outer_wave_times())


def test_strike_tots_can_be_kept_in_or_out_of_the_push(profile) -> None:  # type: ignore[no-untyped-def]
    push = (START + timedelta(hours=2), START + timedelta(hours=3))
    timeline = Timeline(profile, START, END, push=push)
    for i in range(6):
        tot = timeline.strike_tot(_point(i), push=True)
        assert tot is not None and timeline.in_push(tot)
        timeline.reserve(tot, _point(i))
        tot = timeline.strike_tot(_point(i), push=False)
        assert tot is not None and not timeline.in_push(tot)
    # SEAD prefers the first push wave, strikes the second.
    sead = timeline.strike_tot(_point(20), preferred_wave=0, push=True)
    strike = timeline.strike_tot(_point(21), preferred_wave=1, push=True)
    assert sead is not None and strike is not None
    assert sead < strike
    # No push: the old behaviour, any wave.
    plain = Timeline(profile, START, END)
    assert plain.strike_tot(_point(0), push=True) is None
    assert plain.strike_tot(_point(0)) is not None


def _planner(profile: Any, push: Any, quota: dict[Category, int]) -> Any:
    planner = cast(Any, JfaccPlanner.__new__(JfaccPlanner))
    planner.profile = profile
    planner.timeline = Timeline(profile, START, END, push=push)
    planner.apportionment = SimpleNamespace(quota=quota)
    planner.spec = SimpleNamespace(flag=lambda name, default=None: default)
    planner._set_push_quota()
    return planner


def _composed(tot: datetime, sorties: int) -> Any:
    return SimpleNamespace(
        package=SimpleNamespace(time_over_target=tot), sorties=sorties
    )


def test_about_half_of_the_offensive_sorties_go_into_the_push(profile) -> None:  # type: ignore[no-untyped-def]
    push = (START + timedelta(hours=2), START + timedelta(hours=3))
    planner = _planner(profile, push, {Category.STRIKE: 16, Category.SEAD: 8})
    assert planner.push_quota == {Category.STRIKE: 8, Category.SEAD: 4}
    tots = []
    for i in range(8):
        tot = planner._strike_tot(_point(i), Category.STRIKE)
        assert tot is not None
        planner.timeline.reserve(tot, _point(i))
        planner._note_push_spend(Category.STRIKE, _composed(tot, 2))
        tots.append(tot)
    inside = [t for t in tots if planner.timeline.in_push(t)]
    # The first four packages (8 sorties) fill the push, the rest go outside.
    assert len(inside) == 4
    assert tots[:4] == inside
    assert all(not planner.timeline.in_push(t) for t in tots[4:])


def test_no_push_means_any_wave(profile) -> None:  # type: ignore[no-untyped-def]
    planner = _planner(profile, None, {Category.STRIKE: 16})
    assert planner.push_quota == {}
    assert planner._push_first(Category.STRIKE) is None
    assert planner._strike_tot(_point(0), Category.STRIKE) is not None


def test_main_push_sits_where_the_profile_says(profile) -> None:  # type: ignore[no-untyped-def]
    planner = cast(Any, JfaccPlanner.__new__(JfaccPlanner))
    planner.profile = profile
    planner.modifiers = ()
    planner.timeline = Timeline(profile, START, END)
    planner.game = SimpleNamespace(
        settings=SimpleNamespace(desired_player_mission_duration=timedelta(minutes=90))
    )
    push = planner._main_push(START, END)
    assert push == (START + timedelta(hours=2), START + timedelta(hours=3, minutes=30))
    # A short period: the push is pulled back so it fits.
    push = planner._main_push(START, START + timedelta(hours=2))
    assert push == (START + timedelta(minutes=30), START + timedelta(hours=2))
    # A profile without a push.
    irregular = load_profile("irregular")
    assert irregular is not None
    planner.profile = irregular
    assert planner._main_push(START, END) is None


def test_side_records_its_push() -> None:
    side = SideCampaign()
    assert side.push is None
    side.push_start, side.push_end = START, START + timedelta(hours=1)
    assert side.push == (START, START + timedelta(hours=1))
    # Saves from before the push load with none.
    side.__setstate__({"phase_since_turn": 3})
    assert side.push is None


def _package(task: FlightType, name: str = "T") -> Any:
    return SimpleNamespace(
        primary_task=task,
        flights=[SimpleNamespace(flight_type=task, alert=False, returning=False)],
        target=SimpleNamespace(name=name),
    )


def test_offensive_packages_are_strikes_not_lines() -> None:
    assert is_offensive_package(_package(FlightType.STRIKE))
    assert is_offensive_package(_package(FlightType.DEAD))
    assert is_offensive_package(_package(FlightType.OCA_RUNWAY))
    assert not is_offensive_package(_package(FlightType.BARCAP))
    assert not is_offensive_package(_package(FlightType.CAS))
    assert not is_offensive_package(_package(FlightType.AEWC))
