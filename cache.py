"""
RAM-based TTL Cache for FastAPI endpoints.
Bypasses MongoDB round-trips on 0.1 CPU Render instances.
Stores parsed JSON responses in memory (< 5MB) for 5-10ms response times.
"""

import logging
from cachetools import TTLCache

logger = logging.getLogger("openmnc.cache")

# Stores up to 200 API responses in RAM for 10 minutes (600 seconds)
api_cache = TTLCache(maxsize=200, ttl=600)


def get_cached(key: str):
    """Retrieve value from cache if present and unexpired."""
    val = api_cache.get(key)
    if val is not None:
        logger.debug(f"[Cache HIT] {key}")
    return val


def set_cached(key: str, value):
    """Store value in RAM cache."""
    try:
        api_cache[key] = value
        logger.debug(f"[Cache SET] {key}")
    except Exception as e:
        logger.warning(f"[Cache Error] Failed to cache {key}: {e}")


def invalidate_cache(prefix: str = ""):
    """
    Clear cache entries.
    If prefix is provided, only invalidate matching keys.
    If prefix is empty, clear the entire cache.
    """
    if not prefix:
        api_cache.clear()
        logger.info("[Cache CLEAR] Entire API cache cleared.")
    else:
        keys_to_del = [k for k in api_cache.keys() if str(k).startswith(prefix)]
        for k in keys_to_del:
            api_cache.pop(k, None)
        logger.info(f"[Cache INVALIDATE] Cleared keys with prefix '{prefix}'.")
