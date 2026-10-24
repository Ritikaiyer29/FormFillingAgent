from sqlalchemy.engine import make_url

from app.config import normalize_database_url


def test_unescaped_at_in_password_is_tolerated():
    u = make_url(normalize_database_url("postgresql://postgres.abc:pa@ss word@host.example.com:5432/postgres"))
    assert u.host == "host.example.com" and u.password == "pa@ss word" and u.username == "postgres.abc"
    assert u.drivername == "postgresql+psycopg" and u.port == 5432 and u.database == "postgres"


def test_encoded_password_and_postgres_scheme():
    u = make_url(normalize_database_url("postgres://u:p%40q@h.example.com/db"))
    assert u.password == "p@q" and u.host == "h.example.com" and u.drivername == "postgresql+psycopg"


def test_sqlite_untouched():
    assert normalize_database_url("sqlite:///./x.db") == "sqlite:///./x.db"
