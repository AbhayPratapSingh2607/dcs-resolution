"""ATO sidebar and timeline presentation helpers (qt_ui.atopresentation)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from game.ato.flighttype import FlightType
from game.commander.jfacc.campaignstate import AirCampaignState
from qt_ui import atopresentation as ap

START = datetime(2020, 6, 1, 6, 0)


class _Plan:
    def __init__(
        self,
        startup: int,
        takeoff: int,
        tot: int,
        land: Optional[int],
        patrol: Optional[tuple[int, int]] = None,
    ) -> None:
        self._startup = START + timedelta(minutes=startup)
        self._takeoff = START + timedelta(minutes=takeoff)
        self.tot = START + timedelta(minutes=tot)
        self._land = None if land is None else START + timedelta(minutes=land)
        if patrol is not None:
            self.patrol_start_time = START + timedelta(minutes=patrol[0])
            self.patrol_end_time = START + timedelta(minutes=patrol[1])

    def startup_time(self) -> datetime:
        return self._startup

    def takeoff_time(self) -> datetime:
        return self._takeoff

    @property
    def landing_time(self) -> datetime:
        if self._land is None:
            raise NotImplementedError
        return self._land


def _flight(
    task: FlightType, count: int, name: str, plan: Any, jammer: bool = False
) -> Any:
    return SimpleNamespace(
        flight_type=task,
        count=count,
        unit_type=SimpleNamespace(display_name=name, has_built_in_jamming=jammer),
        flight_plan=plan,
        departure=SimpleNamespace(name="Kutaisi"),
        package=None,
    )


class _Package:
    def __init__(
        self, task: FlightType, target: str, *flights: Any, tot: int = 60
    ) -> None:
        self.flights = list(flights)
        for f in self.flights:
            f.package = self
        self._task = task
        self.target = SimpleNamespace(name=target)
        self.time_over_target = START + timedelta(minutes=tot)
        self.custom_name = None
        self.package_description = task.value
        self.planning_info: Optional[dict[str, Any]] = None
        self.planning_risk: Optional[dict[str, float]] = None
        self.planning_rationale = ""

    @property
    def primary_task(self) -> FlightType:
        return self._task

    @property
    def primary_flight(self) -> Any:
        return next((f for f in self.flights if f.flight_type is self._task), None)


def _game(*blue: _Package) -> Any:
    state = AirCampaignState()
    state.note_period(1, START, START + timedelta(hours=6))
    coalition = lambda packages: SimpleNamespace(  # noqa: E731
        ato=SimpleNamespace(packages=list(packages)),
        player=SimpleNamespace(is_blue=True),
    )
    return SimpleNamespace(
        turn=1,
        air_campaign=state,
        blue=coalition(blue),
        red=coalition([]),
        conditions=SimpleNamespace(start_time=START),
        settings=SimpleNamespace(desired_player_mission_duration=timedelta(minutes=60)),
    )


@pytest.mark.parametrize(
    "task,group",
    [
        (FlightType.BARCAP, "dca"),
        (FlightType.AEWC, "support"),
        (FlightType.REFUELING, "support"),
        (FlightType.RECOVERY, "support"),
        (FlightType.OCA_RUNWAY, "oca"),
        (FlightType.SWEEP, "oca"),
        (FlightType.DEAD, "sead"),
        (FlightType.STRIKE, "strike"),
        (FlightType.BAI, "interdiction"),
        (FlightType.CAS, "cas"),
        (FlightType.CSAR, "pr"),
        (FlightType.AIR_ASSAULT, "lift"),
        (FlightType.TRANSPORT, "lift"),
        (FlightType.FERRY, "lift"),
    ],
)
def test_package_groups(task: FlightType, group: str) -> None:
    package = _Package(
        task, "X", _flight(task, 2, "F-16CM Fighting Falcon", _Plan(0, 10, 60, 90))
    )
    assert ap.package_group(package).key == group  # type: ignore[arg-type]


def test_composition_lists_main_flights_first() -> None:
    plan = _Plan(0, 10, 60, 90)
    package = _Package(
        FlightType.STRIKE,
        "Bridge",
        _flight(FlightType.SEAD_ESCORT, 2, "F-16CM Fighting Falcon (Block 50)", plan),
        _flight(FlightType.STRIKE, 4, "F-15E Strike Eagle (Suite 4+)", plan),
        _flight(FlightType.ESCORT, 2, "EA-18G Growler", plan, jammer=True),
    )
    text = ap.composition(package)  # type: ignore[arg-type]
    assert text.startswith("4× F-15E Strike")
    assert "2× F-16CM SEAD" in text
    assert "2× EA-18G Jammer" in text
    assert ap.sorties(package) == 8  # type: ignore[arg-type]


def test_key_times_survive_plans_without_landing_time() -> None:
    flight = _flight(FlightType.STRIKE, 2, "A-10C", _Plan(0, 12, 50, None))
    times = ap.key_times(flight)
    assert times.land is None
    assert times.takeoff == START + timedelta(minutes=12)
    assert "Land --:--" in ap.flight_times_text(flight)


def test_patrol_window_is_reported() -> None:
    flight = _flight(
        FlightType.BARCAP, 2, "F-16CM", _Plan(0, 10, 30, 120, patrol=(30, 100))
    )
    assert "On station 06:30–07:40" in ap.flight_times_text(flight)


def test_offsets_and_dcs_window() -> None:
    early = _Package(
        FlightType.STRIKE,
        "A",
        _flight(FlightType.STRIKE, 2, "F-15E", _Plan(0, 10, 40, 70)),
    )
    late = _Package(
        FlightType.STRIKE,
        "B",
        _flight(FlightType.STRIKE, 2, "F-15E", _Plan(200, 210, 250, 290)),
        tot=250,
    )
    game = _game(early, late)
    assert ap.offset_text(game, START + timedelta(minutes=85)) == "+1:25"
    game.air_campaign.window_offset_min = 180
    assert ap.in_dcs_window(game, late) is True  # type: ignore[arg-type]
    assert ap.in_dcs_window(game, early) is False  # type: ignore[arg-type]


def test_risk_badges() -> None:
    package = _Package(
        FlightType.STRIKE,
        "A",
        _flight(FlightType.STRIKE, 2, "F-15E", _Plan(0, 10, 40, 70)),
    )
    assert ap.risk_badge(package) is None  # type: ignore[arg-type]
    for estimate, level in ((0.01, "low"), (0.03, "medium"), (0.09, "high")):
        package.planning_risk = {"estimate": estimate, "limit": 0.03}
        badge = ap.risk_badge(package)  # type: ignore[arg-type]
        assert badge is not None and badge.level == level and badge.limit == 0.03


def test_tooltip_uses_structured_info() -> None:
    package = _Package(
        FlightType.DEAD,
        "SA-11 Krymsk",
        _flight(FlightType.DEAD, 4, "F-16CM", _Plan(0, 10, 40, 70)),
    )
    package.planning_info = {
        "phase": "Phase II",
        "reason": "Roll back the IADS",
        "threat": "high",
        "notes": [],
    }
    package.planning_risk = {"estimate": 0.04}
    text = ap.package_tooltip(_game(package), package)  # type: ignore[arg-type]
    assert "Roll back the IADS" in text and "Phase II" in text and "4.0%" in text


def test_relief_chains_share_a_lane() -> None:
    plan = lambda a: _Plan(a, a + 10, a + 30, a + 100)  # noqa: E731
    cap1 = _Package(
        FlightType.BARCAP,
        "Axis 045",
        _flight(FlightType.BARCAP, 2, "F-16CM", plan(0)),
        tot=30,
    )
    cap2 = _Package(
        FlightType.BARCAP,
        "Axis 045",
        _flight(FlightType.BARCAP, 2, "F-16CM", plan(60)),
        tot=90,
    )
    other_cap = _Package(
        FlightType.BARCAP,
        "Axis 300",
        _flight(FlightType.BARCAP, 2, "F-16CM", plan(0)),
        tot=30,
    )
    strike1 = _Package(
        FlightType.STRIKE, "Bridge", _flight(FlightType.STRIKE, 4, "F-15E", plan(20))
    )
    strike2 = _Package(
        FlightType.STRIKE, "Bridge", _flight(FlightType.STRIKE, 4, "F-15E", plan(120))
    )
    result = ap.lanes([strike1, cap2, other_cap, cap1, strike2])  # type: ignore[list-item]
    assert [lane.group.key for lane in result] == ["dca", "dca", "strike", "strike"]
    first = result[0]
    assert first.packages == [cap1, cap2]
    # Strikes are not lines: one lane each, even against the same target.
    assert len([lane for lane in result if lane.group.key == "strike"]) == 2


def test_focused_turn_counts_from_mission_start_and_shows_the_run_out() -> None:
    package = _Package(
        FlightType.STRIKE,
        "A",
        _flight(FlightType.STRIKE, 2, "F-15E", _Plan(0, 10, 50, 130)),
    )
    game = _game(package)
    game.air_campaign = AirCampaignState()
    game.air_campaign.note_period(1, START, START + timedelta(minutes=90), 30)
    # Offsets from mission start; the lead-in is negative.
    assert ap.offset_text(game, START + timedelta(minutes=50)) == "+0:20"
    assert ap.offset_text(game, START + timedelta(minutes=10)) == "-0:20"
    # The whole plan is the mission: no DCS badge, nothing dimmed.
    assert ap.in_dcs_window(game, package) is None  # type: ignore[arg-type]
    # The timeline runs on past the window until the last landing.
    assert ap.period_bounds(game) == (START, START + timedelta(minutes=130))
