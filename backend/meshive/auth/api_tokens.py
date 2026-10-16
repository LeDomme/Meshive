import hashlib
import secrets
from datetime import datetime, timedelta

from meshive.auth.sessions import utc_now

TOKEN_PREFIX = "msh_pat_"
TOKEN_DISPLAY_LENGTH = 16


def generate_api_token() -> str:
    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def display_api_token_prefix(token: str) -> str:
    return f"{token[:TOKEN_DISPLAY_LENGTH]}..."


def api_token_expiration(expires_in_seconds: int | None) -> datetime | None:
    if expires_in_seconds is None:
        return None
    return utc_now() + timedelta(seconds=expires_in_seconds)
