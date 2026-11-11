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
#: after its historical calibration (USA 2005 vs Iran 2015, Caucasus, blue
#: flying every package regardless of risk, 2 seeds x 3 turns, about 10 SEAD
#: aircraft per package): route weight 0-8 lost 0.5% per sortie (1/190),
#: 8-16 0% (0/134), 16-24 5.3% (8/152), 24-32 21% (5/24). Desert Storm-like
#: runs agree (DEAD 6/572 lost, 1.0%, against 5.6% estimated). The fit stays above the
#: losses: those runs re-estimated give 0.4%, 3%, 7% and 33%.
#: (The earlier 0.007 predated the combat model's historical calibration and
#: overestimated 5-12x, so a dense IADS was never attacked at all.)
SAM_EXPOSURE = 0.001
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
#: CAP stations: SAM exposure per unit of route SAM weight. A CAP orbits at
#: altitude near the edge of coverage and turns away; it doesn't press
#: through the engagement zone to a target, so overlapping sites don't
#: compound against it the way they do against a strike package: the term
#: is linear in the weight, not quadratic. Fitted to the combat model (USA
#: 2005 vs Iran 2015, Caucasus): blue CAPs whose routes crossed SAM weight
#: ~14 lost 2-4.3% per sortie over four runs, later 0 of ~30 sorties at
#: weights 12-21.
STATION_EXPOSURE = 0.0018
#: CAP stations deep in overlapping coverage: above a route SAM weight of
#: STATION_KNEE the sites do compound against the orbit, and the exposure
#: gains STATION_OVERLAP * (w - STATION_KNEE)^2. Fitted to the combat model
#: (USA 1990 vs Iraq 1991, Caucasus, 2 seeds x 4 turns): CAP stations whose
#: routes crossed weight below 28 lost 0 of 184 sorties, 28-44 lost 6 of 20
#: (one station on the axis toward Sochi, 37-43, lost 5 of 12) while the
#: linear term estimated 1.1-1.7%. With the knee and Iraq's SAM crews that
#: station estimates ~25% (observed 42%), over the 6% DCA limit, so it is
#: pulled back along its axis; stations under weight ~32 stay where they are.
STATION_KNEE = 24.0
STATION_OVERLAP = 0.004


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
    station_exposure: float = STATION_EXPOSURE
    station_knee: float = STATION_KNEE
    station_overlap: float = STATION_OVERLAP

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
    #: The model's estimate before the loss experience factor.
    model_loss_rate: float = -1.0
    experience: float = 1.0
    #: Ground fire over the front (casestimate.front_flak_loss).
    ground_component: float = 0.0

    def describe(self) -> str:
        scaled = (
            f", x{self.experience:.2f} from losses so far"
            if abs(self.experience - 1.0) >= 0.01
            else ""
        )
        ground = (
            f", ground fire {self.ground_component:.1%}"
            if self.ground_component > 0
            else ""
        )
        return (
            f"{self.expected_loss_rate:.1%} per sortie "
            f"(SAM {self.sam_component:.1%}, air {self.air_component:.1%}"
            f"{ground}{scaled})"
        )

    def with_ground_fire(self, ground: float) -> RiskEstimate:
        """This estimate with ground fire over the front added."""
        if ground <= 0:
            return self
        return RiskEstimate(
            1 - (1 - self.expected_loss_rate) * (1 - ground),
            self.sam_component,
            self.air_component,
            self.model_loss_rate,
            self.experience,
            ground,
        )

    def scaled(self, factor: float) -> RiskEstimate:
        """This estimate corrected by the side's loss experience."""
        return RiskEstimate(
            min(1.0, self.expected_loss_rate * factor),
            self.sam_component,
            self.air_component,
            self.expected_loss_rate,
            factor,
            self.ground_component,
        )

    @property
    def model_estimate(self) -> float:
        return (
            self.expected_loss_rate
            if self.model_loss_rate < 0
            else self.model_loss_rate
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
    station: bool = False,
) -> RiskEstimate:
    """Expected losses per sortie. ``station``: a CAP holding a station
    rather than a package attacking a target."""
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
    if station:
        per_crew = model.station_exposure * w + model.station_overlap * (
            max(0.0, w - model.station_knee) ** 2
        )
    else:
        per_crew = model.sam_exposure * (1 + w) * w
    exposure = per_crew * threat.enemy_sam_crew * suppression / max(own_aircrew, 0.3)
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
