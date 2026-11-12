"""Which theater tanker tracks to fly, and with which kind of tanker.

A tanker refuels only aircraft of its own system: a flying boom (mostly USAF)
or probe-and-drogue (US Navy and Marines, and most other air forces; see
resources/combat/fuel.yaml). So the tracks follow the receivers:

* land-based squadrons with boom receptacles get a boom track off the base
  nearest the front;
* land-based squadrons with probes get a drogue track there too, set further
  back so the two tracks don't overlap (theaterrefueling.py);
* each carrier with probe squadrons aboard gets a drogue track off the
  carrier, between it and the enemy's air defenses: where its jets pass on
  the way out and back.

Tracks go to the largest groups of receivers first, up to the profile's
``enablers.tanker_tracks_max``. A system with receivers but no tanker of its
own in the air wing gets no track: the other kind can't refuel them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType
from game.sim.combat.model.fuel import (
    RefuelingSystem,
    receiver_system,
    tanker_system,
)

if TYPE_CHECKING:
    from game.coalition import Coalition
    from game.squadrons import Squadron
    from game.theater import ControlPoint

#: Squadrons whose aircraft fly these count as receivers. Tankers, AEW&C and
#: transports don't: they are what the tracks are not for.
RECEIVER_TASKS = (
    FlightType.BARCAP,
    FlightType.ESCORT,
    FlightType.SWEEP,
    FlightType.STRIKE,
    FlightType.BAI,
    FlightType.CAS,
    FlightType.SEAD,
    FlightType.DEAD,
    FlightType.OCA_AIRCRAFT,
    FlightType.OCA_RUNWAY,
    FlightType.ANTISHIP,
)


@dataclass(frozen=True)
class TankerTrack:
    #: The base or carrier the track is placed off.
    anchor: ControlPoint
    #: None: any tanker (no receivers known; the old single track).
    system: Optional[RefuelingSystem]
    #: Receiver airframes the track serves.
    receivers: int

    @property
    def reason(self) -> str:
        if self.system is None:
            return "Theater tanker track"
        where = f"off {self.anchor.name}" if self.anchor.is_fleet else "for land bases"
        return (
            f"Theater {self.system.label} tanker track {where} "
            f"({self.receivers} {self.system.label} receivers)"
        )


def _is_receiver(squadron: Squadron) -> bool:
    aircraft = squadron.aircraft
    if aircraft.helicopter or aircraft.capable_of(FlightType.REFUELING):
        return False
    return any(aircraft.capable_of(task) for task in RECEIVER_TASKS)


def tanker_systems(coalition: Coalition) -> set[RefuelingSystem]:
    """The refueling systems the coalition's own tankers provide."""
    systems: set[RefuelingSystem] = set()
    for squadron in coalition.air_wing.iter_squadrons():
        if squadron.owned_aircraft <= 0:
            continue
        if not squadron.can_auto_assign(FlightType.REFUELING):
            continue
        system = tanker_system(squadron.aircraft)
        if system is not None:
            systems.add(system)
    return systems


def tanker_tracks(
    coalition: Coalition, front: ControlPoint, max_tracks: int = 3
) -> list[TankerTrack]:
    """The tracks to fly, most receivers first. ``front`` is the friendly
    base nearest the front, where land-based receivers are served."""
    available = tanker_systems(coalition)
    if not available:
        return []
    demand: Counter[tuple[int, RefuelingSystem]] = Counter()
    anchors: dict[int, ControlPoint] = {id(front): front}
    for squadron in coalition.air_wing.iter_squadrons():
        if squadron.owned_aircraft <= 0 or not _is_receiver(squadron):
            continue
        system = receiver_system(squadron.aircraft)
        if system is None:
            continue
        location = squadron.location
        # Carrier air wings get their own drogue track; anything else (and a
        # boom receiver at sea, if a campaign has one) is served off the front.
        if location.is_fleet and system is RefuelingSystem.DROGUE:
            anchor = location
        else:
            anchor = front
        anchors[id(anchor)] = anchor
        demand[(id(anchor), system)] += squadron.owned_aircraft

    tracks = [
        TankerTrack(anchors[anchor_id], system, count)
        for (anchor_id, system), count in demand.items()
        if system in available
    ]
    if not tracks and not demand:
        # Nobody's receivers are known (no combat squadrons that refuel):
        # the old single track, flown by any tanker.
        return [TankerTrack(front, None, 0)]
    tracks.sort(key=lambda t: -t.receivers)
    return tracks[:max_tracks]
