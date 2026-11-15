"""
Motor async MongoDB client for OpenMNC backend.
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017/openmnc")
DB_NAME: str = "openmnc"

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGODB_URI)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[DB_NAME]


def get_collection(name: str):
    return get_database()[name]


async def connect_db() -> None:
    """Call on app startup to verify connection."""
    client = get_client()
    # Ping to verify connection
    await client.admin.command("ping")
    print(f"[DB] Connected to MongoDB — database: {DB_NAME}")


async def close_db() -> None:
    """Call on app shutdown to close connection."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        print("[DB] MongoDB connection closed.")
