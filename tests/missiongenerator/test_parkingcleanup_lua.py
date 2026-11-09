"""The parking cleanup plugin (resources/plugins/parkingcleanup), run under
lupa with a stubbed DCS scripting API, and the base plugin's handling of the
units it removes (not losses)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

lupa = pytest.importorskip("lupa")

PLUGINS = Path(__file__).resolve().parents[2] / "resources" / "plugins"

STUBS = r"""
logs = {}
errors = {}
env = {
    info = function(msg) table.insert(logs, msg) end,
    error = function(msg) table.insert(errors, msg) end,
}
scheduled = {}
timer = {
    getTime = function() return 100 end,
    scheduleFunction = function(fn, arg, t) table.insert(scheduled, { fn = fn, t = t }) end,
}
world = {
    event = { S_EVENT_ENGINE_SHUTDOWN = 18, S_EVENT_UNIT_LOST = 30 },
    addEventHandler = function(h) handler = h end,
}
Unit = { Category = { AIRPLANE = 0, HELICOPTER = 1 } }
destroyed = {}
units = {}
function make_unit(name, opts)
    local u = {
        name = name,
        player = opts.player,
        category = opts.category or 0,
        air = opts.air or false,
        speed = opts.speed or 0,
        alive = true,
    }
    function u:isExist() return self.alive end
    function u:getName() return self.name end
    function u:getPlayerName() return self.player end
    function u:getDesc() return { category = self.category } end
    function u:inAir() return self.air end
    function u:getVelocity() return { x = self.speed, y = 0, z = 0 } end
    function u:destroy() self.alive = false; table.insert(destroyed, self.name) end
    units[name] = u
    return u
end
Unit.getByName = function(name) return units[name] end
function shutdown(name)
    handler:onEvent({ id = world.event.S_EVENT_ENGINE_SHUTDOWN, initiator = units[name] })
end
function run_scheduled()
    local pending = scheduled
    scheduled = {}
    for _, s in ipairs(pending) do s.fn() end
end
"""


def _lua(options: str = "") -> Any:
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STUBS)
    lua.execute(
        f"dcsRetribution = {{ plugins = {{ parkingcleanup = {{ {options} }} }} }}"
    )
    script = (PLUGINS / "parkingcleanup" / "parkingcleanup.lua").read_text("utf-8")
    lua.execute(script)
    return lua


def _destroyed(lua: Any) -> list[str]:
    return list(lua.globals().destroyed.values())


def test_parked_ai_aircraft_is_removed_after_the_delay() -> None:
    lua = _lua()
    lua.execute('make_unit("AI 1", {})')
    lua.execute('shutdown("AI 1")')
    assert lua.eval("scheduled[1].t") == 100 + 10 * 60
    assert _destroyed(lua) == []
    lua.execute("run_scheduled()")
    assert _destroyed(lua) == ["AI 1"]
    # Marked, so the base plugin won't count it as lost.
    assert lua.eval('dcsRetributionDespawned["AI 1"]') is True


def test_players_and_helicopters_are_left_alone() -> None:
    lua = _lua()
    lua.execute('make_unit("Player", { player = "Viper" })')
    lua.execute('make_unit("Helo", { category = 1 })')
    lua.execute('shutdown("Player"); shutdown("Helo"); run_scheduled()')
    assert _destroyed(lua) == []


def test_helicopters_when_the_option_says_so() -> None:
    lua = _lua("helicopters = true, delayMinutes = 2")
    lua.execute('make_unit("Helo", { category = 1 })')
    lua.execute('shutdown("Helo")')
    assert lua.eval("scheduled[1].t") == 100 + 2 * 60
    lua.execute("run_scheduled()")
    assert _destroyed(lua) == ["Helo"]


def test_an_aircraft_that_started_moving_again_is_kept() -> None:
    lua = _lua()
    lua.execute('make_unit("AI 1", {})')
    lua.execute('shutdown("AI 1")')
    lua.execute('units["AI 1"].speed = 8')
    lua.execute("run_scheduled()")
    assert _destroyed(lua) == []


def test_base_plugin_ignores_losses_of_despawned_units() -> None:
    base = (PLUGINS / "base" / "dcs_retribution.lua").read_text("utf-8")
    assert "isDespawned(event.initiator)" in base
    assert "dcsRetributionDespawned = dcsRetributionDespawned or {}" in base
