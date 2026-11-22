"""Email+password auth with opaque bearer tokens.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib, no extra deps).
Tokens are random urlsafe strings stored in `auth_sessions`; presenting one
maps to a user_id that scopes tracker data. No JWT dependency needed.
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel, Field

from .db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PBKDF2_ITERATIONS = 200_000
TOKEN_PREFIX = "cl_"
SESSION_TTL_DAYS = 30

_indexes_ready = False


# ---------------------------------------------------------------- models

class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)


class SignupRequest(Credentials):
    display_name: str | None = Field(default=None, max_length=60)


class AuthUser(BaseModel):
    id: str
    email: str
    display_name: str


class AuthResponse(BaseModel):
    token: str
    user: AuthUser


# ---------------------------------------------------------------- helpers

def _hash_password(password: str, salt_hex: str | None = None) -> str:
    salt_hex = salt_hex or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS
    )
    return f"{salt_hex}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(_hash_password(password, salt_hex), stored)


def _user_out(doc: dict[str, Any]) -> AuthUser:
    return AuthUser(
        id=str(doc["_id"]),
        email=doc.get("email", ""),
        display_name=doc.get("display_name") or doc.get("email", "").split("@")[0],
    )


async def _ensure_indexes() -> None:
    global _indexes_ready
    if not _indexes_ready:
        db = get_db()
        await db["users"].create_index("email", unique=True)
        await db["auth_sessions"].create_index("token", unique=True)
        await db["auth_sessions"].create_index("expires_at")
        _indexes_ready = True


async def _issue_token(user_id: str) -> str:
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await get_db()["auth_sessions"].insert_one(
        {
            "token": token,
            "user_id": user_id,
            "created_at": now,
            "expires_at": now + timedelta(days=SESSION_TTL_DAYS),
        }
    )
    return token


def _session_alive(sess: dict[str, Any]) -> bool:
    """Sessions without expires_at (pre-expiry docs) are treated as expired."""
    exp = sess.get("expires_at")
    if exp is None:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > datetime.now(timezone.utc)


async def resolve_user_id(authorization: str | None) -> str | None:
    """Bearer token -> user_id, or None. Never raises."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token.startswith(TOKEN_PREFIX):
        return None
    try:
        coll = get_db()["auth_sessions"]
        sess = await coll.find_one({"token": token}, {"user_id": 1, "expires_at": 1})
        if sess is None:
            return None
        if not _session_alive(sess):
            await coll.delete_one({"token": token})
            return None
        return sess["user_id"]
    except Exception:
        return None


async def require_user(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """FastAPI dependency: 401 unless a valid bearer token is presented."""
    uid = await resolve_user_id(authorization)
    if uid is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return uid


# ---------------------------------------------------------------- endpoints

@router.post("/signup", response_model=AuthResponse, status_code=201)
async def signup(body: SignupRequest) -> AuthResponse:
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    await _ensure_indexes()
    db = get_db()
    display_name = (body.display_name or "").strip() or email.split("@")[0]

    try:
        result = await db["users"].insert_one(
            {
                "email": email,
                "display_name": display_name[:60],
                "password_hash": _hash_password(body.password),
                "created_at": datetime.now(timezone.utc),
            }
        )
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="An account with this email already exists") from exc

    user_id = str(result.inserted_id)
    token = await _issue_token(user_id)
    user = AuthUser(id=user_id, email=email, display_name=display_name[:60])
    return AuthResponse(token=token, user=user)


@router.post("/signin", response_model=AuthResponse)
async def signin(body: Credentials) -> AuthResponse:
    email = body.email.strip().lower()
    await _ensure_indexes()
    user = await get_db()["users"].find_one({"email": email})
    if user is None or not _verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    user_id = str(user["_id"])
    token = await _issue_token(user_id)
    return AuthResponse(token=token, user=_user_out(user))


@router.post("/refresh", response_model=AuthResponse)
async def refresh(authorization: Annotated[str | None, Header()] = None) -> AuthResponse:
    """Swap a valid token for a fresh one (sliding 30-day expiry)."""
    token = (authorization or "")[7:].strip() if (authorization or "").lower().startswith("bearer ") else ""
    if not token.startswith(TOKEN_PREFIX):
        raise HTTPException(status_code=401, detail="Sign in required")
    uid = await resolve_user_id(authorization)
    if uid is None:
        raise HTTPException(status_code=401, detail="Session expired — sign in again")
    coll = get_db()["auth_sessions"]
    await coll.delete_one({"token": token})
    new_token = await _issue_token(uid)
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        doc = await get_db()["users"].find_one({"_id": ObjectId(uid)})
    except InvalidId:
        doc = None
    if doc is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return AuthResponse(token=new_token, user=_user_out(doc))


@router.post("/logout")
async def logout(authorization: Annotated[str | None, Header()] = None) -> dict[str, bool]:
    token = (authorization or "")[7:].strip() if (authorization or "").lower().startswith("bearer ") else ""
    if token:
        await get_db()["auth_sessions"].delete_one({"token": token})
    return {"logged_out": True}


@router.get("/me", response_model=AuthUser)
async def me(authorization: Annotated[str | None, Header()] = None) -> AuthUser:
    uid = await resolve_user_id(authorization)
    if uid is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        doc = await get_db()["users"].find_one({"_id": ObjectId(uid)})
    except InvalidId:
        doc = None
    if doc is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return _user_out(doc)
