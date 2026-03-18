"""Authentication endpoints — login, signup, invite tokens.

These routes are always public (no JWT required). They handle
the auth flow between the frontend and Supabase GoTrue.

MVP flow: invite-link based signup. Admin generates tokens,
shares via Discord/DM. Users sign up at /signup?invite=TOKEN.
"""

from __future__ import annotations

import logging
import os
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import persist
from ..auth import AUTH_ENABLED
from ..tier_guard import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

# Default admin credentials (first-time setup)
_DEFAULT_ADMIN_EMAIL = "admin@corridorkey.local"
_DEFAULT_ADMIN_PASSWORD = "admin"


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    invite_token: str = ""


class InviteTokenResponse(BaseModel):
    token: str
    created_at: float
    used: bool = False


@router.get("/status")
def auth_status():
    """Check if auth is enabled and return configuration hints."""
    return {
        "auth_enabled": AUTH_ENABLED,
        "supabase_url": os.environ.get("CK_SUPABASE_URL", ""),
        "gotrue_url": os.environ.get("CK_GOTRUE_URL", "http://localhost:54324"),
    }


@router.post("/invite/generate", dependencies=[Depends(require_admin)])
def generate_invite_token():
    """Generate an invite token for sharing. Admin only."""
    if not AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="Auth is not enabled")

    token = secrets.token_urlsafe(32)
    invites = persist.load_key("invite_tokens", {})
    invites[token] = {
        "created_at": time.time(),
        "used": False,
        "used_by": None,
    }
    persist.save_key("invite_tokens", invites)
    return {"token": token, "signup_url": f"/signup?invite={token}"}


@router.post("/invite/validate")
def validate_invite_token(token: str):
    """Check if an invite token is valid and unused."""
    invites = persist.load_key("invite_tokens", {})
    invite = invites.get(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid invite token")
    if invite.get("used"):
        raise HTTPException(status_code=409, detail="Invite token already used")
    return {"valid": True}


@router.post("/invite/consume")
def consume_invite_token(token: str, email: str):
    """Mark an invite token as used after successful signup."""
    invites = persist.load_key("invite_tokens", {})
    invite = invites.get(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid invite token")
    invite["used"] = True
    invite["used_by"] = email
    invite["used_at"] = time.time()
    persist.save_key("invite_tokens", invites)
    return {"status": "consumed"}


@router.get("/invites", dependencies=[Depends(require_admin)])
def list_invites():
    """List all invite tokens. Admin only."""
    invites = persist.load_key("invite_tokens", {})
    return {
        "invites": [
            {
                "token": t[:8] + "...",
                "created_at": v["created_at"],
                "used": v.get("used", False),
                "used_by": v.get("used_by"),
            }
            for t, v in invites.items()
        ]
    }
