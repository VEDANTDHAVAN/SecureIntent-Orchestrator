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
