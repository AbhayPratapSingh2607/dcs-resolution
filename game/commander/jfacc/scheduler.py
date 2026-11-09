"""The 6 hour ATO timeline: strike waves, TOT deconfliction and relief chains.

Strike packages are placed in waves spread through the period. Two packages
whose targets lie within the corridor radius of each other are separated by
at least the profile's TOT separation, so they don't share airspace over the
target at the same time. Continuous lines (CAP stations, AEW&C, tankers, CAS
stacks) are chained: each relief arrives on station as the previous flight's
patrol ends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from .profile import PlanningProfile

if TYPE_CHECKING:
    from dcs.mapping import Point

    from game.ato import Package


@dataclass
class Slot:
    tot: datetime
    position: Point


@dataclass
class Timeline:
    profile: PlanningProfile
    start: datetime
    end: datetime
    slots: list[Slot] = field(default_factory=list)
    wave_load: dict[int, int] = field(default_factory=dict)

    @property
    def length(self) -> timedelta:
        return self.end - self.start

    @property
    def separation(self) -> timedelta:
        return timedelta(minutes=float(self.profile.get("period", "tot_separation_min", 6)))

    @property
    def corridor_m(self) -> float:
        return float(self.profile.get("period", "corridor_radius_nm", 15)) * 1852

    @property
    def earliest(self) -> datetime:
        return self.start + timedelta(
            minutes=float(self.profile.get("period", "earliest_tot_min", 20))
        )

    def wave_times(self) -> list[datetime]:
        times = [self.start + self.length * f for f in self.profile.wave_fractions]
        return [max(t, self.earliest) for t in times]

    def _conflicts(self, tot: datetime, position: Point) -> bool:
        for slot in self.slots:
            if abs((slot.tot - tot).total_seconds()) >= self.separation.total_seconds():
                continue
            if slot.position.distance_to_point(position) <= self.corridor_m:
                return True
        return False

    def strike_tot(self, position: Point, preferred_wave: Optional[int] = None) -> Optional[datetime]:
        """A deconflicted TOT for a strike package against this position."""
        waves = self.wave_times()
        if not waves:
            return None
        order = sorted(
            range(len(waves)),
            key=lambda i: (
                0 if preferred_wave is not None and i == preferred_wave else 1,
                self.wave_load.get(i, 0),
                i,
            ),
        )
        for index in order:
            base = waves[index]
            # Within a wave packages flow through in TOT order.
            for step in range(0, 8):
                tot = base + self.separation * step
                if tot >= self.end:
                    break
                if not self._conflicts(tot, position):
                    return tot
        return None

    def reserve(self, tot: datetime, position: Point) -> None:
        self.slots.append(Slot(tot, position))
        waves = self.wave_times()
        if waves:
            index = min(
                range(len(waves)), key=lambda i: abs((waves[i] - tot).total_seconds())
            )
            self.wave_load[index] = self.wave_load.get(index, 0) + 1

    def relief_tots(self, on_station: timedelta, first: Optional[datetime] = None, overlap: timedelta = timedelta(minutes=5)) -> list[datetime]:
        """Station arrival times that keep a line continuous over the period."""
        tot = first or self.start + timedelta(minutes=10)
        times: list[datetime] = []
        step = max(on_station - overlap, timedelta(minutes=15))
        while tot < self.end:
            times.append(tot)
            tot += step
        return times


def patrol_end(package: Package) -> Optional[datetime]:
    """When the package's patrolling flight leaves station."""
    from game.ato.flightplans.patrolling import PatrollingFlightPlan

    ends: list[datetime] = []
    for flight in package.flights:
        plan = flight.flight_plan
        if isinstance(plan, PatrollingFlightPlan):
            ends.append(plan.patrol_end_time)
    return max(ends) if ends else None
