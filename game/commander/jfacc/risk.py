"""Expected attrition of a candidate package.

An analytic estimate, calibrated against the fast-forward combat model and
history, rather than a simulation run: planners need a number for every
candidate package, quickly. The estimate is expected losses per sortie, which
the planner compares with the doctrine's acceptable attrition.

The SAM term is fitted to what the fast-forward combat model does to
packages (resources/tools/jfacc_report.py and per-package loss logs), since
that model, or DCS, is what fights the plan. It is far more lethal against
deep packages into an intact modern IADS than history (Desert Storm lost
about 0.05% per sortie), which is why the planner rolls the IADS back with
DEAD before it sends packages deep.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Any, Optional

from .threat import RouteThreat

#: SAM exposure per sortie is SAM_EXPOSURE * w * (1 + w) for route SAM weight
#: w: overlapping sites don't just add, they engage the same package from
#: several directions and longer. Fitted to the fast-forward combat model
#: (Western package with SEAD against a modern Russian IADS, Caucasus):
#: weight 4 -> ~7% per sortie, 8 -> ~20%, 12 -> ~40%, 20 -> ~80%.
SAM_EXPOSURE = 0.007
#: Most suppression a full SEAD package buys: shooters only fire at emitting
#: radars, and sites that stay dark until the package is close still engage.
MAX_SEAD_SUPPRESSION = 0.5
#: Share of the exposure left when the target itself isn't inside SAM
#: coverage: the package only transits the threat, low and fast.
TRANSIT_ONLY = 0.35
#: Share of the exposure for CAS over the front line: low, short legs at the
#: FLOT, mostly short of the SAM belt behind it. Fitted to the combat model
#: (about 1.5% per sortie where the general fit predicts 5%).
FRONT_LINE = 0.35
#: Loss per sortie per unit of enemy fighter strength, unescorted.
AIR_LOSS_PER_FIGHTER = 0.004
#: Low-level ingress (Soviet-style doctrines): share of the radar SAM
#: exposure left. Under the radar horizon and masked by terrain, long-range
#: radar SAMs see the package late and briefly (the combat model applies the
#: radar horizon, terrain masking and late acquisition).
LOW_RADAR_FACTOR = 0.35
#: Low-level ingress: exposure per short-range air defense site (guns,
#: MANPADS, IR and radar SHORAD) near the track or the target.
SHORAD_EXPOSURE = 0.012


@dataclass(frozen=True)
class RiskModel:
    """The risk constants, overridable per planning profile (risk.model)."""

    sam_exposure: float = SAM_EXPOSURE
    max_sead_suppression: float = MAX_SEAD_SUPPRESSION
    transit_only: float = TRANSIT_ONLY
    front_line: float = FRONT_LINE
    air_loss_per_fighter: float = AIR_LOSS_PER_FIGHTER
    low_radar_factor: float = LOW_RADAR_FACTOR
    shorad_exposure: float = SHORAD_EXPOSURE

    @staticmethod
    def from_profile(data: Optional[dict[str, Any]]) -> RiskModel:
        if not data:
            return RiskModel()
        known = {f.name for f in fields(RiskModel)}
        return RiskModel(**{k: float(v) for k, v in data.items() if k in known})


DEFAULT_MODEL = RiskModel()


@dataclass(frozen=True)
class RiskEstimate:
    expected_loss_rate: float
    sam_component: float
    air_component: float

    def describe(self) -> str:
        return (
            f"{self.expected_loss_rate:.1%} per sortie "
            f"(SAM {self.sam_component:.1%}, air {self.air_component:.1%})"
        )


def estimate(
    threat: RouteThreat,
    sead_aircraft: int,
    jammers: int,
    counter_air_aircraft: int,
    aewc_support: bool,
    own_aircrew: float = 1.0,
    standoff: bool = False,
    front_line: bool = False,
    low_level: bool = False,
    model: RiskModel = DEFAULT_MODEL,
) -> RiskEstimate:
    # --- SAMs: suppression from SEAD shooters (HARM) and stand-off jamming.
    # A HARM shooter covers more than one emitter (two missiles, plus
    # pre-emptive shots), so the shooters needed grow with half the weight.
    w = threat.sam_weight
    if low_level:
        # Radar SHORAD is counted with the guns below; the long-range radar
        # SAMs see the package late, under their radar horizon.
        w = max(0.0, w - threat.radar_shorad_weight) * model.low_radar_factor
    suppression = 1.0
    if w > 0:
        needed = 2 + w / 2
        coverage = min(1.0, sead_aircraft / needed)
        suppression *= 1.0 - model.max_sead_suppression * coverage
        if jammers > 0:
            suppression *= 0.8
    if standoff:
        # Stand-off weapons keep strikers out of the target-area defenses.
        suppression *= 0.6
    if not threat.target_defended:
        suppression *= model.transit_only
    if front_line:
        suppression *= model.front_line
    exposure = (
        model.sam_exposure
        * w
        * (1 + w)
        * threat.enemy_sam_crew
        * suppression
        / max(own_aircrew, 0.3)
    )
    if low_level and threat.shorad_weight > 0:
        # Guns and short-range missiles along the track and over the target:
        # SEAD doesn't touch them, stand-off weapons stay outside them.
        exposure += (
            model.shorad_exposure
            * threat.shorad_weight
            * threat.enemy_sam_crew
            * (0.3 if standoff else 1.0)
            / max(own_aircrew, 0.3)
        )
    sam = 1 - math.exp(-exposure)

    # --- Fighters: sweep and escort screen the strikers; AWACS gives warning.
    air = (
        model.air_loss_per_fighter
        * threat.air_strength
        * threat.enemy_aircrew
        / max(own_aircrew, 0.3)
        / (1.0 + 1.5 * counter_air_aircraft)
    )
    if aewc_support:
        air *= 0.7
    total = 1 - (1 - sam) * (1 - min(air, 0.5))
    return RiskEstimate(total, sam, air)
