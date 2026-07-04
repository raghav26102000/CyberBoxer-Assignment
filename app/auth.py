"""
Static API key auth via the X-API-Key header.

This is deliberately simple: one shared key checked with a constant-time
comparison, no user table, no tokens, no sessions. There's no user model
anywhere else in this assignment, so a bearer-token/OAuth flow would be
complexity with nothing real behind it. If this app ever needed per-user
identity, this is the seam where that would plug in.
"""
import hmac
from fastapi import Header
from app.config import API_KEY, API_KEY_HEADER_NAME
from app.exceptions import UnauthorizedError


async def require_api_key(x_api_key: str = Header(default=None, alias=API_KEY_HEADER_NAME)):
    if x_api_key is None:
        raise UnauthorizedError(f"Missing {API_KEY_HEADER_NAME} header")
    if not hmac.compare_digest(x_api_key, API_KEY):
        raise UnauthorizedError("Invalid API key")
    return True
