"""Saves, switching and the default of the turn model (W8).

The model is kept per period (AirCampaignState.focused), so a campaign
saved in either model loads and keeps it, and a changed setting applies
when the next turn is planned."""

from __future__ import annotations

import pickle
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from game.commander.jfacc.campaignstate import AirCampaignState, SideCampaign
from game.commander.jfacc.planner import focused_lead_in, period_hours
from game.commander.jfacc.profile import load_profile
from game.settings.settings import Settings
from game.sim import atoperiod

START = datetime(2026, 6, 1, 6, 0)


def _game(focused: bool, state: AirCampaignState) -> Any:
    settings = SimpleNamespace(
        focused_turns=focused,
        focused_lead_in_min=30,
        desired_player_mission_duration=timedelta(minutes=60),
        ato_period_hours=6,
    )
    return SimpleNamespace(settings=settings, air_campaign=state, turn=1)


def test_mission_only_is_off_by_default() -> None:
    assert Settings().focused_turns is False


def test_a_save_keeps_the_model_it_was_planned_in() -> None:
    state = AirCampaignState()
    state.note_period(3, START, START + timedelta(minutes=90), 30)
    state.window_offset_min = 30
    loaded = pickle.loads(pickle.dumps(state))
    game = _game(False, loaded)  # The setting changed after the save.
    game.turn = 3
    assert atoperiod.is_focused(game)
    assert atoperiod.window(game) == (START + timedelta(minutes=30), START + timedelta(minutes=90))
    assert atoperiod.max_window_offset_min(game) == 0


def test_a_save_from_before_the_choice_loads_as_a_full_turn() -> None:
    state = AirCampaignState()
    state.note_period(2, START, START + timedelta(hours=6))
    old = dict(state.__dict__)
    del old["focused"]  # Saves from before focused turns had no such field.
    loaded = AirCampaignState.__new__(AirCampaignState)
    loaded.__setstate__(old)
    game = _game(True, loaded)
    game.turn = 2
    assert not atoperiod.is_focused(game)
    assert atoperiod.max_window_offset_min(game) == 300


def test_old_side_state_loads_without_a_push() -> None:
    side = SideCampaign()
    old = dict(side.__dict__)
    del old["push_start"]
    del old["push_end"]
    loaded = SideCampaign.__new__(SideCampaign)
    loaded.__setstate__(old)
    assert loaded.push is None


def test_the_switch_applies_at_the_next_turn() -> None:
    profile = load_profile("western")
    assert profile is not None
    state = AirCampaignState()
    # Turn 1 was planned mission only, with packages held back.
    state.note_period(1, START, START + timedelta(minutes=90), 30)
    state.deferred_packages = {True: ["held"]}
    game = _game(False, state)
    assert atoperiod.is_focused(game)
    # The setting is now full turns: the next turn plans 6 hours, and the
    # new period resets the window offset and the held-back packages.
    assert focused_lead_in(game) is None
    assert period_hours(game, profile) == 6
    game.turn = 2
    state.note_period(2, START + timedelta(hours=6), START + timedelta(hours=12))
    assert not atoperiod.is_focused(game)
    assert state.window_offset_min == 0
    assert state.deferred_packages == {}
    assert atoperiod.max_window_offset_min(game) == 300
    # And back again.
    game.settings.focused_turns = True
    assert focused_lead_in(game) == timedelta(minutes=30)
    game.turn = 3
    state.note_period(3, START + timedelta(hours=12), START + timedelta(hours=13, minutes=30), 30)
    assert atoperiod.is_focused(game)
    assert atoperiod.max_window_offset_min(game) == 0
