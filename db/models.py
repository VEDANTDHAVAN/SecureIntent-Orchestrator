import os
from supabase import create_client, Client
from shared.exceptions import DBError
from shared.logger import logger

_client: Client | None = None


def get_supabase() -> Client:
    """Return a singleton Supabase client, initialised from env vars."""
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise DBError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        _client = create_client(url, key)
    return _client


def ping_db() -> bool:
    """Lightweight connectivity check — reads one row from the users table.

    Returns True if the query succeeds, False otherwise.
    Does NOT raise so the health endpoint can report gracefully.
    """
    try:
        client = get_supabase()
        # .limit(1) ensures we fetch at most one row regardless of table size
        client.table("profiles").select("id").limit(1).execute()
        logger.info("Supabase ping succeeded")
        return True
    except Exception as exc:
        logger.error("Supabase ping failed: %s", exc)
        return False


# --- CRUD Helpers ---

def create_email(data: dict) -> dict:
    """Save a new email record."""
    client = get_supabase()
    result = client.table("emails").insert(data).execute()
    return result.data[0]


def get_email(email_id: str) -> dict | None:
    """Fetch a single email by ID."""
    client = get_supabase()
    result = client.table("emails").select("*").eq("id", email_id).execute()
    return result.data[0] if result.data else None


def create_intent(data: dict) -> dict:
    """Save an extracted intent."""
    client = get_supabase()
    result = client.table("extracted_intents").insert(data).execute()
    return result.data[0]


def get_intents_for_email(email_id: str) -> list[dict]:
    """Fetch all intents associated with an email."""
    client = get_supabase()
    result = client.table("extracted_intents").select("*").eq("email_id", email_id).execute()
    return result.data


def create_plan(data: dict) -> dict:
    """Save an execution plan."""
    client = get_supabase()
    result = client.table("plans").insert(data).execute()
    return result.data[0]


def get_plan_by_intent(intent_id: str) -> dict | None:
    """Fetch the plan for a specific intent."""
    client = get_supabase()
    result = client.table("plans").select("*").eq("intent_id", intent_id).execute()
    return result.data[0] if result.data else None


def update_plan_status(plan_id: str, status: str) -> dict:
    """Update plan status (pending, approved, rejected, executed)."""
    client = get_supabase()
    result = client.table("plans").update({"status": status}).eq("id", plan_id).execute()
    return result.data[0]


def create_risk_score(data: dict) -> dict:
    """Save a risk score record."""
    client = get_supabase()
    result = client.table("risk_scores").insert(data).execute()
    return result.data[0]


def get_risk_score_for_email(email_id: str) -> dict | None:
    """Fetch the risk score for an email."""
    client = get_supabase()
    result = client.table("risk_scores").select("*").eq("email_id", email_id).execute()
    return result.data[0] if result.data else None


def log_action(data: dict) -> dict:
    """Log a system or user action."""
    client = get_supabase()
    result = client.table("action_logs").insert(data).execute()
    return result.data[0]
