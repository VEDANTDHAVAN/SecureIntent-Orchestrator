import os
<<<<<<< HEAD
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# .env lives alongside this file in apps/api/.env
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.auth import auth_router
from apps.api.routes import health_router, email_router
from apps.api.webhooks import webhook_router
from db.models import ping_db
from shared.constants import APP_NAME, APP_VERSION
from shared.exceptions import SecureIntentError
from shared.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", APP_NAME, APP_VERSION)
    connected = ping_db()
    if connected:
        logger.info("✅ Supabase connected")
    else:
        logger.warning("⚠️  Supabase NOT reachable — check SUPABASE_URL and SUPABASE_SERVICE_KEY")
    yield
    logger.info("Shutting down %s", APP_NAME)


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Secure AI orchestration layer for intent-driven email actions.",
    lifespan=lifespan,
)

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# Routers
# ──────────────────────────────────────────────

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(webhook_router)
app.include_router(email_router)


# ──────────────────────────────────────────────
# Global exception handlers
# ──────────────────────────────────────────────

@app.exception_handler(SecureIntentError)
async def secure_intent_exception_handler(request: Request, exc: SecureIntentError):
    logger.error("SecureIntentError: %s", exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
