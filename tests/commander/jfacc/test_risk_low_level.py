"""Risk estimate for low-level ingress (Soviet-style doctrines), and the
per-profile risk model."""

from __future__ import annotations

import pytest

from game.commander.jfacc.risk import DEFAULT_MODEL, RiskModel, estimate
from game.commander.jfacc.threat import RouteThreat


def _rate(threat: RouteThreat, sead: int = 0, **kwargs: object) -> float:
    return estimate(threat, sead, 0, 0, False, **kwargs).expected_loss_rate  # type: ignore[arg-type]


def test_medium_altitude_is_unchanged_by_shorad() -> None:
    plain = RouteThreat(sam_weight=6.0, target_defended=True)
    guns = RouteThreat(sam_weight=6.0, target_defended=True, shorad_weight=5.0)
    assert _rate(plain) == _rate(guns)
    # Passing the default model explicitly is the same estimate.
    assert _rate(plain) == _rate(plain, model=DEFAULT_MODEL)


def test_low_level_trades_radar_sams_for_guns() -> None:
    lorad = RouteThreat(sam_weight=9.0, target_defended=True)
    assert _rate(lorad, low_level=True) < _rate(lorad) / 3
    shorad = RouteThreat(
        sam_weight=2.0, radar_shorad_weight=2.0, shorad_weight=6.0, target_defended=True
    )
    # Medium altitude flies above the guns and IR SAMs; low level doesn't.
    assert _rate(shorad, low_level=True) > _rate(shorad)


def test_sead_does_not_suppress_guns() -> None:
    guns = RouteThreat(shorad_weight=4.0, target_defended=True)
    assert _rate(guns, sead=0, low_level=True) == pytest.approx(
        _rate(guns, sead=8, low_level=True)
    )
    assert _rate(guns, low_level=True, standoff=True) < _rate(guns, low_level=True)


def test_risk_model_from_profile() -> None:
    model = RiskModel.from_profile({"low_radar_factor": 0.5, "unknown": 3})
    assert model.low_radar_factor == 0.5
    assert model.sam_exposure == DEFAULT_MODEL.sam_exposure
    assert RiskModel.from_profile(None) == DEFAULT_MODEL
    threat = RouteThreat(sam_weight=9.0, target_defended=True)
    assert _rate(threat, low_level=True, model=model) > _rate(threat, low_level=True)
