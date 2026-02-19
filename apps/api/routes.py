from fastapi import APIRouter

from db.models import ping_db
from apps.api.schemas import HealthResponse

health_router = APIRouter(prefix="/health", tags=["Health"])


@health_router.get("/", response_model=HealthResponse, summary="Liveness check")
def liveness():
    """Always returns 200 OK if the server is running."""
    return HealthResponse(status="ok")


@health_router.get("/db", response_model=HealthResponse, summary="Supabase connectivity check")
def db_health():
    """Pings Supabase and reports connectivity status."""
    connected = ping_db()
    return HealthResponse(
        status="ok" if connected else "degraded",
        db_connected=connected,
    )
