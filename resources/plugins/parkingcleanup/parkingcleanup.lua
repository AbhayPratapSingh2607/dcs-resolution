-------------------------------------------------------------------------------
-- DCS Retribution: parking cleanup
--
-- AI aircraft that land and shut down stay parked for the rest of the mission,
-- filling ramps and carrier decks that later flights (and players) need, and
-- costing frame rate. This removes an AI aircraft some minutes after its
-- engines shut down, if it is still on the ground and stopped by then.
--
-- The removal is marked in dcsRetributionDespawned before the unit is
-- destroyed, so the base plugin doesn't record it as a loss. The aircraft
-- returns to its squadron as usual after the mission.
--
-- Player aircraft are never touched. Helicopters are left alone unless the
-- option says otherwise (CSAR and FARP helicopters may shut down in the field).
-------------------------------------------------------------------------------

local Cleanup = {
    delayMinutes = 10,
    helicopters = false,
    debug = false,
}

if dcsRetribution and dcsRetribution.plugins and dcsRetribution.plugins.parkingcleanup then
    local options = dcsRetribution.plugins.parkingcleanup
    Cleanup.delayMinutes = tonumber(options.delayMinutes) or Cleanup.delayMinutes
    Cleanup.helicopters = options.helicopters == true or options.helicopters == "true"
    Cleanup.debug = options.debug == true or options.debug == "true"
end

dcsRetributionDespawned = dcsRetributionDespawned or {}

local function log(message)
    if Cleanup.debug then
        env.info("DCSRetribution|ParkingCleanup - " .. message)
    end
end

local function isCandidate(unit)
    if not unit or not unit.isExist or not unit:isExist() then
        return false
    end
    if unit:getPlayerName() ~= nil then
        return false
    end
    local category = unit:getDesc().category
    if category == Unit.Category.AIRPLANE then
        return true
    end
    return category == Unit.Category.HELICOPTER and Cleanup.helicopters
end

local function stopped(unit)
    local v = unit:getVelocity()
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z) < 1
end

local function remove(name)
    local unit = Unit.getByName(name)
    if not unit or not unit:isExist() then
        return nil
    end
    if unit:inAir() or not stopped(unit) then
        -- Started up again (or never stopped): leave it.
        log(name .. " is moving, kept")
        return nil
    end
    dcsRetributionDespawned[name] = true
    log(name .. " removed from parking")
    unit:destroy()
    return nil
end

local handler = {}
function handler:onEvent(event)
    if event.id ~= world.event.S_EVENT_ENGINE_SHUTDOWN then
        return
    end
    local unit = event.initiator
    local ok, candidate = pcall(isCandidate, unit)
    if not ok or not candidate or unit:inAir() then
        return
    end
    local name = unit:getName()
    log(name .. " shut down, removal in " .. Cleanup.delayMinutes .. " min")
    timer.scheduleFunction(function()
        local removed, err = pcall(remove, name)
        if not removed then
            env.error("DCSRetribution|ParkingCleanup - " .. tostring(err))
        end
        return nil
    end, nil, timer.getTime() + Cleanup.delayMinutes * 60)
end

world.addEventHandler(handler)
env.info("DCSRetribution|ParkingCleanup - active, delay " .. Cleanup.delayMinutes .. " min")
