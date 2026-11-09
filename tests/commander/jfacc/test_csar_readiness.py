"""The JFACC keeps a standing CSAR force: request_csar_readiness asks for
helicopters when the side is short, ahead of ordinary replacements."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.ato.flighttype import FlightType
from game.commander.jfacc.planner import request_csar_readiness


def _squadron(owned: int, pending: int = 0, max_size: int = 8, csar: bool = True) -> Any:
    tasks = {FlightType.CSAR} if csar else {FlightType.BARCAP}
    return SimpleNamespace(
        owned_aircraft=owned,
        pending_deliveries=pending,
        max_size=max_size,
        auto_assignable_mission_types=tasks,
        location=SimpleNamespace(name=f"base{owned}"),
        aircraft=SimpleNamespace(helicopter=True),
    )


def _coalition(squadrons: list[Any], blue: bool = True, enabled: bool = True) -> Any:
    requests: list[Any] = []
    settings = SimpleNamespace(csar_enabled=enabled, csar_enabled_red=enabled)
    return SimpleNamespace(
        game=SimpleNamespace(settings=settings),
        player=SimpleNamespace(is_blue=blue),
        air_wing=SimpleNamespace(iter_squadrons=lambda: iter(squadrons)),
        add_procurement_request=requests.append,
        requests=requests,
    )


def test_requests_shortfall_for_empty_squadron() -> None:
    empty = _squadron(0)
    coalition = _coalition([empty, _squadron(1), _squadron(6, csar=False)])
    assert request_csar_readiness(coalition, 4) == 3
    # The full order, then a pair as the fallback for a tight budget.
    assert [(r.task_capability, r.number) for r in coalition.requests] == [
        (FlightType.CSAR, 3),
        (FlightType.CSAR, 2),
    ]
    assert coalition.requests[0].near is empty.location
    assert coalition.requests[0].heli


def test_pending_deliveries_count_as_ready() -> None:
    coalition = _coalition([_squadron(0, pending=4)])
    assert request_csar_readiness(coalition, 4) == 0
    assert coalition.requests == []


def test_spreads_over_squadrons_when_one_is_full() -> None:
    coalition = _coalition([_squadron(0, max_size=2), _squadron(1, max_size=2)])
    assert request_csar_readiness(coalition, 4) == 3
    assert [r.number for r in coalition.requests] == [2, 1]


def test_nothing_when_csar_disabled_or_no_squadrons() -> None:
    off = _coalition([_squadron(0)], enabled=False)
    assert request_csar_readiness(off, 4) == 0
    none = _coalition([_squadron(0, csar=False)])
    assert request_csar_readiness(none, 4) == 0
    red = _coalition([_squadron(0)], blue=False)
    assert request_csar_readiness(red, 4) == 4
