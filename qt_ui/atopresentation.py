"""How packages and flights are presented in the ATO sidebar and timeline.

Qt-free so it can be unit tested: groups and colours (hex strings), short
composition strings, flight roles, key times, offsets into the ATO period,
risk badges, tooltips, timeline lanes and the folds that keep a 6 hour plan
to one screen (each routine line one row, the main push open, the other
waves one row per category).
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
    if task in (FlightType.CSAR, FlightType.RESCUE_KING):
        # The King's C-130 stages the rescue helicopters: it belongs with them.
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


def row_sort_key(
    package: Package, fold: Optional[Fold]
) -> tuple[int, datetime, str, int, datetime]:
    """The package list's order: by group, then by TOT, except that a fold's
    packages all sort at its first package's TOT, in fold order, so an opened
    fold's packages come straight under its first row instead of spreading
    out among the others."""
    group, tot = sort_key(package)
    if fold is None:
        return group, tot, "", 0, tot
    first = fold.representative.time_over_target
    position = next(i for i, p in enumerate(fold.packages) if p is package)
    return group, first, fold.key, position, tot


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


def bubble_preview(game: Game) -> Any:
    """The bubble the mission will have (game.sim.bubble.preview), or None."""
    from game.sim import bubble

    if game is None:
        return None
    return bubble.preview(game)


def elsewhere_ids(game: Game) -> set[int]:
    from game.sim import bubble

    if game is None:
        return set()
    return bubble.elsewhere_ids(game)


def bubble_text(game: Game) -> Optional[str]:
    """One line for the Your flight card: what the mission will hold."""
    preview = bubble_preview(game)
    if preview is None:
        return None
    blue_in, red_in = len(preview.packages(True)), len(preview.packages(False))
    out = len(preview.packages(True, False)) + len(preview.packages(False, False))
    return (
        f"In your mission: {blue_in} friendly and {red_in} enemy packages, "
        f"{preview.aircraft()} aircraft. {out} elsewhere, fought by the combat model."
    )


def bubble_html(game: Game) -> Optional[str]:
    """The bubble, package by package with its reason (B6)."""
    preview = bubble_preview(game)
    if preview is None:
        return None
    e = html.escape
    out = []
    for blue in (True, False):
        side = "Friendly" if blue else "Enemy"
        for inside, heading in ((True, "in your mission"), (False, "elsewhere")):
            packages = sorted(
                preview.packages(blue, inside), key=lambda p: p.time_over_target
            )
            out.append(f"<h3>{side} packages {heading} ({len(packages)})</h3>")
            if not packages:
                out.append("<p><i>None.</i></p>")
                continue
            out.append("<ul>")
            for package in packages:
                out.append(
                    f"<li><b>{e(title(package))}</b> TOT "
                    f"{fmt(package.time_over_target)}: {e(preview.reason(package))}</li>"
                )
            out.append("</ul>")
    return "".join(out)


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
    preview = bubble_preview(game)
    inside = preview.in_mission(package) if preview is not None else None
    if inside is not None:
        reason = e(preview.reason(package))  # type: ignore[union-attr]
        lines.append(
            f"In your mission: {reason}"
            if inside
            else f"Elsewhere, fought by the combat model: {reason}"
        )
    elif window is not None:
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


# ------------------------------------------------------------------- folds


@dataclass
class Fold:
    """Packages shown as one row until opened (W4): a routine line with its
    reliefs, or the packages of a category before or after the main push."""

    key: str
    label: str
    packages: list[Package] = field(default_factory=list)

    @property
    def representative(self) -> Package:
        return self.packages[0]

    @property
    def count(self) -> int:
        return len(self.packages)

    @property
    def sorties(self) -> int:
        return sum(sorties(p) for p in self.packages)

    @property
    def span_text(self) -> str:
        tots = [p.time_over_target for p in self.packages]
        return f"{fmt(min(tots))}–{fmt(max(tots))}"

    def summary(self) -> str:
        n = self.count
        return f"{n} package{'' if n == 1 else 's'} · {self.sorties} sorties · {self.span_text}"


def main_push(game: Game, blue: bool = True) -> Optional[tuple[datetime, datetime]]:
    """The side's main push this turn (game.commander.jfacc), or None."""
    state = getattr(game, "air_campaign", None)
    side = state.maybe_side(blue) if state is not None else None
    if side is None:
        return None
    return getattr(side, "push", None)


def fold_key(
    package: Package,
    push: Optional[tuple[datetime, datetime]],
    elsewhere: Optional[set[int]] = None,
) -> Optional[tuple[str, str]]:
    """The fold a package belongs to, as (key, label), or None when it
    stands on its own: a package with players, or one in the main push.
    Packages outside the bubble (M3, ``elsewhere``) fold by group."""
    if package.has_players:
        return None
    line = _line_key(package)
    if line is not None:
        task, name = line
        return f"line:{task.value}:{name}", f"{task.value} — {name}"
    if elsewhere and id(package) in elsewhere:
        group = package_group(package)
        return f"elsewhere:{group.key}", f"{group.label} elsewhere (combat model)"
    if push is None:
        return None
    tot = package.time_over_target
    if push[0] <= tot < push[1]:
        return None
    group = package_group(package)
    side = "before" if tot < push[0] else "after"
    return f"wave:{group.key}:{side}", f"{group.label} {side} the main push"


def folds(
    packages: Iterable[Package],
    push: Optional[tuple[datetime, datetime]],
    elsewhere: Optional[set[int]] = None,
) -> dict[int, Fold]:
    """id(package) -> its fold, for every package in a fold of two or more.
    The fold's packages are in TOT order; the first is its representative
    row."""
    by_key: dict[str, Fold] = {}
    for package in packages:
        found = fold_key(package, push, elsewhere)
        if found is None:
            continue
        key, label = found
        by_key.setdefault(key, Fold(key, label)).packages.append(package)
    result: dict[int, Fold] = {}
    for fold in by_key.values():
        if fold.count < 2:
            continue
        fold.packages.sort(key=lambda p: p.time_over_target)
        for package in fold.packages:
            result[id(package)] = fold
    return result


def folded_rows(
    packages: Iterable[Package],
    push: Optional[tuple[datetime, datetime]],
    elsewhere: Optional[set[int]] = None,
) -> int:
    """How many rows the list shows with every fold closed."""
    packages = list(packages)
    table = folds(packages, push, elsewhere)
    rows = 0
    seen: set[str] = set()
    for package in packages:
        fold = table.get(id(package))
        if fold is None:
            rows += 1
        elif fold.key not in seen:
            seen.add(fold.key)
            rows += 1
    return rows


# ------------------------------------------------------------- turn briefing


def turn_briefing(game: Game, blue: bool = True) -> Optional[str]:
    """The turn summary (game.commander.jfacc.briefing) as HTML for the ATO
    panel, or None when the side doesn't use the air campaign planner."""
    from html import escape as e

    from game.commander.jfacc.briefing import turn_summary

    summary = turn_summary(game, blue, name_of=title)
    if summary is None:
        return None
    when = e(summary.period_text).replace(", ", " · ", 1)
    lines = [f"<b>Turn {summary.turn}: {e(summary.phase)}</b>{when}"]
    if blue:
        # Turn 1 opens with the opening estimate and the BDA (game.opening).
        from game.opening import turn_one_lines

        opening = turn_one_lines(game)
        if opening:
            lines.append("<b>The opening</b>")
            lines.extend(
                ("&nbsp;&nbsp;" + e(l.strip())) if l.startswith("  ") else e(l)
                for l in opening
            )
    if summary.intent:
        lines.append(e(summary.intent))
    if summary.key:
        lines.append(f"<b>{summary.key_heading}</b>")
        for package in summary.key:
            you = " (you)" if package.players else ""
            lines.append(
                f"&nbsp;&nbsp;{fmt(package.tot)} {e(package.name)}{you}: "
                f"{e(package.reason)}"
            )
        if summary.more_key:
            lines.append(f"&nbsp;&nbsp;and {summary.more_key} more")
    if summary.around_push:
        lines.append(e(summary.around_push))
    if summary.routine:
        lines.append("Also: " + ", ".join(summary.routine) + ".")
    if summary.threats:
        lines.append(
            "Enemy expected (our intelligence): " + e(", ".join(summary.threats)) + "."
        )
    return "<br>".join(lines)


# ------------------------------------------------------------------ debrief (F16)


def plan_debrief_html(debriefing: object, blue: bool = True) -> Optional[str]:
    """How the side's plan went (game.commander.jfacc.briefing.plan_debrief)
    as HTML for the debriefing window, or None when there's nothing to say."""
    from html import escape as e

    from game.commander.jfacc.briefing import plan_debrief

    debrief = plan_debrief(debriefing, blue, name_of=title)
    if debrief.empty:
        return None

    def package_lines(results: list[Any]) -> list[str]:
        found = []
        for result in results:
            you = " (you)" if result.players else ""
            colour = (
                "#c0392b" if result.lost else ("#7f8c8d" if not result.flown else "")
            )
            outcome = e(result.result)
            if colour:
                outcome = f'<span style="color:{colour}">{outcome}</span>'
            found.append(
                f"<b>{e(result.name)}</b>{you}<br>"
                f"&nbsp;&nbsp;Goal: {e(result.goal)}<br>"
                f"&nbsp;&nbsp;Result: {outcome}"
            )
        return found

    lines: list[str] = []
    parts = [p for p in debrief.parts if not p.empty]
    if len(parts) <= 1:
        lines += package_lines(debrief.key)
        if debrief.routine:
            lines.append("Also: " + "; ".join(e(r) for r in debrief.routine) + ".")
        return "<br>".join(lines)
    # The turn by part (W6): the mission first, then before and after it.
    ordered = sorted(
        parts, key=lambda p: (p.simulated, p.span[0] if p.span else datetime.min)
    )
    for part in ordered:
        lines.append(f"<b><u>{e(part.title)}</u></b>")
        lines += package_lines(part.key)
        if part.routine:
            lines.append("Also: " + "; ".join(e(r) for r in part.routine) + ".")
    return "<br>".join(lines)
