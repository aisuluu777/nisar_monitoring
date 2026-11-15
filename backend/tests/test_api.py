"""Интеграционные тесты API на живой БД (нужен запущенный PostGIS и хотя бы один прогон конвейера).
Запуск: pytest tests/test_api.py  (пропускаются, если БД недоступна или пуста)."""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine
from app.init_db import DEMO_PASSWORD
from app.main import app

try:
    with engine.connect() as c:
        HAS_DATA = bool(c.execute(text("SELECT count(*) FROM statuses")).scalar())
except Exception:
    HAS_DATA = False

pytestmark = pytest.mark.skipif(not HAS_DATA, reason="нет БД или данных; сначала python -m pipeline run")
client = TestClient(app)


def token(username):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health_and_sources_public():
    assert client.get("/api/v1/health").json()["status"] == "ok"
    src = client.get("/api/v1/sources").json()
    assert any(f["synthetic"] for f in src["families"])  # заглушки видны явно


def test_public_sees_only_aggregates():
    assert client.get("/api/v1/cells").status_code == 401
    assert client.get("/api/v1/glaciers").status_code == 401
    s = client.get("/api/v1/districts/jeti-oguz/summary").json()
    assert set(s["cells"]["latest"]) == {"green", "yellow", "red", "gray"}
    assert "ai_summary" not in s
    assert client.get("/api/v1/export", params={"dataset": "statuses"}).status_code == 401
    assert client.get("/api/v1/export", params={"dataset": "district_summary"}).status_code == 200


def test_district_admin_is_scoped_by_server():
    h = token("admin_jeti_oguz")
    fc = client.get("/api/v1/cells", params={"district_id": "at-bashy"}, headers=h).json()
    assert fc["count"] > 0 and {f["properties"]["district_id"] for f in fc["features"]} == {"jeti-oguz"}
    other = client.get("/api/v1/cells", headers=token("emercom"), params={"district_id": "at-bashy", "limit": 1})
    cid = other.json()["features"][0]["id"]
    assert client.get(f"/api/v1/cells/{cid}", headers=h).status_code == 403


def test_cell_card_has_reasons_and_series():
    h = token("emercom")
    fc = client.get("/api/v1/cells", params={"district_id": "jeti-oguz", "status": "red"}, headers=h).json()
    assert fc["count"] >= 1
    cid = fc["features"][0]["id"]
    card = client.get(f"/api/v1/cells/{cid}", headers=h).json()
    assert card["status"] == "red" and any(r["code"] == "primary_anomaly" for r in card["reasons"])
    assert "plain" in card["bulletins"] and "Чего мы не знаем" in card["bulletins"]["plain"]["text"]
    series = client.get(f"/api/v1/cells/{cid}/series", headers=h).json()
    assert {s["signal"] for s in series["series"]} >= {"displacement_mm", "precip_30d"}
    assert client.get(f"/api/v1/cells/{cid}/products", headers=h).json()


def test_glaciers_endpoint():
    h = token("emercom")
    fc = client.get("/api/v1/glaciers", params={"district_id": "jeti-oguz", "limit": 5}, headers=h).json()
    assert fc["count"] > 0
    gid = fc["features"][0]["id"]
    card = client.get(f"/api/v1/glaciers/{gid}", headers=h).json()
    assert card["entity_type"] == "glacier" and card["status"] in ("green", "yellow", "red", "gray")


def test_decision_is_append_only():
    h = token("emercom")
    cid = client.get("/api/v1/cells", params={"district_id": "jeti-oguz", "limit": 1}, headers=h).json()["features"][0]["id"]
    r = client.post(f"/api/v1/cells/{cid}/decisions", json={"verdict": "false_alarm", "comment": "тест"}, headers=h)
    assert r.status_code == 201
    with pytest.raises(Exception):
        with engine.begin() as c:
            c.execute(text("UPDATE decisions SET verdict='confirmed' WHERE id=:i"), {"i": r.json()["id"]})
    assert client.post(f"/api/v1/cells/{cid}/decisions", json={"verdict": "maybe"}, headers=h).status_code == 422


def test_researcher_key_and_sysadmin():
    key = os.environ.get("RESEARCHER_KEY")
    if key:
        r = client.get("/api/v1/export", params={"dataset": "statuses", "district_id": "jeti-oguz"},
                       headers={"X-API-Key": key})
        assert r.status_code == 200 and r.text.startswith("# generated_at")
    assert client.get("/api/v1/admin/pipeline", headers=token("emercom")).status_code == 403
    assert client.get("/api/v1/admin/pipeline", headers=token("sysadmin")).status_code == 200


def test_assistant_refuses_forecast():
    h = token("emercom")
    r = client.post("/api/v1/assistant/ask", json={"question": "Будет ли оползень? Это безопасно?",
                                                    "district_id": "jeti-oguz"}, headers=h).json()
    assert r["refused"] is True and "не делает" in r["answer"]
    r = client.post("/api/v1/assistant/ask", json={"question": "Что изменилось за месяц?",
                                                    "district_id": "jeti-oguz"}, headers=h).json()
    assert "Сравнение" in r["answer"] and r["used"]


def test_bulletin_approval_flow():
    h = token("emercom")
    drafts = client.get("/api/v1/bulletins", params={"district_id": "jeti-oguz", "approval": "draft"}, headers=h).json()
    assert drafts
    assert client.get("/api/v1/bulletins").json() == [] or all(
        b["approval"] == "approved" for b in client.get("/api/v1/bulletins").json())
    b = next(x for x in drafts if x["check"].get("ok"))
    assert client.post(f"/api/v1/bulletins/{b['id']}/approve", headers=h).json()["approval"] == "approved"
