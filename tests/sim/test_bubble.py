"""The bubble (M3): relevance, clusters and the budget."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from game.ato.flighttype import FlightType
from game.sim import bubble

START = datetime(2026, 6, 1, 8, 0)
WINDOW = (START, START + timedelta(hours=1))
NM = 1852.0
BLUE = SimpleNamespace(is_blue=True)
RED = SimpleNamespace(is_blue=False)


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y


class _Plan:
    """A straight plan: takeoff at ``takeoff_min``, then legs of equal time."""

    def __init__(
        self,
        points: list[tuple[float, float]],
        takeoff_min: int,
        leg_min: int = 20,
        patrol: bool = False,
        reach_nm: float = 30,
    ) -> None:
        self.waypoints = [
            SimpleNamespace(position=_Point(x * NM, y * NM)) for x, y in points
        ]
        self._takeoff = START + timedelta(minutes=takeoff_min)
        self._leg = timedelta(minutes=leg_min)
        self.landing_time = self._takeoff + self._leg * (len(points) - 1)
        if patrol:
            self.layout = SimpleNamespace(
                patrol_start=self.waypoints[1], patrol_end=self.waypoints[2]
            )
            self.engagement_distance = SimpleNamespace(meters=reach_nm * NM)

    def takeoff_time(self) -> datetime:
        return self._takeoff

    def startup_time(self) -> datetime:
        return self._takeoff - timedelta(minutes=15)

    def total_time_between_waypoints(self, a: Any, b: Any) -> timedelta:
        return self._leg


def _package(
    side: Any,
    task: FlightType,
    plan: _Plan,
    target: tuple[float, float],
    players: bool = False,
    alert_radius_nm: float = 0.0,
    n: int = 2,
    name: str = "T",
) -> Any:
    package = SimpleNamespace(
        has_players=players,
        primary_task=task,
        target=SimpleNamespace(
            name=name, position=_Point(target[0] * NM, target[1] * NM)
        ),
        time_over_target=plan._takeoff + plan._leg,
        alert_radius_m=alert_radius_nm * NM,
        pinned=False,
    )
    flight = SimpleNamespace(
        flight_type=task,
        count=n,
        client_count=1 if players else 0,
        flight_plan=plan,
        squadron=SimpleNamespace(player=side),
        departure=SimpleNamespace(
            position=_Point(plan.waypoints[0].position.x, plan.waypoints[0].position.y)
        ),
        alert=alert_radius_nm > 0,
        package=package,
    )
    package.flights = [flight]
    package.primary_flight = flight
    return package


def _game(blue: list[Any], red: list[Any], budget: int = 10) -> Any:
    return SimpleNamespace(
        blue=SimpleNamespace(ato=SimpleNamespace(packages=blue), player=BLUE),
        red=SimpleNamespace(ato=SimpleNamespace(packages=red), player=RED),
        settings=SimpleNamespace(bubble_package_target=budget, bubble_enabled=True),
    )


def test_route_samples_follow_the_plan_inside_the_window() -> None:
    plan = _Plan(
        [(0, 0), (60, 0), (120, 0)], takeoff_min=-10
    )  # 08:10 at 60 nm, 08:30 at 120 nm
    flight = SimpleNamespace(flight_plan=plan)
    samples = bubble.route_samples(flight, WINDOW)  # type: ignore[arg-type]
    assert samples[0][0] == START
    at_0810 = next(p for t, p in samples if t == START + timedelta(minutes=10))
    assert abs(at_0810[0] / NM - 60) < 0.01
    assert samples[-1][0] <= START + timedelta(minutes=30)


def test_relevance_reasons() -> None:
    you = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 0), (50, 0), (100, 0), (0, 0)], takeoff_min=0),
        (100, 0),
        players=True,
    )
    crossing = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(50, 50), (50, 0), (50, -50)], takeoff_min=0),
        (50, -50),
    )
    far = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 300), (100, 300), (0, 300)], takeoff_min=0),
        (100, 300),
    )
    later = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 0), (50, 0), (0, 0)], takeoff_min=120),
        (50, 0),
    )
    near_target = _package(
        BLUE,
        FlightType.BAI,
        _Plan([(200, 0), (110, 10), (200, 0)], takeoff_min=0),
        (110, 10),
    )
    corridor = _package(
        BLUE,
        FlightType.DEAD,
        _Plan([(0, 100), (95, 5), (0, 100)], takeoff_min=-10),
        (95, 5),
    )
    cap = _package(
        RED,
        FlightType.BARCAP,
        _Plan(
            [(150, 0), (120, 20), (120, -20), (150, 0)], takeoff_min=-30, patrol=True
        ),
        (120, 0),
        name="CAP",
    )
    far_cap = _package(
        RED,
        FlightType.BARCAP,
        _Plan(
            [(300, 0), (280, 20), (280, -20), (300, 0)],
            takeoff_min=-30,
            patrol=True,
            reach_nm=20,
        ),
        (280, 0),
        name="CAP far",
    )
    alert = _package(
        RED,
        FlightType.BARCAP,
        _Plan([(130, 0), (130, 0), (130, 0)], takeoff_min=0),
        (130, 0),
        alert_radius_nm=80,
        name="Alert",
    )
    game = _game(
        [you, crossing, far, later, near_target, corridor], [cap, far_cap, alert]
    )

    result = bubble.compute(game, WINDOW)  # type: ignore[arg-type]
    assert result is not None
    reason = {
        p.target.name if p.target.name != "T" else id(p): result.reason(p)
        for p in [cap, far_cap, alert]
    }
    assert result.reason(you) == "your package" and result.in_mission(you)
    assert result.reason(crossing).startswith("crosses your route at 08:")
    assert result.reason(far).endswith(
        "nm from your mission"
    ) and not result.in_mission(far)
    assert result.reason(later) == "not in the air during your mission"
    assert result.reason(near_target).startswith("near your target")
    assert result.reason(
        corridor
    ) == "SEAD corridor on your route" and result.in_mission(corridor)
    assert reason["CAP"] == "CAP covers your route" and result.in_mission(cap)
    assert reason["CAP far"] == "on station away from your route"
    assert reason["Alert"] == "alert sector covers your route" and result.in_mission(
        alert
    )


def test_clusters_keep_a_cap_and_its_raid_together() -> None:
    you = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 0), (50, 0), (100, 0), (0, 0)], takeoff_min=0),
        (100, 0),
        players=True,
    )
    # A red raid far from the player, but it flies through a blue CAP's
    # commit region; the CAP itself is near the player's base.
    raid = _package(
        RED,
        FlightType.STRIKE,
        _Plan([(300, 200), (20, 200), (300, 200)], takeoff_min=0),
        (20, 200),
        name="Raid",
    )
    cap = _package(
        BLUE,
        FlightType.BARCAP,
        _Plan(
            [(0, 0), (10, 190), (30, 190), (0, 0)],
            takeoff_min=-20,
            patrol=True,
            reach_nm=40,
        ),
        (20, 190),
        name="CAP",
    )
    game = _game([you, cap], [raid], budget=10)
    result = bubble.compute(game, WINDOW)  # type: ignore[arg-type]
    assert result is not None
    assert result.relevance(cap).partners == [raid]  # type: ignore[union-attr]
    assert result.relevance(raid).partners == [cap]  # type: ignore[union-attr]
    # The raid alone is 200 nm away, but it comes in with the CAP.
    assert result.in_mission(cap) and result.in_mission(raid)


def test_budget_is_guidance_and_always_in_packages_are_outside_it() -> None:
    you = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 0), (50, 0), (100, 0), (0, 0)], takeoff_min=0),
        (100, 0),
        players=True,
    )
    pinned = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 300), (100, 300), (0, 300)], takeoff_min=0),
        (100, 300),
    )
    pinned.pinned = True
    tanker = _package(
        BLUE,
        FlightType.REFUELING,
        _Plan([(0, 0), (20, 40), (40, 40), (0, 0)], takeoff_min=-30, patrol=True),
        (30, 40),
        name="Texaco",
    )
    others = [
        _package(
            BLUE,
            FlightType.STRIKE,
            _Plan([(50, i * 5 + 5), (50, 0), (50, -50)], takeoff_min=0),
            (50, -50),
        )
        for i in range(6)
    ]
    game = _game([you, pinned, tanker] + others, [], budget=3)
    result = bubble.compute(game, WINDOW)  # type: ignore[arg-type]
    assert result is not None
    assert result.reason(pinned) == "pinned: keep in my mission" and result.in_mission(
        pinned
    )
    assert result.reason(tanker) == "your tanker" and result.in_mission(tanker)
    inside = [p for p in others if result.in_mission(p)]
    assert len(inside) == 3
    assert result.packages(True, inside=False) == [p for p in others if p not in inside]
    assert result.summary().startswith("bubble: blue 6 in, 3 elsewhere")


def test_no_bubble_without_a_player_flight() -> None:
    lone = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 0), (50, 0), (0, 0)], takeoff_min=0),
        (50, 0),
    )
    assert bubble.compute(_game([lone], []), WINDOW) is None  # type: ignore[arg-type]


def test_defer_elsewhere_holds_back_the_rest() -> None:
    you = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 0), (50, 0), (100, 0), (0, 0)], takeoff_min=0),
        (100, 0),
        players=True,
    )
    far = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 300), (100, 300), (0, 300)], takeoff_min=0),
        (100, 300),
    )
    red_far = _package(
        RED,
        FlightType.STRIKE,
        _Plan([(400, 300), (300, 300), (400, 300)], takeoff_min=0),
        (300, 300),
    )
    game = _game([you, far], [red_far])
    game.air_campaign = SimpleNamespace(deferred_packages={})
    result = bubble.compute(game, WINDOW)  # type: ignore[arg-type]
    assert result is not None
    assert bubble.defer_elsewhere(game, result) == 2  # type: ignore[arg-type]
    assert game.blue.ato.packages == [you]
    assert game.red.ato.packages == []
    assert game.air_campaign.deferred_packages == {True: [far], False: [red_far]}
    assert bubble.is_elsewhere(far) and not bubble.is_elsewhere(you)


def test_preview_places_the_window_on_the_player_and_caches(monkeypatch: Any) -> None:
    from game.sim import atoperiod

    you = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 0), (50, 0), (100, 0), (0, 0)], takeoff_min=0),
        (100, 0),
        players=True,
    )
    far = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 300), (100, 300), (0, 300)], takeoff_min=0),
        (100, 300),
    )
    game = _game([you, far], [])
    monkeypatch.setattr(atoperiod, "is_focused", lambda g: False)
    monkeypatch.setattr(atoperiod, "player_window_start", lambda g: START)
    monkeypatch.setattr(atoperiod, "window_length", lambda g: timedelta(hours=1))
    calls = []
    real = bubble.compute
    monkeypatch.setattr(bubble, "compute", lambda g, w: calls.append(w) or real(g, w))
    first = bubble.preview(game)  # type: ignore[arg-type]
    assert first is not None and calls == [WINDOW]
    assert bubble.elsewhere_ids(game) == {id(far)}  # type: ignore[arg-type]
    assert len(calls) == 1  # cached
    far.pinned = True
    assert bubble.elsewhere_ids(game) == set()  # type: ignore[arg-type]
    assert len(calls) == 2
    game.settings.bubble_enabled = False
    assert bubble.preview(game) is None  # type: ignore[arg-type]


def test_parked_aircraft_of_packages_elsewhere_at_the_player_base() -> None:
    from game.ato.flightstate import Completed, WaitingForStart

    you = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 0), (50, 0), (0, 0)], takeoff_min=0),
        (50, 0),
        players=True,
    )
    home = you.flights[0].departure
    later = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 300), (100, 300), (0, 300)], takeoff_min=30),
        (100, 300),
        n=4,
    )
    airborne = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 300), (100, 300), (0, 300)], takeoff_min=-10),
        (100, 300),
    )
    other_base = _package(
        BLUE,
        FlightType.STRIKE,
        _Plan([(0, 300), (100, 300), (0, 300)], takeoff_min=30),
        (100, 300),
    )
    for package in (later, airborne):
        package.flights[0].departure = home
        package.deferred_reason = "elsewhere"
    other_base.deferred_reason = "elsewhere"
    later.flights[0].state = object.__new__(WaitingForStart)
    airborne.flights[0].state = SimpleNamespace()
    other_base.flights[0].state = object.__new__(Completed)
    game = _game([you], [])
    game.air_campaign = SimpleNamespace(
        deferred_packages={True: [later, airborne, other_base]}
    )
    parked = bubble.parked_at_player_bases(game)  # type: ignore[arg-type]
    assert [(s is later.flights[0].squadron, n) for s, n in parked] == [(True, 4)]
