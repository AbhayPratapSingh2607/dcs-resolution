"""How packages and flights are presented in the ATO sidebar and timeline.

Qt-free so it can be unit tested: groups and colours (hex strings), short
composition strings, flight roles, key times, offsets into the ATO period,
risk badges, tooltips and timeline lanes.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight, Package


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    color: str
    #: Chip label in the sidebar.
    short: str


#: Sidebar and timeline groups, in display order. Colours follow the task
#: label palette of the DCS stylesheet (resources/stylesheets/style-dcs.css).
GROUPS: tuple[Group, ...] = (
    Group("dca", "Defensive counter-air", "#445299", "DCA"),
    Group("support", "Support (AEW&C, tankers)", "#3b8a8a", "Support"),
    Group("oca", "Offensive counter-air", "#6a52bc", "OCA"),
    Group("sead", "SEAD / DEAD", "#cc8844", "SEAD/DEAD"),
    Group("strike", "Strike", "#ab2244", "Strike"),
    Group("interdiction", "Interdiction", "#b0503a", "Interdiction"),
    Group("cas", "Close air support", "#c23b5a", "CAS"),
    Group("pr", "Personnel recovery", "#3f9a5c", "CSAR"),
    Group("lift", "Airlift / air assault", "#7a8a3c", "Lift"),
    Group("other", "Other", "#66727e", "Other"),
)
GROUP_BY_KEY = {g.key: g for g in GROUPS}
GROUP_ORDER = {g.key: i for i, g in enumerate(GROUPS)}

LIFT_TASKS = {
    FlightType.TRANSPORT,
    FlightType.AIR_ASSAULT,
    FlightType.FERRY,
    FlightType.PRETENSE_CARGO,
}
#: Flights that support a package rather than carry out its mission.
SUPPORT_ROLES = {
    FlightType.ESCORT: "Escort",
    FlightType.SWEEP: "Sweep",
    FlightType.TARCAP: "TARCAP",
    FlightType.SEAD_ESCORT: "SEAD",
    FlightType.SEAD_SWEEP: "SEAD",
    FlightType.REFUELING: "Tanker",
}
#: Missions flown as continuous lines (relief chains), merged into one
#: timeline lane per station.
LINE_TASKS = {
    FlightType.BARCAP,
    FlightType.TARCAP,
    FlightType.AEWC,
    FlightType.REFUELING,
    FlightType.RECOVERY,
    FlightType.CAS,
}

#: Risk badge thresholds: expected losses per sortie.
RISK_MEDIUM = 0.02
RISK_HIGH = 0.05
RISK_COLORS = {"low": "#5fa85f", "medium": "#d9a23a", "high": "#d9534f"}


# ------------------------------------------------------------------ groups


def package_group(package: Package) -> Group:
    task = package.primary_task
    if task is None:
        return GROUP_BY_KEY["other"]
    if task is FlightType.CSAR:
        return GROUP_BY_KEY["pr"]
    if task in LIFT_TASKS:
        return GROUP_BY_KEY["lift"]
    if task is FlightType.RECOVERY:
        return GROUP_BY_KEY["support"]
    from game.commander.jfacc.profile import category_for_task

    category = category_for_task(task)
    if category is None:
        return GROUP_BY_KEY["other"]
    return GROUP_BY_KEY.get(category.value, GROUP_BY_KEY["other"])


def sort_key(package: Package) -> tuple[int, datetime]:
    return GROUP_ORDER[package_group(package).key], package.time_over_target


# ------------------------------------------------------------- composition


def short_aircraft_name(flight: Flight) -> str:
    """ "F-15E Strike Eagle (Suite 4+)" -> "F-15E"."""
    name = str(getattr(flight.unit_type, "display_name", flight.unit_type))
    return name.split(" ")[0] if name else "?"


def flight_role(flight: Flight) -> str:
    role = SUPPORT_ROLES.get(flight.flight_type)
    if role is None:
        return flight.flight_type.value
    if role in ("Escort", "SEAD") and getattr(
        flight.unit_type, "has_built_in_jamming", False
    ):
        return "Jammer"
    return role


def is_support(flight: Flight) -> bool:
    return (
        flight.flight_type in SUPPORT_ROLES
        and flight.package.primary_flight is not flight
    )


def composition(package: Package) -> str:
    """Main flights first, then support: "4× F-15E Strike · 2× F-16CM SEAD"."""
    flights = sorted(
        package.flights, key=lambda f: (is_support(f), f.flight_type.value)
    )
    return " · ".join(
        f"{f.count}× {short_aircraft_name(f)} {flight_role(f)}" for f in flights
    )


def sorties(package: Package) -> int:
    return sum(f.count for f in package.flights)


def title(package: Package) -> str:
    text = f"{package.package_description} — {package.target.name}"
    if package.custom_name:
        text += f" ({package.custom_name})"
    return text


def purpose(package: Package) -> str:
    info = getattr(package, "planning_info", None) or {}
    reason = str(info.get("reason", "") or "")
    return reason or f"{package.package_description} against {package.target.name}"


# ------------------------------------------------------------------- times


@dataclass(frozen=True)
class KeyTimes:
    startup: Optional[datetime] = None
    takeoff: Optional[datetime] = None
    tot: Optional[datetime] = None
    land: Optional[datetime] = None
    patrol: Optional[tuple[datetime, datetime]] = None


def _safe(get: Any) -> Optional[datetime]:
    try:
        value = get()
    except Exception:
        return None
    return value if isinstance(value, datetime) else None


def key_times(flight: Flight) -> KeyTimes:
    plan = flight.flight_plan
    patrol: Optional[tuple[datetime, datetime]] = None
    start = _safe(lambda: plan.patrol_start_time)
    end = _safe(lambda: plan.patrol_end_time)
    if start is not None and end is not None:
        patrol = (start, end)
    return KeyTimes(
        startup=_safe(plan.startup_time),
        takeoff=_safe(plan.takeoff_time),
        tot=_safe(lambda: plan.tot),
        land=_safe(lambda: plan.landing_time),
        patrol=patrol,
    )


def package_span(package: Package) -> tuple[Optional[datetime], Optional[datetime]]:
    starts: list[datetime] = []
    ends: list[datetime] = []
    for flight in package.flights:
        times = key_times(flight)
        if times.startup is not None:
            starts.append(times.startup)
        end = times.land or (times.patrol[1] if times.patrol else None) or times.tot
        if end is not None:
            ends.append(end)
    return (min(starts) if starts else None, max(ends) if ends else None)


def period_bounds(game: Game) -> tuple[datetime, datetime]:
    """The ATO period, or for legacy turns turn start to the last landing."""
    from game.sim import atoperiod

    bounds = atoperiod.period(game)
    if bounds is not None and not atoperiod.is_focused(game):
        return bounds
    if bounds is not None:
        # Focused turn: the lead-in, the mission, and the run-out after it
        # while flights finish their legs and land.
        start, end = bounds
        for coalition in (game.blue, game.red):
            for package in coalition.ato.packages:
                _, last = package_span(package)
                if last is not None and last > end:
                    end = last
        return start, end
    start = game.conditions.start_time
    end = start + game.settings.desired_player_mission_duration
    for coalition in (game.blue, game.red):
        for package in coalition.ato.packages:
            _, last = package_span(package)
            if last is not None and last > end:
                end = last
    return start, end


def offset_text(game: Game, when: datetime) -> str:
    """ "+1:25": time into the ATO period, or from mission start in a focused
    turn ("-0:10" is during the lead-in)."""
    from game.sim import atoperiod

    window = atoperiod.window(game) if atoperiod.is_focused(game) else None
    start = window[0] if window is not None else period_bounds(game)[0]
    minutes = int((when - start) / timedelta(minutes=1))
    sign = "-" if minutes < 0 else "+"
    minutes = abs(minutes)
    return f"{sign}{minutes // 60}:{minutes % 60:02d}"


def dcs_window(game: Game) -> Optional[tuple[datetime, datetime]]:
    from game.sim import atoperiod

    return atoperiod.window(game)


def in_dcs_window(game: Game, package: Package) -> Optional[bool]:
    """Whether the package flies in the DCS window; None without a period
    or in a focused turn (where the whole plan is the mission)."""
    from game.sim import atoperiod

    bounds = dcs_window(game)
    if bounds is None or atoperiod.is_focused(game):
        return None
    first, last = package_span(package)
    if first is None or last is None:
        return False
    return first < bounds[1] and last > bounds[0]


def fmt(when: Optional[datetime]) -> str:
    return f"{when:%H:%M}" if when is not None else "--:--"


def flight_times_text(flight: Flight) -> str:
    t = key_times(flight)
    parts = [f"Start {fmt(t.startup)}", f"T/O {fmt(t.takeoff)}"]
    if t.patrol is not None:
        parts.append(f"On station {fmt(t.patrol[0])}–{fmt(t.patrol[1])}")
    else:
        parts.append(f"TOT {fmt(t.tot)}")
    parts.append(f"Land {fmt(t.land)}")
    return " · ".join(parts)


# -------------------------------------------------------------------- risk


@dataclass(frozen=True)
class RiskBadge:
    estimate: float
    level: str
    limit: Optional[float] = None

    @property
    def color(self) -> str:
        return RISK_COLORS[self.level]

    @property
    def text(self) -> str:
        return f"{self.estimate:.1%}"


def risk_badge(package: Package) -> Optional[RiskBadge]:
    risk = getattr(package, "planning_risk", None)
    if not risk or "estimate" not in risk:
        return None
    estimate = float(risk["estimate"])
    level = (
        "low"
        if estimate < RISK_MEDIUM
        else "medium" if estimate < RISK_HIGH else "high"
    )
    limit = risk.get("limit")
    return RiskBadge(estimate, level, float(limit) if limit is not None else None)


# ----------------------------------------------------------------- tooltip


def package_tooltip(game: Game, package: Package) -> str:
    e = html.escape
    group = package_group(package)
    lines = [
        f"<b>{e(title(package))}</b>",
        f"<span style='color:{group.color}'>■</span> {e(group.label)}",
        f"<i>{e(purpose(package))}</i>",
        f"TOT {fmt(package.time_over_target)} ({offset_text(game, package.time_over_target)})",
    ]
    info = getattr(package, "planning_info", None) or {}
    if info.get("phase"):
        lines.append(f"Phase: {e(str(info['phase']))}")
    if info.get("threat"):
        lines.append(f"Threat: {e(str(info['threat']))}")
    badge = risk_badge(package)
    if badge is not None:
        limit = f" (limit {badge.limit:.1%})" if badge.limit is not None else ""
        lines.append(
            f"Estimated losses: <span style='color:{badge.color}'>{badge.text}</span>"
            f" per sortie{limit}"
        )
    for note in info.get("notes", []) or []:  # type: ignore[attr-defined]
        lines.append(e(str(note)))
    if not info and getattr(package, "planning_rationale", ""):
        lines.append(e(package.planning_rationale))
    window = in_dcs_window(game, package)
    if window is not None:
        lines.append(
            "Flies in the DCS window"
            if window
            else "Resolved by the combat model (outside the DCS window)"
        )
    lines.append("")
    for flight in package.flights:
        lines.append(
            f"<b>{flight.count}× {e(short_aircraft_name(flight))} {e(flight_role(flight))}</b>"
            f" from {e(flight.departure.name)}: {e(flight_times_text(flight))}"
        )
    return "<br/>".join(lines)


# ---------------------------------------------------------------- timeline


@dataclass
class Lane:
    group: Group
    label: str
    packages: list[Package] = field(default_factory=list)

    @property
    def first_start(self) -> datetime:
        starts = [s for s in (package_span(p)[0] for p in self.packages) if s]
        return min(starts) if starts else datetime.max


def _line_key(package: Package) -> Optional[tuple[Any, ...]]:
    task = package.primary_task
    if task not in LINE_TASKS:
        return None
    return (task, package.target.name)


def lanes(packages: Iterable[Package]) -> list[Lane]:
    """Timeline lanes: one per continuous line (same task and station, e.g. a
    CAP relief chain), one per other package; grouped and in time order."""
    by_key: dict[tuple[Any, ...], Lane] = {}
    result: list[Lane] = []
    for package in packages:
        group = package_group(package)
        key = _line_key(package)
        if key is not None and key in by_key:
            by_key[key].packages.append(package)
            continue
        task = package.primary_task
        label = (
            f"{task.value if task else 'Package'} — {package.target.name}"
            if key is not None
            else title(package)
        )
        lane = Lane(group, label, [package])
        if key is not None:
            by_key[key] = lane
        result.append(lane)
    for lane in result:
        lane.packages.sort(key=lambda p: p.time_over_target)
    result.sort(key=lambda lane: (GROUP_ORDER[lane.group.key], lane.first_start))
    return result
