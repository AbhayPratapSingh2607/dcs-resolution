"""The bubble (M3): the flights of both sides the player is likely to meet
during the mission. Only the bubble is in DCS; the combat model fights the
rest over the same time (game.sim.atoperiod.resolve_remainder).

B1 relevance: for each package, how likely the player is to meet it during
the mission window, with one reason: where its flight plan puts it minute
by minute against the route, target and base of every flight with a
player, and for enemy CAPs and ground alerts whether their commit region
or sector covers that route.

B2 clusters: packages that would fight each other during the mission go
in or out together (a CAP with the raid it would commit on, an alert pair
with the raid that would launch it), one step of "would fight".

B3 budget: about ``packages per side in DCS`` (guidance, not a limit).
Always in, outside the budget: the player's package, their tanker and
AWACS, the SEAD corridor on their route, and pinned packages.

Everything here is a pure function of the plan; nothing in it changes the
plan.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight, Package

NM = 1852.0
#: Sampling step along flight plans.
STEP = timedelta(minutes=1)
#: A flight within this of the player's route at about the same time
#: crosses it.
CROSS_M = 15 * NM
CROSS_TIME = timedelta(minutes=5)
#: Beyond this from the player's route, target and base a flight is far.
RANGE_M = 60 * NM
NEAR_M = 25 * NM
#: SEAD and DEAD this close to the player's route, striking before or
#: during the mission, are the corridor the player flies through.
CORRIDOR_M = 15 * NM
CORRIDOR_LEAD = timedelta(minutes=20)
#: Default budget when the setting is missing.
DEFAULT_BUDGET = 10
#: Warn when the bubble holds more aircraft than this.
AIRCRAFT_WARNING = 120

XY = tuple[float, float]
Sample = tuple[datetime, XY]

SEAD_TASKS = {FlightType.SEAD, FlightType.DEAD, FlightType.SEAD_SWEEP}
CAP_TASKS = {FlightType.BARCAP, FlightType.TARCAP}


# --------------------------------------------------------------- geometry


def _xy(position: Any) -> XY:
    return float(position.x), float(position.y)


def _dist(a: XY, b: XY) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _dist_to_segment(p: XY, a: XY, b: XY) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 0:
        return _dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return _dist(p, (ax + t * dx, ay + t * dy))


def route_samples(
    flight: Flight, window: tuple[datetime, datetime], step: timedelta = STEP
) -> list[Sample]:
    """Where the flight's plan puts it, every ``step``, during the window."""
    plan = flight.flight_plan
    try:
        when = plan.takeoff_time()
        waypoints = list(plan.waypoints)
    except Exception:
        return []
    if len(waypoints) < 2:
        return []
    samples: list[Sample] = []
    start, end = window
    for a, b in zip(waypoints, waypoints[1:]):
        try:
            duration = plan.total_time_between_waypoints(a, b)
        except Exception:
            break
        t0, t1 = when, when + duration
        seconds = duration.total_seconds()
        if seconds > 0 and t1 >= start and t0 <= end:
            ax, ay = _xy(a.position)
            bx, by = _xy(b.position)
            cursor = max(t0, start)
            last = min(t1, end)
            while cursor <= last:
                f = (cursor - t0).total_seconds() / seconds
                samples.append((cursor, (ax + (bx - ax) * f, ay + (by - ay) * f)))
                cursor += step
        when = t1
        if when > end:
            break
    return samples


def commit_region(flight: Flight) -> Optional[tuple[XY, XY, float]]:
    """A CAP's commit region as (track start, track end, engagement
    distance), or an alert pair's sector as (station, station, radius)."""
    package = flight.package
    if getattr(flight, "alert", False):
        radius = float(getattr(package, "alert_radius_m", 0.0) or 0.0)
        if radius <= 0:
            return None
        station = _xy(package.target.position)
        return station, station, radius
    if flight.flight_type not in CAP_TASKS:
        return None
    plan = flight.flight_plan
    try:
        a = _xy(plan.layout.patrol_start.position)
        b = _xy(plan.layout.patrol_end.position)
        reach = float(getattr(plan, "engagement_distance").meters)
    except Exception:
        return None
    return a, b, reach


def region_covers(region: tuple[XY, XY, float], point: XY) -> bool:
    a, b, reach = region
    return _dist_to_segment(point, a, b) <= reach


def active_during(package: Package, window: tuple[datetime, datetime]) -> bool:
    from .atoperiod import package_span

    first, last = package_span(package)
    if first is None or last is None:
        return False
    return first < window[1] and last > window[0]


# -------------------------------------------------------------- relevance


@dataclass
class PlayerGeometry:
    """The route, targets and bases of every flight with a player."""

    samples: list[Sample] = field(default_factory=list)
    targets: list[XY] = field(default_factory=list)
    bases: list[XY] = field(default_factory=list)
    packages: list[Package] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.packages


def player_geometry(game: Game, window: tuple[datetime, datetime]) -> PlayerGeometry:
    geometry = PlayerGeometry()
    for package in game.blue.ato.packages:
        if not package.has_players:
            continue
        geometry.packages.append(package)
        try:
            geometry.targets.append(_xy(package.target.position))
        except Exception:
            pass
        for flight in package.flights:
            try:
                geometry.bases.append(_xy(flight.departure.position))
            except Exception:
                pass
            geometry.samples.extend(route_samples(flight, window))
    return geometry


@dataclass
class Relevance:
    package: Package
    score: float
    reason: str
    #: In the mission regardless of the budget.
    always: bool = False
    #: Packages this one would fight during the mission (one step).
    partners: list[Package] = field(default_factory=list)
    #: Flying during the mission; packages that aren't are before or after
    #: it, not elsewhere.
    active: bool = True

    @property
    def blue(self) -> bool:
        flights = self.package.flights
        return bool(flights) and flights[0].squadron.player.is_blue


def _closest(
    samples: Iterable[Sample], player: PlayerGeometry
) -> tuple[float, Optional[datetime], str]:
    """(distance, time, what) of the package's closest approach to the
    player's route, target or base."""
    best: tuple[float, Optional[datetime], str] = (math.inf, None, "")
    for when, point in samples:
        for t, p in player.samples:
            d = _dist(point, p)
            if d < best[0] and abs(t - when) <= CROSS_TIME:
                best = (d, when, "route")
        for target in player.targets:
            d = _dist(point, target)
            if d < best[0]:
                best = (d, when, "target")
        for base in player.bases:
            d = _dist(point, base)
            if d < best[0]:
                best = (d, when, "base")
    return best


def relevance_of(
    package: Package,
    player: PlayerGeometry,
    window: tuple[datetime, datetime],
    blue: bool,
) -> Relevance:
    """How likely the player is to meet this package during the mission."""
    if package.has_players:
        return Relevance(package, 1.0, "your package", always=True)
    if getattr(package, "pinned", False):
        return Relevance(package, 1.0, "pinned: keep in my mission", always=True)
    if not active_during(package, window):
        return Relevance(
            package, 0.0, "not in the air during your mission", active=False
        )
    task = package.primary_task
    if blue and task in SEAD_TASKS:
        tot = package.time_over_target
        if window[0] - CORRIDOR_LEAD <= tot <= window[1]:
            try:
                target = _xy(package.target.position)
            except Exception:
                target = None
            if target is not None and any(
                _dist(target, p) <= CORRIDOR_M for _, p in player.samples
            ):
                return Relevance(
                    package, 1.0, "SEAD corridor on your route", always=True
                )
    samples: list[Sample] = []
    for flight in package.flights:
        if not blue:
            region = commit_region(flight)
            if region is not None:
                if any(region_covers(region, p) for _, p in player.samples):
                    what = "alert sector" if getattr(flight, "alert", False) else "CAP"
                    return Relevance(package, 1.0, f"{what} covers your route")
                continue
        samples.extend(route_samples(flight, window))
    if not samples:
        return Relevance(package, 0.05, "on station away from your route")
    distance, when, what = _closest(samples, player)
    if what == "route" and distance <= CROSS_M and when is not None:
        return Relevance(package, 1.0, f"crosses your route at {when:%H:%M}")
    if distance >= RANGE_M or when is None:
        return Relevance(package, 0.0, f"{distance / NM:.0f} nm from your mission")
    score = 1.0 - 0.7 * distance / RANGE_M
    if what == "target" and distance <= NEAR_M:
        return Relevance(package, max(score, 0.8), f"near your target at {when:%H:%M}")
    if what == "base" and distance <= NEAR_M:
        return Relevance(package, max(score, 0.6), f"near your base at {when:%H:%M}")
    return Relevance(package, score, f"passes {distance / NM:.0f} nm from your {what}")


def support_for_player(
    game: Game, player: PlayerGeometry, window: tuple[datetime, datetime]
) -> dict[int, str]:
    """The tanker and AWACS the player needs: the nearest blue tanker track
    and AWACS orbit on station during the mission, by package id."""
    found: dict[int, str] = {}
    if not player.samples:
        return found
    for task, label in (
        (FlightType.REFUELING, "your tanker"),
        (FlightType.AEWC, "your AWACS"),
    ):
        best: tuple[float, Optional[Package]] = (math.inf, None)
        for package in game.blue.ato.packages:
            if package.has_players or package.primary_task is not task:
                continue
            if not active_during(package, window):
                continue
            flight = package.primary_flight
            if flight is None:
                continue
            try:
                station = _xy(flight.flight_plan.layout.patrol_start.position)
            except Exception:
                station = _xy(package.target.position)
            distance = min(_dist(station, p) for _, p in player.samples)
            if distance < best[0]:
                best = (distance, package)
        if best[1] is not None:
            found[id(best[1])] = label
    return found


# --------------------------------------------------------------- clusters


def find_partners(
    relevances: list[Relevance], window: tuple[datetime, datetime]
) -> None:
    """One step of "would fight": a CAP or alert of one side and a package
    of the other whose route during the mission enters its commit region."""
    regions: list[tuple[Relevance, tuple[XY, XY, float]]] = []
    routes: list[tuple[Relevance, list[Sample]]] = []
    for relevance in relevances:
        package = relevance.package
        if not active_during(package, window):
            continue
        covered = False
        for flight in package.flights:
            region = commit_region(flight)
            if region is not None:
                regions.append((relevance, region))
                covered = True
        if not covered:
            samples: list[Sample] = []
            for flight in package.flights:
                samples.extend(route_samples(flight, window))
            if samples:
                routes.append((relevance, samples))
    for cap, region in regions:
        for other, samples in routes:
            if other.blue == cap.blue:
                continue
            if any(region_covers(region, p) for _, p in samples):
                if other.package not in cap.partners:
                    cap.partners.append(other.package)
                if cap.package not in other.partners:
                    other.partners.append(cap.package)


# ------------------------------------------------------------------ bubble


@dataclass
class Bubble:
    window: tuple[datetime, datetime]
    budget: int
    relevances: dict[int, Relevance] = field(default_factory=dict)
    inside: set[int] = field(default_factory=set)

    def relevance(self, package: Package) -> Optional[Relevance]:
        return self.relevances.get(id(package))

    def in_mission(self, package: Package) -> Optional[bool]:
        if id(package) not in self.relevances:
            return None
        return id(package) in self.inside

    def reason(self, package: Package) -> str:
        relevance = self.relevance(package)
        return relevance.reason if relevance is not None else ""

    def packages(self, blue: bool, inside: bool = True) -> list[Package]:
        """The side's packages in the mission, or (``inside=False``) the ones
        flying elsewhere during it."""
        return [
            r.package
            for r in self.relevances.values()
            if r.blue == blue
            and ((id(r.package) in self.inside) == inside)
            and (inside or r.active)
        ]

    def aircraft(self) -> int:
        return sum(
            f.count
            for r in self.relevances.values()
            if id(r.package) in self.inside
            for f in r.package.flights
        )

    def summary(self) -> str:
        blue_in, red_in = len(self.packages(True)), len(self.packages(False))
        blue_out, red_out = len(self.packages(True, False)), len(
            self.packages(False, False)
        )
        return (
            f"bubble: blue {blue_in} in, {blue_out} elsewhere; red {red_in} in, "
            f"{red_out} elsewhere; {self.aircraft()} aircraft in DCS"
        )


def budget_of(game: Game) -> int:
    return int(getattr(game.settings, "bubble_package_target", DEFAULT_BUDGET))


def enabled(game: Game) -> bool:
    return bool(getattr(game.settings, "bubble_enabled", True))


def compute(
    game: Game,
    window: Optional[tuple[datetime, datetime]] = None,
    budget: Optional[int] = None,
) -> Optional[Bubble]:
    """The bubble for this mission, or None when there is no window or no
    flight with a player (then everything flies in DCS, as before)."""
    from .atoperiod import is_focused
    from .atoperiod import window as window_of

    if window is None:
        if is_focused(game) or not enabled(game):
            return None
        window = window_of(game)
    if window is None:
        return None
    player = player_geometry(game, window)
    if player.empty:
        return None
    if budget is None:
        budget = budget_of(game)
    bubble = Bubble(window, budget)
    support = support_for_player(game, player, window)
    relevances: list[Relevance] = []
    for coalition in (game.blue, game.red):
        blue = coalition.player.is_blue
        for package in coalition.ato.packages:
            try:
                relevance = relevance_of(package, player, window, blue)
            except Exception:
                logging.exception(f"Could not score {package} for the bubble")
                relevance = Relevance(package, 0.5, "unscored")
            label = support.get(id(package))
            if label is not None:
                relevance = Relevance(package, 1.0, label, always=True)
            relevances.append(relevance)
            bubble.relevances[id(package)] = relevance
    find_partners(relevances, window)
    _select(bubble, relevances)
    return bubble


def _select(bubble: Bubble, relevances: list[Relevance]) -> None:
    counts = {True: 0, False: 0}

    def add(relevance: Relevance, with_partners: bool = True) -> None:
        key = id(relevance.package)
        if key in bubble.inside:
            return
        bubble.inside.add(key)
        counts[relevance.blue] += 1
        if with_partners:
            for partner in relevance.partners:
                other = bubble.relevances.get(id(partner))
                if other is not None:
                    add(other, with_partners=False)

    for relevance in relevances:
        if relevance.always:
            add(relevance)
    # Always-in packages don't count toward the budget.
    counts = {True: 0, False: 0}
    ranked = sorted(
        (r for r in relevances if not r.always and r.score > 0),
        key=lambda r: (-r.score, r.package.time_over_target),
    )
    for relevance in ranked:
        if id(relevance.package) in bubble.inside:
            continue
        if counts[relevance.blue] >= bubble.budget:
            continue
        add(relevance)


# ---------------------------------------------------------------- preview

_preview_cache: dict[int, tuple[tuple[Any, ...], Optional[Bubble]]] = {}


def _signature(game: Game) -> tuple[Any, ...]:
    parts: list[Any] = [getattr(game, "turn", 0), budget_of(game), enabled(game)]
    for coalition in (game.blue, game.red):
        for package in coalition.ato.packages:
            parts.append(
                (
                    id(package),
                    package.time_over_target,
                    len(package.flights),
                    package.has_players,
                    getattr(package, "pinned", False),
                )
            )
    return tuple(parts)


def preview(game: Game) -> Optional[Bubble]:
    """The bubble the mission will have, before it is generated (B6): the
    window placed on the player's flight as Take off will place it. Cached
    until the plan changes."""
    from .atoperiod import is_focused, player_window_start, window_length

    try:
        if is_focused(game) or not enabled(game):
            return None
        start = player_window_start(game)
        if start is None:
            return None
        signature = _signature(game)
        cached = _preview_cache.get(id(game))
        if cached is not None and cached[0] == signature:
            return cached[1]
        result = compute(game, (start, start + window_length(game)))
    except Exception:
        logging.exception("Could not preview the bubble")
        return None
    _preview_cache.clear()
    _preview_cache[id(game)] = (signature, result)
    return result


def elsewhere_ids(game: Game) -> set[int]:
    """id() of the packages the preview leaves out of the mission."""
    result = preview(game)
    if result is None:
        return set()
    return {
        key
        for key, r in result.relevances.items()
        if key not in result.inside and r.active
    }


# --------------------------------------------------------------- deferral

ELSEWHERE = "elsewhere"


def defer_elsewhere(game: Game, bubble: Bubble) -> int:
    """Hold the packages outside the bubble back from the .miz, the way
    atoperiod.defer_after_window holds back later packages, marked
    "elsewhere" so the combat model fights them over the mission's time
    and the debrief reports them apart (B4)."""
    state = game.air_campaign
    deferred = 0
    for coalition in (game.blue, game.red):
        held = state.deferred_packages.setdefault(coalition.player.is_blue, [])
        for package in list(coalition.ato.packages):
            if bubble.in_mission(package) is not False:
                continue
            if package.has_players:
                continue
            relevance = bubble.relevance(package)
            if relevance is not None and not relevance.active:
                # Not flying during the mission (an alert pair that hasn't
                # scrambled): it stays in the .miz, late-activated as before.
                continue
            package.deferred_reason = ELSEWHERE  # type: ignore[attr-defined]
            coalition.ato.packages.remove(package)
            held.append(package)
            deferred += 1
    if deferred:
        logging.info(
            f"Held back {deferred} packages outside the bubble ({bubble.summary()})"
        )
    return deferred


def is_elsewhere(package: Package) -> bool:
    return getattr(package, "deferred_reason", "") == ELSEWHERE


def parked_at_player_bases(game: Game) -> list[tuple[Any, int]]:
    """B8: aircraft of packages held elsewhere that sit on the ramp at a
    base the player flies from when the mission starts (they start up later,
    or flew earlier and are back). Without them the player's base would look
    emptier than it is. (squadron, aircraft) pairs, to be spawned parked and
    uncontrolled; the combat model still flies them."""
    from game.ato.flightstate import Completed, WaitingForStart

    bases = set()
    for coalition in (game.blue, game.red):
        for package in coalition.ato.packages:
            for flight in package.flights:
                if flight.client_count > 0:
                    bases.add(id(flight.departure))
    if not bases:
        return []
    state = getattr(game, "air_campaign", None)
    held = getattr(state, "deferred_packages", {}) or {}
    counts: dict[int, tuple[Any, int]] = {}
    for packages in held.values():
        for package in packages:
            if not is_elsewhere(package):
                continue
            for flight in package.flights:
                if id(flight.departure) not in bases:
                    continue
                if not isinstance(flight.state, (WaitingForStart, Completed)):
                    continue
                squadron = flight.squadron
                _, n = counts.get(id(squadron), (squadron, 0))
                counts[id(squadron)] = (squadron, n + flight.count)
    return list(counts.values())


def hold_back_elsewhere(game: Game) -> Optional[Bubble]:
    """B4: compute this mission's bubble and hold the rest back from the
    .miz. Called after atoperiod.defer_after_window, so only packages flying
    during the window are scored. Returns the bubble (None when there is
    none: mission-only turns, the bubble off, or no player flight)."""
    try:
        result = compute(game)
    except Exception:
        logging.exception("Could not compute the bubble; everything flies in DCS")
        return None
    if result is None:
        return None
    defer_elsewhere(game, result)
    aircraft = result.aircraft()
    if aircraft > AIRCRAFT_WARNING:
        logging.warning(f"The bubble holds {aircraft} aircraft")
    return result
