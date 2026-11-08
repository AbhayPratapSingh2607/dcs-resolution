"""Health of an air defense network: early warning, command and control, power.

A SAM battery fights best when it is cued by early warning radars through a
working command and control chain, and has power. Strip those away and it has
to find targets with its own radar, react on its own, and run on generators.
Desert Storm's opening night went for exactly these nodes first.

Only Retribution's *advanced* IADS mode models command centres, comms and
power. In basic mode a site is considered networked when it is covered by a
friendly early warning radar; this is evaluated by the combat model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game import Game
    from game.theater import TheaterGroundObject
    from game.theater.iadsnetwork.iadsnetwork import IadsNetworkNode
    from game.theater.theatergroup import TheaterGroup


@dataclass(frozen=True)
class SiteNetworkStatus:
    #: The site is part of an advanced IADS network with real dependencies.
    advanced: bool
    #: A live EWR (or SAM acting as EWR) feeds this site.
    has_ew_cue: bool
    #: A live command centre is reachable through live comms.
    has_c2: bool
    #: A live power source supplies the site.
    has_power: bool

    @property
    def networked(self) -> bool:
        return self.has_ew_cue and self.has_c2

    @staticmethod
    def standalone() -> SiteNetworkStatus:
        return SiteNetworkStatus(False, False, False, True)


def _alive(group: TheaterGroup) -> bool:
    return any(u.alive for u in group.units)


def _node_for(game: Game, tgo: TheaterGroundObject) -> Optional[IadsNetworkNode]:
    network = getattr(game.theater, "iads_network", None)
    if network is None:
        return None
    for node in network.nodes:
        if node.group.ground_object is tgo:
            return node
    return None


def site_status(game: Game, tgo: TheaterGroundObject) -> Optional[SiteNetworkStatus]:
    """Network status of a SAM site, or None when the network does not model
    dependencies (basic IADS, or the site is not part of the network)."""
    from game.theater.iadsnetwork.iadsrole import IadsRole

    network = getattr(game.theater, "iads_network", None)
    if network is None or not getattr(network, "advanced_iads", False):
        return None
    node = _node_for(game, tgo)
    if node is None:
        return None
    friendly = tgo.control_point.captured
    roles: dict[IadsRole, list[bool]] = {}
    for group in node.connections.values():
        if group.ground_object.control_point.captured is not friendly:
            continue
        roles.setdefault(group.iads_role, []).append(_alive(group))

    def any_alive(*wanted: IadsRole) -> Optional[bool]:
        values = [alive for role in wanted for alive in roles.get(role, [])]
        if not values:
            return None
        return any(values)

    ew = any_alive(IadsRole.EWR, IadsRole.SAM_AS_EWR)
    command = any_alive(IadsRole.COMMAND_CENTER)
    comms = any_alive(IadsRole.CONNECTION_NODE)
    power = any_alive(IadsRole.POWER_SOURCE)
    if command is None:
        # No command centre in this network: comms alone carry the picture.
        has_c2 = comms if comms is not None else True
    else:
        has_c2 = command and (comms if comms is not None else True)
    return SiteNetworkStatus(
        advanced=True,
        has_ew_cue=bool(ew),
        has_c2=bool(has_c2),
        has_power=power if power is not None else True,
    )


def dependency_targets(
    game: Game, sites: Iterable[TheaterGroundObject]
) -> list[TheaterGroundObject]:
    """Live command, comms and power TGOs that the given SAM sites depend on,
    most depended-on first."""
    from game.theater.iadsnetwork.iadsrole import IadsRole

    wanted = (IadsRole.COMMAND_CENTER, IadsRole.CONNECTION_NODE, IadsRole.POWER_SOURCE)
    counts: dict[int, tuple[int, TheaterGroundObject]] = {}
    for site in sites:
        node = _node_for(game, site)
        if node is None:
            continue
        for group in node.connections.values():
            if group.iads_role not in wanted or not _alive(group):
                continue
            tgo = group.ground_object
            if tgo.control_point.captured is not site.control_point.captured:
                continue
            count, _ = counts.get(id(tgo), (0, tgo))
            # Command centres are worth most: they blind the whole sector.
            weight = 3 if group.iads_role is IadsRole.COMMAND_CENTER else 1
            counts[id(tgo)] = (count + weight, tgo)
    ranked = sorted(counts.values(), key=lambda c: -c[0])
    return [tgo for _, tgo in ranked]
