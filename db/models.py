import os
from supabase import create_client, Client
from shared.exceptions import DBError
from shared.logger import logger

_client: Client | None = None

# ── Shared in-memory plan cache ────────────────────────────────────────────────
# Used as a fallback when Supabase writes fail or haven't completed yet.
# Both main.py and agent_routes.py should read/write through get_plan_cached().
PLAN_CACHE: dict[str, dict] = {}


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
    """Update plan status (pending, approved, rejected, executing, executed, failed)."""
    # Sync cache first
    if plan_id in PLAN_CACHE:
        PLAN_CACHE[plan_id]["status"] = status
    
    client = get_supabase()
    result = client.table("plans").update({"status": status}).eq("id", plan_id).execute()
    return result.data[0] if result.data else {}


def save_plan(data: dict) -> dict:
    """
    Upsert a plan record with full metadata.
    Expects: user_email, goal_type, risk_level, risk_score, policy_decision,
             subject, sender, intent_json, plan_json  (all serializable dicts/primitives).
    Returns the saved row including id.
    """
    client = get_supabase()
    result = client.table("plans").insert(data).execute()
    return result.data[0]


def get_plan(plan_id: str) -> dict | None:
    """Fetch a full plan row by UUID."""
    client = get_supabase()
    result = client.table("plans").select("*").eq("id", plan_id).limit(1).execute()
    return result.data[0] if result.data else None


def get_plan_cached(plan_id: str) -> dict | None:
    """
    Fetch a plan — checks in-memory PLAN_CACHE first, then Supabase.
    Use this everywhere instead of get_plan() so plans survive Supabase write failures.
    """
    if plan_id in PLAN_CACHE:
        return PLAN_CACHE[plan_id]
    row = get_plan(plan_id)
    if row:
        PLAN_CACHE[plan_id] = row   # warm the cache for future reads
    return row


def update_plan(plan_id: str, updates: dict) -> dict:
    """Partial-update a plan row."""
    # Sync cache first
    if plan_id in PLAN_CACHE:
        PLAN_CACHE[plan_id].update(updates)
    
    client = get_supabase()
    result = client.table("plans").update(updates).eq("id", plan_id).execute()
    return result.data[0] if result.data else {}


def get_pending_plans(user_email: str) -> list[dict]:
    """Return all pending plans for a user, newest first."""
    client = get_supabase()
    result = (
        client.table("plans")
        .select("id, goal_type, risk_level, risk_score, subject, sender, created_at, policy_decision")
        .eq("user_email", user_email)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return result.data


def get_history_plans(user_email: str, limit: int = 20) -> list[dict]:
    """Return recent approved/executed/rejected plans for the dashboard history view."""
    client = get_supabase()
    result = (
        client.table("plans")
        .select("id, goal_type, risk_level, risk_score, status, subject, sender, created_at, reject_reason, execution_log, plan_json")
        .eq("user_email", user_email)
        .in_("status", ["approved", "executed", "rejected", "failed"])
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


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


def save_gmail_tokens(user_id: str, refresh_token: str, history_id: str | None = None) -> dict:
    """Upsert Gmail OAuth refresh token (and optionally last history ID) on a profile.

    Requires profiles table to have:
      google_refresh_token text
      last_history_id      text
    """
    client = get_supabase()
    payload: dict = {"google_refresh_token": refresh_token}
    if history_id is not None:
        payload["last_history_id"] = str(history_id)
    result = (
        client.table("profiles")
        .update(payload)
        .eq("id", user_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def get_gmail_token(email_address: str) -> dict | None:
    """Fetch google_refresh_token and last_history_id for a user by email.

    Returns a dict with keys 'id', 'google_refresh_token', 'last_history_id',
    or None if the user is not found.
    """
    client = get_supabase()
    result = (
        client.table("profiles")
        .select("id, google_refresh_token, last_history_id")
        .eq("email", email_address)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None
