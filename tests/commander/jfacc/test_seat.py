"""Your seat (M2): the preference, ranked offers and fragging."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from game.ato.flighttype import FlightType
from game.commander.jfacc import seat
from game.commander.jfacc.seat import PlayerPreference
from game.settings.settings import AutoAtoBehavior

START = datetime(2026, 6, 1, 6, 0)
PUSH = (START + timedelta(hours=2), START + timedelta(hours=3))


class _Pilot:
    def __init__(self, player: bool = False) -> None:
        self.player = player


class _Roster:
    def __init__(self, n: int) -> None:
        self.pilots: list[Any] = [_Pilot() for _ in range(n)]

    @property
    def max_size(self) -> int:
        return len(self.pilots)

    def pilot_at(self, i: int) -> Any:
        return self.pilots[i]

    def set_pilot(self, i: int, pilot: Any) -> None:
        self.pilots[i] = pilot

    def iter_pilots(self):  # type: ignore[no-untyped-def]
        yield from self.pilots


def _squadron(name: str, task: FlightType, flyable: bool = True, owned: int = 12) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        aircraft=SimpleNamespace(flyable=flyable, display_name="F-16C"),
        auto_assignable_mission_types={task, FlightType.BARCAP},
        primary_task=task,
        owned_aircraft=owned,
        untasked_aircraft=owned,
        location=SimpleNamespace(name="Kutaisi"),
        claim_available_pilot=lambda: _Pilot(),
    )


def _flight(squadron: Any, task: FlightType, n: int = 2, alert: bool = False) -> Any:
    flight = SimpleNamespace(
        squadron=squadron,
        flight_type=task,
        count=n,
        unit_type=squadron.aircraft,
        alert=alert,
        returning=False,
        roster=_Roster(n),
        state=SimpleNamespace(is_waiting_for_start=True),
    )
    flight.client_count = 0  # replaced by a property below
    return flight


def _package(target: str, tot_min: int, *flights: Any) -> Any:
    package = SimpleNamespace(
        target=SimpleNamespace(name=target),
        time_over_target=START + timedelta(minutes=tot_min),
        flights=list(flights),
        package_description=flights[0].flight_type.value if flights else "Package",
    )
    for flight in flights:
        flight.package = package
    return package


def _client_count(flight: Any) -> int:
    return sum(1 for p in flight.roster.pilots if p is not None and p.player)


def _game(packages: list[Any], squadrons: list[Any], behavior: Any = AutoAtoBehavior.Default) -> Any:
    for package in packages:
        for flight in package.flights:
            # SimpleNamespace can't have properties; the seat reads
            # client_count, so keep it in step by hand in the tests.
            flight.client_count = _client_count(flight)
    side = SimpleNamespace(push=PUSH, phase_title="Phase I")
    return SimpleNamespace(
        blue=SimpleNamespace(
            ato=SimpleNamespace(packages=packages),
            air_wing=SimpleNamespace(iter_squadrons=lambda: iter(squadrons)),
        ),
        air_campaign=SimpleNamespace(maybe_side=lambda blue: side),
        settings=SimpleNamespace(auto_ato_behavior=behavior),
        player_preference=PlayerPreference(),
        turn=1,
    )


def test_offers_rank_squadron_then_mission_type_then_push(monkeypatch: Any) -> None:
    import game.commander.jfacc.planner as planner

    monkeypatch.setattr(planner, "counts_toward_target", lambda p: True)
    vfa = _squadron("VFA-103", FlightType.STRIKE)
    vf = _squadron("VF-41", FlightType.SWEEP)
    awacs = _squadron("VAW-124", FlightType.AEWC, flyable=False)
    packages = [
        _package("Bridge", 45, _flight(vf, FlightType.STRIKE)),
        _package("SA-10", 125, _flight(vfa, FlightType.DEAD)),
        _package("Depot", 250, _flight(vfa, FlightType.STRIKE)),
        _package("Sweep", 130, _flight(vf, FlightType.SWEEP)),
        _package("AWACS", 20, _flight(awacs, FlightType.AEWC)),
        _package("Alert", 20, _flight(vf, FlightType.BARCAP, alert=True)),
    ]
    game = _game(packages, [vfa, vf, awacs])
    game.player_preference = PlayerPreference(squadron_id=vfa.id, mission_type=FlightType.SWEEP)
    offers = seat.rank_offers(game)
    names = [o.package.target.name for o in offers]
    # The squadron's flights first (the push before the later one), then the
    # mission type, then the rest; AWACS isn't flyable, the alert isn't offered.
    assert names == ["SA-10", "Depot", "Sweep", "Bridge"]
    assert offers[0].reasons == ["your squadron", "main push"]
    assert offers[2].reasons == ["your mission type", "main push"]
    assert seat.why_no_match(game) == ""


def test_reason_when_the_plan_has_nothing_for_the_preference(monkeypatch: Any) -> None:
    import game.commander.jfacc.planner as planner

    monkeypatch.setattr(planner, "counts_toward_target", lambda p: True)
    vfa = _squadron("VFA-103", FlightType.STRIKE, owned=12)
    vfa.untasked_aircraft = 4
    vf = _squadron("VF-41", FlightType.SWEEP)
    game = _game([_package("Sweep", 130, _flight(vf, FlightType.SWEEP))], [vfa, vf])
    game.player_preference = PlayerPreference(squadron_id=vfa.id)
    assert seat.why_no_match(game) == (
        "VFA-103 isn't tasked this turn: 8 of 12 aircraft are in turnaround or on order"
    )
    game.player_preference = PlayerPreference(mission_type=FlightType.STRIKE)
    assert seat.why_no_match(game) == "No Strike package in the Phase I plan this turn"
    game.player_preference = PlayerPreference(mission_type=FlightType.CAS)
    assert seat.why_no_match(game).startswith("No squadron you can fly is set to plan CAS")
    # The preference still gets an offer: the best of the rest.
    assert [o.tier for o in seat.rank_offers(game)] == [2]


def test_frag_moves_the_player_between_flights(monkeypatch: Any) -> None:
    import game.commander.jfacc.planner as planner

    monkeypatch.setattr(planner, "counts_toward_target", lambda p: True)
    vfa = _squadron("VFA-103", FlightType.STRIKE)
    a = _flight(vfa, FlightType.STRIKE)
    b = _flight(vfa, FlightType.DEAD)
    game = _game([_package("Bridge", 125, a), _package("SA-10", 130, b)], [vfa])
    # Auto-frag takes the top offer.
    assert seat.auto_frag(game) is a
    assert a.roster.pilots[0].player and getattr(a, "fragged", False)
    a.client_count = _client_count(a)
    assert seat.fragged_flight(game) is a
    # Taking another flight moves the player.
    assert seat.frag(game, b)
    assert not a.roster.pilots[0].player and not a.fragged
    assert b.roster.pilots[0].player and b.fragged
    a.client_count, b.client_count = _client_count(a), _client_count(b)
    assert seat.fragged_flight(game) is b
    # A player already in a flight by hand is left alone by auto-frag.
    seat.unfrag(game)
    b.client_count = 0
    a.roster.pilots[1].player = True
    a.client_count = _client_count(a)
    assert seat.auto_frag(game) is a
    assert not getattr(b, "fragged", False)


def test_auto_frag_only_with_no_preference_behaviour() -> None:
    vfa = _squadron("VFA-103", FlightType.STRIKE)
    game = _game([_package("Bridge", 125, _flight(vfa, FlightType.STRIKE))], [vfa])
    for behavior in (AutoAtoBehavior.Prefer, AutoAtoBehavior.Never, AutoAtoBehavior.RoutineOnly):
        game.settings.auto_ato_behavior = behavior
        assert not seat.auto_frag_enabled(game)
        assert seat.auto_frag(game) is None
    game.settings.auto_ato_behavior = AutoAtoBehavior.Default
    assert seat.auto_frag_enabled(game)


def test_preference_loads_from_old_saves() -> None:
    preference = PlayerPreference.__new__(PlayerPreference)
    preference.__setstate__({})
    assert preference.empty
    preference.__setstate__({"mission_type": FlightType.CAS})
    assert preference.mission_type is FlightType.CAS and preference.squadron_id is None


def test_frag_moves_the_dcs_window_to_the_new_flight(monkeypatch: Any) -> None:
    import game.sim.atoperiod as atoperiod

    calls: list[Any] = []
    monkeypatch.setattr(atoperiod, "follow_player_selection", calls.append)
    vfa = _squadron("VFA-103", FlightType.STRIKE)
    a = _flight(vfa, FlightType.STRIKE)
    game = _game([_package("Bridge", 125, a)], [vfa])
    assert seat.frag(game, a)
    assert calls == [game]
