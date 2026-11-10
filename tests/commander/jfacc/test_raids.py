"""Massed, echeloned raids (game/commander/jfacc/raids.py), with a fake
planner: echelon timing, all-or-nothing release, and which profiles raid."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from game.ato.flighttype import FlightType
from game.commander.jfacc.apportionment import Apportionment
from game.commander.jfacc.composer import ComposedPackage, FlightRequest, PackageRequest
from game.commander.jfacc.profile import Category, TargetSystem, load_profile
from game.commander.jfacc.raids import RaidPlanner
from game.commander.jfacc.scheduler import Timeline
from game.commander.jfacc.targets import TargetNomination
from game.commander.jfacc.threat import RouteThreat

START = datetime(2020, 6, 1, 6, 0)


class _Point:
    def __init__(self, x: float) -> None:
        self.x = x
        self.y = 0.0

    def distance_to_point(self, other: Any) -> float:
        return abs(self.x - other.x)


def _target(name: str, x: float) -> Any:
    return SimpleNamespace(name=name, id=name, position=_Point(x), task=None)


class _Ato:
    def __init__(self) -> None:
        self.packages: list[Any] = []

    def remove_package(self, package: Any) -> None:
        self.packages.remove(package)


class FakePlanner:
    def __init__(self, profile_name: str, fail_main: bool = False) -> None:
        self.profile = load_profile(profile_name)
        assert self.profile is not None
        phase = self.profile.phase("initial_air_operation") or self.profile.start_phase
        self.spec = self.profile.phases[phase]
        self.game = SimpleNamespace(turn=3)
        self.timeline = Timeline(self.profile, START, START + timedelta(hours=6))
        self.apportionment = Apportionment.for_phase(self.profile, self.spec, 200)
        self.planned_keys: set[str] = set()
        self.suppressed: dict[object, datetime] = {}
        self.released: list[Any] = []
        self.ledger = SimpleNamespace(release=self.released.append)
        self.coalition = SimpleNamespace(
            ato=_Ato(),
            air_wing=SimpleNamespace(can_auto_plan=lambda task: True),
        )
        self.sams = [_target("SA-11", 50_000), _target("SA-10", 80_000)]
        self.composer = SimpleNamespace(
            threat_for=lambda target, exclude=None, suppressed=None: RouteThreat(
                sam_weight=5, sams=list(self.sams), air_level="medium", target_defended=True
            ),
            support_for=lambda threat, n: [FlightRequest(FlightType.ESCORT, 2)],
        )
        self.fail_main = fail_main
        self.commits: list[tuple[str, datetime]] = []
        self.marked: list[str] = []
        self.target = _target("Krymsk airbase", 100_000)
        self.nominations = [
            TargetNomination(
                target=self.target,
                key="cp:krymsk",
                system=TargetSystem.AIR,
                target_class="airfield",
                mission=FlightType.OCA_RUNWAY,
                category=Category.OCA,
                priority=1.0,
                desired_effect=0.0,
                assessed_effect=0.0,
                bda_confidence=0.0,
                confidence=1.0,
                status="nominated",
                risk_kind="hvt",
                rank=1,
            )
        ]

    @property
    def raid_style(self) -> str:
        return str(self.spec.flag("raid_style", "none"))

    def _wave_preference(
        self, category: Category, push: Optional[bool] = None
    ) -> Optional[int]:
        return 0

    def _note_push_spend(self, category: Any, composed: Any) -> None:
        pass

    def _offensive_request(self, nomination: Any, tot: Any = None) -> PackageRequest:
        return PackageRequest(
            target=nomination.target,
            flights=[FlightRequest(nomination.mission, 2)],
            category_name=nomination.category.value,
            reason="JIPTL #1",
            risk_kind=nomination.risk_kind,
            threat=RouteThreat(air_level="medium"),
        )

    def _commit(
        self, request: PackageRequest, tot: datetime, category: Any, quiet: bool = False
    ) -> Optional[ComposedPackage]:
        is_main = request.target is self.target and "main" in request.reason
        if is_main and self.fail_main:
            return None
        package = SimpleNamespace(
            target=request.target,
            time_over_target=tot,
            flights=[],
            planning_info={},
            raid_id="",
            raid_role="",
            requests=request.flights,
        )
        self.coalition.ato.packages.append(package)
        sorties = sum(f.count for f in request.flights)
        composed = ComposedPackage(package, None, allocations=[f"alloc-{len(self.commits)}"])  # type: ignore[arg-type,list-item]
        composed.__dict__["_sorties"] = sorties
        if category is not None:
            self.apportionment.spend(category, sorties)
        self.timeline.reserve(tot, request.target.position)
        self.commits.append((request.reason, tot))
        return composed

    def _mark_planned(self, nomination: Any) -> None:
        self.planned_keys.add(nomination.key)
        self.marked.append(nomination.key)


@pytest.fixture(autouse=True)
def _fakes(monkeypatch: Any) -> None:
    from game.commander.jfacc import raids, weaponeering

    # The fake packages have no flights; count the requested aircraft.
    monkeypatch.setattr(
        ComposedPackage, "sorties", property(lambda self: self.__dict__.get("_sorties", 0))
    )
    monkeypatch.setattr(raids, "classify", lambda target: (TargetSystem.IADS, "sam_merad"))
    monkeypatch.setattr(weaponeering, "live_elements", lambda target: 4)


def test_echelons_are_staggered_and_tagged() -> None:
    planner = FakePlanner("russian_modern")
    raids = RaidPlanner(planner).plan()  # type: ignore[arg-type]
    assert len(raids) == 1
    raid = raids[0]
    roles = [role for _, _, role in raid.committed]
    assert roles == ["suppression", "suppression", "main", "follow_up"]
    by_role = {role: c.package for c, _, role in reversed(raid.committed)}
    main_tot = by_role["main"].time_over_target
    assert by_role["suppression"].time_over_target == main_tot - timedelta(minutes=6)
    assert by_role["follow_up"].time_over_target == main_tot + timedelta(minutes=8)
    assert all(c.package.raid_id == raid.raid_id for c, _, _ in raid.committed)
    # The suppression targets are marked suppressed before the main TOT.
    assert set(planner.suppressed) == {"SA-11", "SA-10"}
    # Massed main group, with a fighter clearing element.
    main_request = by_role["main"].requests
    assert main_request[0].count >= 6
    assert any(r.task is FlightType.SWEEP for r in main_request)
    assert planner.marked == ["cp:krymsk"]


def test_failed_main_group_releases_the_raid() -> None:
    planner = FakePlanner("russian_modern", fail_main=True)
    used_before = dict(planner.apportionment.used)
    raids = RaidPlanner(planner).plan()  # type: ignore[arg-type]
    assert raids == []
    assert planner.coalition.ato.packages == []
    assert len(planner.released) == 2  # both suppression echelons' allocations
    assert {k: v for k, v in planner.apportionment.used.items() if v} == {
        k: v for k, v in used_before.items() if v
    }
    assert planner.timeline.slots == []
    assert planner.suppressed == {}
    assert planner.marked == []


def test_soviet_raids_are_bigger_and_wider_spaced() -> None:
    planner = FakePlanner("soviet")
    raid = RaidPlanner(planner).plan()[0]  # type: ignore[arg-type]
    by_role = {role: c.package for c, _, role in reversed(raid.committed)}
    main_tot = by_role["main"].time_over_target
    assert by_role["suppression"].time_over_target == main_tot - timedelta(minutes=8)
    assert by_role["main"].requests[0].count >= 8


@pytest.mark.parametrize("profile", ["western", "client", "irregular"])
def test_no_massed_raids_outside_massed_doctrine(profile: str) -> None:
    planner = FakePlanner(profile)
    assert RaidPlanner(planner).plan() == []  # type: ignore[arg-type]
    assert planner.commits == []


def test_force_preservation_stops_raids() -> None:
    planner = FakePlanner("russian_modern")
    planner.__class__ = type(
        "Preserving", (FakePlanner,), {"raid_style": property(lambda self: "none")}
    )
    assert RaidPlanner(planner).plan() == []  # type: ignore[arg-type]
