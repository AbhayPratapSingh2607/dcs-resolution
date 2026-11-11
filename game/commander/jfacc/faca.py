"""FAC(A), the airborne forward air controller (V3).

A western doctrine flies a FAC(A) line over the main effort while CAS is on
station there: CAS-capable flights flagged ``fac_a`` that find and mark
targets and talk the CAS flights onto them instead of attacking. In DCS they
get the AFAC task and a FAC enroute task on their own frequency (listed on the
kneeboard with the JTACs); in the combat model, CAS over the same front while
a FAC(A) is on station hits more often (``attack.FAC_BONUS``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

from dcs.task import AFAC

if TYPE_CHECKING:
    from game.ato.flight import Flight
    from game.theater.player import Player

#: How far from the front's centre the FAC(A) counts as on station.
ON_STATION_KM = 40.0


def is_fac(flight: "Flight") -> bool:
    return bool(getattr(flight, "fac_a", False))


def fac_capable(flight: "Flight") -> bool:
    """Whether DCS lets this type fly the AFAC task."""
    return AFAC in flight.unit_type.dcs_unit_type.tasks


def mark_fac(flight: "Flight") -> bool:
    """Flags a CAS flight as FAC(A) if its type can do it."""
    if not fac_capable(flight):
        return False
    flight.fac_a = True  # type: ignore[attr-defined]
    return True


def fac_flights(game: object, player: "Player") -> Iterator["Flight"]:
    coalition = game.coalition_for(player)  # type: ignore[attr-defined]
    for package in coalition.ato.packages:
        for flight in package.flights:
            if is_fac(flight):
                yield flight


def fac_on_station(game: object, player: "Player", target: object) -> bool:
    """Whether a live FAC(A) of ``player`` is airborne over ``target``."""
    from game.sim.combat.model.engine import distance_km

    position = getattr(target, "position", None)
    if position is None:
        return False
    for flight in fac_flights(game, player):
        if not flight.alive or not flight.state.in_flight:
            continue
        if flight.package.target is not target:
            continue
        try:
            here = flight.state.estimate_position()
        except Exception:
            continue
        if distance_km(here, position) <= ON_STATION_KM:
            return True
    return False
