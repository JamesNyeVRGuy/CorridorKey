"""Trust tier route guards.

Provides FastAPI dependencies that enforce minimum trust tiers on routes.
Use as route dependencies to gate access by tier.

Tier hierarchy: pending < member < contributor < org_admin < platform_admin

Usage:
    @router.get("/protected", dependencies=[Depends(require_member)])
    def protected_route(): ...

    @router.post("/admin-only", dependencies=[Depends(require_admin)])
    def admin_route(): ...
"""

from __future__ import annotations

from fastapi import Request

from .auth import AUTH_ENABLED, UserContext, require_tier, require_user


def _get_user_or_none(request: Request) -> UserContext | None:
    """Get user from request state, or None if auth disabled."""
    if not AUTH_ENABLED:
        return None
    return getattr(request.state, "user", None)


def require_member(request: Request) -> UserContext | None:
    """Require at least 'member' tier. No-op when auth is disabled."""
    if not AUTH_ENABLED:
        return None
    return require_tier(request, "member")


def require_contributor(request: Request) -> UserContext | None:
    """Require at least 'contributor' tier."""
    if not AUTH_ENABLED:
        return None
    return require_tier(request, "contributor")


def require_org_admin(request: Request) -> UserContext | None:
    """Require at least 'org_admin' tier."""
    if not AUTH_ENABLED:
        return None
    return require_tier(request, "org_admin")


def require_admin(request: Request) -> UserContext | None:
    """Require 'platform_admin' tier."""
    if not AUTH_ENABLED:
        return None
    return require_tier(request, "platform_admin")


def require_authenticated(request: Request) -> UserContext | None:
    """Require any authenticated user (even pending). No-op when auth disabled."""
    if not AUTH_ENABLED:
        return None
    return require_user(request)
