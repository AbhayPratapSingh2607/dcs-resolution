"""The GCI plugin (resources/plugins/gci/gci.lua), run under lupa with a
stubbed DCS scripting API, and the Skynet config fix."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

lupa = pytest.importorskip("lupa")

PLUGINS = Path(__file__).resolve().parents[2] / "resources" / "plugins"

STUBS = r"""
logs = {}
env = { info = function(msg) table.insert(logs, msg) end }
activated = {}
pushed = {}
scheduled = {}
timer = {
    getTime = function() return 100 end,
    scheduleFunction = function(fn, arg, t) table.insert(scheduled, fn) end,
}
trigger = { action = {
    activateGroup = function(group) table.insert(activated, group.name) end,
    outText = function() end,
} }
coalition = { side = { RED = 1, BLUE = 2 } }
Controller = { Detection = { RADAR = 4 } }
Object = { Category = { UNIT = 1 }, getCategory = function(o) return 1 end }
Unit = { Category = { AIRPLANE = 0, HELICOPTER = 1 } }
Group = { Category = { AIRPLANE = 0, GROUND = 2 } }

-- Aircraft in the air: name -> {x, z, coalition}
aircraft = {}
local function target(name)
    local a = aircraft[name]
    return { object = {
        isExist = function() return true end,
        getCoalition = function() return a.coalition end,
        getDesc = function() return { category = 0 } end,
        getName = function() return name end,
        inAir = function() return true end,
        getPoint = function() return { x = a.x, y = 5000, z = a.z } end,
    } }
end

-- Red early warning radar; it sees the names in radarSees.
radarSees = {}
radarAlive = true
local ewr = {
    isExist = function() return radarAlive end,
    getUnits = function() return { {
        isExist = function() return radarAlive end,
        isActive = function() return true end,
        hasAttribute = function(self, a) return a == "EWR" end,
    } } end,
    getController = function() return {
        getDetectedTargets = function()
            local list = {}
            for _, name in ipairs(radarSees) do table.insert(list, target(name)) end
            return list
        end,
    } end,
}
coalition.getGroups = function(side, category)
    if side == coalition.side.RED and category == Group.Category.GROUND then
        return { ewr }
    end
    return {}
end
local groups = {}
Group.getByName = function(name)
    if not groups[name] then
        groups[name] = {
            name = name,
            isExist = function() return true end,
            getController = function() return {
                pushTask = function(self, task) table.insert(pushed, { name, task.id }) end,
            } end,
        }
    end
    return groups[name]
end
"""

DATA = r"""
dcsRetribution = {
    plugins = { gci = { scanInterval = 15 } },
    GCI = {
        raidClusterMeters = "40000",
        red = {
            maxPerRaid = "2",
            alerts = {
                { group = "Maykop alert 1", x = "0", y = "0", radius = "150000" },
                { group = "Maykop alert 2", x = "10000", y = "0", radius = "150000" },
                { group = "Krymsk alert", x = "500000", y = "0", radius = "150000" },
            },
        },
        blue = { maxPerRaid = "1", alerts = {} },
    },
}
"""


def _runtime() -> Any:
    runtime = lupa.LuaRuntime()
    runtime.execute(STUBS)
    runtime.execute(DATA)
    runtime.execute((PLUGINS / "gci" / "gci.lua").read_text(encoding="utf-8"))
    return runtime


def _scan(runtime: Any) -> None:
    # The plugin schedules its first scan; run the newest scan function.
    scheduled = runtime.globals().scheduled
    scan = scheduled[len(scheduled)]
    scan(None, 0)


def _activated(runtime: Any) -> list[str]:
    activated = runtime.globals().activated
    return [activated[i + 1] for i in range(len(activated))]


def test_raid_seen_by_radar_scrambles_nearest_pairs() -> None:
    runtime = _runtime()
    runtime.execute(r"""
        for i = 1, 6 do
            aircraft["F-16 " .. i] = { x = 40000 + i * 100, z = 5000, coalition = 2 }
            table.insert(radarSees, "F-16 " .. i)
        end
    """)
    _scan(runtime)
    assert _activated(runtime) == ["Maykop alert 2", "Maykop alert 1"]
    # Scanning again doesn't scramble more against the same raid.
    _scan(runtime)
    assert len(_activated(runtime)) == 2


def test_no_scramble_into_a_raid_beyond_the_odds() -> None:
    runtime = _runtime()
    runtime.execute(r"""
        dcsRetribution.GCI.red.maxOdds = "1"
        for i = 1, 6 do
            aircraft["F-16 " .. i] = { x = 40000 + i * 100, z = 5000, coalition = 2 }
            table.insert(radarSees, "F-16 " .. i)
        end
    """)
    # Six raiders against the four alert aircraft in the sector: beyond 1:1.
    _scan(runtime)
    assert _activated(runtime) == []


def test_no_scramble_without_radar_contact() -> None:
    runtime = _runtime()
    runtime.execute(r"""
        aircraft["F-16 1"] = { x = 40000, z = 0, coalition = 2 }
        radarAlive = false
        table.insert(radarSees, "F-16 1")
    """)
    _scan(runtime)
    assert _activated(runtime) == []


def test_small_raid_and_out_of_sector() -> None:
    runtime = _runtime()
    runtime.execute(r"""
        aircraft["pair 1"] = { x = 30000, z = 0, coalition = 2 }
        aircraft["pair 2"] = { x = 30500, z = 0, coalition = 2 }
        aircraft["far"] = { x = 900000, z = 0, coalition = 2 }
        aircraft["own"] = { x = 20000, z = 0, coalition = 1 }
        radarSees = { "pair 1", "pair 2", "far", "own" }
    """)
    _scan(runtime)
    assert _activated(runtime) == ["Maykop alert 2"]


def test_skynet_config_parses() -> None:
    runtime = lupa.LuaRuntime()
    source = (PLUGINS / "skynetiads" / "skynetiads-config.lua").read_text(
        encoding="utf-8"
    )
    # Compiles without running (load returns nil and the error on syntax errors).
    ok = runtime.eval(
        "function(src) local f, err = load(src); return f ~= nil, err end"
    )(source)
    assert ok[0], ok[1]


def test_generator_writes_alert_groups(monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from game.commander.jfacc import planner
    from game.missiongenerator.luagenerator import LuaData, LuaGenerator
    from game.missiongenerator.missiondata import AlertGroupInfo, MissionData

    monkeypatch.setattr(planner, "profile_for", lambda game, player: None)
    generator = LuaGenerator.__new__(LuaGenerator)
    generator.game = SimpleNamespace()  # type: ignore[assignment]
    generator.mission_data = MissionData()
    generator.mission_data.alert_groups.append(
        AlertGroupInfo("Maykop alert 1", False, 1000.4, -2000.6, 185200.0)
    )
    lua_data = LuaData("dcsRetribution")
    generator.generate_gci_data(lua_data)
    runtime = lupa.LuaRuntime()
    runtime.execute("env = { info = function() end }")
    runtime.execute(lua_data.create_operations_lua())
    gci = runtime.globals().dcsRetribution.GCI
    alert = gci.red.alerts[1]
    assert (alert.group, alert.x, alert.y, alert.radius) == (
        "Maykop alert 1",
        "1000",
        "-2001",
        "185200",
    )
    assert gci.red.maxPerRaid == "2"
    assert len(gci.blue.alerts) == 0
