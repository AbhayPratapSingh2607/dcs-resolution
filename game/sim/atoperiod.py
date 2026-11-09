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
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game import Game
    from game.ato import Package
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


def max_window_offset_min(game: Game) -> int:
    bounds = period(game)
    if bounds is None:
        return 0
    start, end = bounds
    span = (end - start) - window_length(game)
    return max(0, int(span.total_seconds() // 60))


def set_window_offset(game: Game, minutes: int) -> None:
    game.air_campaign.window_offset_min = max(
        0, min(int(minutes), max_window_offset_min(game))
    )


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


def resolve_remainder(
    game: Game, events: GameUpdateEvents
) -> Optional[Debriefing]:
    """Fight the packages held back from the DCS mission with the combat
    model and commit their results."""
    if not has_deferred(game):
        return None
    bounds = window(game)
    period_bounds = period(game)
    restored = restore_deferred(game)
    if bounds is None or period_bounds is None or not restored:
        return None
    from game.debriefing import Debriefing
    from game.sim.aircraftsimulation import AircraftSimulation
    from game.sim.missionresultsprocessor import MissionResultsProcessor
    from game.settings.settings import CombatResolutionMethod
    from game.unitmap import UnitMap

    # Only the held-back packages fly: everything else already did.
    restored_ids = {id(p) for p in restored}
    others: dict[bool, list[Package]] = {}
    for coalition in (game.blue, game.red):
        keep = [p for p in coalition.ato.packages if id(p) not in restored_ids]
        others[coalition.player.is_blue] = keep
        for package in keep:
            coalition.ato.packages.remove(package)

    start = bounds[1]
    end = period_bounds[1] + RECOVERY
    simulation = AircraftSimulation(game)
    simulation.ground_war_enabled = False
    simulation.begin_simulation(start)
    time = start
    with_events = events
    try:
        while time < end:
            time += TICK
            simulation.on_game_tick(
                with_events, time, TICK, CombatResolutionMethod.RESOLVE, True
            )
            if not simulation.has_activity():
                break
        debriefing = Debriefing({"mission_ended": True}, game, UnitMap())
        debriefing.merge_simulation_results(simulation.results)
        MissionResultsProcessor(game).commit_resolved_period(debriefing, events)
        simulation.results.forget_undo()
    finally:
        for coalition in (game.blue, game.red):
            coalition.ato.packages.extend(others[coalition.player.is_blue])
    logging.info(f"Resolved {len(restored)} packages after the DCS window")
    return debriefing
