"""What a side has seen of the enemy's air operations, and the axes it learns.

Each side keeps, per own asset (control point), a histogram of the bearings
along which enemy aircraft were seen: 36 bins of 10 degrees, decayed every
turn so old habits fade. It also keeps how often each of its own ground
objects was hit.

Only the side's own observations feed it, never ground truth:

* enemy flights its own surveillance (EWR, AWACS, GCI radars) covered during
  the fast-forward simulation (``Observation``, collected by
  ``AircraftSimulation``);
* its own losses at the debriefing: aircraft shot down and ground objects
  destroyed, in DCS missions as well as in fast-forward.

The learned axes feed the DCA layout (``dca.threat_axes``), GCI sectors, SAM
moves and decoy placement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from dcs import Point

    from game import Game
    from game.theater import ControlPoint, Player
    from .campaignstate import SideCampaign

BINS = 36
BIN_DEG = 360.0 / BINS
#: Weight kept from earlier turns, applied once per turn.
DECAY = 0.7
#: Observations farther than this from every own asset are not attributed.
ASSET_RADIUS_M = 300_000.0
#: Weight of one observation of an enemy flight, per aircraft in it.
SEEN_WEIGHT = 0.25
#: Weight of an own aircraft lost, and of an own ground unit destroyed.
LOSS_WEIGHT = 1.0
GROUND_LOSS_WEIGHT = 0.5
#: Histogram mass below which nothing has been learned for an asset.
MIN_MASS = 1.0


@dataclass(frozen=True)
class Observation:
    """One sighting of an enemy flight by a side's own surveillance."""

    viewer_is_blue: bool
    flight_key: int
    x: float
    y: float
    aircraft: int


@dataclass(frozen=True)
class LearnedAxis:
    asset_name: str
    heading: float
    #: Share of the asset's observed activity along this axis.
    share: float
    #: Total (decayed) observations behind the asset's histogram.
    mass: float


def _own_assets(game: Game, player: Player) -> list[ControlPoint]:
    return [cp for cp in game.theater.control_points_for(player) if not cp.is_fleet]


def _nearest_asset(
    assets: Iterable[ControlPoint], x: float, y: float
) -> Optional[ControlPoint]:
    best: Optional[ControlPoint] = None
    best_d = ASSET_RADIUS_M
    for cp in assets:
        d = math.hypot(cp.position.x - x, cp.position.y - y)
        if d <= best_d:
            best, best_d = cp, d
    return best


def heading_deg(origin: Point, x: float, y: float) -> float:
    """DCS heading (0 = north = +x, 90 = east = +y) from origin to (x, y)."""
    return math.degrees(math.atan2(y - origin.y, x - origin.x)) % 360


def _bin(heading: float) -> int:
    return int(heading // BIN_DEG) % BINS


class ObservationLog:
    """Reads and updates a side's observation state (``SideCampaign``)."""

    def __init__(self, side: SideCampaign) -> None:
        self.side = side

    # ------------------------------------------------------------- update

    def start_turn(self, turn: int) -> None:
        """Decay the history once per turn, before this turn's observations."""
        side = self.side
        if side.observed_turn == turn:
            return
        steps = 1 if side.observed_turn < 0 else max(1, turn - side.observed_turn)
        factor = DECAY**steps
        for key, bins in list(side.observed_axes.items()):
            bins[:] = [b * factor for b in bins]
            if sum(bins) < 0.05:
                del side.observed_axes[key]
        for key in list(side.attacked):
            side.attacked[key] *= factor
            if side.attacked[key] < 0.05:
                del side.attacked[key]
        side.observed_turn = turn
        side.enemy_sorties_seen = 0

    def add_point(
        self, assets: list[ControlPoint], x: float, y: float, weight: float
    ) -> None:
        asset = _nearest_asset(assets, x, y)
        if asset is None:
            return
        if math.hypot(asset.position.x - x, asset.position.y - y) < 1000:
            return  # On top of the asset: no bearing.
        bins = self.side.observed_axes.setdefault(str(asset.id), [0.0] * BINS)
        bins[_bin(heading_deg(asset.position, x, y))] += weight

    def record_attack(self, tgo_id: Any, weight: float) -> None:
        key = str(tgo_id)
        self.side.attacked[key] = self.side.attacked.get(key, 0.0) + weight

    # -------------------------------------------------------------- query

    def mass(self, asset: ControlPoint) -> float:
        return sum(self.side.observed_axes.get(str(asset.id), ()))

    def axes(self, asset: ControlPoint, max_axes: int = 3) -> list[LearnedAxis]:
        """Peaks of the asset's histogram (smoothed over neighbouring bins)."""
        bins = self.side.observed_axes.get(str(asset.id))
        if not bins:
            return []
        mass = sum(bins)
        if mass < MIN_MASS:
            return []
        smooth = [
            0.25 * bins[(i - 1) % BINS] + 0.5 * bins[i] + 0.25 * bins[(i + 1) % BINS]
            for i in range(BINS)
        ]
        peaks = [
            i
            for i in range(BINS)
            if smooth[i] > 0
            and smooth[i] >= smooth[(i - 1) % BINS]
            and smooth[i] > smooth[(i + 1) % BINS]
        ]
        peaks.sort(key=lambda i: -smooth[i])
        result = []
        for i in peaks[:max_axes]:
            # Weighted mean heading over the peak and its neighbours.
            sx = sy = 0.0
            share = 0.0
            for j in (i - 1, i, i + 1):
                w = bins[j % BINS]
                centre = math.radians((j % BINS + 0.5) * BIN_DEG)
                sx += w * math.cos(centre)
                sy += w * math.sin(centre)
                share += w
            heading = math.degrees(math.atan2(sy, sx)) % 360
            result.append(LearnedAxis(asset.name, heading, share / mass, mass))
        return result

    def attack_weight(self, tgo_id: Any) -> float:
        return self.side.attacked.get(str(tgo_id), 0.0)


# ------------------------------------------------------------------ commit


def record_turn(game: Game, debriefing: Any) -> None:
    """Feed both sides' observation logs from a committed debriefing."""
    from game.theater import Player

    state = getattr(game, "air_campaign", None)
    if state is None:
        return
    for player in (Player.BLUE, Player.RED):
        side = state.side(player.is_blue)
        log = ObservationLog(side)
        log.start_turn(game.turn)
        assets = _own_assets(game, player)
        if not assets:
            continue
        seen_flights: dict[int, int] = {}
        for obs in getattr(debriefing, "observations", None) or []:
            if obs.viewer_is_blue != player.is_blue:
                continue
            seen_flights[obs.flight_key] = obs.aircraft
            log.add_point(assets, obs.x, obs.y, SEEN_WEIGHT * obs.aircraft)
        side.enemy_sorties_seen += sum(seen_flights.values())
        # Own aircraft lost: the side knows where its own crews went down.
        for detail in getattr(debriefing, "air_loss_details", None) or []:
            try:
                own = detail.flight.squadron.player.is_blue == player.is_blue
            except AttributeError:
                continue
            if own and detail.position is not None:
                log.add_point(assets, detail.position.x, detail.position.y, LOSS_WEIGHT)
        # Own sites that engaged: the side knows its crews fired.
        for event in getattr(debriefing, "intel_events", None) or []:
            if getattr(getattr(event, "source", None), "name", "") != "ENGAGEMENT":
                continue
            if event.observer_blue == player.is_blue:
                continue  # The enemy's own sites fired at this side.
            side.fired_sites[str(event.tgo_id)] = game.turn
        for key, turn in list(side.fired_sites.items()):
            if turn < game.turn - 3:
                del side.fired_sites[key]
        # Own ground objects hit.
        losses = debriefing.ground_losses
        own_tgos = (
            losses.player_ground_objects
            if player.is_blue
            else losses.enemy_ground_objects
        )
        for mapping in own_tgos:
            unit = getattr(mapping, "theater_unit", None)
            tgo = getattr(unit, "ground_object", None)
            if tgo is None:
                continue
            log.record_attack(tgo.id, GROUND_LOSS_WEIGHT)
            log.add_point(assets, tgo.position.x, tgo.position.y, GROUND_LOSS_WEIGHT)


def collect(model: Any, time: Any, flights: Iterable[Any]) -> list[Observation]:
    """Enemy flights each side's own surveillance covers right now."""
    from game.theater import Player

    result: list[Observation] = []
    in_flight = [f for f in flights if f.alive and f.state.in_flight]
    for player in (Player.BLUE, Player.RED):
        awareness = model.awareness(player, time)
        if not awareness.sources:
            continue
        for flight in in_flight:
            if flight.squadron.player.is_blue == player.is_blue:
                continue
            airframes = model.airframes(flight)
            if not airframes:
                continue
            lead = airframes[0]
            try:
                position = lead.position
                altitude = lead.altitude_m
            except Exception:
                continue
            if awareness.covers(position, altitude, lead.effective_rcs):
                result.append(
                    Observation(
                        player.is_blue, id(flight), position.x, position.y, len(airframes)
                    )
                )
    return result
