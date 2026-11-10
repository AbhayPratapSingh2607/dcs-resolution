"""The 6 hour ATO timeline: strike waves, the main push, TOT deconfliction
and relief chains.

Strike packages are placed in waves spread through the period. One block of
the period is the main push: the turn's main effort, as long as the mission.
Its waves run suppression at H-hour, strikes minutes later through the
corridors it opens, then the follow-up. The other waves are smaller and sit
before and after it. Two packages whose targets lie within the corridor
radius of each other are separated by at least the profile's TOT separation,
so they don't share airspace over the target at the same time. Continuous
lines (CAP stations, AEW&C, tankers, CAS stacks) are chained: each relief
arrives on station as the previous flight's patrol ends.
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
    #: Focused turns: strike TOTs fall between H-hour (just after the DCS
    #: window opens) and this long before it closes, so packages strike and
    #: egress inside the mission. None: anywhere in the period.
    window: Optional[tuple[datetime, datetime]] = None
    #: Full turns: the main push, the turn's main effort in one block as
    #: long as the mission. None: no push (a mission only turn, or a profile
    #: that spreads its packages over the period).
    push: Optional[tuple[datetime, datetime]] = None

    @property
    def length(self) -> timedelta:
        return self.end - self.start

    @property
    def separation(self) -> timedelta:
        return timedelta(
            minutes=float(self.profile.get("period", "tot_separation_min", 6))
        )

    @property
    def corridor_m(self) -> float:
        return float(self.profile.get("period", "corridor_radius_nm", 15)) * 1852

    @property
    def earliest(self) -> datetime:
        earliest = self.start + timedelta(
            minutes=float(self.profile.get("period", "earliest_tot_min", 20))
        )
        if self.window is not None:
            h_hour = self.window[0] + timedelta(
                minutes=float(self.profile.get("period", "h_hour_min", 5))
            )
            earliest = max(earliest, h_hour)
        return earliest

    @property
    def latest(self) -> datetime:
        """The last TOT a strike package may have."""
        if self.window is None:
            return self.end
        egress = timedelta(
            minutes=float(self.profile.get("period", "window_egress_min", 15))
        )
        return max(self.earliest, self.window[1] - egress)

    @property
    def h_hour(self) -> timedelta:
        return timedelta(minutes=float(self.profile.get("period", "h_hour_min", 5)))

    def in_push(self, when: datetime) -> bool:
        return self.push is not None and self.push[0] <= when < self.push[1]

    def push_wave_times(self) -> list[datetime]:
        """The main push's waves: suppression at H-hour, the strikes minutes
        later, then the follow-up."""
        if self.push is None:
            return []
        delay = timedelta(
            minutes=float(self.profile.get("period", "push_strike_delay_min", 8))
        )
        first = self.push[0] + self.h_hour
        waves = [first, first + delay, first + 2 * delay]
        return [w for w in waves if w < self.push[1]]

    def outer_wave_times(self) -> list[datetime]:
        """The smaller waves before and after the main push (every wave
        when there is no push)."""
        if self.window is not None:
            span = self.latest - self.earliest
            return [self.earliest + span * f for f in self.profile.wave_fractions]
        times = [self.start + self.length * f for f in self.profile.wave_fractions]
        times = [max(t, self.earliest) for t in times]
        if self.push is None:
            return times
        push_start, push_end = self.push
        margin = self.separation * 2
        times = [
            t for t in times if t < push_start - margin or t >= push_end + margin
        ]
        # There is a war before the push: at least one wave comes before it.
        if not any(t < push_start for t in times):
            before = max(self.earliest, push_start - timedelta(minutes=45))
            if before < push_start - self.separation:
                times.append(before)
        return sorted(times)

    def wave_times(self) -> list[datetime]:
        return sorted(self.outer_wave_times() + self.push_wave_times())

    def is_push_wave(self, index: int) -> bool:
        waves = self.wave_times()
        return 0 <= index < len(waves) and self.in_push(waves[index])

    def _conflicts(self, tot: datetime, position: Point) -> bool:
        for slot in self.slots:
            if abs((slot.tot - tot).total_seconds()) >= self.separation.total_seconds():
                continue
            if slot.position.distance_to_point(position) <= self.corridor_m:
                return True
        return False

    def strike_tot(
        self,
        position: Point,
        preferred_wave: Optional[int] = None,
        push: Optional[bool] = None,
    ) -> Optional[datetime]:
        """A deconflicted TOT for a strike package against this position.

        ``push`` True restricts it to the main push's waves, False to the
        waves outside it, None allows any. ``preferred_wave`` indexes the
        waves considered."""
        waves = self.wave_times()
        candidates = [
            i
            for i in range(len(waves))
            if push is None or self.in_push(waves[i]) == push
        ]
        if not candidates:
            return None
        preferred = (
            candidates[preferred_wave]
            if preferred_wave is not None and 0 <= preferred_wave < len(candidates)
            else None
        )
        order = sorted(
            candidates,
            key=lambda i: (0 if i == preferred else 1, self.wave_load.get(i, 0), i),
        )
        limit = self.push[1] if push and self.push is not None else None
        for index in order:
            base = waves[index]
            # Within a wave packages flow through in TOT order.
            for step in range(0, 8):
                tot = base + self.separation * step
                if tot > self.latest or tot >= self.end:
                    break
                if limit is not None and tot >= limit:
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

    def unreserve(self, tot: datetime, position: Point) -> None:
        """Undo a reservation (a raid echelon released when the raid fails)."""
        for slot in self.slots:
            if slot.tot == tot and slot.position.distance_to_point(position) < 1.0:
                self.slots.remove(slot)
                break
        else:
            return
        waves = self.wave_times()
        if waves:
            index = min(
                range(len(waves)), key=lambda i: abs((waves[i] - tot).total_seconds())
            )
            self.wave_load[index] = max(0, self.wave_load.get(index, 0) - 1)

    def relief_tots(
        self,
        on_station: timedelta,
        first: Optional[datetime] = None,
        overlap: timedelta = timedelta(minutes=5),
    ) -> list[datetime]:
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
