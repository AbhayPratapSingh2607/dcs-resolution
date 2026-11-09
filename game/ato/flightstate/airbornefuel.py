"""Fuel for AI flights that are already airborne when the mission starts.

A flight that took off before mission start (the lead-in of a focused turn,
a flight returning from an earlier sortie, or a window later in an ATO
period) has burned fuel getting where it is. It used to spawn with full
internal fuel regardless. It now spawns with the fuel its flight so far
leaves it, but never less than what it needs to fly the rest of its plan
with a reserve, so the AI doesn't go bingo the moment it appears.

The estimate counts internal fuel only: external tanks are spawned full, as
before, which is a further margin.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from game.utils import LBS_TO_KG, pairwise

if TYPE_CHECKING:
    from game.ato import Flight

#: Fuel needed for the rest of the plan is scaled by this (winds, combat,
#: holding and racetracks the leg distances don't count).
REMAINING_MARGIN = 1.3
#: Plus this share of the flight's full fuel load as a landing reserve.
RESERVE_SHARE = 0.25
#: A flight returning from an earlier sortie, for an aircraft without fuel
#: consumption data: this share of its full load.
RETURNING_SHARE = 0.4


def airborne_fuel(flight: Flight) -> Optional[float]:
    """Internal fuel in kg for an AI flight airborne at mission start, or None
    to keep the flight's default load."""
    from .inflight import InFlight

    state = flight.state
    if not isinstance(state, InFlight):
        return None
    full = float(flight.fuel)
    if flight.unit_type.fuel_consumption is None:
        if getattr(flight, "returning", False):
            return full * RETURNING_SHARE
        return None
    try:
        estimate = float(state.estimate_fuel())
        plan = flight.flight_plan
        remaining = plan.waypoints[state.waypoint_index :]
        needed = 0.0
        for a, b in pairwise(remaining):
            consumption = plan.fuel_consumption_between_points(a, b)
            if consumption is None:
                return None
            needed += consumption * LBS_TO_KG
    except Exception:
        return None
    floor = needed * REMAINING_MARGIN + full * RESERVE_SHARE
    return min(full, max(estimate, floor))
