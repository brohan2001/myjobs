-- Claim one task from the tiered domain-based ready queues.
--
-- ARGV[1] = wtype ("simple" or "browser")
-- ARGV[2] = now (float timestamp)
-- ARGV[3] = default_rate_delay (float seconds)
-- ARGV[4] = max_domains_to_check (int) for the scrape pass
-- ARGV[5] = lease_ttl (float seconds; lease set on claim — see #3159 / #3173)
--
-- Returns: {task_id, source_type, domain} or nil
--
-- Two passes (myjobs, 2026-10-15):
--   A. Board checks. Among due domains that aren't rate-limited, claim a monitor from the one
--      with the most due monitors. Monitors find new jobs and number under one per second
--      overall, so they always go first.
--   B. Page scrapes. jobseek's round-robin: tiers in order 0, 1, 2, the first max_check due
--      domains each, pop that domain's next task.
--   One pass used to do both, and a scrape backlog starved board checks twice over: tier-0
--   domains went first on every claim, and a shared throttle key such as "greenhouse"
--   (~1,400 boards) got one claim per round of all domains. On 2026-10-14, 2,371 of 2,845
--   boards were more than 2 h overdue.
--
-- Lease semantics (#3159 / #3173): a claim records "<task_type>|<domain>|<task_id>" in
-- inflight:<wtype> with score now + lease_ttl. The worker must call complete_task.lua (or
-- reschedule_task.lua); reap_expired.lua re-enqueues leases that expire.

local wtype = ARGV[1]
local now = tonumber(ARGV[2])
local default_delay = tonumber(ARGV[3])
local max_check = tonumber(ARGV[4]) or 10
local lease_ttl = tonumber(ARGV[5]) or 600

local MONITOR_SCAN = 2000  -- due domains examined in pass A

local function key(prefix, domain)
    return prefix .. wtype .. ":" .. domain
end

local function rate_limited(domain)
    local rl_val = redis.call("GET", "ratelimit:" .. domain)
    if rl_val and tonumber(rl_val) > now then
        return tonumber(rl_val)
    end
    return nil
end

local function pop_due(prefix, domain)
    local ft = redis.call("ZPOPMIN", key("ft_" .. prefix, domain), 1)
    if #ft >= 2 then
        return ft[1]
    end
    local due = redis.call("ZRANGEBYSCORE", key(prefix, domain), "-inf", tostring(now), "LIMIT", 0, 1)
    if #due > 0 then
        redis.call("ZREM", key(prefix, domain), due[1])
        return due[1]
    end
    return nil
end

local function earliest(zkey)
    local r = redis.call("ZRANGE", zkey, 0, 0, "WITHSCORES")
    if #r >= 2 then
        return tonumber(r[2])
    end
    return nil
end

-- Rate-limit the domain, record the lease, and re-file the domain in the tier of its next task
-- (first-time work → 0, else the earlier of next monitor (1) and next scrape (2)).
local function finish(ready_key, domain, task_id, source_type)
    local rate_delay = tonumber(redis.call("GET", "delay:" .. domain) or default_delay)
    redis.call("SET", "ratelimit:" .. domain, tostring(now + rate_delay), "EX", math.ceil(rate_delay) + 1)
    redis.call("ZREM", ready_key, domain)
    redis.call("ZADD", "inflight:" .. wtype, now + lease_ttl, source_type .. "|" .. domain .. "|" .. task_id)

    local ft_score = earliest(key("ft_monitors_", domain))
    local ft_scr = earliest(key("ft_scrapes_", domain))
    if ft_scr ~= nil and (ft_score == nil or ft_scr < ft_score) then
        ft_score = ft_scr
    end
    local mon_score = earliest(key("monitors_", domain))
    local scr_score = earliest(key("scrapes_", domain))

    local next_score, next_tier = nil, nil
    if ft_score ~= nil then
        next_score, next_tier = ft_score, 0
    end
    if mon_score ~= nil and (next_score == nil or mon_score < next_score) then
        next_score, next_tier = mon_score, 1
    end
    if scr_score ~= nil and (next_score == nil or scr_score < next_score) then
        next_score, next_tier = scr_score, 2
    end
    if next_score ~= nil then
        redis.call("ZADD", "ready:" .. wtype .. ":" .. next_tier, math.max(now + rate_delay, next_score), domain)
    end
    return {task_id, source_type, domain}
end

-- Pass A: board checks, longest queue first. A shared throttle key such as "greenhouse" holds
-- ~1,400 boards; served one domain per turn it would get one check per round of ~1,500 company
-- domains. Picking the non-rate-limited domain with the most due checks drains big backlogs at
-- their rate limit, and everything else is served in between.
local best_domain, best_key, best_backlog = nil, nil, 0
for tier = 0, 2 do
    local ready_key = "ready:" .. wtype .. ":" .. tier
    local due = redis.call("ZRANGEBYSCORE", ready_key, "-inf", tostring(now), "LIMIT", 0, MONITOR_SCAN)
    for _, domain in ipairs(due) do
        local backlog = redis.call("ZCARD", key("ft_monitors_", domain))
            + redis.call("ZCOUNT", key("monitors_", domain), "-inf", tostring(now))
        if backlog > best_backlog and not rate_limited(domain) then
            best_domain, best_key, best_backlog = domain, ready_key, backlog
        end
    end
end
if best_domain then
    return finish(best_key, best_domain, pop_due("monitors_", best_domain), "monitor")
end

-- Pass B: page scrapes (and any monitor pass A couldn't reach), jobseek's round-robin.
for tier = 0, 2 do
    local ready_key = "ready:" .. wtype .. ":" .. tier
    local candidates = redis.call("ZRANGEBYSCORE", ready_key, "-inf", tostring(now), "LIMIT", 0, max_check)
    for _, domain in ipairs(candidates) do
        local rl_at = rate_limited(domain)
        if rl_at then
            -- Rate-limited: move it to when it becomes available
            redis.call("ZADD", ready_key, rl_at, domain)
        else
            local task_id = pop_due("monitors_", domain)
            local source_type = "monitor"
            if not task_id then
                task_id = pop_due("scrapes_", domain)
                source_type = "scrape"
            end
            if task_id then
                return finish(ready_key, domain, task_id, source_type)
            end
            -- Domain had no claimable tasks — remove from ready queue
            redis.call("ZREM", ready_key, domain)
        end
    end
end

return nil
