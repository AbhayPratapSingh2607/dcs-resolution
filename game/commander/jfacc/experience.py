"""Loss experience: the planner checks its risk estimates against its losses.

The risk model is fitted to a few reference scenarios. Against other
opponents it can be far off: against Iran's IADS blue's DEAD packages
estimated 11-20% per sortie and lost 1.4%, so every later strike was
scrubbed and the rollback stalled. Real planners revise threat assessments
from what their packages ran into; this does the same, from the side's own
losses only (no cheating: a side always knows which of its aircraft didn't
come back).

At planning, the model's expected losses (estimate x sorties) of the
estimated packages are noted per kind (strike packages and CAP stations).
At the debrief, the side's actual losses on those packages are added. Both
sums decay each turn, and the factor applied to later estimates is

    (actual + prior) / (expected + prior)

clamped to [min, max]: with little data it stays near 1, and it never
trusts its experience completely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game.ato import Package
    from .campaignstate import SideCampaign

STRIKE = "strike"
STATION = "station"


@dataclass(frozen=True)
class ExperienceConfig:
    #: Pseudo-count, in expected aircraft lost, that holds the factor at 1.
    prior: float = 3.0
    #: Share of the history kept from one turn to the next.
    decay: float = 0.7
    min_factor: float = 0.35
    max_factor: float = 3.0

    @staticmethod
    def from_profile(data: Optional[dict[str, Any]]) -> ExperienceConfig:
        if not data:
            return ExperienceConfig()
        return ExperienceConfig(
            prior=float(data.get("prior", 3.0)),
            decay=float(data.get("decay", 0.7)),
            min_factor=float(data.get("min", 0.35)),
            max_factor=float(data.get("max", 3.0)),
        )


def kind_of(package: Package) -> str:
    from game.ato.flighttype import FlightType

    tasks = {f.flight_type for f in package.flights}
    if tasks and tasks <= {FlightType.BARCAP, FlightType.TARCAP}:
        return STATION
    return STRIKE


def _model_estimate(package: Package) -> Optional[float]:
    risk = getattr(package, "planning_risk", None)
    if not risk:
        return None
    return float(risk.get("model_estimate", risk.get("estimate", 0.0)))


def note_plan(side: SideCampaign, packages: Iterable[Package]) -> None:
    """The model's expected losses for the packages about to fly."""
    expected: dict[str, float] = {}
    for package in packages:
        estimate = _model_estimate(package)
        if estimate is None:
            continue
        sorties = sum(
            f.count for f in package.flights if not getattr(f, "alert", False)
        )
        kind = kind_of(package)
        expected[kind] = expected.get(kind, 0.0) + estimate * sorties
    side.expected_losses = expected


def record_losses(
    side: SideCampaign, lost_packages: Iterable[Package], config: ExperienceConfig
) -> None:
    """Add a debrief's losses (one entry per aircraft lost, by its package)
    and the plan's expected losses to the decayed history."""
    actual: dict[str, float] = {}
    for package in lost_packages:
        if _model_estimate(package) is None:
            continue
        kind = kind_of(package)
        actual[kind] = actual.get(kind, 0.0) + 1.0
    for kind in set(side.expected_losses) | set(actual) | set(side.experience):
        expected_sum, actual_sum = side.experience.get(kind, (0.0, 0.0))
        side.experience[kind] = (
            expected_sum * config.decay + side.expected_losses.get(kind, 0.0),
            actual_sum * config.decay + actual.get(kind, 0.0),
        )
    side.expected_losses = {}


def factor(side: SideCampaign, kind: str, config: ExperienceConfig) -> float:
    expected_sum, actual_sum = side.experience.get(kind, (0.0, 0.0))
    raw = (actual_sum + config.prior) / (expected_sum + config.prior)
    return min(config.max_factor, max(config.min_factor, raw))


def record_turn(game: Any, debriefing: Any) -> None:
    """Feed both sides' loss experience from a committed debriefing."""
    from game.theater import Player

    from .profile import load_profile

    state = getattr(game, "air_campaign", None)
    if state is None:
        return
    for player in (Player.BLUE, Player.RED):
        side = state.maybe_side(player.is_blue)
        if side is None:
            continue
        lost = []
        for loss in debriefing.air_losses.losses:
            flight = loss.flight
            try:
                own = flight.squadron.player.is_blue == player.is_blue
            except AttributeError:
                continue
            if own and getattr(flight, "package", None) is not None:
                lost.append(flight.package)
        try:
            profile = load_profile(side.profile_name or "western")
            data = profile.section("risk").get("experience") if profile else None
        except Exception:
            data = None
        record_losses(side, lost, ExperienceConfig.from_profile(data))
