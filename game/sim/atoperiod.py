"""The 6 hour ATO period and the DCS window inside it.

When a side plans with the JFACC planner, a turn covers a whole ATO period
(6 hours by default), longer than any DCS mission. The player picks a window
of the period to fly in DCS:

* everything before the window is fought by the combat model first
  (MissionSimulation.advance_to_window), so flights still airborne at the
  window start spawn in flight at the right place;
* packages that start after the window are held back from the .miz
  (defer_after_window);
* once the DCS results are in, the held-back packages are fought by the
  combat model (resolve_remainder) and their air, strike and intelligence
  results are committed.

Ground combat belongs to the window only: the front-line model is calibrated
for about one mission's worth of fighting per turn.

A focused turn (settings.focused_turns) plans only the lead-in and the
window: the window starts when the lead-in ends, there is nothing to pick,
and the lead-in is where flights that "took off before the mission" fly to
where they are at mission start.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight, Package
    from game.debriefing import Debriefing
    from game.sim.gameupdateevents import GameUpdateEvents

TICK = timedelta(seconds=1)
#: Time after the last TOT for flights to recover, as for normal turns.
RECOVERY = timedelta(minutes=45)


def period(game: Game) -> Optional[tuple[datetime, datetime]]:
    state = getattr(game, "air_campaign", None)
    if state is None:
        return None
    return state.period_for(game.turn)


def window_length(game: Game) -> timedelta:
    return game.settings.desired_player_mission_duration


def window(game: Game) -> Optional[tuple[datetime, datetime]]:
    """Start and end of the DCS window, or None without an ATO period."""
    bounds = period(game)
    if bounds is None:
        return None
    start, end = bounds
    offset = timedelta(minutes=game.air_campaign.window_offset_min)
    window_start = min(start + offset, end)
    return window_start, window_start + window_length(game)


def is_focused(game: Game) -> bool:
    """Whether this turn's period is a focused turn (fixed window, no picker)."""
    return period(game) is not None and bool(
        getattr(game.air_campaign, "focused", False)
    )


def max_window_offset_min(game: Game) -> int:
    """How far into the period the player may move the DCS window (0: there's
    nothing to pick)."""
    bounds = period(game)
    if bounds is None or is_focused(game):
        return 0
    start, end = bounds
    span = (end - start) - window_length(game)
    return max(0, int(span.total_seconds() // 60))


def set_window_offset(game: Game, minutes: int) -> None:
    if is_focused(game):
        return
    game.air_campaign.window_offset_min = max(
        0, min(int(minutes), max_window_offset_min(game))
    )


def player_flights(game: Game) -> list[Flight]:
    """Blue's flights with a player in them."""
    return [
        flight
        for package in game.blue.ato.packages
        for flight in package.flights
        if flight.client_count
    ]


def player_window_start(game: Game) -> Optional[datetime]:
    """Full turns (P4): the mission starts when the earliest flight with a
    player in it starts up, kept inside the period. None in a mission only
    turn, without a period, or without a player flight."""
    bounds = period(game)
    if bounds is None or is_focused(game):
        return None
    starts: list[datetime] = []
    for flight in player_flights(game):
        try:
            starts.append(flight.flight_plan.startup_time())
        except Exception:
            continue
    if not starts:
        return None
    start, end = bounds
    latest = max(start, end - window_length(game))
    return max(start, min(min(starts), latest))


def pin_window(game: Game, minutes: int) -> None:
    """The player moved the window (dragging it on the timeline)."""
    set_window_offset(game, minutes)
    if not is_focused(game):
        game.air_campaign.window_pinned = True


def pinned_window_holds_players(game: Game) -> bool:
    """Whether the window the player placed has every player flight starting
    inside it (else Take off moves it to them)."""
    if not getattr(game.air_campaign, "window_pinned", False):
        return False
    bounds = window(game)
    if bounds is None:
        return False
    for flight in player_flights(game):
        try:
            startup = flight.flight_plan.startup_time()
        except Exception:
            continue
        if not bounds[0] <= startup < bounds[1]:
            return False
    return True


def align_window_to_players(game: Game) -> bool:
    """Move the DCS window to the player's flight (P4). Returns False when
    there is no player flight, in which case the window stays where it was
    (blue's main push, or the player's pick). A window the player dragged
    stays put while it still holds every player flight's startup."""
    when = player_window_start(game)
    if when is None:
        return False
    if pinned_window_holds_players(game):
        return True
    bounds = period(game)
    assert bounds is not None
    set_window_offset(game, int((when - bounds[0]).total_seconds() // 60))
    return True


def late_player_flights(game: Game) -> list[Flight]:
    """Player flights that start up after the mission window ends: they are
    in the mission, but a long wait from the earliest player's startup."""
    bounds = window(game)
    if bounds is None:
        return []
    late = []
    for flight in player_flights(game):
        try:
            if flight.flight_plan.startup_time() >= bounds[1]:
                late.append(flight)
        except Exception:
            continue
    return late


def ground_window(game: Game) -> Optional[tuple[datetime, datetime]]:
    bounds = window(game)
    if bounds is None:
        return None
    return bounds[0], bounds[1] + RECOVERY


def simulated_turn_limit(game: Game) -> timedelta:
    """How long a turn fought entirely by the combat model may run."""
    bounds = period(game)
    base = game.settings.desired_player_mission_duration
    if bounds is not None:
        base = max(base, bounds[1] - bounds[0])
    return base + RECOVERY


def packages_in_window(game: Game, blue: bool = True) -> list[Package]:
    bounds = window(game)
    coalition = game.blue if blue else game.red
    if bounds is None:
        return list(coalition.ato.packages)
    start, end = bounds
    result = []
    for package in coalition.ato.packages:
        first, last = package_span(package)
        if first is None or last is None:
            continue
        if first < end and last > start:
            result.append(package)
    return result


def package_span(package: Package) -> tuple[Optional[datetime], Optional[datetime]]:
    starts: list[datetime] = []
    ends: list[datetime] = []
    for flight in package.flights:
        try:
            start = flight.flight_plan.startup_time()
            end = flight.flight_plan.landing_time
        except Exception:
            continue
        starts.append(start)
        ends.append(end)
    if not starts:
        return None, None
    return min(starts), max(ends)


def align_player_packages(game: Game, now: datetime) -> list[Package]:
    """Focused turns: a package with player slots whose players would start
    up during the lead-in is moved later as a whole, so the players start at
    mission start with the start type they chose rather than being flown
    into the air by the combat model. ``now`` is the simulation time; the
    moved flights' states are reset to it."""
    from game.ato.flightstate import Uninitialized

    bounds = window(game)
    if bounds is None or not is_focused(game):
        return []
    window_start = bounds[0]
    moved: list[Package] = []
    for coalition in (game.blue, game.red):
        for package in coalition.ato.packages:
            players = [f for f in package.flights if f.client_count]
            if not players:
                continue
            try:
                first = min(f.flight_plan.startup_time() for f in players)
            except Exception:
                continue
            if first >= window_start:
                continue
            package.time_over_target += window_start - first
            for flight in package.flights:
                flight.set_state(Uninitialized(flight, game.settings))
                flight.state.reinitialize(now)
            moved.append(package)
            logging.info(
                f"Moved {package} by {window_start - first} so its players start "
                "at mission start"
            )
    return moved


def defer_after_window(game: Game) -> int:
    """Hold back packages that start after the DCS window. Their aircraft stay
    claimed; the packages return to the ATO in resolve_remainder."""
    bounds = window(game)
    if bounds is None:
        return 0
    _, window_end = bounds
    state = game.air_campaign
    deferred = 0
    for coalition in (game.blue, game.red):
        held = state.deferred_packages.setdefault(coalition.player.is_blue, [])
        for package in list(coalition.ato.packages):
            first, _ = package_span(package)
            if first is None or first < window_end:
                continue
            if package.has_players:
                # Player flights are only ever flown, never resolved.
                continue
            coalition.ato.packages.remove(package)
            held.append(package)
            deferred += 1
    if deferred:
        logging.info(f"Deferred {deferred} packages past the DCS window")
    return deferred


def restore_deferred(game: Game) -> list[Package]:
    state = game.air_campaign
    restored: list[Package] = []
    for coalition in (game.blue, game.red):
        held = state.deferred_packages.pop(coalition.player.is_blue, [])
        for package in held:
            coalition.ato.packages.append(package)
            restored.append(package)
    return restored


def has_deferred(game: Game) -> bool:
    state = getattr(game, "air_campaign", None)
    if state is None:
        return False
    return any(state.deferred_packages.values())


def quit_time(game: Game, debriefing: Optional[Debriefing]) -> Optional[datetime]:
    """When the player quit DCS (P6): the window start plus the mission time
    the state file reports. None without a window; the window end when the
    state has no elapsed time (a crash, a manually submitted result or an
    old plugin), in which case the mission counts as flown to the end of
    its window."""
    bounds = window(game)
    if bounds is None:
        return None
    elapsed = None
    if debriefing is not None:
        state = getattr(debriefing, "state_data", None)
        elapsed = getattr(state, "elapsed_seconds", None)
    if elapsed is None:
        return bounds[1]
    when = bounds[0] + timedelta(seconds=float(elapsed))
    return max(bounds[0], min(when, bounds[1]))


def unfinished_packages(
    game: Game, debriefing: Optional[Debriefing], when: datetime
) -> list[Package]:
    """Packages in the mission whose flights hadn't finished when the player
    quit at ``when``: no players (their flights are only ever flown), at
    least one flight still airborne or yet to fly by its plan, and not
    every aircraft lost in DCS."""
    lost: dict[int, int] = {}
    air_losses = getattr(debriefing, "air_losses", None)
    for loss in list(getattr(air_losses, "losses", []) or []):
        key = id(loss.flight)
        lost[key] = lost.get(key, 0) + 1
    found: list[Package] = []
    for coalition in (game.blue, game.red):
        for package in coalition.ato.packages:
            if package.has_players:
                continue
            alive = [f for f in package.flights if lost.get(id(f), 0) < f.count]
            if not alive:
                continue
            _, last = package_span(package)
            if last is None or last <= when:
                continue
            found.append(package)
    return found


def resolve_remainder(
    game: Game, events: GameUpdateEvents, debriefing: Optional[Debriefing] = None
) -> Optional[Debriefing]:
    """Fight what DCS didn't with the combat model and commit the results:
    the flights in the mission that hadn't finished when the player quit
    (P6), from where their plans put them at that time, and then the
    packages held back for after the window. ``debriefing`` is the DCS
    result; None fights only the held-back packages from the window end."""
    bounds = window(game)
    period_bounds = period(game)
    if bounds is None or period_bounds is None:
        return None
    from .bubble import is_elsewhere

    quit = quit_time(game, debriefing) if debriefing is not None else None
    when = quit if quit is not None else bounds[1]
    continued = unfinished_packages(game, debriefing, when) if when < bounds[1] else []
    restored = restore_deferred(game)
    if not restored and not continued:
        return None
    # Packages outside the bubble (M3) fly the mission's time here: they
    # carry on from where the fighting before the window left them.
    elsewhere = [p for p in restored if is_elsewhere(p)]
    saved_states = {id(f): f.state for p in elsewhere for f in p.flights}
    from game.debriefing import Debriefing
    from game.sim.aircraftsimulation import AircraftSimulation
    from game.sim.missionresultsprocessor import MissionResultsProcessor
    from game.settings.settings import CombatResolutionMethod
    from game.unitmap import UnitMap

    # Only the held-back and the unfinished packages fly: everything else
    # already did. The unfinished ones join at the quit.
    flying = {id(p) for p in restored}
    pending = {id(p) for p in continued}
    others: dict[bool, list[Package]] = {}
    joining: dict[bool, list[Package]] = {}
    for coalition in (game.blue, game.red):
        keep = [p for p in coalition.ato.packages if id(p) not in flying]
        others[coalition.player.is_blue] = [p for p in keep if id(p) not in pending]
        joining[coalition.player.is_blue] = [p for p in keep if id(p) in pending]
        for package in keep:
            coalition.ato.packages.remove(package)

    # With packages elsewhere the combat model starts at the window start;
    # otherwise at the quit (or the window end when the player flew it all).
    if elsewhere:
        start = bounds[0]
    elif continued:
        start = when
    else:
        start = bounds[1]
    end = period_bounds[1] + RECOVERY
    simulation = AircraftSimulation(game)
    simulation.ground_war_enabled = False
    simulation.begin_simulation(start)
    _restore_states(saved_states, game, start)
    time = start
    joined = not continued
    if not joined and when <= start:
        _join(game, joining, when, simulation)
        joined = True
    with_events = events
    try:
        while time < end:
            time += TICK
            if not joined and time >= when:
                _join(game, joining, when, simulation)
                joined = True
            simulation.on_game_tick(
                with_events, time, TICK, CombatResolutionMethod.RESOLVE, True
            )
            if joined and not simulation.has_activity():
                break
        debriefing_out = Debriefing({"mission_ended": True}, game, UnitMap())
        debriefing_out.merge_simulation_results(simulation.results)
        MissionResultsProcessor(game).commit_resolved_period(debriefing_out, events)
        simulation.results.forget_undo()
    finally:
        for coalition in (game.blue, game.red):
            side = coalition.player.is_blue
            coalition.ato.packages.extend(others[side])
            if not joined:
                coalition.ato.packages.extend(joining[side])
    logging.info(
        f"Resolved {len(continued)} packages from {when:%H:%M}, {len(elsewhere)} "
        f"outside the bubble and {len(restored) - len(elsewhere)} held back after "
        "the DCS window"
    )
    return debriefing_out


def _restore_states(saved: dict[int, Any], game: Game, start: datetime) -> None:
    """Give the packages outside the bubble back the states the fighting
    before the window left them in (begin_simulation reset them), so a
    flight killed before the mission stays dead."""
    from game.ato.flightstate import Uninitialized

    for coalition in (game.blue, game.red):
        for package in coalition.ato.packages:
            for flight in package.flights:
                state = saved.get(id(flight))
                if state is None or isinstance(state, Uninitialized):
                    continue
                flight.set_state(state)


def _join(
    game: Game,
    joining: dict[bool, list[Package]],
    when: datetime,
    simulation: Any,
) -> None:
    """The flights that hadn't finished when the player quit join the
    combat model at the quit, where their plans put them by then."""
    for coalition in (game.blue, game.red):
        for package in joining[coalition.player.is_blue]:
            coalition.ato.packages.append(package)
            for flight in list(package.flights):
                place_at(flight, when)
                simulation.results.flights_flown.append(flight)


def place_at(flight: Flight, when: datetime) -> None:
    """Put a flight where its plan has it at ``when``, moved along its
    route without fighting."""
    from game.ato.flightstate import Uninitialized
    from game.ato.flightstate.onstation import advance_to

    flight.set_state(Uninitialized(flight, flight.squadron.settings))
    startup = flight.flight_plan.startup_time()
    if startup >= when:
        flight.state.reinitialize(when)
        return
    flight.state.reinitialize(startup)
    advance_to(flight, startup, when)
