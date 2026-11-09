"""Route and target-area threat analysis for package sizing and risk.

The threat is judged from the side's intelligence picture: known SAM sites at
their believed positions, and the estimated enemy fighter strength whose bases
can reach the route.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from shapely.geometry import LineString, Point as ShapelyPoint

from .targetclass import sam_weight

if TYPE_CHECKING:
    from dcs.mapping import Point

    from game import Game
    from game.theater import MissionTarget
    from game.theater.player import Player
    from game.theater.theatergroundobject import TheaterGroundObject

LEVELS = ("low", "medium", "high", "extreme")


@dataclass
class RouteThreat:
    #: Quality-weighted enemy fighters able to reach the route.
    air_strength: float = 0.0
    #: Sum of radar SAM weights (LORAD 3, MERAD 2, SHORAD 1) covering the route.
    sam_weight: float = 0.0
    sams: list[TheaterGroundObject] = field(default_factory=list)
    #: Whether the target lies inside known radar SAM coverage.
    target_defended: bool = False
    air_level: str = "low"
    sam_level: str = "low"
    #: Allowance for SAM sites intelligence hasn't found.
    unknown_weight: float = 0.0
    #: Enemy aircrew and SAM crew quality (1.0 = baseline).
    enemy_aircrew: float = 1.0
    enemy_sam_crew: float = 1.0

    @property
    def level(self) -> str:
        return LEVELS[max(LEVELS.index(self.air_level), LEVELS.index(self.sam_level))]


def _level(value: float, thresholds: dict[str, float]) -> str:
    level = "low"
    for name in ("medium", "high", "extreme"):
        if value >= float(thresholds.get(name, 1e9)):
            level = name
    return level


def _picture(game: Game, player: Player) -> Optional[object]:
    war_state = getattr(game, "war_state", None)
    if war_state is None or not war_state.intel_enabled(game):
        return None
    return war_state.picture(game, player)


def _add_sam_exposure(
    game: Game,
    player: Player,
    threat: RouteThreat,
    route: LineString,
    target: MissionTarget,
    picture: Optional[object],
    packages_cfg: dict[str, object],
    exclude: Optional[TheaterGroundObject],
    suppressed: Optional[set[object]],
) -> None:
    """Add the radar SAMs whose envelope the route crosses, plus an allowance
    for sites intelligence hasn't found."""
    from game.theater.theatergroundobject import IadsGroundObject, NavalGroundObject
    from game.warfare.intel import is_mobile
    from .assessment import enemy_tgos
    from .intelview import believed_radar_reach_m

    target_point = ShapelyPoint(target.position.x, target.position.y)
    cap_m = float(game.settings.max_threat_range) * 1852.0
    known_mobile = 0
    for tgo in enemy_tgos(game, player):
        if not isinstance(tgo, (IadsGroundObject, NavalGroundObject)):
            continue
        if tgo is exclude:
            continue
        if suppressed and tgo.id in suppressed:
            continue
        reach_m = believed_radar_reach_m(game, player, tgo)
        weight = sam_weight(tgo, live=reach_m > 0)
        if weight <= 0:
            continue
        if picture is not None:
            if not picture.knows(tgo) or not picture.believed_alive(tgo):  # type: ignore[attr-defined]
                continue
            position = picture.estimated_position(tgo)  # type: ignore[attr-defined]
        else:
            position = tgo.position
        reach = min(reach_m, cap_m)
        if reach <= 0:
            continue
        site = ShapelyPoint(position.x, position.y)
        distance = route.distance(site)
        if distance <= reach:
            # The edge of a long-range envelope is less dangerous than its core.
            depth = 1.0 - 0.5 * distance / reach
            threat.sam_weight += weight * depth
            threat.sams.append(tgo)
            if target_point.distance(site) <= reach:
                threat.target_defended = True
            if is_mobile(tgo) and not isinstance(tgo, NavalGroundObject):
                known_mobile += 1
    # Pop-up threats: mobile SAMs intelligence hasn't located. Planners scale
    # the known density by how complete they believe their picture is.
    if picture is not None and known_mobile:
        found = float(packages_cfg.get("mobile_sam_detection_belief", 0.5))  # type: ignore[arg-type]
        unknown = known_mobile * (1 - found) / max(found, 0.1)
        threat.unknown_weight = 2.0 * 0.5 * unknown
        threat.sam_weight += threat.unknown_weight


def analyse_path(
    game: Game,
    player: Player,
    points: list[Point],
    target: MissionTarget,
    packages_cfg: dict[str, object],
    exclude: Optional[TheaterGroundObject] = None,
    suppressed: Optional[set[object]] = None,
) -> RouteThreat:
    """SAM threat along a planned route (waypoints from take-off to landing)."""
    threat = RouteThreat()
    from game.sim.combat.model.forcequality import for_faction

    try:
        threat.enemy_sam_crew = for_faction(
            game.coalition_for(player).opponent.faction.name
        ).sam_crew
    except Exception:
        pass
    if len(points) < 2:
        return threat
    route = LineString([(p.x, p.y) for p in points])
    _add_sam_exposure(
        game,
        player,
        threat,
        route,
        target,
        _picture(game, player),
        packages_cfg,
        exclude,
        suppressed,
    )
    from .assessment import believed_alive
    from .intelview import believed_live_radar_sam

    if exclude is not None and believed_alive(game, player, exclude):
        threat.sam_weight += sam_weight(
            exclude, live=believed_live_radar_sam(game, player, exclude)
        )
        threat.target_defended = True
    threat.sam_level = _level(
        threat.sam_weight,
        packages_cfg.get("sam_threat_thresholds", {}),  # type: ignore[arg-type]
    )
    return threat


def analyse_route(
    game: Game,
    player: Player,
    origin: Point,
    target: MissionTarget,
    packages_cfg: dict[str, object],
    exclude: Optional[TheaterGroundObject] = None,
    suppressed: Optional[set[object]] = None,
) -> RouteThreat:
    """Threat to a package attacking the target.

    Packages route around known SAM coverage on the way to the IP (the
    navmesh does this), so SAM exposure is counted on the ingress leg only:
    from the ingress distance out to the target, plus the target area.
    ``suppressed`` holds sites an earlier package this period is tasked to
    destroy before this one arrives (IADS rollback).
    """
    from game.sim.combat.model.forcequality import for_faction
    from .assessment import believed_alive, fighter_value
    from .intelview import believed_live_radar_sam

    threat = RouteThreat()
    enemy = game.coalition_for(player).opponent
    try:
        quality = for_faction(enemy.faction.name)
        threat.enemy_aircrew = quality.aircrew
        threat.enemy_sam_crew = quality.sam_crew
    except Exception:
        pass

    picture = _picture(game, player)
    ingress_m = float(packages_cfg.get("ingress_exposure_nm", 40)) * 1852.0  # type: ignore[arg-type]
    total_m = origin.distance_to_point(target.position)
    if total_m > ingress_m:
        heading = target.position.heading_between_point(origin)
        start = target.position.point_from_heading(heading, ingress_m)
    else:
        start = origin
    route = LineString([(start.x, start.y), (target.position.x, target.position.y)])
    _add_sam_exposure(
        game, player, threat, route, target, picture, packages_cfg, exclude, suppressed
    )
    if exclude is not None and believed_alive(game, player, exclude):
        # Attacking a SAM means flying into it.
        threat.sam_weight += sam_weight(
            exclude, live=believed_live_radar_sam(game, player, exclude)
        )
        threat.target_defended = True

    # Enemy fighters able to engage over the target. Only part of an air
    # force is airborne or on alert at any moment, and nearer bases react
    # faster.
    from game.sim.combat.model.fuel import fuel_profile

    from .intelview import enemy_squadrons

    availability = float(packages_cfg.get("enemy_fighter_availability", 0.25))  # type: ignore[arg-type]
    for squadron, estimated in enemy_squadrons(game, player):
        base = squadron.location
        radius_m = fuel_profile(squadron.aircraft).radius_km * 1000
        distance = base.position.distance_to_point(target.position)
        if distance > radius_m:
            continue
        factor = availability * (1.0 - 0.5 * distance / radius_m)
        if not base.runway_is_operational() and not base.is_fleet:
            factor *= 0.3
        threat.air_strength += factor * fighter_value(
            squadron, estimated, threat.enemy_aircrew
        )

    threat.air_level = _level(
        threat.air_strength,
        packages_cfg.get("air_threat_thresholds", {}),  # type: ignore[arg-type]
    )
    threat.sam_level = _level(
        threat.sam_weight,
        packages_cfg.get("sam_threat_thresholds", {}),  # type: ignore[arg-type]
    )
    return threat
