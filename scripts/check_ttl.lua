-- Redis TTL audit helper for iterlog keys.
-- Usage:
--   redis-cli --eval scripts/check_ttl.lua [, pattern, limit]
-- Defaults:
--   pattern = bmad:chiseai:iterlog:story:*
--   limit = 200

local pattern = ARGV[1] or "bmad:chiseai:iterlog:story:*"
local limit = tonumber(ARGV[2]) or 200
local cursor = "0"
local out = {}

repeat
  local res = redis.call("SCAN", cursor, "MATCH", pattern, "COUNT", 100)
  cursor = res[1]
  local keys = res[2]

  for _, key in ipairs(keys) do
    local ttl = redis.call("TTL", key)
    table.insert(out, key .. "\t" .. ttl)
    if #out >= limit then
      cursor = "0"
      break
    end
  end
until cursor == "0"

return out
