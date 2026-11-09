"""Emission control orders from the IADS management (game/commander/jfacc/iads.py)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.commander.jfacc import iads
from game.commander.jfacc.campaignstate import AirCampaignState, SideCampaign
from game.commander.jfacc.profile import load_profile
from game.data.groups import GroupTask
from game.theater import Player


def _site(name: str, task: GroupTask, blue: bool = False) -> Any:
    return SimpleNamespace(
        id=name,
        name=name,
        task=task,
        control_point=SimpleNamespace(captured=Player.BLUE if blue else Player.RED),
    )


@pytest.fixture
def sites(monkeypatch: Any) -> list[Any]:
    result = [
        _site("sa10", GroupTask.LORAD),
        _site("sa11-a", GroupTask.MERAD),
        _site("sa11-b", GroupTask.MERAD),
        _site("sa15", GroupTask.SHORAD),
    ]
    monkeypatch.setattr(iads, "_radar_sams", lambda game, player: result)
    return result


def _plan(profile_name: str, side: SideCampaign, preserving: bool = False) -> dict[str, str]:
    profile = load_profile(profile_name)
    assert profile is not None
    return iads.plan_emcon(None, Player.RED, side, profile, preserving)  # type: ignore[arg-type]


def test_western_does_not_manage_its_iads(sites: list[Any]) -> None:
    side = SideCampaign()
    side.iads_orders = {"stale": "dark"}
    assert _plan("western", side) == {}
    assert side.iads_orders == {}


def test_doctrine_defaults(sites: list[Any]) -> None:
    modern = _plan("russian_modern", SideCampaign())
    assert set(modern.values()) == {"active"}
    soviet = _plan("soviet", SideCampaign())
    assert soviet["sa10"] == "active"
    assert soviet["sa11-a"] == soviet["sa15"] == "ambush"


def test_hunted_sites_ambush_and_go_dark_when_preserving(sites: list[Any]) -> None:
    side = SideCampaign()
    side.attacked = {"sa11-a": 2.0, "sa10": 1.0, "sa15": 0.2}
    orders = _plan("russian_modern", side)
    assert orders["sa11-a"] == orders["sa10"] == "ambush"
    assert orders["sa15"] == "active"
    preserving = _plan("russian_modern", side, preserving=True)
    # max_dark_share 0.3 of 4 sites: only the most hunted goes dark.
    assert preserving["sa11-a"] == "dark"
    assert preserving["sa10"] == "ambush"


def test_client_hides_more_of_its_iads(sites: list[Any]) -> None:
    side = SideCampaign()
    side.attacked = {"sa11-a": 2.0, "sa10": 1.0, "sa15": 0.6}
    orders = _plan("client", side, preserving=True)
    assert [orders[s] for s in ("sa11-a", "sa10")] == ["dark", "dark"]
    assert orders["sa15"] == "ambush"


def test_order_lookup_by_owner() -> None:
    state = AirCampaignState()
    state.side(False).iads_orders = {"sa11": "ambush"}
    game = SimpleNamespace(air_campaign=state)
    assert iads.emcon_order(game, _site("sa11", GroupTask.MERAD)) == "ambush"  # type: ignore[arg-type]
    # A blue site of the same id is not red's to order.
    assert iads.emcon_order(game, _site("sa11", GroupTask.MERAD, blue=True)) == ""  # type: ignore[arg-type]
    assert iads.emcon_order(None, _site("sa11", GroupTask.MERAD)) == ""


def test_skynet_overrides_use_the_dark_autonomous_mode() -> None:
    assert iads.skynet_overrides("active") == {}
    ambush = iads.skynet_overrides("ambush")
    assert ambush["autonomous_behaviour"].endswith("AUTONOMOUS_STATE_DARK")
    assert int(iads.skynet_overrides("dark")["go_live_range_in_percent"]) < int(
        ambush["go_live_range_in_percent"]
    )


def test_combat_model_reads_the_order() -> None:
    from game.sim.combat.model.engine import CombatModel

    state = AirCampaignState()
    state.side(False).iads_orders = {"sa11": "dark"}
    model = CombatModel.__new__(CombatModel)
    model.game = SimpleNamespace(air_campaign=state)  # type: ignore[assignment]
    assert model.site_emcon(_site("sa11", GroupTask.MERAD)) == "dark"  # type: ignore[arg-type]
    assert model.site_emcon(_site("sa6", GroupTask.MERAD)) == ""  # type: ignore[arg-type]
