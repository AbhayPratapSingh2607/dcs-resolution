"""Sortie generation: mission-capable rates, turnaround and second sorties.

Each squadron's untasked aircraft are split into airframe slots. Only the
mission-capable share of them is available this period. Every slot keeps a
timeline of the sorties it flies; a slot can fly again once it has landed and
completed its turnaround, up to the profile's surge limit. A sortie flown by an
airframe that has already flown this period doesn't claim more inventory from
the squadron: the same jet is flying twice, and with the crew that flew it first: a slot
remembers the flights (and seats) that flew it, and a second sortie's seat
takes that crew instead of a fresh pilot.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from .profile import PlanningProfile

if TYPE_CHECKING:
    from game.ato import Flight
    from game.squadrons import Squadron


def role_for(squadron: Squadron) -> str:
    from game.ato.flighttype import FlightType

    aircraft = squadron.aircraft
    if aircraft.helicopter:
        return "helicopter"
    if aircraft.capable_of(FlightType.AEWC) or aircraft.capable_of(
        FlightType.REFUELING
    ):
        return "support"
    fuel = float(getattr(aircraft.dcs_unit_type, "fuel_max", 0) or 0)
    if fuel > 25000:
        return "bomber"
    from game.sim.combat.model.profiles import CombatProfiles

    if CombatProfiles.instance().aircraft(aircraft).fighter:
        return "fighter"
    return "attack"


@dataclass
class AirframeSlot:
    sorties: list[tuple[datetime, datetime]] = field(default_factory=list)
    #: (flight, seat) of the sorties flown by this airframe, in order.
    crews: list[tuple[Flight, int]] = field(default_factory=list)

    def available(
        self,
        takeoff: datetime,
        land: datetime,
        turnaround: timedelta,
        max_sorties: int,
    ) -> bool:
        if len(self.sorties) >= max_sorties:
            return False
        for start, end in self.sorties:
            # The new sortie must start after this one ended plus turnaround,
            # or end (plus turnaround) before this one started.
            if not (takeoff >= end + turnaround or land + turnaround <= start):
                return False
        return True


@dataclass
class Allocation:
    squadron: Squadron
    slots: list[int]
    fresh: int
    takeoff: datetime
    land: datetime
    #: The flight flying it, once composed (for its crews).
    flight: Optional[Flight] = None

    @property
    def count(self) -> int:
        return len(self.slots)

    @property
    def reused(self) -> int:
        return self.count - self.fresh


class SortieLedger:
    def __init__(
        self,
        profile: PlanningProfile,
        period_start: datetime,
        period_end: datetime,
        seed: int,
    ) -> None:
        self.profile = profile
        self.period_start = period_start
        self.period_end = period_end
        self.seed = seed
        self.slots: dict[Squadron, list[AirframeSlot]] = {}
        self.not_mission_capable: dict[Squadron, int] = {}

    # -------------------------------------------------------------- capacity

    def _init(self, squadron: Squadron) -> list[AirframeSlot]:
        slots = self.slots.get(squadron)
        if slots is not None:
            return slots
        untasked = max(0, squadron.untasked_aircraft)
        rng = random.Random(f"{self.seed}:{squadron.name}:{squadron.aircraft.variant_id}")
        exact = untasked * self.profile.mc_rate
        capable = math.floor(exact)
        if rng.random() < exact - capable:
            capable += 1
        # Small detachments still get at least one jet up when they have any.
        if untasked > 0:
            capable = max(1, capable)
        slots = [AirframeSlot() for _ in range(capable)]
        self.slots[squadron] = slots
        self.not_mission_capable[squadron] = untasked - capable
        return slots

    def mission_capable(self, squadron: Squadron) -> int:
        return len(self._init(squadron))

    def turnaround(self, squadron: Squadron) -> timedelta:
        return timedelta(hours=self.profile.turnaround_hours(role_for(squadron)))

    def sorties_possible(self, squadron: Squadron, sortie_hours: float) -> int:
        """Sorties the squadron can generate this period for sorties of the
        given length (planning estimate for apportionment)."""
        capable = self.mission_capable(squadron)
        if capable == 0:
            return 0
        cycle = sortie_hours + self.turnaround(squadron).total_seconds() / 3600
        period = (self.period_end - self.period_start).total_seconds() / 3600
        per_airframe = 1 + max(0, int((period - sortie_hours) // max(cycle, 0.5)))
        per_airframe = min(per_airframe, self.profile.max_sorties_per_airframe)
        return capable * per_airframe

    # ------------------------------------------------------------ allocation

    def find(
        self,
        squadron: Squadron,
        count: int,
        takeoff: datetime,
        land: datetime,
    ) -> Optional[Allocation]:
        slots = self._init(squadron)
        turnaround = self.turnaround(squadron)
        max_sorties = self.profile.max_sorties_per_airframe
        # Prefer airframes that already flew (keeps fresh ones for later), but
        # only when they are genuinely available.
        reusable = [
            i
            for i, slot in enumerate(slots)
            if slot.sorties and slot.available(takeoff, land, turnaround, max_sorties)
        ]
        fresh = [i for i, slot in enumerate(slots) if not slot.sorties]
        fresh_needed = max(0, count - len(reusable))
        # Fresh airframes need inventory and pilots.
        if fresh_needed > min(len(fresh), squadron.untasked_aircraft):
            return None
        chosen = reusable[:count]
        chosen += fresh[: count - len(chosen)]
        if len(chosen) < count:
            return None
        n_fresh = sum(1 for i in chosen if not slots[i].sorties)
        return Allocation(squadron, chosen, n_fresh, takeoff, land)

    def commit(self, allocation: Allocation) -> None:
        slots = self._init(allocation.squadron)
        for seat, index in enumerate(allocation.slots):
            slots[index].sorties.append((allocation.takeoff, allocation.land))
            if allocation.flight is not None:
                slots[index].crews.append((allocation.flight, seat))

    def release(self, allocation: Allocation) -> None:
        slots = self._init(allocation.squadron)
        for index in allocation.slots:
            entry = (allocation.takeoff, allocation.land)
            if entry in slots[index].sorties:
                slots[index].sorties.remove(entry)
            slots[index].crews = [
                c for c in slots[index].crews if c[0] is not allocation.flight
            ]

    def earlier_crews(self, allocation: Allocation) -> list[tuple[int, Flight, int]]:
        """For each seat of the allocation whose airframe already flew:
        (seat, earlier flight, its seat). The crew of that sortie flies this
        one too."""
        slots = self._init(allocation.squadron)
        crews = []
        for seat, index in enumerate(allocation.slots):
            earlier = [c for c in slots[index].crews if c[0] is not allocation.flight]
            if earlier:
                flight, earlier_seat = earlier[-1]
                crews.append((seat, flight, earlier_seat))
        return crews

    def update(self, allocation: Allocation, takeoff: datetime, land: datetime) -> None:
        """Replace an allocation's estimated times with the planned ones."""
        self.release(allocation)
        allocation.takeoff = takeoff
        allocation.land = land
        self.commit(allocation)

    # ----------------------------------------------------------------- stats

    def sorties_flown(self) -> int:
        return sum(len(s.sorties) for slots in self.slots.values() for s in slots)

    def second_sorties(self) -> int:
        return sum(
            max(0, len(s.sorties) - 1) for slots in self.slots.values() for s in slots
        )
