"""
Async Redis client — singleton initialized at app startup.

Used for start-ping duration tracking: stores the ISO timestamp of a /start
ping keyed by monitor UUID, with a TTL so stale starts auto-expire.
"""
from redis.asyncio import Redis

from app.config import settings

_redis: Redis | None = None

# Start pings expire after 24h — if a job hasn't completed in 24h, the
# duration is meaningless anyway.
START_PING_TTL_SECONDS = 86400


async def init_redis() -> None:
    global _redis
    import logging
    logger = logging.getLogger(__name__)
    try:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=5)
        await _redis.ping()
        logger.info("Redis connected: %s", settings.redis_url)
    except Exception as e:
        logger.warning("Redis unavailable (%s) — duration tracking disabled", e)
        _redis = None


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


def get_redis() -> Redis | None:
    return _redis
