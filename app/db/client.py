"""Supabase client factory.

Service-role client is used for all server-side operations.
Admin operations (create/delete auth users) require the service-role key.
"""

from supabase import create_client, Client
from app.config import settings


def get_supabase_service() -> Client:
    """Return a Supabase client authenticated with the service-role key.

    The service-role key bypasses RLS — use only in server-side code,
    never expose to clients.
    """
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
