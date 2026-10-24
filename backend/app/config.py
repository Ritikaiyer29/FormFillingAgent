import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")
# Render supplies postgres:// URLs; SQLAlchemy needs the driver name.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")
SIGNING_SECRET = os.environ.get("SESSION_CAPABILITY_SIGNING_SECRET", "")
CAPABILITY_TTL = int(os.environ.get("SESSION_CAPABILITY_TTL_SECONDS", "1800"))
TENANT_ID = os.environ.get("TENANT_ID", "hal-kanpur")
# Dummy OTP: the value DUMMY_OTP is accepted. Never enable for real callers.
OTP_MODE = os.environ.get("OTP_MODE", "dummy")
DUMMY_OTP = os.environ.get("DUMMY_OTP", "123456")
CORS_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o]
