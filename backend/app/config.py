import os

from urllib.parse import unquote

from sqlalchemy.engine import URL


def normalize_database_url(raw: str) -> str:
    """Select the psycopg driver and tolerate an unescaped '@' in the password
    (the host is whatever follows the LAST '@'). Passwords with '/', '#' or '?' still need %-encoding."""
    raw = raw.strip().strip("\"'")
    if raw.startswith("sqlite"):
        return raw
    scheme, _, rest = raw.partition("://")
    if not scheme.startswith("postgres") or "@" not in rest:
        return raw
    cred, hostpart = rest.rsplit("@", 1)
    user, _, password = cred.partition(":")
    hostport, _, db = hostpart.partition("/")
    host, _, port = hostport.partition(":")
    return URL.create("postgresql+psycopg", username=unquote(user), password=unquote(password) if password else None,
                      host=host, port=int(port) if port else None,
                      database=db.split("?")[0] or None).render_as_string(hide_password=False)


DATABASE_URL = normalize_database_url(os.environ.get("DATABASE_URL", "sqlite:///./dev.db"))

ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")
SIGNING_SECRET = os.environ.get("SESSION_CAPABILITY_SIGNING_SECRET", "")
CAPABILITY_TTL = int(os.environ.get("SESSION_CAPABILITY_TTL_SECONDS", "1800"))
TENANT_ID = os.environ.get("TENANT_ID", "hal-kanpur")
# Dummy OTP: the value DUMMY_OTP is accepted. Never enable for real callers.
OTP_MODE = os.environ.get("OTP_MODE", "dummy")
DUMMY_OTP = os.environ.get("DUMMY_OTP", "123456")
# Outbound dispatch: one standing Sarvam campaign receives a one-user cohort per call.
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
SARVAM_ORG_ID = os.environ.get("SARVAM_ORG_ID", "")
SARVAM_WORKSPACE_ID = os.environ.get("SARVAM_WORKSPACE_ID", "")
SARVAM_CAMPAIGN_ID = os.environ.get("SARVAM_CAMPAIGN_ID", "")
# Shared secret in the call-end webhook URL (?t=...). Set on the API service and in the Sarvam campaign webhook URL.
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
SARVAM_BASE =os.environ.get("SARVAM_BASE", "https://apps.sarvam.ai/api/scheduling/v1")
CORS_ORIGINS =[o for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o]
