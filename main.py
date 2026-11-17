"""
OpenMNC LLP — FastAPI main application entry point.
Includes:
- Gzip HTTP response compression for ultra-low MB/KB bandwidth and lightning speed
- Built-in Keep-Alive Anti-Sleep ping background task (prevents Render/Koyeb 15-minute dyno sleeping)
- Comprehensive health and latency monitoring
"""

import os
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import httpx

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from database import connect_db, close_db
from routers import auth as auth_router
from routers import services as services_router
from routers import careers as careers_router
from routers import settings as settings_router
from routers import contact as contact_router
from routers import blogs as blogs_router
from routers import media as media_router

logger = logging.getLogger("openmnc.main")
SERVER_START_TIME = time.time()

# Keep-alive anti-sleep configuration
PING_SELF_URL = os.getenv("PING_SELF_URL", "")
PING_INTERVAL_SECONDS = int(os.getenv("PING_INTERVAL_SECONDS", "600"))  # Default: 10 minutes


async def keep_alive_ping_task():
    """
    Background worker that pings this server periodically.
    Render/Koyeb free web services spin down after 15 minutes of inactivity.
    By pinging every 10 minutes (600s), the service stays alive and warm 24/7!
    """
    if not PING_SELF_URL or not PING_SELF_URL.startswith("http"):
        logger.info("[KeepAlive] PING_SELF_URL not configured. Self-ping idle (use cron-job.org or set PING_SELF_URL).")
        return

    logger.info(f"[KeepAlive] Starting 24/7 Anti-Sleep Keep-Alive loop hitting {PING_SELF_URL} every {PING_INTERVAL_SECONDS}s.")
    await asyncio.sleep(30)  # Wait for initial boot

    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            try:
                res = await client.get(PING_SELF_URL)
                logger.info(f"[KeepAlive] Keep-alive ping dispatched: Status {res.status_code}")
            except Exception as e:
                logger.warning(f"[KeepAlive] Ping warning: {e}")
            await asyncio.sleep(PING_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_db()
    ping_task = asyncio.create_task(keep_alive_ping_task())
    yield
    # Shutdown
    ping_task.cancel()
    await close_db()


app = FastAPI(
    title="OpenMNC LLP API",
    description="Backend API for OpenMNC LLP company website.",
    version="1.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Compression Middleware — Compress any JSON/HTTP response over 500 bytes
# Drastically reduces bandwidth usage and accelerates mobile page loads
# ---------------------------------------------------------------------------
app.add_middleware(GZipMiddleware, minimum_size=500)

# ---------------------------------------------------------------------------
# CORS — allow all origins
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router.router)
app.include_router(services_router.router)
app.include_router(careers_router.router)
app.include_router(settings_router.router)
app.include_router(contact_router.router)
app.include_router(blogs_router.router)
app.include_router(media_router.router)

# Mount uploads directory for resume and document serving
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


ROBOTS_TXT = """User-agent: *
Allow: /
Sitemap: https://openmnc.com/sitemap.xml
"""

# ---------------------------------------------------------------------------
# Keep-Alive & Health endpoints (supports both GET and HEAD for Render/cloud probes)
# ---------------------------------------------------------------------------
@app.api_route("/", methods=["GET", "HEAD"], tags=["health"])
async def root():
    """Root entry point — returns 200 OK so visiting backend directly in browser never 404s."""
    uptime_sec = int(time.time() - SERVER_START_TIME)
    return {
        "status": "online",
        "service": "OpenMNC API Gateway",
        "version": "1.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime_sec,
        "endpoints": {
            "ping": "/ping",
            "health": "/health",
            "api_ping": "/api/ping",
            "docs": "/docs",
        },
    }


@app.api_route("/ping", methods=["GET", "HEAD"], tags=["health"])
@app.api_route("/health", methods=["GET", "HEAD"], tags=["health"])
@app.api_route("/api/ping", methods=["GET", "HEAD"], tags=["health"])
@app.api_route("/api/health", methods=["GET", "HEAD"], tags=["health"])
async def ping():
    """High-frequency keep-alive endpoint for cron-job.org / UptimeRobot / internal loop."""
    uptime_sec = int(time.time() - SERVER_START_TIME)
    return {
        "status": "ok",
        "service": "OpenMNC API",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime_sec,
        "compression": "gzip_enabled",
        "keep_alive": "active" if bool(PING_SELF_URL) else "standby",
    }


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
async def robots_txt():
    """robots.txt — welcoming all major crawlers and AI bots."""
    return ROBOTS_TXT
