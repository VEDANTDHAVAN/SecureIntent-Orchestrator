import base64
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jose import JWTError, jwt

from db.models import get_supabase, save_gmail_tokens
from shared.constants import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, UserRole
from shared.exceptions import AuthError
from shared.logger import logger
from apps.api.schemas import UserOut, TokenResponse

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _build_google_auth_url(source: str = "web") -> str:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    # Full scopes needed for read + send + calendar
    scope = (
        "openid email profile "
        "https://www.googleapis.com/auth/gmail.readonly "
        "https://www.googleapis.com/auth/gmail.send "
        "https://www.googleapis.com/auth/gmail.modify "
        "https://www.googleapis.com/auth/calendar "
        "https://www.googleapis.com/auth/documents "
        "https://www.googleapis.com/auth/drive.file"
    )
    # Encode source in state so callback knows where to redirect
    state = base64.urlsafe_b64encode(json.dumps({"source": source}).encode()).decode()
    return (
        f"{GOOGLE_AUTH_URL}"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&access_type=offline"
        f"&prompt=consent"    # force consent so we always get a refresh_token
        f"&state={state}"
    )


def _create_jwt(payload: dict) -> str:
    secret = os.getenv("JWT_SECRET")
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload.update({"exp": expire})
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


async def _exchange_code_for_tokens(code: str) -> dict:
    """POST to Google token endpoint to exchange auth code for tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
                "grant_type": "authorization_code",
            },
        )
    resp.raise_for_status()
    return resp.json()


async def _get_google_userinfo(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    resp.raise_for_status()
    return resp.json()


def _upsert_user(userinfo: dict, refresh_token: str | None = None) -> dict:
    """Upsert user into Supabase auth.users + profiles table."""
    supabase = get_supabase()
    email = userinfo.get("email")

    # 1. Check if profile already exists
    existing = (
        supabase.table("profiles")
        .select("*")
        .eq("email", email)
        .limit(1)
        .execute()
        .data
    )

    if existing:
        user_row = existing[0]
        # Update tokens if we received a new refresh_token
        if refresh_token:
            save_gmail_tokens(user_row["id"], refresh_token)
        return user_row

    # 2. Create user in Supabase Auth first (satisfies FK on profiles.id)
    try:
        auth_response = supabase.auth.admin.create_user({
            "email": email,
            "email_confirm": True,   # auto-confirm since they used Google
        })
        auth_user_id = auth_response.user.id
    except Exception as e:
        # User might already exist in auth.users (e.g. signed up differently)
        logger.warning("Auth create failed (may already exist): %s", e)
        users_list = supabase.auth.admin.list_users()
        auth_user_id = None
        for u in users_list:
            if u.email == email:
                auth_user_id = u.id
                break
        if not auth_user_id:
            raise

    # 3. Now insert profile with the real auth.users ID
    new_profile = {
        "id": str(auth_user_id),
        "email": email,
        "role": UserRole.USER.value,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = supabase.table("profiles").insert(new_profile).execute()
    user_row = result.data[0]

    # 4. Store Gmail refresh token if provided
    if refresh_token:
        save_gmail_tokens(user_row["id"], refresh_token)

    return user_row


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@auth_router.get("/login", summary="Redirect to Google OAuth consent screen")
def login(source: str = "web"):
    """source=extension → callback will render an HTML page instead of JSON."""
    url = _build_google_auth_url(source=source)
    logger.info("Redirecting to Google OAuth (source=%s)", source)
    return RedirectResponse(url)


@auth_router.get("/callback", summary="OAuth callback — returns JWT")
async def callback(code: str, request: Request, state: str = ""):
    # Decode source from state param
    source = "web"
    if state:
        try:
            decoded = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
            source = decoded.get("source", "web")
        except Exception:
            pass

    try:
        tokens = await _exchange_code_for_tokens(code)
        userinfo = await _get_google_userinfo(tokens["access_token"])
        refresh_token = tokens.get("refresh_token")
        user_row = _upsert_user(userinfo, refresh_token=refresh_token)

        jwt_token = _create_jwt(
            {"sub": user_row["id"], "email": user_row["email"], "role": user_row["role"]}
        )

        logger.info("User authenticated: %s (source=%s)", user_row["email"], source)

        # Extension flow: return an HTML page the background.js can read
        if source == "extension":
            return HTMLResponse(_extension_success_page(jwt_token, user_row["email"]))

        # Standard web flow: return JSON
        return TokenResponse(
            access_token=jwt_token,
            user=UserOut(**user_row),
        )
    except httpx.HTTPStatusError as exc:
        logger.error("Google OAuth error: %s", exc)
        raise HTTPException(status_code=400, detail="Google OAuth failed")
    except Exception as exc:
        logger.error("Callback error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


def _extension_success_page(token: str, email: str) -> str:
    """Minimal HTML page that embeds the JWT for the extension to capture."""
    return f"""
<!DOCTYPE html>
<html>
<head><title>SecureIntent — Authenticated</title>
<meta charset="utf-8">
<style>
  body {{ font-family: system-ui, sans-serif; background: #0f1117; color: #e2e8f0;
         display:flex; flex-direction:column; align-items:center; justify-content:center;
         height:100vh; margin:0; }}
  .card {{ background:#1a1f2e; border-radius:12px; padding:32px 40px; text-align:center; }}
  h2 {{ color:#7c8cf8; margin:0 0 8px; }}
  p {{ color:#718096; margin:0 0 4px; }}
  .check {{ font-size:48px; margin-bottom:16px; }}
</style>
</head>
<body>
<div class="card">
  <div class="check">✅</div>
  <h2>Signed in successfully</h2>
  <p>Logged in as <strong>{email}</strong></p>
  <p style="margin-top:12px;color:#4a5568;font-size:12px">This tab will close automatically…</p>
</div>
<!-- SecureIntent Extension Token (read by background.js) -->
<div id="si-token" data-token="{token}" data-email="{email}" style="display:none"></div>
<script>
  // Signal the extension background script
  window.__SI_TOKEN__ = "{token}";
  window.__SI_EMAIL__ = "{email}";
</script>
</body>
</html>
"""


# ──────────────────────────────────────────────
# Auth dependency
# ──────────────────────────────────────────────

async def get_current_user(request: Request) -> UserOut:
    """FastAPI dependency — decode JWT and return the current user."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.removeprefix("Bearer ").strip()
    try:
        secret = os.getenv("JWT_SECRET")
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM], options={"leeway": 30})
        return UserOut(
            id=payload["sub"],
            email=payload["email"],
            role=payload.get("role", "user"),
        )
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user_optional(request: Request) -> Optional[UserOut]:
    """Optional version of get_current_user for endpoints that work without auth."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        secret = os.getenv("JWT_SECRET")
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM], options={"leeway": 30})
        return UserOut(
            id=payload["sub"],
            email=payload["email"],
            role=payload.get("role", "user"),
        )
    except Exception:
        return None


# ──────────────────────────────────────────────
# Gmail Watch Setup
# ──────────────────────────────────────────────

@auth_router.get("/gmail/watch", summary="Register Gmail push notifications via Pub/Sub")
async def gmail_watch(current_user: UserOut = Depends(get_current_user)):
    """
    Calls Gmail API users.watch() to register a Pub/Sub push subscription
    for the authenticated user's inbox.

    Prerequisites:
    - GMAIL_PUBSUB_TOPIC must be set in .env  (e.g. projects/my-project/topics/gmail-push)
    - Pub/Sub topic must have granted publish permission to
      serviceAccount:gmail-api-push@system.gserviceaccount.com
    """
    from db.models import get_gmail_token
    from apps.api.gmail_service import build_gmail_service

    pubsub_topic = os.getenv("GMAIL_PUBSUB_TOPIC")
    if not pubsub_topic:
        raise HTTPException(status_code=500, detail="GMAIL_PUBSUB_TOPIC not configured")

    token_row = get_gmail_token(current_user.email)
    if not token_row or not token_row.get("google_refresh_token"):
        raise HTTPException(
            status_code=400,
            detail="No Gmail refresh token found. Please re-authenticate via /auth/login.",
        )

    try:
        service = build_gmail_service(token_row["google_refresh_token"])
        response = (
            service.users()
            .watch(
                userId=current_user.email,
                body={
                    "labelIds": ["INBOX"],
                    "topicName": pubsub_topic,
                },
            )
            .execute()
        )
        logger.info("Gmail watch registered for %s: %s", current_user.email, response)
        return {
            "status": "watch_registered",
            "historyId": response.get("historyId"),
            "expiration": response.get("expiration"),
        }
    except Exception as exc:
        logger.error("Gmail watch failed for %s: %s", current_user.email, exc)
        raise HTTPException(status_code=502, detail=f"Gmail watch failed: {exc}")
