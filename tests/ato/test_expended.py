"""Weapons expended past the TOT (P5): what an AI flight carries when it
appears in the mission, by start stage."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.ato.flightstate.expended import (
    expended_loadout,
    loadout_at_mission_start,
    past_time_on_target,
)
from game.ato.loadouts import Loadout


class _Weapon:
    def __init__(self, name: str) -> None:
        self.name = name


ROLES = {"GBU-12": "a2g", "AGM-88": "arm", "AIM-120": "a2a", "Tank": "other", "TGP": "tgp"}


def _loadout(*names: str) -> Loadout:
    return Loadout("test", {i + 1: _Weapon(n) for i, n in enumerate(names)}, date=None)


def test_expended_loadout_keeps_air_to_air_pods_and_tanks() -> None:
    loadout = _loadout("GBU-12", "AGM-88", "AIM-120", "Tank", "TGP")
    expended = expended_loadout(loadout, lambda w: ROLES.get(w.name))
    assert [w.name for w in expended.pylons.values()] == ["AIM-120", "Tank", "TGP"]
    # The original is untouched, and a loadout with nothing to drop is itself.
    assert len(loadout.pylons) == 5
    clean = _loadout("AIM-120", "Tank")
    assert expended_loadout(clean, lambda w: ROLES.get(w.name)) is clean
    # Unknown weapons stay on the aircraft.
    unknown = _loadout("Mystery")
    assert expended_loadout(unknown, lambda w: None) is unknown


class _InFlight:
    def __init__(self, passed: bool) -> None:
        self._passed = passed

    def has_passed_waypoint(self, waypoint: Any) -> bool:
        return self._passed


def _flight(state: Any) -> Any:
    from game.ato.flightstate import InFlight

    # past_time_on_target checks isinstance(state, InFlight); fake it.
    flight = SimpleNamespace(state=state, flight_plan=SimpleNamespace(tot_waypoint="target"))
    return flight


def test_three_start_stages(monkeypatch: Any) -> None:
    import game.ato.flightstate.expended as expended
    from game.ato.flightstate import InFlight

    class _Airborne(InFlight):  # type: ignore[misc]
        def __init__(self, passed: bool) -> None:
            self._passed = passed

        def has_passed_waypoint(self, waypoint: Any) -> bool:
            return self._passed

        def estimate_altitude(self):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        def estimate_position(self):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        def estimate_speed(self):  # type: ignore[no-untyped-def]
            raise NotImplementedError

    monkeypatch.setattr(expended, "_role_of", lambda w: ROLES.get(w.name))
    loadout = _loadout("GBU-12", "AIM-120")
    # Not yet started: on the ground with everything.
    waiting = _flight(SimpleNamespace(is_waiting_for_start=True))
    assert not past_time_on_target(waiting)
    assert loadout_at_mission_start(waiting, loadout, player=False) is loadout
    # In the air before the TOT: on its route with everything.
    inbound = _flight(_Airborne(passed=False))
    assert not past_time_on_target(inbound)
    assert loadout_at_mission_start(inbound, loadout, player=False) is loadout
    # Past the TOT: on its way home, bombs gone, missiles kept.
    egressing = _flight(_Airborne(passed=True))
    assert past_time_on_target(egressing)
    result = loadout_at_mission_start(egressing, loadout, player=False)
    assert [w.name for w in result.pylons.values()] == ["AIM-120"]
    # Players always get their own loadout.
    assert loadout_at_mission_start(egressing, loadout, player=True) is loadout
