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

import math
from dataclasses import dataclass, fields
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
    # Turn 1: red's posture at H-hour (game.opening, T8).
    from game.opening import mobile_emcon

    mobile_default = mobile_emcon(game, player) or mobile_default
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


# ===================================================================== moves
#
# Mobile SAM sites relocate between turns: away from where the enemy has
# found and hit them, toward the axes the side has seen the enemy use. The
# enemy's intel picture is not told: its contact (and any decoys left at the
# old position) stay where they were, so its picture of the site goes stale
# until it finds the site again.


@dataclass(frozen=True)
class SiteMove:
    tgo_id: str
    name: str
    distance_km: float
    reason: str

    def describe(self) -> str:
        return f"{self.name} moved {self.distance_km:.0f} km ({self.reason})"


@dataclass(frozen=True)
class MoveRules:
    move_share: float = 0.3
    road_move_km: float = 25.0
    scoot_km: float = 6.0
    road_factor: float = 1.3
    min_flot_km: float = 15.0
    min_spacing_km: float = 3.0
    min_shift_km: float = 3.0
    improvement: float = 0.25

    @staticmethod
    def from_profile(data: Optional[dict[str, Any]]) -> MoveRules:
        known = {f.name for f in fields(MoveRules)}
        return MoveRules(**{k: float(v) for k, v in (data or {}).items() if k in known})


def manages_iads(game: Game, player: Any) -> bool:
    from .planner import profile_for

    try:
        profile = profile_for(game, player)
    except Exception:
        return False
    return profile is not None and bool(profile.section("iads").get("manage", False))


def reposition_iads(
    game: Game, for_blue: bool = True, for_red: bool = True
) -> list[SiteMove]:
    """Start of turn, before threat zones are computed: each side that
    manages its IADS relocates some of its mobile SAM sites."""
    from game.theater import Player
    from .planner import profile_for

    state = getattr(game, "air_campaign", None)
    if state is None:
        return []
    moves: list[SiteMove] = []
    for player, wanted in ((Player.BLUE, for_blue), (Player.RED, for_red)):
        if not wanted:
            continue
        profile = profile_for(game, player)
        if profile is None:
            continue
        side = state.side(player.is_blue)
        if side.moves_turn == game.turn:
            continue
        side.moves_turn = game.turn
        side.iads_moves = []
        cfg = profile.section("iads")
        if not cfg.get("manage", False) or not cfg.get("moves"):
            continue
        mover = SiteMover(game, player, side, MoveRules.from_profile(cfg["moves"]))
        done = mover.run()
        side.iads_moves = [m.describe() for m in done]
        moves.extend(done)
    return moves


class SiteMover:
    BEARINGS = 12

    def __init__(
        self, game: Game, player: Any, side: SideCampaign, rules: MoveRules
    ) -> None:
        from .observations import ObservationLog

        self.game = game
        self.player = player
        self.side = side
        self.rules = rules
        self.log = ObservationLog(side)
        self.sites = _radar_sams(game, player)
        self.assets = [
            cp for cp in game.theater.control_points_for(player) if not cp.is_fleet
        ]
        self.fronts = [f.position for f in game.theater.conflicts()]
        self.terrain = getattr(game.theater, "farp_terrain", None)

    # ------------------------------------------------------------ choose

    def run(self) -> list[SiteMove]:
        from game.warfare.intel import is_mobile

        mobile = [s for s in self.sites if is_mobile(s)]
        if not mobile:
            return []
        limit = max(1, int(math.ceil(self.rules.move_share * len(mobile))))
        ranked = sorted(mobile, key=lambda s: -self._urgency(s))
        moves: list[SiteMove] = []
        for tgo in ranked:
            if len(moves) >= limit:
                break
            move = self._consider(tgo)
            if move is not None:
                moves.append(move)
        return moves

    def _fired(self, tgo: TheaterGroundObject) -> bool:
        return self.side.fired_sites.get(str(tgo.id), -99) >= self.game.turn - 1

    def _urgency(self, tgo: TheaterGroundObject) -> float:
        fired = 1.0 if self._fired(tgo) else 0.0
        return self.side.attacked.get(str(tgo.id), 0.0) + fired

    def _reach_m(self, tgo: TheaterGroundObject) -> float:
        try:
            return max(5000.0, float(tgo.max_threat_range().meters))
        except Exception:
            return 15000.0

    def _consider(self, tgo: TheaterGroundObject) -> Optional[SiteMove]:
        rules = self.rules
        fired = self._fired(tgo)
        hunted = self.side.attacked.get(str(tgo.id), 0.0) >= 0.5
        # A site that fired last turn only scoots: it packs up and shifts,
        # it doesn't drive across the country.
        max_km = rules.scoot_km if fired else rules.road_move_km
        straight_m = max_km * 1000 / rules.road_factor
        reach = self._reach_m(tgo)
        origin = tgo.position
        current_axis, current_overlap = self._score(tgo, origin.x, origin.y, reach)
        best: Optional[tuple[float, float, float, float]] = None
        for x, y in self._candidates(tgo, straight_m, reach):
            shift = math.hypot(x - origin.x, y - origin.y)
            if shift < rules.min_shift_km * 1000 or shift > straight_m:
                continue
            if not self._valid(tgo, x, y):
                continue
            axis_score, overlap = self._score(tgo, x, y, reach)
            score = axis_score - overlap
            if best is None or score > best[0]:
                best = (score, axis_score, x, y)
        if best is None:
            return None
        _, axis_score, x, y = best
        if fired:
            reason = "shoot and scoot"
        elif hunted:
            reason = "relocating away from enemy attacks"
        elif (
            axis_score >= current_axis + rules.improvement
            and self.assets
            and self.log.axes(self._nearest_asset(origin))
        ):
            # Only what the side has seen justifies a move: the campaign's
            # initial layout isn't second-guessed without observations.
            reason = "covering the observed threat axis"
        else:
            return None
        distance_km = math.hypot(x - origin.x, y - origin.y) / 1000
        shift_site(self.game, tgo, x - origin.x, y - origin.y)
        return SiteMove(str(tgo.id), tgo.name, distance_km, reason)

    def _candidates(
        self, tgo: TheaterGroundObject, straight_m: float, reach: float
    ) -> list[tuple[float, float]]:
        origin = tgo.position
        points = []
        for fraction in (0.35, 0.7, 1.0):
            for i in range(self.BEARINGS):
                h = math.radians(i * 360 / self.BEARINGS + 15 * fraction)
                d = straight_m * fraction
                points.append((origin.x + d * math.cos(h), origin.y + d * math.sin(h)))
        # Forward of the defended assets along the learned axes.
        for asset in self.assets:
            if asset.position.distance_to_point(origin) > straight_m + reach:
                continue
            for axis in self.log.axes(asset):
                h = math.radians(axis.heading)
                for share in (0.3, 0.5):
                    d = reach * share
                    points.append(
                        (
                            asset.position.x + d * math.cos(h),
                            asset.position.y + d * math.sin(h),
                        )
                    )
        return points

    # ------------------------------------------------------------- score

    def _nearest_asset(self, point: Any) -> Any:
        return min(
            self.assets,
            key=lambda cp: cp.position.distance_to_point(point),
        )

    def _score(
        self, tgo: TheaterGroundObject, x: float, y: float, reach: float
    ) -> tuple[float, float]:
        """(coverage of the defended assets and their observed threat
        axes, overlap with the side's other SAM sites)."""
        from .observations import heading_deg

        score = 0.0
        overlap = 0.0
        for asset in self.assets:
            distance = math.hypot(asset.position.x - x, asset.position.y - y)
            if distance > reach * 1.2:
                continue
            axes = self.log.axes(asset)
            if not axes:
                score += 0.2
                continue
            bearing = heading_deg(asset.position, x, y)
            for axis in axes:
                closeness = math.cos(math.radians(bearing - axis.heading))
                if closeness > 0 or distance < 2000:
                    confidence = min(1.0, axis.mass / 6.0)
                    score += axis.share * max(closeness, 0.3) * confidence
        for other in self.sites:
            if other is tgo:
                continue
            if math.hypot(other.position.x - x, other.position.y - y) < 0.5 * reach:
                overlap += 0.3
        return score, overlap

    # ---------------------------------------------------------- validity

    def _valid(self, tgo: TheaterGroundObject, x: float, y: float) -> bool:
        from dcs.mapping import Point

        rules = self.rules
        terrain = tgo.position._terrain
        point = Point(x, y, terrain)
        theater = self.game.theater
        # Own territory, well behind the front line.
        try:
            if theater.closest_control_point(point).captured != self.player:
                return False
        except Exception:
            return False
        for front in self.fronts:
            if front.distance_to_point(point) < rules.min_flot_km * 1000:
                return False
        for other in self.sites:
            if other is tgo:
                continue
            if other.position.distance_to_point(point) < rules.min_spacing_km * 1000:
                return False
        # Every vehicle on dry land, no steep slope or town under the site.
        dx, dy = x - tgo.position.x, y - tgo.position.y
        try:
            if not theater.is_on_land(point):
                return False
            for unit in list(tgo.units)[:8]:
                moved = Point(unit.position.x + dx, unit.position.y + dy, terrain)
                if not theater.is_on_land(moved):
                    return False
        except Exception:
            return False
        if self.terrain is not None:
            site = self.terrain.survey(point, 300)
            if site.known and (site.steep or site.built_up):
                return False
        return True


def shift_site(game: Game, tgo: TheaterGroundObject, dx: float, dy: float) -> None:
    """Moves a site by dx metres north and dy east. The opponent's contact
    and the site's decoys keep their absolute positions: both are stored as
    offsets from the site (offset_x east, offset_y north)."""
    tgo.position.x += dx
    tgo.position.y += dy
    for unit in tgo.units:
        unit.position.x += dx
        unit.position.y += dy
    war_state = getattr(game, "war_state", None)
    if war_state is None:
        return
    owner = tgo.control_point.captured
    picture = war_state.intel.get(not owner.is_blue)
    contact = picture.contacts.get(tgo.id) if picture is not None else None
    if contact is not None:
        contact.offset_x -= dy
        contact.offset_y -= dx
    decoys = war_state.deception.get(tgo.id)
    if decoys:
        war_state.deception[tgo.id] = [(ox - dy, oy - dx) for ox, oy in decoys]


# ==================================================================== decoys
#
# Sides that manage their IADS place decoys where the enemy will look first:
# between the site and the axis the enemy comes from, on open, flat ground.
# Decoys left behind when a site moves stay where they are (shift_site), so
# the site is topped up with fresh ones at its new position.

#: Decoys within this distance of a site count as its own.
DECOY_NEAR_M = 6000.0


def decoy_plan(
    game: Game, player: Any
) -> Optional[tuple[SideCampaign, int]]:
    """(side, decoys per radar SAM site) when the side places its decoys by
    plan, None to leave it to doctrine."""
    from .planner import profile_for

    try:
        profile = profile_for(game, player)
    except Exception:
        return None
    if profile is None:
        return None
    cfg = profile.section("iads")
    decoys = cfg.get("decoys") or {}
    if not cfg.get("manage", False) or not decoys:
        return None
    state = getattr(game, "air_campaign", None)
    if state is None:
        return None
    return state.side(player.is_blue), int(decoys.get("per_site", 1))


def near_decoys(offsets: list[tuple[float, float]]) -> int:
    return sum(1 for ox, oy in offsets if math.hypot(ox, oy) <= DECOY_NEAR_M)


def planned_decoy_offset(
    game: Game, tgo: TheaterGroundObject, side: SideCampaign, rng: Any
) -> Optional[tuple[float, float]]:
    """An offset (east, north) for a decoy toward the threat axis of the
    nearest defended asset, on valid ground; None if no spot is found."""
    from dcs.mapping import Point

    from .observations import ObservationLog

    log = ObservationLog(side)
    assets = [
        cp
        for cp in game.theater.control_points_for(tgo.control_point.captured)
        if not cp.is_fleet
    ]
    heading: Optional[float] = None
    if assets:
        nearest = min(assets, key=lambda cp: cp.position.distance_to_point(tgo.position))
        axes = log.axes(nearest, max_axes=1)
        if axes:
            heading = axes[0].heading
    terrain = getattr(game.theater, "farp_terrain", None)
    for attempt in range(10):
        if heading is not None and attempt < 7:
            bearing = heading + rng.uniform(-45, 45)
        else:
            bearing = rng.uniform(0, 360)
        distance = rng.uniform(1500, 5000)
        north = distance * math.cos(math.radians(bearing))
        east = distance * math.sin(math.radians(bearing))
        point = Point(tgo.position.x + north, tgo.position.y + east, tgo.position._terrain)
        try:
            if not game.theater.is_on_land(point):
                continue
        except Exception:
            pass
        if terrain is not None:
            site = terrain.survey(point, 150)
            if site.known and (site.steep or site.built_up):
                continue
        return east, north
    return None
