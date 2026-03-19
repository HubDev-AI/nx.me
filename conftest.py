"""Root conftest — set test env vars before any app imports."""
import os

os.environ.setdefault("APP_ENV", "test")
_env = os.environ.get("APP_ENV", "")
if _env not in ("development", "test"):
    raise RuntimeError(
        f"Refusing to run tests with APP_ENV={_env!r}. "
        "Set APP_ENV=test or APP_ENV=development."
    )

os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-characters-long!!")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-api-key-minimum-32-chars-long!!")
os.environ.setdefault("SUPABASE_URL", "https://test-project.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-minimum-32-chars-long")
