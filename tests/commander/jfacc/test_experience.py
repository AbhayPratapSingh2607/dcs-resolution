"""Loss experience: risk estimates are corrected by the side's own losses."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.ato.flighttype import FlightType
from game.commander.jfacc import experience
from game.commander.jfacc.campaignstate import SideCampaign
from game.commander.jfacc.risk import RiskEstimate

CONFIG = experience.ExperienceConfig()


def _package(task: FlightType, count: int, estimate: float | None) -> Any:
    flights = [SimpleNamespace(flight_type=task, count=count, alert=False)]
    risk = None if estimate is None else {"estimate": estimate}
    return SimpleNamespace(flights=flights, planning_risk=risk)


def test_no_history_leaves_estimates_alone() -> None:
    side = SideCampaign()
    assert experience.factor(side, experience.STRIKE, CONFIG) == 1.0


def test_fewer_losses_than_expected_lower_the_estimate() -> None:
    side = SideCampaign()
    dead = _package(FlightType.DEAD, 4, 0.2)
    escort = _package(FlightType.SEAD_ESCORT, 16, 0.2)
    experience.note_plan(side, [dead, escort])
    assert side.expected_losses[experience.STRIKE] == pytest.approx(4.0)
    experience.record_losses(side, [], CONFIG)
    # (0 + 3) / (4 + 3)
    assert experience.factor(side, experience.STRIKE, CONFIG) == pytest.approx(3 / 7)
    # CAP stations keep their own experience.
    assert experience.factor(side, experience.STATION, CONFIG) == 1.0


def test_more_losses_than_expected_raise_it_up_to_the_cap() -> None:
    side = SideCampaign()
    cap = _package(FlightType.BARCAP, 2, 0.02)
    experience.note_plan(side, [cap])
    experience.record_losses(side, [cap] * 10, CONFIG)
    assert experience.factor(side, experience.STATION, CONFIG) == CONFIG.max_factor


def test_losses_of_unestimated_packages_dont_count() -> None:
    side = SideCampaign()
    experience.note_plan(side, [])
    experience.record_losses(side, [_package(FlightType.BARCAP, 2, None)], CONFIG)
    assert experience.factor(side, experience.STATION, CONFIG) == 1.0


def test_history_decays() -> None:
    side = SideCampaign()
    experience.note_plan(side, [_package(FlightType.STRIKE, 10, 1.0)])
    experience.record_losses(side, [], CONFIG)
    first = side.experience[experience.STRIKE][0]
    experience.note_plan(side, [])
    experience.record_losses(side, [], CONFIG)
    assert side.experience[experience.STRIKE][0] == pytest.approx(first * CONFIG.decay)


def test_the_factor_uses_the_model_estimate_not_the_corrected_one() -> None:
    side = SideCampaign()
    package = _package(FlightType.DEAD, 4, 0.05)
    package.planning_risk["model_estimate"] = 0.2
    experience.note_plan(side, [package])
    assert side.expected_losses[experience.STRIKE] == pytest.approx(0.8)


def test_scaled_estimate_describes_the_correction() -> None:
    risk = RiskEstimate(0.2, 0.2, 0.0).scaled(0.4)
    assert risk.expected_loss_rate == pytest.approx(0.08)
    assert risk.model_estimate == pytest.approx(0.2)
    assert "x0.40 from losses so far" in risk.describe()
