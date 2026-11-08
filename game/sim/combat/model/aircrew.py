"""What happens to the crew of an aircraft the combat model shoots down.

Every loss records where the aircraft went down and what got it. CSAR
(game.squadrons.csarservice) uses that instead of a flat survival roll and a
spot near the package's target: a pilot downed by an SA-10 on the way in
comes down on the way in, and the chance of a successful ejection depends on
the kind of hit.

Historically about half of the aircrew shot down survived (Vietnam, Desert
Storm). Proximity-fused missiles at altitude leave time to eject; guns and
flak at low level often don't, and helicopter crews ride the aircraft down.
The factors below scale the campaign's "CSAR pilot survival chance" setting,
so that setting still sets the overall level.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from dcs import Point

    from game.ato import Flight
    from game.squadrons import Pilot


class LossCause(Enum):
    AIR_MISSILE = "air-to-air missile"
    AIR_GUN = "guns"
    SAM = "surface-to-air missile"
    AAA = "anti-aircraft artillery"
    GROUND_FIRE = "ground fire"
    OTHER = "other"


#: Survival relative to the campaign setting, by cause.
SURVIVAL_FACTOR = {
    LossCause.AIR_MISSILE: 1.3,
    LossCause.SAM: 1.25,
    LossCause.AIR_GUN: 0.9,
    LossCause.AAA: 0.9,
    LossCause.GROUND_FIRE: 0.85,
    LossCause.OTHER: 1.0,
}
#: Helicopter crews can't eject.
HELICOPTER_FACTOR = 0.75
#: Hit this low there is little time or height to get out.
LOW_ALTITUDE_M = 150.0
LOW_ALTITUDE_FACTOR = 0.6
#: Nobody is guaranteed to survive being shot down.
MAX_SURVIVAL = 0.95


@dataclass(frozen=True)
class AirLossDetail:
    flight: Flight
    pilot: Optional[Pilot]
    position: Optional[Point]
    altitude_m: float
    cause: LossCause
    #: The weapon and shooter, as written in the combat log.
    description: str
    helicopter: bool

    @property
    def survival_factor(self) -> float:
        factor = SURVIVAL_FACTOR[self.cause]
        if self.helicopter:
            factor *= HELICOPTER_FACTOR
        if self.altitude_m < LOW_ALTITUDE_M:
            factor *= LOW_ALTITUDE_FACTOR
        return factor

    def survival_chance(self, setting_percent: float) -> float:
        """Chance the crew gets out alive, given the campaign setting."""
        chance = setting_percent / 100 * self.survival_factor
        return max(0.0, min(MAX_SURVIVAL, chance))


def detail_for(airframe: Any, cause: LossCause, description: str) -> AirLossDetail:
    try:
        position = airframe.position
    except Exception:
        position = None
    try:
        altitude = float(airframe.altitude_m)
    except Exception:
        altitude = 5000.0
    return AirLossDetail(
        flight=airframe.flight,
        pilot=getattr(airframe.member, "pilot", None),
        position=position,
        altitude_m=altitude,
        cause=cause,
        description=description,
        helicopter=bool(getattr(airframe.profile, "helicopter", False)),
    )
