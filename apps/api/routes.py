from fastapi import APIRouter, Depends, HTTPException

from db.models import ping_db, create_email, get_email
from apps.api.schemas import HealthResponse, EmailCreate, EmailOut, UserOut
from apps.api.auth import get_current_user

health_router = APIRouter(prefix="/health", tags=["Health"])
email_router = APIRouter(prefix="/emails", tags=["Emails"])


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


@email_router.post("/ingest", response_model=EmailOut, summary="Manually ingest an email")
async def ingest_email(
    email_data: EmailCreate,
    current_user: UserOut = Depends(get_current_user)
):
    """
    Manually push an email into the system. 
    This is used for development and manual testing.
    """
    # Ensure user_id matches current user if provided, otherwise set it
    if not email_data.user_id:
        email_data.user_id = current_user.id
        
    try:
        saved_email = create_email(email_data.model_dump())
        return saved_email
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@email_router.get("/{email_id}", response_model=EmailOut, summary="Fetch an email by ID")
async def fetch_email(
    email_id: str,
    current_user: UserOut = Depends(get_current_user)
):
    """Retrieve email details from the database."""
    email = get_email(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Optional: Check ownership
    if email["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    return email
