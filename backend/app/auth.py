import hmac
import time
import uuid

import jwt
from fastapi import Depends, Header, HTTPException

from . import config

AUD_TOOLS = "form-tools"
AUD_STREAM = "form-stream"
TOOL_ACTIONS = ["context", "consent", "otp", "save", "validate", "submit", "help"]


def _secret() -> str:
    if len(config.SIGNING_SECRET) < 16:
        raise HTTPException(503, "Signing secret is not configured")
    return config.SIGNING_SECRET


def mint(app_id: str, tenant: str, nonce: str, aud: str, actions: list[str], ttl: int) -> str:
    now = int(time.time())
    claims = {"sub": app_id, "tenant": tenant, "nonce": nonce, "aud": aud, "act": actions,
              "iat": now, "exp": now + ttl, "jti": str(uuid.uuid4())}
    return jwt.encode(claims, _secret(), algorithm="HS256")


def decode(token: str, aud: str) -> dict:
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"], audience=aud,
                          options={"require": ["exp", "sub", "aud", "nonce"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    return authorization[7:].strip()


def require_admin(authorization: str | None = Header(default=None)) -> str:
    key = _bearer(authorization)
    if not config.ADMIN_API_KEY or not hmac.compare_digest(key, config.ADMIN_API_KEY):
        raise HTTPException(401, "Invalid admin key")
    return config.TENANT_ID


def tool_claims(action: str):
    """Dependency factory: verifies the per-call capability and that it allows `action`."""
    def dep(authorization: str | None = Header(default=None)) -> dict:
        claims = decode(_bearer(authorization), AUD_TOOLS)
        if action not in claims.get("act", []):
            raise HTTPException(403, "Action not allowed by this token")
        return claims
    return dep
