"""IADS management: emission control orders for a side's SAM sites.

Each period a side that manages its IADS (planning profile ``iads.manage``)
gives every radar SAM site an emission control order:

* ``active``: the site radiates and fights as part of the network.
* ``ambush``: the radars stay dark until a target is close, then a short,
  unexpected engagement. Harder for ELINT and anti-radiation hunters to find.
* ``dark``: the site stays silent to survive, and only fires in self-defense
  against a target almost on top of it.

The orders come from what the side itself knows: which of its sites have
been hit (``SideCampaign.attacked``), whether it is preserving its forces,
and doctrine. They never read the enemy's picture.

The orders are read by the fast-forward combat model (``CombatModel.site_emcon``)
and exported to Skynet for DCS missions (``skynet_overrides``).
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game import Game
    from game.theater.theatergroundobject import TheaterGroundObject
    from .campaignstate import SideCampaign
    from .profile import PlanningProfile

ACTIVE = "active"
AMBUSH = "ambush"
DARK = "dark"
ORDERS = (ACTIVE, AMBUSH, DARK)

#: Skynet settings per order (resources/plugins/skynetiads). Go-live range is
#: the share of the engagement range at which the site turns its radars on;
#: autonomous DARK keeps a site that lost its network silent.
SKYNET_OVERRIDES: dict[str, dict[str, str]] = {
    AMBUSH: {
        "go_live_range_in_percent": "60",
        "autonomous_behaviour": "SkynetIADSAbstractRadarElement.AUTONOMOUS_STATE_DARK",
    },
    DARK: {
        "go_live_range_in_percent": "25",
        "autonomous_behaviour": "SkynetIADSAbstractRadarElement.AUTONOMOUS_STATE_DARK",
        "harm_detection_chance": "90",
    },
}


def _radar_sams(game: Game, player: Any) -> list[TheaterGroundObject]:
    from game.data.groups import GroupTask
    from game.theater.theatergroundobject import SamGroundObject

    sites: list[TheaterGroundObject] = []
    for cp in game.theater.control_points_for(player):
        for tgo in cp.ground_objects:
            if not isinstance(tgo, SamGroundObject) or tgo.is_dead:
                continue
            if tgo.task not in (GroupTask.LORAD, GroupTask.MERAD, GroupTask.SHORAD):
                continue
            if not any(
                u.alive and getattr(u, "is_anti_air", False) for u in tgo.units
            ):
                continue
            sites.append(tgo)
    return sites


def plan_emcon(
    game: Game,
    player: Any,
    side: SideCampaign,
    profile: PlanningProfile,
    preserving: bool,
) -> dict[str, str]:
    """Emission control orders for the side's radar SAM sites, by TGO id."""
    from game.data.groups import GroupTask

    cfg = profile.section("iads")
    if not cfg.get("manage", False):
        side.iads_orders = {}
        return side.iads_orders
    emcon = cfg.get("emcon") or {}
    lorad_default = str(emcon.get("lorad", ACTIVE))
    mobile_default = str(emcon.get("mobile", ACTIVE))
    hunted_at = float(emcon.get("hunted_threshold", 0.8))
    hunted_order = str(emcon.get("hunted", AMBUSH))
    preserve_order = str(emcon.get("preserve", DARK))
    max_dark = float(emcon.get("max_dark_share", 0.4))

    sites = _radar_sams(game, player)
    orders: dict[str, str] = {}
    hunted: list[tuple[float, TheaterGroundObject]] = []
    for tgo in sites:
        order = lorad_default if tgo.task is GroupTask.LORAD else mobile_default
        weight = side.attacked.get(str(tgo.id), 0.0)
        if weight >= hunted_at:
            hunted.append((weight, tgo))
            order = hunted_order
        orders[str(tgo.id)] = order
    if preserving and preserve_order in ORDERS:
        # The most hunted sites go silent to survive, but the IADS keeps
        # enough of its sites up to still defend.
        budget = int(max_dark * len(sites))
        for _, tgo in sorted(hunted, key=lambda h: -h[0])[:budget]:
            orders[str(tgo.id)] = preserve_order
    side.iads_orders = {k: v for k, v in orders.items() if v in ORDERS}
    return side.iads_orders


def emcon_order(game: Optional[Game], tgo: TheaterGroundObject) -> str:
    """The order the owning side gave the site, "" for doctrine default."""
    state = getattr(game, "air_campaign", None) if game is not None else None
    if state is None:
        return ""
    try:
        blue = tgo.control_point.captured.is_blue
    except AttributeError:
        return ""
    side = state.maybe_side(blue)
    if side is None:
        return ""
    return str(getattr(side, "iads_orders", {}).get(str(tgo.id), ""))


def skynet_overrides(order: str) -> dict[str, str]:
    return dict(SKYNET_OVERRIDES.get(order, {}))
