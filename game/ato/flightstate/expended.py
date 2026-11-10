"""Weapons expended (P5): an AI flight that is past its time on target when
the mission starts is on its way home. It spawns without the air-to-ground
weapons it has already used, keeping its air-to-air missiles, pods, decoys
and tanks, so it looks and behaves like a flight egressing rather than one
with a full load it never dropped.

The fuel it has left is handled by game.ato.flightstate.airbornefuel.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game.ato import Flight
    from game.ato.loadouts import Loadout
    from game.data.weapons import Weapon

#: Weapon roles (game.sim.combat.model.profiles.WeaponRole values) that a
#: flight drops on its target.
EXPENDED_ROLES = {"a2g", "arm", "antiship"}


def past_time_on_target(flight: Flight) -> bool:
    """Whether the flight is airborne and has passed its target waypoint."""
    from game.ato.flightstate import InFlight

    state = flight.state
    if not isinstance(state, InFlight):
        return False
    try:
        return state.has_passed_waypoint(flight.flight_plan.tot_waypoint)
    except Exception:
        return False


def _role_of(weapon: Weapon) -> Optional[str]:
    from game.sim.combat.model.profiles import CombatProfiles

    try:
        return str(CombatProfiles.instance().weapon(weapon).role.value)
    except Exception:
        return None


def expended_loadout(
    loadout: Loadout, role_of: Optional[Callable[[Weapon], Optional[str]]] = None
) -> Loadout:
    """The loadout without the stores dropped on the target."""
    if role_of is None:
        role_of = _role_of
    pylons = {}
    dropped = []
    for number, weapon in loadout.pylons.items():
        if weapon is None:
            continue
        role = role_of(weapon)
        if role in EXPENDED_ROLES:
            dropped.append(weapon.name)
            continue
        pylons[number] = weapon
    if not dropped:
        return loadout
    expended = loadout.clone()
    expended.pylons = pylons
    return expended


def loadout_at_mission_start(flight: Flight, member_loadout: Loadout, player: bool) -> Loadout:
    """What an AI flight carries when it appears in the mission: its full
    loadout, or the expended one when its time on target has passed."""
    if player or not past_time_on_target(flight):
        return member_loadout
    expended = expended_loadout(member_loadout)
    if expended is not member_loadout:
        logging.debug(f"{flight} is past its TOT: spawning with weapons expended")
    return expended
