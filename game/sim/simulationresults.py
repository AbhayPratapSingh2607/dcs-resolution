from __future__ import annotations

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

from game.unitmap import ConvoyUnit, FlyingUnit, FrontLineUnit
from game.sim.combatlog import CombatLog

if TYPE_CHECKING:
    from game.ato import Flight
    from game.ato.flightmember import FlightMember
    from game.ground_forces.ai_ground_planner import CombatGroup
    from game.squadrons import Pilot, Squadron
    from game.theater import ControlPoint
    from game.theater.theatergroup import TheaterUnit
    from game.transfers import CargoShip
    from game.sim.gameupdateevents import GameUpdateEvents


@dataclass
class SimulationResults:
    """Losses and damage produced by the fast-forward simulation.

    The simulation must have minimal impact on the save game until the debriefing
    is committed, because cancelling a mission resets the turn. Damage that has
    to be visible in the generated mission (dead flight members, destroyed TGO
    units, thinned out front-line groups) is applied to the in-memory game state
    but journaled, so :meth:`revert` can undo it. Everything is also recorded
    here so that :meth:`Debriefing.merge_simulation_results` can commit it.
    """

    air_losses: list[FlyingUnit] = field(default_factory=list)
    ground_losses: list[TheaterUnit] = field(default_factory=list)
    front_line_losses: list[FrontLineUnit] = field(default_factory=list)
    convoy_losses: list[ConvoyUnit] = field(default_factory=list)
    runway_damage: list[ControlPoint] = field(default_factory=list)
    parked_aircraft_losses: list[Squadron] = field(default_factory=list)
    cargo_ship_losses: list[CargoShip] = field(default_factory=list)
    #: What each side learned (game.warfare.IntelEvent).
    intel_events: list[Any] = field(default_factory=list)
    #: Achievements and failures of flights (game.warfare.CombatCredit).
    combat_credits: list[Any] = field(default_factory=list)
    #: Civilian casualty incidents: True when caused by blue.
    collateral_events: list[bool] = field(default_factory=list)
    #: Every flight that took part in this turn's simulation.
    flights_flown: list[Any] = field(default_factory=list)
    #: Seed for the combat model, so auto-resolved results can be reproduced.
    seed: int = field(default_factory=lambda: random.randrange(2**31))
    log: CombatLog = field(default_factory=CombatLog)
    #: Called when a ground unit dies (e.g. to refresh IADS network caches).
    on_ground_unit_killed: Optional[Callable[[], None]] = field(
        default=None, repr=False, compare=False
    )
    _undo: list[Callable[[GameUpdateEvents], None]] = field(
        default_factory=list, repr=False
    )

    def kill_pilot(self, flight: Flight, pilot: Pilot | None) -> None:
        self.air_losses.append(FlyingUnit(flight, pilot))

    def kill_flight_member(
        self, flight: Flight, member: FlightMember, events: GameUpdateEvents
    ) -> bool:
        """Removes one aircraft from a flight. Returns True if the whole flight is
        now dead."""
        from game.ato.flightstate.killed import Killed

        members = flight.roster.members
        if member not in members:
            return not members
        index = members.index(member)
        self.kill_pilot(flight, member.pilot)
        members.pop(index)

        def restore(_events: GameUpdateEvents) -> None:
            flight.roster.members.insert(min(index, len(flight.roster.members)), member)

        self._undo.append(restore)

        if not members:
            flight.set_state(
                Killed(
                    flight.state.estimate_position(), flight, flight.squadron.settings
                )
            )
        events.update_flight(flight)
        return not members

    def kill_theater_unit(self, unit: TheaterUnit, events: GameUpdateEvents) -> bool:
        from game.data.units import UnitClass

        if not unit.alive:
            return False
        unit_type = unit.unit_type
        if unit_type is not None and unit_type.unit_class in (
            UnitClass.AIRCRAFT_CARRIER,
            UnitClass.HELICOPTER_CARRIER,
        ):
            # Killing a carrier removes its squadrons, which cannot be undone.
            logging.info(f"Combat model does not sink carriers: {unit}")
            return False
        unit.kill(events)
        self.ground_losses.append(unit)
        if self.on_ground_unit_killed is not None:
            self.on_ground_unit_killed()

        def restore(e: GameUpdateEvents) -> None:
            unit.revive(e)

        self._undo.append(restore)
        return True

    def kill_front_line_unit(
        self, group: CombatGroup, origin: ControlPoint, count: int = 1
    ) -> int:
        count = min(count, group.size)
        if count <= 0:
            return 0
        group.size -= count
        for _ in range(count):
            self.front_line_losses.append(FrontLineUnit(group.unit_type, origin))

        def restore(_events: GameUpdateEvents) -> None:
            group.size += count

        self._undo.append(restore)
        return count

    def kill_convoy_unit(self, unit: ConvoyUnit) -> None:
        self.convoy_losses.append(unit)

    def damage_runway(self, control_point: ControlPoint) -> None:
        if control_point not in self.runway_damage:
            self.runway_damage.append(control_point)

    def kill_parked_aircraft(self, squadron: Squadron) -> None:
        self.parked_aircraft_losses.append(squadron)

    def kill_cargo_ship(self, ship: CargoShip) -> None:
        if ship not in self.cargo_ship_losses:
            self.cargo_ship_losses.append(ship)

    def revert(self, events: GameUpdateEvents) -> None:
        """Undoes simulated damage applied to the in-memory game state."""
        for undo in reversed(self._undo):
            try:
                undo(events)
            except Exception:
                logging.exception("Failed to revert simulated combat damage")
        self._undo.clear()
        self.air_losses.clear()
        self.ground_losses.clear()
        self.front_line_losses.clear()
        self.convoy_losses.clear()
        self.runway_damage.clear()
        self.parked_aircraft_losses.clear()
        self.cargo_ship_losses.clear()
        self.intel_events.clear()
        self.combat_credits.clear()
        self.collateral_events.clear()
        self.log = CombatLog()

    def forget_undo(self) -> None:
        """Called once the results are committed to the game."""
        self._undo.clear()
