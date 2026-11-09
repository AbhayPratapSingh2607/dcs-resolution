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
from dataclasses import dataclass

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
) -> RiskEstimate:
    # --- SAMs: suppression from SEAD shooters (HARM) and stand-off jamming.
    # A HARM shooter covers more than one emitter (two missiles, plus
    # pre-emptive shots), so the shooters needed grow with half the weight.
    w = threat.sam_weight
    suppression = 1.0
    if w > 0:
        needed = 2 + w / 2
        coverage = min(1.0, sead_aircraft / needed)
        suppression *= 1.0 - MAX_SEAD_SUPPRESSION * coverage
        if jammers > 0:
            suppression *= 0.8
    if standoff:
        # Stand-off weapons keep strikers out of the target-area defenses.
        suppression *= 0.6
    if not threat.target_defended:
        suppression *= TRANSIT_ONLY
    if front_line:
        suppression *= FRONT_LINE
    exposure = (
        SAM_EXPOSURE
        * w
        * (1 + w)
        * threat.enemy_sam_crew
        * suppression
        / max(own_aircrew, 0.3)
    )
    sam = 1 - math.exp(-exposure)

    # --- Fighters: sweep and escort screen the strikers; AWACS gives warning.
    air = (
        AIR_LOSS_PER_FIGHTER
        * threat.air_strength
        * threat.enemy_aircrew
        / max(own_aircrew, 0.3)
        / (1.0 + 1.5 * counter_air_aircraft)
    )
    if aewc_support:
        air *= 0.7
    total = 1 - (1 - sam) * (1 - min(air, 0.5))
    return RiskEstimate(total, sam, air)
