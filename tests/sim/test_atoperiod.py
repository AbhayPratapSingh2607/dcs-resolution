"""The 6 hour ATO period and the DCS window (game.sim.atoperiod)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from game.commander.jfacc.campaignstate import AirCampaignState
from game.sim import atoperiod

START = datetime(2020, 6, 1, 6, 0)


class _Plan:
    def __init__(self, startup: datetime, land: datetime) -> None:
        self._startup = startup
        self.landing_time = land

    def startup_time(self) -> datetime:
        return self._startup


class _BrokenPlan:
    def startup_time(self) -> datetime:
        raise RuntimeError("no plan")


def _package(*windows: tuple[int, int], players: bool = False) -> SimpleNamespace:
    flights = [
        SimpleNamespace(
            flight_plan=_Plan(
                START + timedelta(minutes=a), START + timedelta(minutes=b)
            )
        )
        for a, b in windows
    ]
    return SimpleNamespace(flights=flights, has_players=players)


def _game(*packages: SimpleNamespace) -> SimpleNamespace:
    state = AirCampaignState()
    state.note_period(1, START, START + timedelta(hours=6))
    blue = SimpleNamespace(
        ato=SimpleNamespace(packages=list(packages)),
        player=SimpleNamespace(is_blue=True),
    )
    red = SimpleNamespace(
        ato=SimpleNamespace(packages=[]), player=SimpleNamespace(is_blue=False)
    )
    settings = SimpleNamespace(desired_player_mission_duration=timedelta(minutes=60))
    return SimpleNamespace(
        turn=1, air_campaign=state, blue=blue, red=red, settings=settings
    )


def _player_flight(startup_min: int, clients: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        client_count=clients,
        flight_plan=_Plan(
            START + timedelta(minutes=startup_min),
            START + timedelta(minutes=startup_min + 90),
        ),
    )


def test_mission_starts_at_the_first_player_startup() -> None:
    game = _game()
    assert atoperiod.player_window_start(game) is None  # type: ignore[arg-type]
    assert not atoperiod.align_window_to_players(game)  # type: ignore[arg-type]
    late = _player_flight(200)
    early = _player_flight(130)
    ai = _player_flight(10, clients=0)
    game.blue.ato.packages = [
        SimpleNamespace(flights=[late, ai], has_players=True),
        SimpleNamespace(flights=[early], has_players=True),
    ]
    assert atoperiod.player_window_start(game) == START + timedelta(minutes=130)  # type: ignore[arg-type]
    assert atoperiod.align_window_to_players(game)  # type: ignore[arg-type]
    assert atoperiod.window(game) == (  # type: ignore[arg-type]
        START + timedelta(minutes=130),
        START + timedelta(minutes=190),
    )
    # The late flight starts after the window: a warning, not a move.
    assert atoperiod.late_player_flights(game) == [late]  # type: ignore[arg-type]
    # A startup near the end of the period keeps a whole window inside it.
    game.blue.ato.packages = [
        SimpleNamespace(flights=[_player_flight(350)], has_players=True)
    ]
    assert atoperiod.player_window_start(game) == START + timedelta(minutes=300)  # type: ignore[arg-type]


def test_mission_only_turns_keep_their_fixed_window() -> None:
    game = _game()
    game.air_campaign.note_period(2, START, START + timedelta(minutes=90), 30)
    game.turn = 2
    game.blue.ato.packages = [
        SimpleNamespace(flights=[_player_flight(60)], has_players=True)
    ]
    assert atoperiod.player_window_start(game) is None  # type: ignore[arg-type]
    assert atoperiod.window(game)[0] == START + timedelta(minutes=30)  # type: ignore[arg-type,index]


def test_package_span_covers_all_flights() -> None:
    package = _package((10, 100), (5, 90), (20, 140))
    first, last = atoperiod.package_span(package)  # type: ignore[arg-type]
    assert first == START + timedelta(minutes=5)
    assert last == START + timedelta(minutes=140)


def test_package_span_skips_flights_without_plan() -> None:
    package = _package((10, 100))
    package.flights.append(SimpleNamespace(flight_plan=_BrokenPlan()))
    assert atoperiod.package_span(package) == (  # type: ignore[arg-type]
        START + timedelta(minutes=10),
        START + timedelta(minutes=100),
    )
    assert atoperiod.package_span(SimpleNamespace(flights=[])) == (None, None)  # type: ignore[arg-type]


def test_window_offset_is_clamped() -> None:
    game = _game()
    assert atoperiod.max_window_offset_min(game) == 300  # type: ignore[arg-type]
    atoperiod.set_window_offset(game, 10_000)  # type: ignore[arg-type]
    assert game.air_campaign.window_offset_min == 300
    start, end = atoperiod.window(game)  # type: ignore[arg-type,misc]
    assert start == START + timedelta(hours=5)
    assert end == START + timedelta(hours=6)


def test_defer_and_restore_packages_after_window() -> None:
    early = _package((0, 60))
    straddling = _package((30, 150))
    late = _package((200, 300))
    late_players = _package((200, 300), players=True)
    game = _game(early, straddling, late, late_players)
    atoperiod.set_window_offset(game, 60)  # type: ignore[arg-type]
    in_window = atoperiod.packages_in_window(game)  # type: ignore[arg-type]
    assert straddling in in_window and early not in in_window
    assert atoperiod.defer_after_window(game) == 1  # type: ignore[arg-type]
    assert late not in game.blue.ato.packages
    # Player packages are always flown.
    assert late_players in game.blue.ato.packages
    assert atoperiod.has_deferred(game)  # type: ignore[arg-type]
    assert atoperiod.restore_deferred(game) == [late]  # type: ignore[arg-type]
    assert late in game.blue.ato.packages
    assert not atoperiod.has_deferred(game)  # type: ignore[arg-type]


def test_a_dragged_window_stays_while_it_holds_the_player_flights() -> None:
    """Dragging the window on the timeline pins it: Take off keeps it there
    while every player flight starts inside it, else moves it to them."""
    flight = _player_flight(130)
    game = _game(SimpleNamespace(flights=[flight], has_players=True))
    atoperiod.pin_window(game, 105)  # type: ignore[arg-type]
    assert game.air_campaign.window_pinned
    assert atoperiod.align_window_to_players(game)  # type: ignore[arg-type]
    assert game.air_campaign.window_offset_min == 105
    # Dragged past the player's startup: Take off brings it back.
    atoperiod.pin_window(game, 150)  # type: ignore[arg-type]
    assert atoperiod.align_window_to_players(game)  # type: ignore[arg-type]
    assert game.air_campaign.window_offset_min == 130


def test_the_pin_is_for_one_turn() -> None:
    game = _game()
    atoperiod.pin_window(game, 60)  # type: ignore[arg-type]
    game.air_campaign.note_period(2, START, START + timedelta(hours=6))
    assert not game.air_campaign.window_pinned


class _TimedPlan(_Plan):
    """Startup at 130 min: 15 min to start, 8 to taxi, IP 20 min after
    takeoff."""

    def __init__(self) -> None:
        super().__init__(START + timedelta(minutes=130), START + timedelta(hours=4))
        from game.ato.flightwaypointtype import FlightWaypointType

        self.ip = SimpleNamespace(waypoint_type=FlightWaypointType.INGRESS_STRIKE)
        self.waypoints = [
            SimpleNamespace(waypoint_type=FlightWaypointType.TAKEOFF),
            self.ip,
        ]

    def estimate_startup(self) -> timedelta:
        return timedelta(minutes=15)

    def estimate_ground_ops(self) -> timedelta:
        return timedelta(minutes=8)

    def takeoff_time(self) -> datetime:
        return START + timedelta(minutes=153, seconds=30)

    def _travel_time_to_waypoint(self, waypoint: object) -> timedelta:
        return timedelta(minutes=20) if waypoint is self.ip else timedelta()


def test_the_window_starts_where_fast_forward_stops() -> None:
    """ "Fast forward until" picks where the mission starts for the player:
    startup, taxi, takeoff or the IP."""
    from game.settings.settings import FastForwardStopCondition as FF

    flight = SimpleNamespace(client_count=1, flight_plan=_TimedPlan())
    game = _game(SimpleNamespace(flights=[flight], has_players=True))
    expected = {
        FF.PLAYER_STARTUP: 130,
        FF.PLAYER_TAXI: 145,
        FF.PLAYER_TAKEOFF: 153,
        FF.PLAYER_AT_IP: 173.5,
        FF.FIRST_CONTACT: 130,
        FF.MANUAL: 130,
    }
    for condition, minutes in expected.items():
        game.settings.fast_forward_stop_condition = condition
        assert atoperiod.player_window_start(game) == START + timedelta(  # type: ignore[arg-type]
            minutes=minutes
        ), condition
    # No IP in the plan: the IP setting stops at takeoff.
    flight.flight_plan.waypoints = flight.flight_plan.waypoints[:1]
    game.settings.fast_forward_stop_condition = FF.PLAYER_AT_IP
    assert atoperiod.player_window_start(game) == START + timedelta(minutes=153)  # type: ignore[arg-type]


def test_picking_a_player_flight_moves_the_window_to_it() -> None:
    """A new player flight puts the window back at its default, even one the
    player dragged."""
    from game.settings.settings import FastForwardStopCondition as FF

    flight = SimpleNamespace(client_count=1, flight_plan=_TimedPlan())
    game = _game(SimpleNamespace(flights=[flight], has_players=True))
    game.settings.fast_forward_stop_condition = FF.PLAYER_TAXI
    atoperiod.pin_window(game, 30)  # type: ignore[arg-type]
    assert atoperiod.follow_player_selection(game)  # type: ignore[arg-type]
    assert not game.air_campaign.window_pinned
    assert game.air_campaign.window_offset_min == 145
    assert not atoperiod.follow_player_selection(game)  # type: ignore[arg-type]
    # A dragged window holding the player's taxi time stays at Take off.
    atoperiod.pin_window(game, 120)  # type: ignore[arg-type]
    assert atoperiod.align_window_to_players(game)  # type: ignore[arg-type]
    assert game.air_campaign.window_offset_min == 120
    # Mission only turns have nothing to move.
    game.air_campaign.note_period(2, START, START + timedelta(minutes=90), 30)
    game.turn = 2
    assert not atoperiod.follow_player_selection(game)  # type: ignore[arg-type]
