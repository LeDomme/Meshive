import hashlib
import secrets
from datetime import datetime, timedelta

from meshive.auth.sessions import utc_now

TOKEN_PREFIX = "msh_share_"
TOKEN_DISPLAY_LENGTH = 18


def generate_catalogue_share_token() -> str:
    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def hash_catalogue_share_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def display_catalogue_share_token_prefix(token: str) -> str:
    return f"{token[:TOKEN_DISPLAY_LENGTH]}..."


def catalogue_share_link_expiration(expires_in_seconds: int) -> datetime:
    return utc_now() + timedelta(seconds=expires_in_seconds)
