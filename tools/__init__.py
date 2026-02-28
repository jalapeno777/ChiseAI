"""Tools package for ChiseAI utilities."""

from tools.redis_state import (
    redis_state_delete,
    redis_state_expire,
    redis_state_get,
    redis_state_hdel,
    redis_state_hexists,
    redis_state_hget,
    redis_state_hgetall,
    redis_state_hset,
    redis_state_llen,
    redis_state_lpop,
    redis_state_lpush,
    redis_state_lrange,
    redis_state_rpop,
    redis_state_rpush,
    redis_state_sadd,
    redis_state_set,
    redis_state_smembers,
    redis_state_srem,
    redis_state_zadd,
    redis_state_zrange,
    redis_state_zrem,
)

__all__ = [
    "redis_state_delete",
    "redis_state_expire",
    "redis_state_get",
    "redis_state_hdel",
    "redis_state_hexists",
    "redis_state_hget",
    "redis_state_hgetall",
    "redis_state_hset",
    "redis_state_llen",
    "redis_state_lpop",
    "redis_state_lpush",
    "redis_state_lrange",
    "redis_state_rpop",
    "redis_state_rpush",
    "redis_state_sadd",
    "redis_state_set",
    "redis_state_smembers",
    "redis_state_srem",
    "redis_state_zadd",
    "redis_state_zrange",
    "redis_state_zrem",
]

# Aliases for compatibility
hgetall = redis_state_hgetall
