"""Ground-controlled interception: scrambling the fighters on ground alert.

Each side's GCI watches its own surveillance picture (EWR, AWACS and GCI
radars: ``SideAwareness``, with radar horizon and jamming), never ground
truth. Enemy flights it sees are grouped into raids: contacts within
``RAID_CLUSTER_M`` of each other. A raid inside the sector of an alert
package (its station plus ``Package.alert_radius_m``) gets alert pairs
scrambled against it, nearest first, up to the side's
``alert.max_scrambles_per_raid`` and no more than one pair per two raiders.

A scrambled pair is re-timed so it takes off now: its package TOT moves so
the flight plan's takeoff is the current time, and the flight starts its
takeoff roll. From then on it flies its CAP like any other, engaging what
enters the commit region of its station. Alerts never scrambled stay on the
ground and don't count as flown.

A dead or jammed early-warning network means no scrambles: the fighters
can't be vectored onto what nobody sees.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game import Game
    from game.ato.flight import Flight
    from game.sim.combat.model.engine import CombatModel

#: Contacts closer than this belong to the same raid.
RAID_CLUSTER_M = 40_000.0
DEFAULT_MAX_PER_RAID = 2


def is_on_alert(flight: Flight) -> bool:
    from game.ato.flightstate.onalert import OnAlert

    return isinstance(flight.state, OnAlert)


class Raid:
    def __init__(self, flight: Flight, x: float, y: float, aircraft: int) -> None:
        self.flights: list[Flight] = [flight]
        self.x = x
        self.y = y
        self.aircraft = aircraft

    def absorb(self, flight: Flight, x: float, y: float, aircraft: int) -> None:
        total = self.aircraft + aircraft
        self.x = (self.x * self.aircraft + x * aircraft) / total
        self.y = (self.y * self.aircraft + y * aircraft) / total
        self.aircraft = total
        self.flights.append(flight)


def cluster(contacts: Iterable[tuple[Flight, float, float, int]]) -> list[Raid]:
    raids: list[Raid] = []
    for flight, x, y, aircraft in contacts:
        for raid in raids:
            if math.hypot(raid.x - x, raid.y - y) <= RAID_CLUSTER_M:
                raid.absorb(flight, x, y, aircraft)
                break
        else:
            raids.append(Raid(flight, x, y, aircraft))
    raids.sort(key=lambda r: -r.aircraft)
    return raids


class GciController:
    def __init__(self, game: Game, model: CombatModel) -> None:
        self.game = game
        self.model = model
        #: Pairs scrambled against each enemy flight, per side.
        self.committed: dict[bool, dict[int, int]] = {
            True: defaultdict(int),
            False: defaultdict(int),
        }
        self.max_per_raid: dict[bool, int] = {}
        #: (time, side, alert flight, raid size) for each scramble, for reports.
        self.scrambles: list[tuple[datetime, bool, Flight, int]] = []

    def _max_per_raid(self, blue: bool) -> int:
        if blue not in self.max_per_raid:
            value = DEFAULT_MAX_PER_RAID
            try:
                from game.commander.jfacc.planner import profile_for
                from game.theater import Player

                profile = profile_for(self.game, Player.BLUE if blue else Player.RED)
                if profile is not None:
                    value = int(
                        profile.get("alert", "max_scrambles_per_raid", value)
                    )
            except Exception:
                logging.exception("Could not read the GCI scramble limit")
            self.max_per_raid[blue] = value
        return self.max_per_raid[blue]

    def tick(self, time: datetime, flights: Iterable[Flight]) -> list[Flight]:
        """Scrambles alert pairs against raids the sides' radars see."""
        from game.theater import Player

        flights = list(flights)
        released: list[Flight] = []
        for player in (Player.BLUE, Player.RED):
            alerts = [
                f
                for f in flights
                if f.squadron.player == player
                and getattr(f, "alert", False)
                and f.alive
                and is_on_alert(f)
            ]
            if not alerts:
                continue
            raids = self._raids(player, time, flights)
            if not raids:
                continue
            committed = self.committed[player.is_blue]
            limit = self._max_per_raid(player.is_blue)
            for raid in raids:
                launched = sum(committed[id(f)] for f in raid.flights)
                wanted = min(limit, max(1, math.ceil(raid.aircraft / 2)))
                while launched < wanted and alerts:
                    alert = self._nearest_in_sector(alerts, raid)
                    if alert is None:
                        break
                    self.release(alert, time)
                    alerts.remove(alert)
                    released.append(alert)
                    committed[id(raid.flights[0])] += 1
                    launched += 1
                    self.scrambles.append((time, player.is_blue, alert, raid.aircraft))
        return released

    def _raids(self, player: Any, time: datetime, flights: list[Flight]) -> list[Raid]:
        awareness = self.model.awareness(player, time)
        if not awareness.sources:
            return []
        contacts = []
        for flight in flights:
            if flight.squadron.player == player or not flight.alive:
                continue
            if not flight.state.in_flight:
                continue
            airframes = self.model.airframes(flight)
            if not airframes:
                continue
            lead = airframes[0]
            try:
                position = lead.position
                altitude = lead.altitude_m
            except Exception:
                continue
            if awareness.covers(position, altitude, lead.effective_rcs):
                contacts.append((flight, position.x, position.y, len(airframes)))
        return cluster(contacts)

    @staticmethod
    def _nearest_in_sector(alerts: list[Flight], raid: Raid) -> Optional[Flight]:
        best: Optional[Flight] = None
        best_d = math.inf
        for alert in alerts:
            station = alert.package.target.position
            radius = float(getattr(alert.package, "alert_radius_m", 0.0))
            d = math.hypot(station.x - raid.x, station.y - raid.y)
            if d <= radius and d < best_d:
                best, best_d = alert, d
        return best

    def release(self, flight: Flight, now: datetime) -> None:
        """Scramble: re-time the package so the flight takes off now."""
        from game.ato.flightstate import Takeoff

        package = flight.package
        delay = flight.flight_plan.takeoff_time() - now
        package.time_over_target = package.time_over_target - delay
        flight.alert_released = True
        flight.set_state(Takeoff(flight, flight.squadron.settings, now))
        self.model.log(
            now,
            _air_domain(),
            "blue" if flight.squadron.player.is_blue else "red",
            f"GCI scrambles {flight.count} x {flight.unit_type.display_name} "
            f"from {flight.departure.name}",
        )


def _air_domain() -> Any:
    from game.sim.combatlog import CombatDomain

    return CombatDomain.AIR
