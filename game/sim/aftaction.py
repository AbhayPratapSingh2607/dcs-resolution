"""After-action report for a turn resolved by the fast-forward combat model.

Built from a committed Debriefing, so pilot fates (killed, downed awaiting
rescue, captured, recovered) are already settled. The same report is shown in
the debriefing window and printed by resources/tools/campaign_e2e.py.
"""

from __future__ import annotations

import html
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, TYPE_CHECKING

from game.theater.player import Player

if TYPE_CHECKING:
    from game.debriefing import Debriefing

#: Log lines worth calling out, and the heading they go under.
KEY_EVENTS = (
    ("line breaks", "Front line"),
    ("attack culminates", "Front line"),
    ("lost: flights relying", "Tanker lost"),
    ("short of fuel", "Fuel"),
    ("finds nothing left", "Strike"),
    ("decoy", "Deception"),
)


@dataclass
class SideReport:
    name: str
    aircraft_lost: int = 0
    aircraft_by_cause: Counter[str] = field(default_factory=Counter)
    aircraft_by_type: Counter[str] = field(default_factory=Counter)
    crew: Counter[str] = field(default_factory=Counter)
    front_line_lost: int = 0
    front_line_by_base: Counter[str] = field(default_factory=Counter)
    ground_objects_lost: int = 0
    convoy_lost: int = 0
    cargo_ships_lost: int = 0
    runways_hit: int = 0
    air_kills: int = 0
    strikes_hit: int = 0
    aborts: int = 0
    bingo_breakoffs: int = 0
    intel_by_source: Counter[str] = field(default_factory=Counter)


@dataclass
class AfterActionReport:
    blue: SideReport
    red: SideReport
    events: list[tuple[str, str]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (
            self.events
            or self.blue.aircraft_lost
            or self.red.aircraft_lost
            or self.blue.front_line_lost
            or self.red.front_line_lost
            or self.blue.ground_objects_lost
            or self.red.ground_objects_lost
        )

    # ------------------------------------------------------------------ build

    @classmethod
    def from_debriefing(cls, debriefing: Debriefing) -> AfterActionReport:
        blue = SideReport("Blue")
        red = SideReport("Red")
        sides = {True: blue, False: red}

        for player, side in ((Player.BLUE, blue), (Player.RED, red)):
            counts = debriefing.loss_counts(player)
            side.aircraft_lost = counts.aircraft
            side.front_line_lost = counts.front_line
            side.ground_objects_lost = counts.ground_objects
            side.convoy_lost = counts.convoy
            side.cargo_ships_lost = counts.cargo_ships
            side.runways_hit = counts.runways_destroyed

        detailed: set[int] = set()
        for detail in getattr(debriefing, "air_loss_details", []):
            side = sides[detail.flight.squadron.player.is_blue]
            side.aircraft_by_cause[detail.cause.value] += 1
            side.aircraft_by_type[str(detail.flight.unit_type)] += 1
            if detail.pilot is not None:
                detailed.add(id(detail.pilot))
                side.crew[crew_fate(detail.pilot)] += 1
        # Losses from DCS itself (a flown mission) have no cause.
        for losses, side in (
            (debriefing.air_losses.player, blue),
            (debriefing.air_losses.enemy, red),
        ):
            for loss in losses:
                pilot = getattr(loss, "pilot", None)
                if pilot is not None and id(pilot) in detailed:
                    continue
                side.aircraft_by_cause["in the mission"] += 1
                side.aircraft_by_type[str(loss.flight.unit_type)] += 1
                if pilot is not None:
                    side.crew[crew_fate(pilot)] += 1

        for unit in debriefing.ground_losses.player_front_line:
            blue.front_line_by_base[unit.origin.name] += 1
        for unit in debriefing.ground_losses.enemy_front_line:
            red.front_line_by_base[unit.origin.name] += 1

        for credit in getattr(debriefing, "combat_credits", []):
            side = sides[credit.flight.squadron.player.is_blue]
            if credit.kind == "air_kill":
                side.air_kills += 1
            elif credit.kind == "strike_success":
                side.strikes_hit += 1
            elif credit.kind == "abort":
                side.aborts += 1

        for event in getattr(debriefing, "intel_events", []):
            sides[event.observer_blue].intel_by_source[event.source.value] += 1

        events: list[tuple[str, str]] = []
        for entry in getattr(debriefing, "simulation_log", []):
            text = entry.text
            if "bingo fuel" in text and entry.side in ("blue", "red"):
                sides[entry.side == "blue"].bingo_breakoffs += 1
                continue
            for needle, heading in KEY_EVENTS:
                if needle in text:
                    side_label = f"[{entry.side}] " if entry.side else ""
                    events.append((heading, f"{entry.time:%H:%M} {side_label}{text}"))
                    break
        return cls(blue, red, events)

    # ------------------------------------------------------------------ render

    def to_text(self) -> str:
        lines: list[str] = []
        for side in (self.blue, self.red):
            lines.append(f"{side.name}:")
            lines.extend("  " + line for line in _side_lines(side))
        if self.events:
            lines.append("Key events:")
            lines.extend(f"  {heading}: {text}" for heading, text in self.events)
        return "\n".join(lines)

    def to_html(self) -> str:
        parts: list[str] = []
        for side in (self.blue, self.red):
            colour = "#4a90d9" if side is self.blue else "#d9534f"
            parts.append(f"<p><b style='color:{colour}'>{side.name}</b><br/>")
            parts.append("<br/>".join(html.escape(l) for l in _side_lines(side)))
            parts.append("</p>")
        if self.events:
            parts.append("<p><b>Key events</b><br/>")
            parts.append(
                "<br/>".join(
                    f"<i>{html.escape(heading)}:</i> {html.escape(text)}"
                    for heading, text in self.events
                )
            )
            parts.append("</p>")
        return "".join(parts)


def crew_fate(pilot: Any) -> str:
    """killed | awaiting rescue | captured | recovered"""
    status = getattr(getattr(pilot, "status", None), "name", "")
    if status == "Dead":
        return "killed"
    if status == "Downed":
        return "awaiting rescue"
    if status == "MissingInAction":
        return "captured"
    return "recovered"


def _counter(counter: Counter[str]) -> str:
    return ", ".join(f"{n} {k}" for k, n in counter.most_common())


def _side_lines(side: SideReport) -> Iterable[str]:
    if side.aircraft_lost:
        yield f"Aircraft lost: {side.aircraft_lost} ({_counter(side.aircraft_by_cause)})"
        yield f"  Types: {_counter(side.aircraft_by_type)}"
        if side.crew:
            yield f"  Crews: {_counter(side.crew)}"
    else:
        yield "Aircraft lost: none"
    if side.front_line_lost:
        yield (
            f"Front-line vehicles lost: {side.front_line_lost} "
            f"({_counter(side.front_line_by_base)})"
        )
    other = []
    if side.ground_objects_lost:
        other.append(f"{side.ground_objects_lost} site units")
    if side.convoy_lost:
        other.append(f"{side.convoy_lost} convoy vehicles")
    if side.cargo_ships_lost:
        other.append(f"{side.cargo_ships_lost} cargo ships")
    if side.runways_hit:
        other.append(f"{side.runways_hit} runways")
    if other:
        yield "Other losses: " + ", ".join(other)
    achievements = []
    if side.air_kills:
        achievements.append(f"{side.air_kills} air kills")
    if side.strikes_hit:
        achievements.append(f"{side.strikes_hit} successful strikes")
    if side.aborts:
        achievements.append(f"{side.aborts} aborted")
    if side.bingo_breakoffs:
        achievements.append(f"{side.bingo_breakoffs} broke off at bingo fuel")
    if achievements:
        yield "Flights: " + ", ".join(achievements)
    if side.intel_by_source:
        yield f"Intel reports: {_counter(side.intel_by_source)}"
