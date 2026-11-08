"""After-action report built from a debriefing."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from game.sim.aftaction import AfterActionReport, crew_fate
from game.sim.combat.model.aircrew import AirLossDetail, LossCause
from game.sim.combatlog import CombatDomain, CombatLogEntry
from game.squadrons.pilot import Pilot, PilotStatus
from game.theater.player import Player


def _flight(player: Player, unit: str) -> Any:
    return SimpleNamespace(squadron=SimpleNamespace(player=player), unit_type=unit)


def _counts(aircraft: int, front_line: int) -> Any:
    return SimpleNamespace(
        aircraft=aircraft,
        front_line=front_line,
        ground_objects=0,
        convoy=0,
        cargo_ships=0,
        runways_destroyed=0,
    )


def _debriefing() -> Any:
    killed = Pilot("A")
    killed.status = PilotStatus.Dead
    captured = Pilot("B")
    captured.status = PilotStatus.MissingInAction
    f16 = _flight(Player.BLUE, "F-16C")
    details = [
        AirLossDetail(f16, killed, None, 6000, LossCause.SAM, "SA-10", False),
        AirLossDetail(f16, captured, None, 100, LossCause.AAA, "ZSU-23", False),
    ]
    origin = SimpleNamespace(name="Gudauta")
    time = datetime(2004, 1, 7, 14, 20)
    return SimpleNamespace(
        loss_counts=lambda p: _counts(2, 3) if p.is_blue else _counts(0, 1),
        air_loss_details=details,
        air_losses=SimpleNamespace(
            player=[SimpleNamespace(pilot=killed), SimpleNamespace(pilot=captured)],
            enemy=[],
        ),
        ground_losses=SimpleNamespace(
            player_front_line=[SimpleNamespace(origin=origin)] * 3,
            enemy_front_line=[SimpleNamespace(origin=SimpleNamespace(name="Sochi"))],
        ),
        combat_credits=[SimpleNamespace(flight=f16, kind="air_kill")],
        intel_events=[],
        simulation_log=[
            CombatLogEntry(
                time,
                CombatDomain.GROUND,
                "blue",
                "Front: the blue attack culminates after losing 17 of 51 vehicles",
            ),
            CombatLogEntry(
                time, CombatDomain.AIR, "red", "Flight is at bingo fuel and breaks off"
            ),
        ],
    )


def test_report_counts_causes_crews_and_events() -> None:
    report = AfterActionReport.from_debriefing(_debriefing())
    assert report.blue.aircraft_lost == 2
    assert report.blue.aircraft_by_cause == {
        "surface-to-air missile": 1,
        "anti-aircraft artillery": 1,
    }
    assert report.blue.crew == {"killed": 1, "captured": 1}
    assert report.blue.front_line_by_base == {"Gudauta": 3}
    assert report.blue.air_kills == 1
    assert report.red.bingo_breakoffs == 1
    assert report.events and report.events[0][0] == "Front line"
    text = report.to_text()
    assert "Aircraft lost: 2" in text and "Front-line vehicles lost: 3" in text
    assert "<b" in report.to_html()


def test_crew_fates() -> None:
    pilot = Pilot("C")
    assert crew_fate(pilot) == "recovered"
    pilot.status = PilotStatus.Downed
    assert crew_fate(pilot) == "awaiting rescue"
