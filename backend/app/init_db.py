"""Создание схемы, защита журнала решений от правки, демо-пользователи и ключ исследователя.
Запуск: python -m app.init_db  (идемпотентно)."""
import hashlib
import os
import secrets

from sqlalchemy import select, text

from app import models  # noqa: F401  регистрирует таблицы
from app.auth import hash_password
from app.db import Base, SessionLocal, engine

IMMUTABLE_DECISIONS = """
CREATE OR REPLACE FUNCTION forbid_decision_change() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'decisions is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS decisions_append_only ON decisions;
CREATE TRIGGER decisions_append_only BEFORE UPDATE OR DELETE ON decisions
FOR EACH ROW EXECUTE FUNCTION forbid_decision_change();
"""

DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo12345")
DEMO_USERS = [
    ("sysadmin", "sysadmin", None),
    ("emercom", "emercom", None),
    ("admin_jeti_oguz", "admin_district", "jeti-oguz"),
    ("admin_at_bashy", "admin_district", "at-bashy"),
]


def create_schema():
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(IMMUTABLE_DECISIONS))


def seed_users() -> str | None:
    """Демо-учётки (только для прототипа). Возвращает новый ключ исследователя, если создан."""
    new_key = None
    with SessionLocal() as db:
        existing_districts = {r[0] for r in db.execute(text("SELECT id FROM districts"))}
        for username, role, district in DEMO_USERS:
            if district and district not in existing_districts:
                continue
            if db.scalar(select(models.User).where(models.User.username == username)):
                continue
            db.add(models.User(username=username, password_hash=hash_password(DEMO_PASSWORD),
                               role=role, district_id=district))
        if not db.scalar(select(models.ApiKey).where(models.ApiKey.label == "demo-researcher")):
            new_key = "rk_" + secrets.token_urlsafe(24)
            db.add(models.ApiKey(key_hash=hashlib.sha256(new_key.encode()).hexdigest(),
                                 label="demo-researcher"))
        db.commit()
    return new_key


if __name__ == "__main__":
    create_schema()
    key = seed_users()
    print("схема готова")
    print(f"демо-пользователи: {', '.join(u for u, *_ in DEMO_USERS)}; пароль из DEMO_PASSWORD")
    if key:
        print(f"ключ исследователя (показывается один раз): {key}")
