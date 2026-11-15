"""
OpenMNC LLP — FastAPI main application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from database import connect_db, close_db
from routers import auth as auth_router
from routers import services as services_router
from routers import careers as careers_router
from routers import settings as settings_router
from routers import contact as contact_router
from routers import blogs as blogs_router
from routers import media as media_router


ROBOTS_TXT = """\
User-agent: *
Allow: /

User-agent: GPTBot
Allow: /

User-agent: Claude-Web
Allow: /

User-agent: anthropic-ai
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Googlebot
Allow: /

Sitemap: https://openmnc.com/sitemap.xml
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_db()
    yield
    # Shutdown
    await close_db()


app = FastAPI(
    title="OpenMNC LLP API",
    description="Backend API for OpenMNC LLP company website.",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow all origins (configure more strictly in production if needed)
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


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------
@app.get("/ping", tags=["health"])
async def ping():
    """Health check endpoint."""
    return {"status": "ok", "message": "OpenMNC API alive"}


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
async def robots_txt():
    """robots.txt — welcoming all major crawlers and AI bots."""
    return ROBOTS_TXT
