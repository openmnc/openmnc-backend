"""
Motor async MongoDB client for OpenMNC backend.
"""

import os
import asyncio
import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017/openmnc")
DB_NAME: str = "openmnc"

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        kwargs = {}
        if "mongodb+srv://" in MONGODB_URI or "ssl=true" in MONGODB_URI.lower() or "tls=true" in MONGODB_URI.lower():
            kwargs["tlsCAFile"] = certifi.where()
        _client = AsyncIOMotorClient(MONGODB_URI, **kwargs)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[DB_NAME]


def get_collection(name: str):
    return get_database()[name]


async def init_indexes() -> None:
    """Ensure unique and sorting indexes exist for sub-millisecond query execution."""
    try:
        db = get_database()
        await db.services.create_index("slug", unique=True, background=True)
        await db.services.create_index("order", background=True)
        await db.blogs.create_index("slug", unique=True, background=True)
        await db.blogs.create_index([("is_published", 1), ("created_at", -1)], background=True)
        await db.careers.create_index("is_active", background=True)
        await db.site_settings.create_index("key", unique=True, background=True)
        print("[DB] Critical lookup indexes verified (services.slug, blogs.slug, site_settings.key).")
    except Exception as e:
        print(f"[DB Index Note] Index creation non-blocking note: {e}")


async def connect_db() -> None:
    """Call on app startup to verify connection."""
    try:
        client = get_client()
        # Ping to verify connection with a short timeout so the app can still boot
        await asyncio.wait_for(client.admin.command("ping"), timeout=8.0)
        print(f"[DB] Connected to MongoDB — database: {DB_NAME}")
        await init_indexes()
    except Exception as e:
        print(f"[DB WARNING] Initial MongoDB ping failed: {e}")
        print("[DB NOTE] Server will continue running. Please ensure your MongoDB Atlas IP Access List includes 0.0.0.0/0 (Allow access from anywhere).")


async def close_db() -> None:
    """Call on app shutdown to close connection."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        print("[DB] MongoDB connection closed.")
