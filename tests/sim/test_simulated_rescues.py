"""AI CSAR rescues the simulation resolved show up before commit: in the
results window's count and in the package debrief."""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from game.ato.flighttype import FlightType
from game.commander.jfacc.briefing import PackageResult, _rescued
from game.debriefing import Debriefing
from game.sim.missionresultsprocessor import simulated_rescues
from game.squadrons.downedpilot import DownedPilot
from game.theater import Player


def _downed(player: Player = Player.BLUE) -> Any:
    downed = DownedPilot.__new__(DownedPilot)
    downed.id = uuid4()
    downed.player = player
    downed.simulated_pickup = None
    return downed


class _Flight:
    """Hashable like a real Flight."""

    def __init__(self, package: Any, client_count: int) -> None:
        self.flight_type = FlightType.CSAR
        self.package = package
        self.client_count = client_count
        self.count = 2


def _setup(lost: int = 0, client_count: int = 0) -> tuple[Any, Any, Any]:
    downed = _downed()
    package = SimpleNamespace(target=downed, flights=[])
    flight = _Flight(package, client_count)
    package.flights.append(flight)
    blue = SimpleNamespace(
        ato=SimpleNamespace(packages=[package]), downed_pilots=[downed]
    )
    red = SimpleNamespace(ato=SimpleNamespace(packages=[]), downed_pilots=[])
    game = SimpleNamespace(coalitions=[blue, red])
    debriefing = Debriefing.__new__(Debriefing)
    debriefing.game = game  # type: ignore[assignment]
    debriefing.unit_map = SimpleNamespace(aircraft={})  # type: ignore[assignment]
    debriefing.air_losses = SimpleNamespace(  # type: ignore[assignment]
        surviving_flight_members=lambda f: f.count - lost
    )
    debriefing.rescued_pilots = {}
    return game, debriefing, downed


def test_surviving_ai_csar_flight_rescues_its_pilot() -> None:
    game, debriefing, downed = _setup()
    assert [d for d, _ in simulated_rescues(game, debriefing)] == [downed]
    assert debriefing.pending_simulated_rescues(Player.BLUE) == [downed]
    assert debriefing.pending_simulated_rescues(Player.RED) == []


def test_no_rescue_when_flight_lost_or_player_flown() -> None:
    game, debriefing, _ = _setup(lost=2)
    assert simulated_rescues(game, debriefing) == []
    game, debriefing, _ = _setup(client_count=1)
    assert simulated_rescues(game, debriefing) == []


def test_committed_rescue_is_not_counted_again() -> None:
    game, debriefing, downed = _setup()
    game.coalitions[0].downed_pilots.remove(downed)
    assert simulated_rescues(game, debriefing) == []


def test_package_debrief_says_pilot_rescued() -> None:
    _, debriefing, downed = _setup()
    assert _rescued(debriefing, downed) is True
    _, debriefing, downed = _setup(lost=2)
    assert _rescued(debriefing, downed) is False
    assert _rescued(debriefing, object()) is None

    result = PackageResult(
        name="CSAR",
        goal="CSAR",
        players=False,
        flown=True,
        aircraft=2,
        lost=0,
        target_hits=0,
        target_destroyed=False,
        successes=0,
        air_kills=0,
        aborts=0,
        rescued=True,
    )
    assert result.result == "pilot rescued, all aircraft back"
    result.rescued = False
    assert result.result == "pilot not picked up, all aircraft back"
