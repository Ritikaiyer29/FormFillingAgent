import os
import tempfile

# Must run before any `app` import so every test module sees the same isolated settings.
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["ADMIN_API_KEY"] = "admin-test-key"
os.environ["SESSION_CAPABILITY_SIGNING_SECRET"] = "x" * 32
os.environ["OTP_MODE"] = "dummy"
