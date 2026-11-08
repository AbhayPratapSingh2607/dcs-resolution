"""Weather and light conditions as they affect combat.

Everything here is a multiplier in [0, 1] (or slightly above) derived from the
turn's :class:`~game.weather.conditions.Conditions`. The model treats weather as
something that degrades specific *capabilities* rather than combat as a whole:
radar and GPS weapons ignore clouds, laser designation and TV seekers do not,
night hurts eyeballs but not radars, and so on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from game.timeofday import TimeOfDay

if TYPE_CHECKING:
    from game.weather.conditions import Conditions


def _preset_cover(text: str) -> float:
    text = text.lower()
    if "overcast" in text:
        return 0.95
    if "broken" in text:
        return 0.7
    if "scattered" in text:
        return 0.45
    if "few" in text:
        return 0.2
    return 0.5


@dataclass(frozen=True)
class CombatEnvironment:
    time_of_day: TimeOfDay
    #: Horizontal visibility, km.
    visibility_km: float
    #: Cloud base above sea level, meters. None when there is no meaningful layer.
    cloud_base_m: Optional[float]
    #: Cloud top, meters.
    cloud_top_m: Optional[float]
    #: Fraction of sky covered, 0..1.
    cloud_cover: float
    precipitation: bool
    thunderstorm: bool

    @staticmethod
    def clear_day() -> CombatEnvironment:
        return CombatEnvironment(
            time_of_day=TimeOfDay.Day,
            visibility_km=40.0,
            cloud_base_m=None,
            cloud_top_m=None,
            cloud_cover=0.0,
            precipitation=False,
            thunderstorm=False,
        )

    @staticmethod
    def from_conditions(conditions: Conditions) -> CombatEnvironment:
        from dcs.weather import Weather as PydcsWeather
        from game.weather.weather import Thunderstorm

        weather = conditions.weather
        visibility_km = 40.0
        if weather.fog is not None:
            visibility_km = min(visibility_km, weather.fog.visibility.meters / 1000)

        cloud_base: Optional[float] = None
        cloud_top: Optional[float] = None
        cover = 0.0
        precipitation = False
        clouds = weather.clouds
        if clouds is not None:
            cloud_base = float(clouds.base)
            if clouds.preset is not None:
                cover = _preset_cover(
                    f"{clouds.preset.ui_name} {clouds.preset.description}"
                )
                precipitation = "rain" in clouds.preset.ui_name.lower()
                cloud_top = cloud_base + 1500
            else:
                cover = min(1.0, clouds.density / 10)
                cloud_top = cloud_base + clouds.thickness
                precipitation = (
                    clouds.precipitation is not PydcsWeather.Preceptions.None_
                )
            if cover < 0.1:
                cloud_base = None
                cloud_top = None

        thunderstorm = isinstance(weather, Thunderstorm)
        if precipitation:
            visibility_km = min(visibility_km, 8.0)
        if thunderstorm:
            visibility_km = min(visibility_km, 5.0)

        return CombatEnvironment(
            time_of_day=conditions.time_of_day,
            visibility_km=visibility_km,
            cloud_base_m=cloud_base,
            cloud_top_m=cloud_top,
            cloud_cover=cover,
            precipitation=precipitation or thunderstorm,
            thunderstorm=thunderstorm,
        )

    @property
    def night(self) -> bool:
        return self.time_of_day is TimeOfDay.Night

    @property
    def light_level(self) -> float:
        """1.0 in daylight, low at night."""
        return {
            TimeOfDay.Day: 1.0,
            TimeOfDay.Dawn: 0.7,
            TimeOfDay.Dusk: 0.7,
            TimeOfDay.Night: 0.25,
        }[self.time_of_day]

    @property
    def visibility_factor(self) -> float:
        return max(0.15, min(1.0, self.visibility_km / 10))

    @property
    def visual_factor(self) -> float:
        """Effectiveness of anything relying on the human eye: visual ID, close-in
        fights, visual weapon delivery, optically aimed AAA and MANPADS gunners."""
        factor = self.light_level * self.visibility_factor
        if self.precipitation:
            factor *= 0.85
        return max(0.1, factor)

    @property
    def ir_seeker_factor(self) -> float:
        """IR seekers lose lock range in moisture and behind cloud."""
        factor = 1.0
        if self.precipitation:
            factor *= 0.85
        if self.thunderstorm:
            factor *= 0.85
        if self.cloud_cover > 0.7:
            factor *= 0.92
        return factor

    def line_of_sight_through_cloud(
        self, altitude_m: float, target_alt_m: float = 0
    ) -> float:
        """Probability that a sensor at ``altitude_m`` can see a target at
        ``target_alt_m`` through the cloud layer (laser, TV, eyeballs)."""
        if self.cloud_base_m is None:
            return 1.0
        low, high = sorted((altitude_m, target_alt_m))
        if high < self.cloud_base_m or (
            self.cloud_top_m is not None and low > self.cloud_top_m
        ):
            return 1.0
        return max(0.05, 1.0 - self.cloud_cover)

    def laser_factor(self, release_altitude_m: float) -> float:
        factor = self.line_of_sight_through_cloud(release_altitude_m)
        if self.visibility_km < 3:
            factor *= 0.5
        if self.precipitation:
            factor *= 0.85
        return factor

    def tv_factor(self, release_altitude_m: float) -> float:
        return (
            self.line_of_sight_through_cloud(release_altitude_m)
            * min(1.0, self.light_level * 1.1)
            * self.visibility_factor
        )

    def ground_fire_factor(self, thermal_sights: bool) -> float:
        """Effectiveness of direct ground fire (tanks, ATGMs, IFVs)."""
        light = self.light_level
        if thermal_sights:
            light = max(light, 0.85)
        factor = light * max(0.4, self.visibility_factor)
        if self.precipitation:
            factor *= 0.9
        return factor
