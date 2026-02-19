import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt

from db.models import get_supabase
from shared.constants import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, UserRole
from shared.exceptions import AuthError
from shared.logger import logger
from apps.api.schemas import UserOut, TokenResponse

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _build_google_auth_url() -> str:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    scope = "openid email profile"
    return (
        f"{GOOGLE_AUTH_URL}"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&access_type=offline"
        f"&prompt=select_account"
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


def _upsert_user(userinfo: dict) -> dict:
    """Upsert user into Supabase `users` table and return the row."""
    supabase = get_supabase()
    google_id = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name")

    existing = (
        supabase.table("profiles")
        .select("*")
        .eq("email", email)
        .limit(1)
        .execute()
        .data
    )

    if existing:
        return existing[0]

    new_user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "role": UserRole.USER.value,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = supabase.table("profiles").insert(new_user).execute()
    return result.data[0]


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@auth_router.get("/login", summary="Redirect to Google OAuth consent screen")
def login():
    url = _build_google_auth_url()
    logger.info("Redirecting to Google OAuth")
    return RedirectResponse(url)


@auth_router.get("/callback", response_model=TokenResponse, summary="OAuth callback — returns JWT")
async def callback(code: str, request: Request):
    try:
        tokens = await _exchange_code_for_tokens(code)
        userinfo = await _get_google_userinfo(tokens["access_token"])
        user_row = _upsert_user(userinfo)

        jwt_token = _create_jwt(
            {"sub": user_row["id"], "email": user_row["email"], "role": user_row["role"]}
        )

        logger.info("User authenticated: %s", user_row["email"])
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
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        return UserOut(
            id=payload["sub"],
            email=payload["email"],
            role=payload.get("role", "user"),
        )
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token")
