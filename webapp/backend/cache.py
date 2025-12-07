"""
Redis Cache Module for View Counter WebApp

Provides caching functionality to speed up API responses:
- Project analytics caching (5 min TTL)
- User analytics caching (5 min TTL)
- Finished projects caching (1 hour TTL)
- Cache invalidation on data updates
"""

import redis
import json
import logging
import os
from typing import Optional, Any
from datetime import timedelta

logger = logging.getLogger(__name__)

class RedisCache:
    """Redis cache manager with automatic serialization and TTL management"""

    def __init__(self):
        """Initialize Redis connection"""
        # Get Redis configuration from environment variables
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        redis_password = os.getenv('REDIS_PASSWORD', None)
        redis_db = int(os.getenv('REDIS_DB', 0))

        try:
            self.client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                db=redis_db,
                decode_responses=True,  # Auto-decode bytes to strings
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self.client.ping()
            logger.info(f"✅ Redis connected: {redis_host}:{redis_port}")
            self.enabled = True
        except Exception as e:
            logger.warning(f"⚠️ Redis not available, caching disabled: {e}")
            self.client = None
            self.enabled = False

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value (deserialized from JSON) or None if not found
        """
        if not self.enabled:
            return None

        try:
            value = self.client.get(key)
            if value:
                logger.debug(f"🎯 Cache HIT: {key}")
                return json.loads(value)
            logger.debug(f"❌ Cache MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"Redis GET error for key '{key}': {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Set value in cache with TTL

        Args:
            key: Cache key
            value: Value to cache (will be serialized to JSON)
            ttl: Time to live in seconds (default: 5 minutes)

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        try:
            serialized = json.dumps(value, ensure_ascii=False)
            self.client.setex(key, ttl, serialized)
            logger.debug(f"💾 Cache SET: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Redis SET error for key '{key}': {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete value from cache

        Args:
            key: Cache key or pattern (e.g., "project:*")

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        try:
            # If key contains wildcard, delete all matching keys
            if '*' in key:
                keys = self.client.keys(key)
                if keys:
                    self.client.delete(*keys)
                    logger.info(f"🗑️ Cache DELETE: {len(keys)} keys matching '{key}'")
                    return True
            else:
                result = self.client.delete(key)
                logger.info(f"🗑️ Cache DELETE: {key}")
                return bool(result)
        except Exception as e:
            logger.error(f"Redis DELETE error for key '{key}': {e}")
            return False

    def invalidate_project(self, project_id: str) -> bool:
        """
        Invalidate all cache entries for a specific project

        Args:
            project_id: Project ID

        Returns:
            True if successful
        """
        patterns = [
            f"analytics:project:{project_id}",
            f"analytics:user:*:project:{project_id}",
            f"project:{project_id}:*"
        ]

        for pattern in patterns:
            self.delete(pattern)

        logger.info(f"🧹 Invalidated cache for project: {project_id}")
        return True

    def invalidate_user_project(self, user_id: int, project_id: str) -> bool:
        """
        Invalidate cache for specific user's project analytics

        Args:
            user_id: Telegram user ID
            project_id: Project ID

        Returns:
            True if successful
        """
        key = f"analytics:user:{user_id}:project:{project_id}"
        self.delete(key)
        logger.info(f"🧹 Invalidated user cache: user={user_id}, project={project_id}")
        return True

    def get_or_set(self, key: str, func, ttl: int = 300, *args, **kwargs) -> Any:
        """
        Get from cache or compute and cache the result

        Args:
            key: Cache key
            func: Function to call if cache miss
            ttl: Time to live in seconds
            *args, **kwargs: Arguments to pass to func

        Returns:
            Cached or computed value
        """
        # Try to get from cache
        cached = self.get(key)
        if cached is not None:
            return cached

        # Cache miss - compute value
        result = func(*args, **kwargs)

        # Cache the result
        self.set(key, result, ttl)

        return result

    async def get_or_set_async(self, key: str, func, ttl: int = 300, *args, **kwargs) -> Any:
        """
        Async version of get_or_set

        Args:
            key: Cache key
            func: Async function to call if cache miss
            ttl: Time to live in seconds
            *args, **kwargs: Arguments to pass to func

        Returns:
            Cached or computed value
        """
        # Try to get from cache
        cached = self.get(key)
        if cached is not None:
            return cached

        # Cache miss - compute value
        result = await func(*args, **kwargs)

        # Cache the result
        self.set(key, result, ttl)

        return result


# TTL Constants (in seconds)
TTL_PROJECT_ANALYTICS = 300      # 5 minutes - active projects
TTL_USER_ANALYTICS = 300         # 5 minutes - user's project data
TTL_FINISHED_PROJECT = 3600      # 1 hour - finished projects (they don't change)
TTL_LEADERBOARD = 600            # 10 minutes - top accounts
TTL_HISTORY = 86400              # 24 hours - historical daily data


# Global cache instance
cache = RedisCache()


# Helper functions for common cache keys
def get_project_analytics_key(project_id: str) -> str:
    """Generate cache key for project analytics"""
    return f"analytics:project:{project_id}"


def get_user_analytics_key(user_id: int, project_id: str) -> str:
    """Generate cache key for user's project analytics"""
    return f"analytics:user:{user_id}:project:{project_id}"


def get_project_list_key(user_id: int) -> str:
    """Generate cache key for user's project list"""
    return f"projects:user:{user_id}"
