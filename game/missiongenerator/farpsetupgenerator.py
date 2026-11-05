"""Mission scripts that report when a FARP's equipment has been flown in.

A player FARP is only set up once a transport delivers its equipment: a
helicopter by landing at the site, a plane by an airdrop pass over it (low and
close). For each FARP waiting for its equipment, a mission start script watches
the units of its setup flight and records the delivery in ``farp_setup_events``,
which dcs_retribution.lua writes to the mission's state file.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from dcs import Mission
from dcs.action import DoScript
from dcs.translation import String
from dcs.triggers import TriggerStart

from game.ato.flightplans.farpsetup import is_farp_setup_target
from game.theater.dynamicfarp import (
    AIRDROP_MAX_AGL,
    AIRDROP_RADIUS,
    DynamicFarp,
    SETUP_LANDING_RADIUS,
)
from .tgogenerator import _lua_string

if TYPE_CHECKING:
    from game import Game
    from game.unitmap import UnitMap


class FarpSetupGenerator:
    def __init__(self, mission: Mission, game: Game, unit_map: UnitMap) -> None:
        self.mission = mission
        self.game = game
        self.unit_map = unit_map

    def setup_units(self) -> dict[DynamicFarp, list[str]]:
        """Unit names of the setup flights of each FARP waiting for equipment."""
        units: dict[DynamicFarp, list[str]] = defaultdict(list)
        for name, flying_unit in self.unit_map.aircraft.items():
            target = flying_unit.flight.package.target
            if is_farp_setup_target(target):
                assert isinstance(target, DynamicFarp)
                units[target].append(name)
        return units

    def generate(self) -> None:
        for farp, names in self.setup_units().items():
            trigger = TriggerStart(comment=f"{farp.name} setup")
            trigger.add_action(DoScript(String(self.script(farp, names))))
            self.mission.triggerrules.triggers.append(trigger)

    @staticmethod
    def script(farp: DynamicFarp, unit_names: list[str]) -> str:
        side = 2 if farp.captured.is_blue else 1
        units = ", ".join(f"[{_lua_string(n)}] = true" for n in sorted(unit_names))
        return f"""do
  local farpId = {_lua_string(str(farp.id))}
  local farpName = {_lua_string(farp.name)}
  local side = {side}
  local units = {{ {units} }}
  local center = {{ x = {farp.position.x:.1f}, z = {farp.position.y:.1f} }}
  local landRadius = {SETUP_LANDING_RADIUS.meters:.0f}
  local dropRadius = {AIRDROP_RADIUS.meters:.0f}
  local dropMaxAgl = {AIRDROP_MAX_AGL.meters:.0f}
  local done = false

  local function complete(how)
    if done then return end
    done = true
    farp_setup_events = farp_setup_events or {{}}
    farp_setup_events[#farp_setup_events + 1] = farpId
    dirty_state = true
    trigger.action.outTextForCoalition(
      side, farpName .. ": equipment " .. how .. ". The FARP will be set up next turn.", 20
    )
  end

  local function within(point, radius)
    local dx, dz = point.x - center.x, point.z - center.z
    return dx * dx + dz * dz <= radius * radius
  end

  -- Helicopters (and anything else) deliver by landing at the site.
  local handler = {{}}
  function handler:onEvent(event)
    if done or event.id ~= world.event.S_EVENT_LAND or not event.initiator then
      return
    end
    local ok, name = pcall(function() return event.initiator:getName() end)
    if not ok or not units[name] then return end
    if within(event.initiator:getPoint(), landRadius) then
      complete("delivered")
    end
  end
  world.addEventHandler(handler)

  -- Planes deliver with a low airdrop pass over the site.
  local function checkAirdrop()
    if done then return nil end
    for name, _ in pairs(units) do
      local unit = Unit.getByName(name)
      if unit and unit:isExist() and unit:inAir()
          and unit:getDesc().category == Unit.Category.AIRPLANE then
        local point = unit:getPoint()
        local agl = point.y - land.getHeight({{ x = point.x, y = point.z }})
        if agl <= dropMaxAgl and within(point, dropRadius) then
          complete("airdropped")
          return nil
        end
      end
    end
    return timer.getTime() + 1
  end
  timer.scheduleFunction(checkAirdrop, nil, timer.getTime() + 1)
end"""
