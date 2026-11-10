"""The turn summary (F13, W5): what a side's plan for the turn is, in a few
lines.

Shown at the top of the ATO panel and in the DCS mission briefing: phase and
intent, the main push with its time and key packages, one line for what
flies before and after it, the routine lines counted in one line, and what
the enemy is expected to do as the side's own intelligence sees it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType

if TYPE_CHECKING:
    from game import Game
    from game.ato import Flight, Package

#: How many key packages the summary lists.
KEY_PACKAGES = 5


@dataclass
class KeyPackage:
    tot: datetime
    name: str
    reason: str
    players: bool


@dataclass
class TurnSummary:
    turn: int
    phase: str
    #: The mission window (mission only turns), or None.
    window: Optional[tuple[datetime, datetime]]
    intent: str
    key: list[KeyPackage] = field(default_factory=list)
    more_key: int = 0
    routine: list[str] = field(default_factory=list)
    #: What the enemy is expected to do, from the side's own intelligence
    #: (the threats line before W5).
    threats: list[str] = field(default_factory=list)
    #: The main push (full turns), or None.
    push: Optional[tuple[datetime, datetime]] = None
    #: One line each for what flies before and after the push ("" if nothing).
    before: str = ""
    after: str = ""

    @property
    def period_text(self) -> str:
        if self.push is not None:
            return f", main push {self.push[0]:%H:%M}-{self.push[1]:%H:%M}"
        if self.window is not None:
            return f", mission {self.window[0]:%H:%M}-{self.window[1]:%H:%M}"
        return ""

    @property
    def key_heading(self) -> str:
        return "Main push" if self.push is not None else "Key packages"

    @property
    def around_push(self) -> str:
        parts = [p for p in (self.before, self.after) if p]
        return " · ".join(parts)

    def as_text(self) -> str:
        """Plain text, for the DCS mission briefing."""
        lines = [f"Turn {self.turn}: {self.phase}{self.period_text}"]
        if self.intent:
            lines.append(self.intent)
        if self.key:
            lines.append(f"{self.key_heading}:")
            for package in self.key:
                you = " (you)" if package.players else ""
                lines.append(
                    f"  {package.tot:%H:%M} {package.name}{you}: {package.reason}"
                )
            if self.more_key:
                lines.append(f"  and {self.more_key} more")
        if self.around_push:
            lines.append(self.around_push)
        if self.routine:
            lines.append("Also: " + ", ".join(self.routine) + ".")
        if self.threats:
            lines.append("Enemy expected (our intelligence): " + ", ".join(self.threats) + ".")
        return "\n".join(lines)


def _default_name(package: Package) -> str:
    task = package.primary_task
    label = task.value if task is not None else "Package"
    return f"{label} {package.target.name}"


def _all(package: Package, test: Callable[[Flight], bool]) -> bool:
    return bool(package.flights) and all(test(f) for f in package.flights)


def turn_summary(
    game: Game,
    blue: bool = True,
    name_of: Callable[[Package], str] = _default_name,
) -> Optional[TurnSummary]:
    """The side's plan for this turn, or None when it doesn't plan with the
    air campaign planner."""
    from game.sim import atoperiod

    from .planner import counts_toward_target

    state = getattr(game, "air_campaign", None)
    side = state.maybe_side(blue) if state is not None else None
    if side is None or not side.history:
        return None
    coalition = game.blue if blue else game.red
    window = atoperiod.window(game) if atoperiod.is_focused(game) else None
    summary = TurnSummary(game.turn, side.phase_title, window, side.intent)
    push = getattr(side, "push", None)
    summary.push = push

    packages = list(coalition.ato.packages)
    counted = [p for p in packages if counts_toward_target(p)]
    key = [
        p
        for p in counted
        if p.has_players
        or any(f.flight_type is not FlightType.BARCAP for f in p.flights)
    ]

    def in_push(package: Package) -> bool:
        return push is not None and push[0] <= package.time_over_target < push[1]

    # Your flight first, then the main push, then the rest in TOT order.
    key.sort(key=lambda p: (not p.has_players, not in_push(p), p.time_over_target))
    if push is not None:
        summary.before = _around_push(
            "Before it", [p for p in key if p.time_over_target < push[0]]
        )
        summary.after = _around_push(
            "after it", [p for p in key if p.time_over_target >= push[1]]
        )
        key = [p for p in key if p.has_players or in_push(p)]
    for package in key[:KEY_PACKAGES]:
        info = package.planning_info or {}
        summary.key.append(
            KeyPackage(
                package.time_over_target,
                name_of(package),
                str(info.get("reason") or name_of(package)),
                bool(package.has_players),
            )
        )
    summary.more_key = max(0, len(key) - KEY_PACKAGES)

    def task_is(task: FlightType) -> Callable[[Flight], bool]:
        return lambda f: f.flight_type is task and not getattr(f, "returning", False)

    counts = {
        "CAP station": sum(
            1 for p in counted if _all(p, lambda f: f.flight_type is FlightType.BARCAP)
        ),
        "AWACS": sum(1 for p in packages if _all(p, task_is(FlightType.AEWC))),
        "tanker": sum(1 for p in packages if _all(p, task_is(FlightType.REFUELING))),
        "ground alert pair": sum(
            1 for p in packages if _all(p, lambda f: bool(getattr(f, "alert", False)))
        ),
        "CAP returning home": sum(
            1
            for p in packages
            if _all(p, lambda f: bool(getattr(f, "returning", False)))
        ),
    }
    for name, n in counts.items():
        if n:
            summary.routine.append(f"{n} {name}{'' if n == 1 else 's'}")

    summary.threats = expected_enemy(game, blue, side)
    return summary


def _around_push(label: str, packages: list[Package]) -> str:
    """ "Before it: 3 strike, 2 SEAD from 06:43"."""
    if not packages:
        return ""
    counts: dict[str, int] = {}
    for package in packages:
        task = package.primary_task
        name = task.value if task is not None else "package"
        counts[name] = counts.get(name, 0) + 1
    parts = ", ".join(f"{n} {name}" for name, n in counts.items())
    first = min(p.time_over_target for p in packages)
    return f"{label}: {parts} from {first:%H:%M}"


def expected_enemy(game: Game, blue: bool, side: Any) -> list[str]:
    """What the enemy is expected to do, from the side's own intelligence
    only: its fighter and SAM estimates, the sorties it saw last turn and
    the axes they came from. Never the enemy's real plan."""
    found: list[str] = []
    moes = side.moes or {}
    if moes.get("enemy_fighters"):
        found.append(f"about {moes['enemy_fighters']:.0f} enemy fighters")
    if moes.get("battle_area_sams"):
        found.append(f"{moes['battle_area_sams']:.0f} SAM sites near the front")
    if side.enemy_sorties_seen:
        found.append(f"{side.enemy_sorties_seen} enemy sorties seen last turn")
    try:
        from game.theater.player import Player

        from .observations import ObservationLog

        log = ObservationLog(side)
        player = Player.BLUE if blue else Player.RED
        axes = []
        for cp in game.theater.control_points_for(player):
            for axis in log.axes(cp, max_axes=1):
                axes.append((axis.mass, f"{axis.heading:03.0f} at {cp.name}"))
        axes.sort(key=lambda a: -a[0])
        if axes:
            found.append(
                "air activity from " + ", ".join(text for _, text in axes[:2])
            )
    except Exception:
        pass
    return found


# ====================================================================== debrief


@dataclass
class PackageResult:
    """How one key package went (F16)."""

    name: str
    goal: str
    players: bool
    flown: bool
    aircraft: int
    lost: int
    #: Enemy units destroyed at the package's target.
    target_hits: int
    target_destroyed: bool
    successes: int
    air_kills: int
    aborts: int

    @property
    def result(self) -> str:
        if not self.flown:
            return "not flown"
        parts = []
        if self.target_destroyed:
            parts.append("target destroyed")
        elif self.target_hits:
            parts.append(f"{self.target_hits} units hit at the target")
        elif self.successes:
            n = self.successes
            parts.append(f"{n} successful attack{'' if n == 1 else 's'}")
        if self.air_kills:
            n = self.air_kills
            parts.append(f"{n} air kill{'' if n == 1 else 's'}")
        if self.aborts and not parts:
            parts.append("aborted")
        if not parts:
            parts.append("no effect reported")
        if self.lost:
            parts.append(f"{self.lost} of {self.aircraft} aircraft lost")
        else:
            parts.append("all aircraft back")
        return ", ".join(parts)


@dataclass
class PlanDebrief:
    key: list[PackageResult] = field(default_factory=list)
    #: Routine lines (CAP stations, support), summed: "4 CAP stations: ...".
    routine: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.key and not self.routine


def _is_routine(package: Package) -> bool:
    from .planner import counts_toward_target

    if package.has_players:
        return False
    return not counts_toward_target(package) or all(
        f.flight_type in (FlightType.BARCAP, FlightType.TARCAP) for f in package.flights
    )


def plan_debrief(
    debriefing: object,
    blue: bool = True,
    name_of: Callable[[Package], str] = _default_name,
) -> PlanDebrief:
    """The side's packages this turn, key packages first, with what each
    achieved and lost, from the debriefing."""
    game = getattr(debriefing, "game")
    coalition = game.blue if blue else game.red

    # Packages: those still in the ATO plus any flown or lost whose flights
    # finished and were removed from it.
    packages: list[Package] = list(coalition.ato.packages)
    seen = {id(p) for p in packages}
    flown_flights = list(getattr(debriefing, "flights_flown", None) or [])
    air_losses = getattr(debriefing, "air_losses")
    losses = list(air_losses.player if blue else air_losses.enemy)
    credits = list(getattr(debriefing, "combat_credits", None) or [])
    for flight in (
        flown_flights + [l.flight for l in losses] + [c.flight for c in credits]
    ):
        package = getattr(flight, "package", None)
        if package is None or id(package) in seen:
            continue
        if flight.squadron.player.is_blue != blue:
            continue
        packages.append(package)
        seen.add(id(package))

    simulated = bool(getattr(debriefing, "simulated", False))
    flown = {id(getattr(f, "package", None)) for f in flown_flights}
    lost: dict[int, int] = {}
    for loss in losses:
        key = id(loss.flight.package)
        lost[key] = lost.get(key, 0) + 1
    credit: dict[tuple[int, str], int] = {}
    for c in credits:
        package = getattr(c.flight, "package", None)
        if package is None:
            continue
        k = (id(package), c.kind)
        credit[k] = credit.get(k, 0) + 1
    ground = getattr(debriefing, "ground_losses", None)
    enemy_objects = (
        (ground.enemy_ground_objects if blue else ground.player_ground_objects)
        if ground is not None
        else []
    )
    hits: dict[int, int] = {}
    for mapping in enemy_objects:
        unit = getattr(mapping, "theater_unit", None)
        tgo = getattr(unit, "ground_object", None)
        if tgo is not None:
            hits[id(tgo)] = hits.get(id(tgo), 0) + 1

    def result_of(package: Package) -> PackageResult:
        key = id(package)
        # A DCS mission flies everything; a simulated turn lists what flew.
        was_flown = (
            not simulated
            or key in flown
            or key in lost
            or any(k[0] == key for k in credit)
        )
        target = package.target
        aircraft = sum(
            f.count
            for f in package.flights
            if not (
                getattr(f, "alert", False) and not getattr(f, "alert_released", False)
            )
        )
        info = package.planning_info or {}
        return PackageResult(
            name=name_of(package),
            goal=str(info.get("reason") or name_of(package)),
            players=bool(package.has_players),
            flown=was_flown,
            aircraft=aircraft,
            lost=lost.get(key, 0),
            target_hits=hits.get(id(target), 0),
            target_destroyed=bool(hits.get(id(target)))
            and bool(getattr(target, "is_dead", False)),
            successes=credit.get((key, "strike_success"), 0)
            + credit.get((key, "cas_kill"), 0)
            + credit.get((key, "arm_attack"), 0),
            air_kills=credit.get((key, "air_kill"), 0),
            aborts=credit.get((key, "abort"), 0),
        )

    debrief = PlanDebrief()
    key_packages = [p for p in packages if not _is_routine(p)]
    key_packages.sort(key=lambda p: (not p.has_players, p.time_over_target))
    debrief.key = [result_of(p) for p in key_packages]

    groups: dict[str, list[PackageResult]] = {}
    for package in packages:
        if not _is_routine(package):
            continue
        if all(
            getattr(f, "alert", False) and not getattr(f, "alert_released", False)
            for f in package.flights
        ):
            continue  # Alerts never scrambled didn't fly.
        task = package.primary_task
        labels = {
            FlightType.BARCAP: "CAP station",
            FlightType.TARCAP: "CAP station",
            FlightType.AEWC: "AWACS",
            FlightType.REFUELING: "tanker",
        }
        label = "other" if task is None else labels.get(task, task.value)
        groups.setdefault(label, []).append(result_of(package))
    for label, results in groups.items():
        n = len(results)
        lost_total = sum(r.lost for r in results)
        kills = sum(r.air_kills for r in results)
        text = f"{n} {label}{'' if n == 1 else 's'}: "
        text += f"{lost_total} aircraft lost" if lost_total else "no losses"
        if kills:
            text += f", {kills} air kill{'' if kills == 1 else 's'}"
        debrief.routine.append(text)
    return debrief
