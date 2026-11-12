"""Helicopter detachments stationed at dynamic FARPs.

A detachment is a child :class:`Squadron` that holds a fixed number of aircraft and
pilots split off from a parent squadron. Because it's a regular squadron, flight
planning, the ATO, mission generation and debriefing all work without any special
handling. Detachments cannot buy aircraft or recruit pilots; when recalled,
everything that survived is merged back into the parent.

A new detachment has to fly to its FARP: it starts at the parent's base with the
FARP as its destination, ferry flights carry it there during the turn's mission,
and it arrives when the turn ends (like a squadron relocation). With the instant
transfer cheat enabled it appears at the FARP straight away.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from game.ato import FlightType
from game.theater import ParkingType
from .squadron import Squadron

if TYPE_CHECKING:
    from game.ato import Flight
    from game.sim import GameUpdateEvents
    from game.theater.dynamicfarp import DynamicFarp
    from .airwing import AirWing


def detachments_at(farp: DynamicFarp) -> list[Squadron]:
    """Detachments stationed at ``farp`` or flying there this turn."""
    return [
        s
        for s in farp.coalition.air_wing.iter_squadrons()
        if s.is_detachment and (s.location == farp or s.destination == farp)
    ]


def is_en_route(det: Squadron) -> bool:
    """Whether the detachment is still flying to its FARP (arrives next turn)."""
    return det.destination is not None


def detachments_of(parent: Squadron) -> list[Squadron]:
    return [s for s in parent.coalition.air_wing.iter_squadrons() if s.parent == parent]


def free_farp_slots(farp: DynamicFarp) -> int:
    # Includes helicopters still flying in (the FARP counts them as transferring).
    return farp.unclaimed_parking(ParkingType(True, True, True))


def max_detachment_size(parent: Squadron, farp: DynamicFarp) -> int:
    """The largest detachment ``parent`` could send to ``farp`` right now."""
    if detachment_errors(parent, farp, 1):
        return 0
    limit = min(parent.untasked_aircraft, free_farp_slots(farp))
    if parent.pilot_limits_enabled:
        limit = min(limit, parent.number_of_available_pilots)
    return max(0, limit)


def detachment_errors(parent: Squadron, farp: DynamicFarp, count: int) -> list[str]:
    """Returns the reasons ``parent`` can't detach ``count`` aircraft to ``farp``.

    An empty list means the detachment is allowed.
    """
    errors = []
    if not farp.established:
        errors.append(f"{farp} isn't set up yet: its equipment must be flown in.")
    if parent.is_detachment:
        errors.append(f"{parent} is already a detachment.")
    if not parent.aircraft.helicopter:
        errors.append(f"Only helicopters can operate from {farp}.")
    if not farp.is_friendly(parent.player):
        errors.append(f"{farp} does not belong to {parent.coalition.player.name}.")
    if parent.location == farp:
        errors.append(f"{parent} is already based at {farp}.")
    if parent.destination is not None:
        errors.append(f"{parent} is relocating and can't send a detachment.")
    if not farp.can_operate(parent.aircraft):
        errors.append(f"{parent.aircraft} cannot operate from {farp}.")
    if count < 1:
        errors.append("A detachment needs at least one aircraft.")
    if parent.untasked_aircraft < count:
        errors.append(
            f"{parent} only has {parent.untasked_aircraft} untasked aircraft."
        )
    if not parent.can_provide_pilots(count):
        errors.append(
            f"{parent} only has {parent.number_of_available_pilots} available pilots."
        )
    if free_farp_slots(farp) < count:
        errors.append(f"{farp} only has {free_farp_slots(farp)} free slots.")
    return errors


def _take_pilots(parent: Squadron, det: Squadron, count: int) -> None:
    if not parent.pilot_limits_enabled:
        # Without pilot limits, pilots are recruited on demand; nothing to move.
        count = min(count, parent.number_of_available_pilots)
    # Prefer player pilots so that the player can fly the detachment.
    candidates = sorted(parent.available_pilots, key=lambda p: not p.player)[:count]
    for pilot in candidates:
        parent.available_pilots.remove(pilot)
        parent.current_roster.remove(pilot)
        det.current_roster.append(pilot)
        det.available_pilots.append(pilot)


def _new_detachment(parent: Squadron, farp: DynamicFarp, en_route: bool) -> Squadron:
    det = Squadron(
        name=f"{parent.name} Det. {farp.name}",
        nickname=parent.nickname,
        country=parent.country,
        role=parent.role,
        aircraft=parent.aircraft,
        max_size=0,
        livery=parent.livery,
        livery_set=list(parent.livery_set),
        primary_task=parent.primary_task,
        auto_assignable_mission_types=set(),
        radio_presets=parent.radio_presets,
        operating_bases=parent.operating_bases,
        female_pilot_percentage=parent.female_pilot_percentage,
        pilot_pool=[],
        coalition=parent.coalition,
        flight_db=parent.flight_db,
        settings=parent.settings,
        # En route detachments start at the parent's base and fly to the FARP.
        location=parent.location if en_route else farp,
    )
    det.parent = parent
    det.use_livery_set = parent.use_livery_set
    det.set_auto_assignable_mission_types(parent.auto_assignable_mission_types)
    if en_route:
        det.destination = farp
    # List the detachment right after its parent (and the parent's other
    # detachments) so they read together in the air wing.
    squadrons = parent.coalition.air_wing.squadrons[parent.aircraft]
    if parent in squadrons:
        index = squadrons.index(parent) + 1
        while index < len(squadrons) and squadrons[index].parent == parent:
            index += 1
        squadrons.insert(index, det)
    else:
        parent.coalition.air_wing.add_squadron(det)
    return det


def _flights_of(
    det: Squadron, flight_type: Optional[FlightType] = None
) -> list[Flight]:
    return [
        flight
        for package in det.coalition.ato.packages
        for flight in package.flights
        if flight.squadron == det
        and (flight_type is None or flight.flight_type is flight_type)
    ]


def create_detachment(
    parent: Squadron,
    farp: DynamicFarp,
    count: int,
    now: Optional[datetime] = None,
    events: Optional[GameUpdateEvents] = None,
    instant: Optional[bool] = None,
) -> Squadron:
    """Splits ``count`` aircraft and pilots from ``parent`` and sends them to
    ``farp``.

    ``instant`` stations them at once whatever the transfer cheat says (the
    Rescue King's helicopters are flown out with it).

    Normally the helicopters fly there during this turn's mission (ferry flights
    are planned) and arrive at the end of the turn. With the instant transfer cheat
    they are stationed at the FARP immediately.

    Helicopters sent to the same FARP by the same parent join the existing group:
    the detachment already there (with the cheat), or the one already flying in.
    A group flying in to reinforce a detachment that's already there merges into
    it on arrival (see :func:`merge_arrived_detachments`).
    """
    errors = detachment_errors(parent, farp, count)
    if errors:
        raise ValueError(" ".join(errors))

    if instant is None:
        instant = parent.settings.enable_transfer_cheat
    same_parent = [d for d in detachments_at(farp) if d.parent == parent]
    existing = [d for d in same_parent if is_en_route(d) != instant]
    det = existing[0] if existing else _new_detachment(parent, farp, not instant)

    det.max_size += count
    parent.owned_aircraft -= count
    parent.untasked_aircraft -= count
    det.owned_aircraft += count
    det.untasked_aircraft += count
    det.initial_aircraft += count
    _take_pilots(parent, det, count)

    if is_en_route(det):
        if events is not None:
            for flight in _flights_of(det, FlightType.FERRY):
                events.delete_flight(flight)
        if now is None:
            now = parent.coalition.game.conditions.start_time
        det.replan_ferry_flights(now)
        if events is not None:
            for flight in _flights_of(det, FlightType.FERRY):
                events.new_flight(flight)
        logging.info(
            f"Detached {count} {parent.aircraft} from {parent}; flying to {farp}"
        )
    else:
        logging.info(f"Detached {count} {parent.aircraft} from {parent} to {farp}")
    return det


def _cancel_flights(det: Squadron, events: GameUpdateEvents | None) -> None:
    ato = det.coalition.ato
    for package in list(ato.packages):
        for flight in list(package.flights):
            if flight.squadron == det:
                if events is not None:
                    events.delete_flight(flight)
                package.remove_flight(flight)
        if not package.flights:
            ato.remove_package(package)


def _remove_from_air_wing(det: Squadron) -> None:
    squadrons = det.coalition.air_wing.squadrons[det.aircraft]
    if det in squadrons:
        squadrons.remove(det)


def recall_detachment(det: Squadron, events: GameUpdateEvents | None = None) -> None:
    """Merges a detachment back into its parent squadron and removes it.

    Also cancels a detachment that is still flying to its FARP.
    """
    parent = det.parent
    if parent is None:
        raise ValueError(f"{det} is not a detachment")

    _cancel_flights(det, events)

    parent.owned_aircraft += det.owned_aircraft
    parent.untasked_aircraft += det.owned_aircraft
    parent.destroyed_aircraft += det.destroyed_aircraft
    for pilot in det.current_roster:
        parent.current_roster.append(pilot)
        if pilot in det.available_pilots:
            parent.available_pilots.append(pilot)

    parking = ParkingType().from_squadron(parent)
    if parent.location.unclaimed_parking(parking) < 0:
        logging.warning(
            f"{parent.location} is over capacity after {det} returned to {parent}."
        )

    _remove_from_air_wing(det)
    logging.info(f"Recalled {det} to {parent} at {parent.location}")


def destroy_detachment(det: Squadron, events: GameUpdateEvents | None = None) -> None:
    """The detachment's FARP was destroyed: its aircraft are lost, surviving pilots
    make their way back to the parent squadron."""
    _cancel_flights(det, events)
    lost = det.owned_aircraft
    det.destroyed_aircraft += lost
    det.owned_aircraft = 0
    det.untasked_aircraft = 0
    logging.info(f"{det} lost {lost} aircraft when {det.location} was destroyed")
    recall_detachment(det, events)


def merge_arrived_detachments(air_wing: AirWing) -> None:
    """Merges a reinforcement group into the detachment it joined.

    Runs after the air wing finishes the turn, once en route detachments have
    arrived at their FARPs.
    """
    stationed: dict[tuple[int, object], Squadron] = {}
    for det in list(air_wing.iter_squadrons()):
        if not det.is_detachment or is_en_route(det):
            continue
        key = (id(det.parent), det.location.id)
        target = stationed.get(key)
        if target is None:
            stationed[key] = det
            continue
        _cancel_flights(det, None)
        target.max_size += det.max_size
        target.owned_aircraft += det.owned_aircraft
        target.untasked_aircraft += det.untasked_aircraft
        target.initial_aircraft += det.initial_aircraft
        target.destroyed_aircraft += det.destroyed_aircraft
        target.current_roster.extend(det.current_roster)
        target.available_pilots.extend(det.available_pilots)
        _remove_from_air_wing(det)
        logging.info(f"Merged arriving {det} into {target}")
