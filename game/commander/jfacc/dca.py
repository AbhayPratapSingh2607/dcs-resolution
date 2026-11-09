"""Defensive counter-air layout: threat axes, CAP stations, HVAA and point defense.

CAP stations are placed on the axes along which enemy air can come, rather
than over every base: from each enemy airbase with fighters toward the
friendly assets it can reach. Axes closer than the merge angle share a
station. Stations sit forward of the defended asset, short of known SAM
coverage, so the CAP's commit range covers the axis without flying into the
enemy IADS.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator, Optional, TYPE_CHECKING

from dcs.mapping import Point

from game.theater.missiontarget import MissionTarget

if TYPE_CHECKING:
    from game import Game
    from game.theater import ControlPoint
    from game.theater.player import Player
    from .observations import ObservationLog

NM = 1852.0


class CapStation(MissionTarget):
    """A CAP station on a threat axis in friendly airspace."""

    def __init__(
        self,
        name: str,
        position: Point,
        owner: Player,
        defended: ControlPoint,
        axis_heading: float,
    ) -> None:
        super().__init__(name, position)
        self.owner = owner
        self.defended = defended
        self.axis_heading = axis_heading

    def is_friendly(self, to_player: Player) -> bool:
        return to_player is self.owner

    @property
    def coalition(self):  # type: ignore[no-untyped-def]
        return self.defended.coalition

    @property
    def captured(self) -> Player:
        return self.owner


@dataclass
class ThreatAxis:
    defended: ControlPoint
    heading: float
    strength: float
    source_names: list[str]


def _enemy_fighter_bases(
    game: Game, player: Player
) -> Iterator[tuple[ControlPoint, float]]:
    from .assessment import fighter_value
    from .intelview import enemy_squadrons

    strength: dict[ControlPoint, float] = {}
    for squadron, count in enemy_squadrons(game, player):
        value = fighter_value(squadron, count, 1.0)
        if value <= 0:
            continue
        strength[squadron.location] = strength.get(squadron.location, 0.0) + value
    yield from strength.items()


def defended_assets(game: Game, player: Player) -> list[ControlPoint]:
    """Friendly bases worth defending: those with aircraft, carriers and
    front-line bases."""
    assets: list[ControlPoint] = []
    for cp in game.theater.controlpoints:
        if cp.captured is not player:
            continue
        if cp.is_fleet or cp.squadrons or cp.has_active_frontline:
            assets.append(cp)
    return assets


def _merge_axis(
    local: list[ThreatAxis],
    asset: ControlPoint,
    heading: float,
    weight: float,
    source: str,
    merge_deg: float,
) -> None:
    for axis in local:
        delta = abs((axis.heading - heading + 180) % 360 - 180)
        if delta <= merge_deg:
            total = axis.strength + weight
            # Strength-weighted mean heading.
            axis.heading = (
                math.degrees(
                    math.atan2(
                        axis.strength * math.sin(math.radians(axis.heading))
                        + weight * math.sin(math.radians(heading)),
                        axis.strength * math.cos(math.radians(axis.heading))
                        + weight * math.cos(math.radians(heading)),
                    )
                )
                % 360
            )
            axis.strength = total
            if source not in axis.source_names:
                axis.source_names.append(source)
            return
    local.append(ThreatAxis(asset, heading, weight, [source]))


#: Label of the axes learned from observed enemy activity.
OBSERVED = "observed enemy activity"


def threat_axes(
    game: Game,
    player: Player,
    reach_nm: float,
    merge_deg: float,
    max_axes: int,
    learned: Optional[ObservationLog] = None,
    learned_weight: float = 0.0,
) -> list[ThreatAxis]:
    """Axes enemy air can come from, per defended asset: toward the enemy
    fighter bases in reach, plus (``learned``) the bearings the side has
    actually seen enemy air activity on. ``learned_weight`` scales the
    observed axes relative to the strongest geometric axis of the asset."""
    bases = list(_enemy_fighter_bases(game, player))
    axes: list[ThreatAxis] = []
    for asset in defended_assets(game, player):
        local: list[ThreatAxis] = []
        for base, strength in bases:
            distance = asset.position.distance_to_point(base.position)
            if distance > reach_nm * NM:
                continue
            heading = asset.position.heading_between_point(base.position)
            # Nearer bases are a more pressing threat.
            weight = strength * (1.0 - 0.6 * distance / (reach_nm * NM))
            _merge_axis(local, asset, heading, weight, base.name, merge_deg)
        if learned is not None and learned_weight > 0:
            scale = max((a.strength for a in local), default=1.0)
            for observed in learned.axes(asset):
                # Confidence grows with the number of observations.
                confidence = min(1.0, observed.mass / 6.0)
                weight = learned_weight * scale * observed.share * confidence
                if weight > 0:
                    _merge_axis(
                        local, asset, observed.heading, weight, OBSERVED, merge_deg
                    )
        axes.extend(local)
    axes.sort(key=lambda a: -a.strength)
    # One station can screen several assets on the same axis: keep the
    # strongest axes, but no more than two per asset.
    chosen: list[ThreatAxis] = []
    per_asset: dict[str, int] = {}
    for axis in axes:
        if len(chosen) >= max_axes:
            break
        key = axis.defended.name
        if per_asset.get(key, 0) >= 2:
            continue
        duplicate = False
        for other in chosen:
            if (
                other.defended.position.distance_to_point(axis.defended.position)
                < 40 * NM
                and abs((other.heading - axis.heading + 180) % 360 - 180) <= merge_deg
            ):
                duplicate = True
                break
        if duplicate:
            continue
        chosen.append(axis)
        per_asset[key] = per_asset.get(key, 0) + 1
    return chosen


def station_for(
    game: Game,
    player: Player,
    axis: ThreatAxis,
    forward_nm: tuple[float, float],
    under_own_sams: bool = False,
) -> CapStation:
    """Place a CAP station forward of the defended asset along the axis, but
    clear of known enemy SAM coverage. With ``under_own_sams`` (force
    preservation) the station must also sit inside the side's own SAM
    coverage when any point on the axis is."""
    coalition = game.coalition_for(player)
    threat_zone = coalition.opponent.threat_zone
    own_zone = coalition.threat_zone
    near, far = forward_nm
    best: Optional[Point] = None
    fallback: Optional[Point] = None
    distance = far
    while distance >= near:
        point = axis.defended.position.point_from_heading(axis.heading, distance * NM)
        if not threat_zone.threatened_by_air_defense(point):
            if not under_own_sams or own_zone.threatened_by_air_defense(point):
                best = point
                break
            if fallback is None:
                fallback = point
        distance -= 5
    if best is None:
        best = fallback
    if best is None:
        best = axis.defended.position.point_from_heading(axis.heading, near * NM * 0.5)
    name = f"CAP {axis.defended.name} {int(axis.heading):03d}"
    return CapStation(name, best, player, axis.defended, axis.heading)


#: Name prefix of the CAP stations that protect AEW&C and tanker orbits.
HVAA_PREFIX = "HVAA CAP"


def hvaa_station(
    player: Player, defended: ControlPoint, position: Point, label: str
) -> CapStation:
    return CapStation(f"{HVAA_PREFIX} {label}", position, player, defended, 0.0)


def threatened_bases(game: Game, player: Player, reach_nm: float) -> list[ControlPoint]:
    bases = [b for b, _ in _enemy_fighter_bases(game, player)]
    result: list[ControlPoint] = []
    for asset in defended_assets(game, player):
        if any(
            asset.position.distance_to_point(b.position) <= reach_nm * NM * 0.6
            for b in bases
        ):
            result.append(asset)
    return result
