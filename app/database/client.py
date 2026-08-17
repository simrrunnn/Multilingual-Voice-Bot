"""Supabase client construction.

This is the *only* place in the codebase that should import `supabase`.
Everything else talks to `app.database.repository`, which depends on this
module's `get_supabase_client()` and can be trivially mocked in tests.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from supabase import Client, create_client

from app.config import get_settings


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when Supabase credentials are missing but a DB call was attempted."""


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Return a cached Supabase client built from environment configuration.

    Raises `SupabaseNotConfiguredError` if SUPABASE_URL / SUPABASE_KEY are not
    set, so callers fail with a clear message rather than a confusing
    attribute error deep inside the supabase-py client.
    """

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise SupabaseNotConfiguredError(
            "SUPABASE_URL and SUPABASE_KEY must be set to use the database. "
            "See .env.example."
        )
    return create_client(settings.supabase_url, settings.supabase_key)


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_key)


def reset_client_cache() -> None:
    """Test helper: clear the cached client so a new one is built next call."""

    get_supabase_client.cache_clear()
