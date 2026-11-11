"""Campaign start (M4, game.opening): red's posture by surprise, the salvo size
by era, the emphasis and the BDA report."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from game import opening
from game.opening import Emphasis, OpeningPlan, SalvoShot, Surprise
from game.theater.player import Player


def _game(surprise: Surprise = Surprise.PARTIAL, turn: int = 1, begun: bool = True) -> Any:
    plan = OpeningPlan(begun=begun, surprise=surprise)
    return SimpleNamespace(
        turn=turn,
        opening=plan,
        settings=SimpleNamespace(strategic_surprise=surprise),
    )


def test_red_posture_follows_the_surprise_on_turn_1_only() -> None:
    from game.commander.jfacc.iads import ACTIVE, AMBUSH

    expected = _game(Surprise.NONE)
    caught = _game(Surprise.FULL)
    assert opening.alert_pairs_bonus(expected, Player.RED) == 1
    assert opening.alert_pairs_bonus(caught, Player.RED) == -1
    assert opening.mobile_emcon(expected, Player.RED) == AMBUSH
    assert opening.mobile_emcon(caught, Player.RED) == ACTIVE
    assert opening.mobile_emcon(_game(Surprise.PARTIAL), Player.RED) is None
    assert not opening.decoys_allowed(caught, Player.RED)
    assert opening.decoys_allowed(expected, Player.RED)
    assert opening.parked_in_open(caught, Player.RED) > opening.parked_in_open(expected, Player.RED)
    # Blue is never affected, and from turn 2 the posture is the doctrine's.
    assert opening.alert_pairs_bonus(expected, Player.BLUE) == 0
    later = _game(Surprise.NONE, turn=2)
    assert opening.alert_pairs_bonus(later, Player.RED) == 0
    assert opening.mobile_emcon(later, Player.RED) is None
    assert opening.decoys_allowed(_game(Surprise.FULL, turn=2), Player.RED)
    # Before Begin Campaign nothing applies.
    assert opening.alert_pairs_bonus(_game(Surprise.NONE, begun=False), Player.RED) == 0


def _salvo_game(year: int, doctrine: str, country: str, ships: int = 0, bombers: int = 0, monkeypatch: Any = None) -> Any:
    from game.theater.controlpoint import ControlPointType

    units = [SimpleNamespace(alive=True, type=SimpleNamespace(id="TICONDEROG")) for _ in range(ships)]
    cp = SimpleNamespace(ground_objects=[SimpleNamespace(units=units)])
    squadron = SimpleNamespace(
        location=SimpleNamespace(cptype=ControlPointType.OFF_MAP),
        aircraft=SimpleNamespace(variant_id="B-52H Stratofortress"),
        owned_aircraft=bombers,
    )
    game = SimpleNamespace(
        current_day=date(year, 6, 1),
        blue=SimpleNamespace(faction=SimpleNamespace(country=country), air_wing=SimpleNamespace(iter_squadrons=lambda: [squadron])),
        theater=SimpleNamespace(control_points_for=lambda player: [cp]),
    )
    monkeypatch.setattr(opening, "_doctrine_name", lambda g, p: doctrine)
    return game


def test_salvo_size_by_era_ships_and_bombers(monkeypatch: pytest.MonkeyPatch) -> None:
    assert opening.salvo_size(_salvo_game(1975, "western", "USA", monkeypatch=monkeypatch))[0] == 0
    assert opening.salvo_size(_salvo_game(1991, "western", "USA", monkeypatch=monkeypatch))[0] == 16
    assert opening.salvo_size(_salvo_game(2005, "western", "USA", monkeypatch=monkeypatch))[0] == 24
    # Ships (at most 4 count) and bombers raise it.
    missiles, sized = opening.salvo_size(_salvo_game(2005, "western", "USA", ships=6, bombers=4, monkeypatch=monkeypatch))
    assert missiles == 24 + 32 + 8
    assert "4 cruise missile ships" in sized and "4 bombers" in sized
    # Russia only from 2015 (Kalibr); others none.
    assert opening.salvo_size(_salvo_game(2010, "russian_modern", "Russia", monkeypatch=monkeypatch))[0] == 0
    assert opening.salvo_size(_salvo_game(2016, "russian_modern", "Russia", monkeypatch=monkeypatch))[0] == 12
    assert opening.salvo_size(_salvo_game(2016, "irregular", "Iraq", monkeypatch=monkeypatch))[0] == 0


def test_bda_report_lists_targets_and_changes_with_the_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    picture = SimpleNamespace(isr=0.8)
    game = SimpleNamespace(
        opening=OpeningPlan(begun=True, surprise=Surprise.FULL, emphasis=Emphasis.AIRFIELDS),
        settings=SimpleNamespace(strategic_surprise=Surprise.FULL),
        war_state=SimpleNamespace(picture=lambda g, p: picture),
    )
    shots = [
        SalvoShot("Krymsk", "airfield", 4, 3, 3, 3, runway_cut=True, aircraft_destroyed=2),
        SalvoShot("EWR 1", "ewr", 2, 0, 0, 0),
    ]
    lines = opening.bda_report(game, shots, "24 from the 2005 arsenal")  # type: ignore[arg-type]
    assert lines[0].startswith("Opening salvo: 6 cruise missiles at 2 targets")
    assert "emphasis: airfields, surprise: full" in lines[0]
    assert "1 of 2 targets hit" in lines[1] and "confidence high" in lines[1]
    assert "runway cratered, about 2 aircraft destroyed on the ground" in lines[2]
    assert lines[3].endswith("no effect seen")
    assert opening.bda_report(game, [], "no cruise missiles")[0].startswith("No opening missile strikes")  # type: ignore[arg-type]


def test_turn_1_target_weight_follows_the_emphasis() -> None:
    from game.commander.jfacc.targets import TargetNominator

    nominator = object.__new__(TargetNominator)
    nominator.player = Player.BLUE  # type: ignore[attr-defined]
    nominator.game = SimpleNamespace(turn=1, opening=OpeningPlan(begun=True, emphasis=Emphasis.C2))  # type: ignore[attr-defined]
    assert nominator._opening_weight("c2_node") == opening.EMPHASIS_WEIGHT
    assert nominator._opening_weight("airfield") == 1.0
    nominator.game.turn = 2  # type: ignore[attr-defined]
    assert nominator._opening_weight("c2_node") == 1.0
    nominator.game.turn = 1  # type: ignore[attr-defined]
    nominator.player = Player.RED  # type: ignore[attr-defined]
    assert nominator._opening_weight("c2_node") == 1.0


def test_old_saves_get_an_opening_plan() -> None:
    plan = OpeningPlan.__new__(OpeningPlan)
    plan.__setstate__({"begun": True})
    assert plan.begun and plan.emphasis is Emphasis.BALANCED and plan.shots == []
    game = SimpleNamespace()
    assert opening.opening_of(game).begun is False  # type: ignore[arg-type]


def test_planned_salvo_spends_the_missiles_down_the_target_list(monkeypatch: pytest.MonkeyPatch) -> None:
    airfield = SimpleNamespace(name="Krymsk")
    sam = SimpleNamespace(name="SA-10")
    ewr = SimpleNamespace(name="EWR 1")
    seen: list[Any] = []

    def candidates(game: Any, emphasis: Any = None) -> list[Any]:
        seen.append(emphasis)
        return [(5.0, airfield, "airfield"), (4.0, sam, "sam_lorad"), (3.0, ewr, "ewr")]

    monkeypatch.setattr(opening, "salvo_size", lambda g: (8, "8 from the arsenal"))
    monkeypatch.setattr(opening, "_salvo_candidates", candidates)
    planned = opening.planned_salvo(SimpleNamespace(), Emphasis.C2)  # type: ignore[arg-type]
    assert [(p.name, p.missiles) for p in planned] == [("Krymsk", 4), ("SA-10", 3), ("EWR 1", 1)]
    assert seen == [Emphasis.C2]

    monkeypatch.setattr(opening, "salvo_size", lambda g: (0, "none"))
    assert opening.planned_salvo(SimpleNamespace()) == []  # type: ignore[arg-type]


def test_turned_off_missile_strikes_fire_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opening, "salvo_size", lambda g: (24, "24 from the 2005 arsenal"))
    game = SimpleNamespace(
        opening=OpeningPlan(begun=True),
        settings=SimpleNamespace(opening_missile_strikes=False),
    )
    assert opening.fire_salvo(game, None, None) == []  # type: ignore[arg-type]
    lines = opening.bda_report(game, [], "24 from the 2005 arsenal")  # type: ignore[arg-type]
    assert lines == ["No opening missile strikes: they were turned off."]
