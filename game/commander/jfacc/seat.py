"""Your seat (M2): the player's preference, the flights the plan offers them,
and the flight they are fragged to.

The plan is never changed to suit the player (decision 4). After blue's
commander has planned the turn, its flights are ranked for the player:
the preferred squadron's flights first, then flights of the preferred
mission type, then anything else a player can fly; within each, the main
push first, then key packages, then by time on target. The top offer is
fragged: one of its pilots becomes the player. The player can take any
other offer, or put themselves in any flight by hand as before.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING
from uuid import UUID

from game.ato.flighttype import FlightType

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight, Package
    from game.squadrons import Squadron


@dataclass
class PlayerPreference:
    """What the player would like to fly: a squadron, a mission type, or
    both. One per campaign; it names a squadron, so it lives with the game,
    not in the settings."""

    squadron_id: Optional[UUID] = None
    mission_type: Optional[FlightType] = None

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update({**PlayerPreference().__dict__, **state})

    @property
    def empty(self) -> bool:
        return self.squadron_id is None and self.mission_type is None


def preference_of(game: Game) -> PlayerPreference:
    preference = getattr(game, "player_preference", None)
    if preference is None:
        preference = PlayerPreference()
        game.player_preference = preference
    return preference


def preferred_squadron(game: Game, preference: PlayerPreference) -> Optional[Squadron]:
    if preference.squadron_id is None:
        return None
    for squadron in game.blue.air_wing.iter_squadrons():
        if squadron.id == preference.squadron_id:
            return squadron
    return None


def flyable_squadrons(game: Game) -> list[Squadron]:
    """Blue squadrons whose aircraft a player can fly."""
    return [
        s for s in game.blue.air_wing.iter_squadrons() if s.aircraft.flyable
    ]


def offered_mission_types(game: Game) -> list[FlightType]:
    """Mission types a player could be offered: what the flyable squadrons
    may be tasked with."""
    found: set[FlightType] = set()
    for squadron in flyable_squadrons(game):
        found |= set(squadron.auto_assignable_mission_types)
        found.add(squadron.primary_task)
    return sorted(found, key=lambda t: t.value)


# ------------------------------------------------------------------ offers


@dataclass
class Offer:
    flight: Flight
    #: 0: the preferred squadron, 1: the preferred mission type, 2: other.
    tier: int
    in_push: bool
    key: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def package(self) -> Package:
        return self.flight.package

    @property
    def tot(self) -> datetime:
        return self.package.time_over_target

    @property
    def sort_key(self) -> tuple[int, int, int, datetime]:
        return (self.tier, 0 if self.in_push else 1, 0 if self.key else 1, self.tot)

    def describe(self) -> str:
        flight = self.flight
        parts = [
            f"{flight.squadron.name}",
            f"{flight.count}× {flight.unit_type.display_name} {flight.flight_type.value}",
            f"{self.package.target.name}",
            f"TOT {self.tot:%H:%M}",
        ]
        if self.reasons:
            parts.append(", ".join(self.reasons))
        return " · ".join(parts)


def eligible(flight: Flight) -> bool:
    """Whether a player could be put in this flight: a flyable aircraft, a
    real sortie (not a ground alert, not a flight returning from an
    earlier sortie), still waiting to start."""
    if not getattr(flight.unit_type, "flyable", False):
        return False
    if getattr(flight, "alert", False) or getattr(flight, "returning", False):
        return False
    if flight.count <= 0:
        return False
    state = getattr(flight, "state", None)
    if state is not None and not getattr(state, "is_waiting_for_start", True):
        return False
    return True


def _main_push(game: Game) -> Optional[tuple[datetime, datetime]]:
    state = getattr(game, "air_campaign", None)
    side = state.maybe_side(True) if state is not None else None
    return getattr(side, "push", None) if side is not None else None


def _is_key(package: Package) -> bool:
    from .planner import counts_toward_target

    if not counts_toward_target(package):
        return False
    return any(f.flight_type is not FlightType.BARCAP for f in package.flights)


def rank_offers(
    game: Game, preference: Optional[PlayerPreference] = None
) -> list[Offer]:
    """Blue's flights ranked for the player. A pure function of the plan:
    nothing in it changes."""
    if preference is None:
        preference = preference_of(game)
    squadron = preferred_squadron(game, preference)
    push = _main_push(game)
    offers: list[Offer] = []
    for package in game.blue.ato.packages:
        in_push = push is not None and push[0] <= package.time_over_target < push[1]
        key = _is_key(package)
        for flight in package.flights:
            if not eligible(flight):
                continue
            reasons = []
            tier = 2
            if squadron is not None and flight.squadron is squadron:
                tier = 0
                reasons.append("your squadron")
            elif (
                preference.mission_type is not None
                and flight.flight_type is preference.mission_type
            ):
                tier = 1
                reasons.append("your mission type")
            if in_push:
                reasons.append("main push")
            elif key:
                reasons.append("key package")
            offers.append(Offer(flight, tier, in_push, key, reasons))
    offers.sort(key=lambda o: o.sort_key)
    return offers


def why_no_match(game: Game, preference: Optional[PlayerPreference] = None) -> str:
    """Why the plan has nothing for the preference, from the plan's own
    records; "" when it has."""
    if preference is None:
        preference = preference_of(game)
    if preference.empty:
        return ""
    offers = rank_offers(game, preference)
    squadron = preferred_squadron(game, preference)
    if squadron is not None:
        if any(o.tier == 0 for o in offers):
            return ""
        return _squadron_reason(game, squadron)
    if preference.mission_type is not None:
        if any(o.tier == 1 for o in offers):
            return ""
        task = preference.mission_type.value
        if not any(
            preference.mission_type in s.auto_assignable_mission_types
            for s in flyable_squadrons(game)
        ):
            return f"No squadron you can fly is set to plan {task} missions"
        return _mission_reason(game, task)
    return ""


def _squadron_reason(game: Game, squadron: Squadron) -> str:
    name = squadron.name
    if squadron.owned_aircraft <= 0:
        return f"{name} isn't tasked this turn: it has no aircraft"
    if not squadron.auto_assignable_mission_types:
        return f"{name} isn't tasked this turn: it has no auto-planned mission types"
    tasked = sum(
        f.count
        for p in game.blue.ato.packages
        for f in p.flights
        if f.squadron is squadron
    )
    if tasked:
        return (
            f"{name} flies only ground alerts or returning flights this turn "
            f"({tasked} aircraft)"
        )
    side = getattr(game, "air_campaign", None)
    side = side.maybe_side(True) if side is not None else None
    phase = getattr(side, "phase_title", "") if side is not None else ""
    if squadron.untasked_aircraft < squadron.owned_aircraft:
        return (
            f"{name} isn't tasked this turn: {squadron.owned_aircraft - squadron.untasked_aircraft}"
            f" of {squadron.owned_aircraft} aircraft are in turnaround or on order"
        )
    if phase:
        return (
            f"{name} isn't tasked this turn: the {phase} plan had no "
            f"{squadron.primary_task.value} package it could fly"
        )
    return f"{name} isn't tasked this turn"


def _mission_reason(game: Game, task: str) -> str:
    side = getattr(game, "air_campaign", None)
    side = side.maybe_side(True) if side is not None else None
    phase = getattr(side, "phase_title", "") if side is not None else ""
    if phase:
        return f"No {task} package in the {phase} plan this turn"
    return f"No {task} package this turn"


# --------------------------------------------------------------- fragging


def fragged_flight(game: Game) -> Optional[Flight]:
    """The flight the player is fragged to: the auto-fragged one, else the
    first flight with a player in it."""
    first = None
    for package in game.blue.ato.packages:
        for flight in package.flights:
            if getattr(flight, "fragged", False) and flight.client_count:
                return flight
            if first is None and flight.client_count:
                first = flight
    return first


def unfrag(game: Game) -> None:
    """Take the player out of the auto-fragged flight (flights the player
    joined by hand are left alone)."""
    for package in game.blue.ato.packages:
        for flight in package.flights:
            if not getattr(flight, "fragged", False):
                continue
            for pilot in flight.roster.iter_pilots():
                if pilot is not None and pilot.player:
                    pilot.player = False
            flight.fragged = False  # type: ignore[attr-defined]


def frag(game: Game, flight: Flight) -> bool:
    """Put the player in this flight (its first pilot becomes the player)
    and take them out of the flight they were fragged to before. Returns
    False when the flight has no pilot to give."""
    unfrag(game)
    roster = flight.roster
    if roster.max_size <= 0:
        return False
    pilot = roster.pilot_at(0)
    if pilot is None:
        pilot = flight.squadron.claim_available_pilot()
        if pilot is None:
            return False
        roster.set_pilot(0, pilot)
    pilot.player = True
    flight.fragged = True  # type: ignore[attr-defined]
    logging.info(f"Fragged the player to {flight} ({flight.package.target.name})")
    # The DCS window goes to where fast forward stops for the new flight.
    try:
        from game.sim.atoperiod import follow_player_selection

        follow_player_selection(game)
    except Exception:
        logging.exception("Could not move the DCS window to the fragged flight")
    return True


def auto_frag_enabled(game: Game) -> bool:
    """Whether the commander frags one flight for the player: with the
    "No preference" ATO behaviour. "Prefer player pilots" keeps the old
    way (players spread over many flights), "Never" assigns nobody, and
    with the commander planning nothing or only routine lines the player
    plans their own flight."""
    from game.settings.settings import AutoAtoBehavior

    return game.settings.auto_ato_behavior is AutoAtoBehavior.Default


def auto_frag(game: Game) -> Optional[Flight]:
    """After blue's plan is made: frag the top offer, unless the player is
    already in a flight."""
    if not auto_frag_enabled(game):
        return None
    if any(
        f.client_count for p in game.blue.ato.packages for f in p.flights
    ):
        return fragged_flight(game)
    for offer in rank_offers(game):
        if frag(game, offer.flight):
            return offer.flight
    return None
