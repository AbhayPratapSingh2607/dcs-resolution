-------------------------------------------------------------------------------
-- DCS Retribution: GCI ground alert scrambles
--
-- The air campaign planner holds fighter pairs on ground alert: late-activated
-- groups at the runway end, listed in dcsRetribution.GCI with the station and
-- sector radius of each. Every scan interval, each coalition's GCI looks at
-- what its own early warning radars and AWACS detect, groups the enemy aircraft
-- into raids (contacts within raidClusterMeters of each other) and activates
-- the nearest alert pairs whose sector holds the raid: no more than maxPerRaid
-- pairs, and one pair per two raiders. The activated pair flies its CAP route
-- to the station and is told to engage air targets around the raid.
--
-- The same rules as the fast-forward GCI (game/sim/gci.py). A coalition whose
-- radars are dead or jammed sees nothing and scrambles nothing.
-------------------------------------------------------------------------------

if not dcsRetribution or not dcsRetribution.GCI then
    env.info("DCSRetribution|GCI - no GCI data in the mission, plugin idle")
    return
end

local GCI = {
    scanInterval = 15,
    announce = false,
    debug = false,
    activated = {},
    committed = { blue = {}, red = {} },
}

if dcsRetribution.plugins and dcsRetribution.plugins.gci then
    local options = dcsRetribution.plugins.gci
    GCI.scanInterval = tonumber(options.scanInterval) or GCI.scanInterval
    GCI.announce = options.announce == true or options.announce == "true"
    GCI.debug = options.debug == true or options.debug == "true"
end

local data = dcsRetribution.GCI
local clusterMeters = tonumber(data.raidClusterMeters) or 40000

local function log(fmt, ...)
    env.info("DCSRetribution|GCI - " .. string.format(fmt, ...))
end

local function debug(fmt, ...)
    if GCI.debug then
        log(fmt, ...)
    end
end

local sides = {
    { key = "blue", coalitionId = coalition.side.BLUE },
    { key = "red", coalitionId = coalition.side.RED },
}

-- Groups whose radars feed the coalition's GCI picture: early warning radars
-- and AWACS.
local function sensorGroups(coalitionId)
    local result = {}
    local categories = { Group.Category.GROUND, Group.Category.AIRPLANE }
    for _, category in ipairs(categories) do
        for _, group in ipairs(coalition.getGroups(coalitionId, category) or {}) do
            if group and group:isExist() then
                for _, unit in ipairs(group:getUnits() or {}) do
                    if unit and unit:isExist() and unit:isActive()
                        and (unit:hasAttribute("EWR") or unit:hasAttribute("AWACS")) then
                        table.insert(result, group)
                        break
                    end
                end
            end
        end
    end
    return result
end

-- Enemy aircraft in the air that the coalition's sensors detect by radar.
local function contacts(coalitionId)
    local seen = {}
    local result = {}
    for _, group in ipairs(sensorGroups(coalitionId)) do
        local controller = group:getController()
        local ok, detected = pcall(function()
            return controller:getDetectedTargets(Controller.Detection.RADAR)
        end)
        if ok and detected then
            for _, target in ipairs(detected) do
                local object = target.object
                if object and object:isExist()
                    and Object.getCategory(object) == Object.Category.UNIT
                    and object:getCoalition() ~= coalitionId then
                    local desc = object:getDesc()
                    local name = object:getName()
                    if desc and (desc.category == Unit.Category.AIRPLANE
                        or desc.category == Unit.Category.HELICOPTER)
                        and object:inAir() and not seen[name] then
                        seen[name] = true
                        local point = object:getPoint()
                        table.insert(result, { name = name, x = point.x, y = point.z })
                    end
                end
            end
        end
    end
    return result
end

local function cluster(list)
    local raids = {}
    for _, contact in ipairs(list) do
        local joined = false
        for _, raid in ipairs(raids) do
            local dx, dy = raid.x - contact.x, raid.y - contact.y
            if math.sqrt(dx * dx + dy * dy) <= clusterMeters then
                local n = raid.size
                raid.x = (raid.x * n + contact.x) / (n + 1)
                raid.y = (raid.y * n + contact.y) / (n + 1)
                raid.size = n + 1
                table.insert(raid.members, contact.name)
                joined = true
                break
            end
        end
        if not joined then
            table.insert(raids, { x = contact.x, y = contact.y, size = 1, members = { contact.name } })
        end
    end
    table.sort(raids, function(a, b) return a.size > b.size end)
    return raids
end

local function inSector(alert, raid)
    local dx = (tonumber(alert.x) or 0) - raid.x
    local dy = (tonumber(alert.y) or 0) - raid.y
    return math.sqrt(dx * dx + dy * dy) <= (tonumber(alert.radius) or 0)
end

-- Alert aircraft still on the ground that could meet the raid.
local function ableToMeet(alerts, raid)
    local able = 0
    for _, alert in ipairs(alerts) do
        if not GCI.activated[alert.group] and inSector(alert, raid) then
            local group = Group.getByName(alert.group)
            if group and group:isExist() then
                able = able + (tonumber(alert.size) or 2)
            end
        end
    end
    return able
end

local function nearestAlert(alerts, raid)
    local best, bestDistance = nil, math.huge
    for _, alert in ipairs(alerts) do
        if not GCI.activated[alert.group] then
            local group = Group.getByName(alert.group)
            if group and group:isExist() then
                local dx = (tonumber(alert.x) or 0) - raid.x
                local dy = (tonumber(alert.y) or 0) - raid.y
                local distance = math.sqrt(dx * dx + dy * dy)
                if distance <= (tonumber(alert.radius) or 0) and distance < bestDistance then
                    best, bestDistance = alert, distance
                end
            end
        end
    end
    return best
end

local function scramble(alert, raid, sideKey)
    local group = Group.getByName(alert.group)
    if not group then
        return false
    end
    GCI.activated[alert.group] = true
    trigger.action.activateGroup(group)
    log("%s scrambles %s against a raid of %d", sideKey, alert.group, raid.size)
    if GCI.announce then
        trigger.action.outText(string.format("GCI (%s): %s scrambled", sideKey, alert.group), 10)
    end
    local name, x, y = alert.group, raid.x, raid.y
    timer.scheduleFunction(function()
        local active = Group.getByName(name)
        if active and active:isExist() then
            local ok, err = pcall(function()
                active:getController():pushTask({
                    id = "EngageTargetsInZone",
                    params = {
                        point = { x = x, y = y },
                        zoneRadius = clusterMeters + 20000,
                        targetTypes = { "Air" },
                        priority = 0,
                    },
                })
            end)
            if not ok then
                debug("could not task %s: %s", name, tostring(err))
            end
        end
        return nil
    end, nil, timer.getTime() + 5)
    return true
end

local function scan()
    for _, side in ipairs(sides) do
        local sideData = data[side.key]
        local alerts = sideData and sideData.alerts or {}
        if #alerts > 0 then
            local maxPerRaid = tonumber(sideData.maxPerRaid) or 2
            local maxOdds = tonumber(sideData.maxOdds) or 3
            local raids = cluster(contacts(side.coalitionId))
            local committed = GCI.committed[side.key]
            for _, raid in ipairs(raids) do
                local launched = 0
                for _, member in ipairs(raid.members) do
                    launched = launched + (committed[member] or 0)
                end
                local wanted = math.min(maxPerRaid, math.max(1, math.ceil(raid.size / 2)))
                -- No pairs thrown at a raid that outnumbers them beyond the
                -- doctrine's odds (pairs already sent count, two each).
                local able = ableToMeet(alerts, raid) + 2 * math.min(launched, maxPerRaid)
                if raid.size > maxOdds * math.max(able, 1) then
                    debug("%s raid of %d too strong for %d alert aircraft", side.key, raid.size, able)
                    wanted = 0
                end
                debug("%s raid of %d at %d/%d, %d pairs committed", side.key, raid.size, raid.x, raid.y, launched)
                while launched < wanted do
                    local alert = nearestAlert(alerts, raid)
                    if not alert then
                        break
                    end
                    if not scramble(alert, raid, side.key) then
                        break
                    end
                    committed[raid.members[1]] = (committed[raid.members[1]] or 0) + 1
                    launched = launched + 1
                end
            end
        end
    end
    return timer.getTime() + GCI.scanInterval
end

log("ready: %d blue and %d red alert groups, scan every %d s",
    #((data.blue or {}).alerts or {}), #((data.red or {}).alerts or {}), GCI.scanInterval)
timer.scheduleFunction(scan, nil, timer.getTime() + GCI.scanInterval)
