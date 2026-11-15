"""Ячейки и ледники: один набор эндпоинтов на тип объекта (раздел 8 ТЗ)."""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.auth import Principal, check_district, require
from app.db import get_db
from app.routers.common import ENTITY, latest_date, product_passports, status_dates
from pipeline.sources.base import SIGNALS

STAFF = ("admin_district", "emercom", "sysadmin")
SERIES_ROLES = STAFF + ("researcher",)
DECIDERS = ("admin_district", "emercom")


class DecisionIn(BaseModel):
    verdict: str = Field(pattern="^(confirmed|false_alarm)$")
    comment: str = Field(default="", max_length=2000)
    status_date: date | None = None


def make_router(entity_type: str, prefix: str) -> APIRouter:
    model = ENTITY[entity_type]
    router = APIRouter(prefix=f"/api/v1/{prefix}", tags=[prefix])

    def _get(db, entity_id, p: Principal):
        e = db.get(model, entity_id)
        if not e:
            raise HTTPException(404, "объект не найден")
        check_district(p, e.district_id)
        return e

    def _props(e) -> dict:
        base = {"id": e.id, "district_id": e.district_id}
        if entity_type == "cell":
            base.update(row=e.row, col=e.col, size_km=e.size_km, inside_frac=e.inside_frac)
        else:
            base.update(name=e.name, area_km2=e.area_km2, catalog=e.catalog, catalog_id=e.catalog_id,
                        synthetic=e.synthetic, license=(e.attrs or {}).get("license"))
        return base

    @router.get("", summary=f"Список ({prefix}) со статусами, GeoJSON")
    def list_entities(district_id: str | None = None, oblast: str | None = None,
                      status: str | None = Query(None, pattern="^(green|yellow|red|gray)$"),
                      on: date | None = Query(None, description="дата цикла; по умолчанию последний"),
                      limit: int = Query(5000, le=20000),
                      p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)):
        scope = p.district_scope()
        if scope:
            district_id = scope          # фильтр района задаётся сервером, а не запросом
        d = on or latest_date(db, district_id)
        q = (select(model, m.Status.status, m.Status.reasons, func.ST_AsGeoJSON(model.geom, 5))
             .join(m.Status, (m.Status.entity_id == model.id) & (m.Status.entity_type == entity_type)
                   & (m.Status.status_date == d), isouter=True))
        if district_id:
            q = q.where(model.district_id == district_id)
        if oblast:
            q = q.join(m.District, m.District.id == model.district_id).where(m.District.oblast == oblast)
        if status:
            q = q.where(m.Status.status == status)
        feats = []
        for e, st, reasons, gj in db.execute(q.limit(limit)):
            feats.append({"type": "Feature", "id": e.id, "geometry": json.loads(gj),
                          "properties": {**_props(e), "status": st or "gray",
                                         "reason_codes": [r["code"] for r in (reasons or [])]}})
        return {"type": "FeatureCollection", "date": d, "count": len(feats),
                "available_dates": status_dates(db, district_id), "features": feats}

    @router.get("/ranking", summary="Рейтинг для панели МЧС: красные и жёлтые, по силе отклонения")
    def ranking(district_id: str | None = None, on: date | None = None, limit: int = 100,
                p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)):
        district_id = p.district_scope() or district_id
        d = on or latest_date(db, district_id)
        q = select(m.Status).where(m.Status.entity_type == entity_type, m.Status.status_date == d,
                                   m.Status.status.in_(("red", "yellow")))
        if district_id:
            q = q.where(m.Status.district_id == district_id)
        rows = db.scalars(q).all()

        def strength(s):
            return max((abs(r.get("z") or 0) for r in s.reasons if r["code"] == "primary_anomaly"), default=0)
        rows.sort(key=lambda s: (s.status != "red", -strength(s)))
        return [{"entity_id": s.entity_id, "district_id": s.district_id, "status": s.status,
                 "max_z": round(strength(s), 2), "reasons": s.reasons} for s in rows[:limit]]

    @router.get("/{entity_id}", summary="Карточка: статус, причины, история статусов, бюллетени")
    def card(entity_id: str, p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)):
        e = _get(db, entity_id, p)
        hist = db.scalars(select(m.Status).where(m.Status.entity_type == entity_type, m.Status.entity_id == entity_id)
                          .order_by(m.Status.status_date)).all()
        cur = hist[-1] if hist else None
        bulletins = db.scalars(select(m.Bulletin).where(
            m.Bulletin.entity_type == entity_type, m.Bulletin.entity_id == entity_id)
            .order_by(m.Bulletin.status_date.desc())).all()
        latest_b = {}
        for b in bulletins:
            latest_b.setdefault(b.mode, b)
        decisions = db.scalars(select(m.Decision).where(m.Decision.entity_type == entity_type,
                                                        m.Decision.entity_id == entity_id)
                               .order_by(m.Decision.created_at.desc())).all()
        geom = db.scalar(select(func.ST_AsGeoJSON(model.geom, 5)).where(model.id == entity_id))
        return {
            **_props(e), "entity_type": entity_type, "geometry": json.loads(geom),
            "status": cur.status if cur else "gray", "status_date": cur.status_date if cur else None,
            "reasons": cur.reasons if cur else [],
            "analytics_version": cur.analytics_version if cur else None,
            "thresholds_version": cur.thresholds_version if cur else None,
            "status_history": [{"date": s.status_date, "status": s.status} for s in hist],
            "bulletins": {mode: {"id": b.id, "text": b.text, "generator": b.generator, "ai_generated": b.generator != "template",
                                 "approval": b.approval, "status_date": b.status_date, "check_ok": b.check.get("ok")}
                          for mode, b in latest_b.items()},
            "decisions": [{"id": x.id, "verdict": x.verdict, "comment": x.comment, "created_at": x.created_at,
                           "user_id": x.user_id, "status_date": x.status_date} for x in decisions],
            "disclaimer": "Статус означает «нужна проверка», а не оценку опасности. Это не прогноз.",
        }

    @router.get("/{entity_id}/series", summary="Временные ряды сигналов и полоса нормы")
    def series(entity_id: str, start: date | None = None, end: date | None = None,
               p: Principal = Depends(require(*SERIES_ROLES)), db: Session = Depends(get_db)):
        e = _get(db, entity_id, p)
        q = select(m.Observation).where(m.Observation.entity_type == entity_type,
                                        m.Observation.entity_id == entity_id)
        if start:
            q = q.where(m.Observation.obs_date >= start)
        if end:
            q = q.where(m.Observation.obs_date <= end)
        obs = db.scalars(q.order_by(m.Observation.obs_date)).all()
        bl = db.scalars(select(m.Baseline).where(m.Baseline.entity_type == entity_type,
                                                 m.Baseline.entity_id == entity_id)).all()
        norm = {(b.signal, b.month): b for b in bl}
        out = {}
        for o in obs:
            s = out.setdefault(o.signal, {"signal": o.signal, "unit": o.unit,
                                          "label_ru": SIGNALS.get(o.signal, {}).get("label_ru"),
                                          "family": o.family, "product_id": o.product_id, "points": []})
            b = norm.get((o.signal, o.obs_date.month))
            band = None if not b else {"median": b.median, "low": round(b.median - 1.4826 * b.mad * 2, 4),
                                       "high": round(b.median + 1.4826 * b.mad * 2, 4), "n": b.n}
            s["points"].append({"date": o.obs_date, "value": o.value, "reliable_frac": o.reliable_frac,
                                "quality": o.quality, "norm": band})
        return {"entity_id": e.id, "entity_type": entity_type, "series": list(out.values()),
                "note": "Ряды разных семейств продуктов (family) не объединяются; норма — медиана ± 2 MAD·1.4826 "
                        "для окна ±1 месяц."}

    @router.get("/{entity_id}/products", summary="Паспорта продуктов, из которых посчитаны значения")
    def products(entity_id: str, p: Principal = Depends(require(*SERIES_ROLES)), db: Session = Depends(get_db)):
        _get(db, entity_id, p)
        return product_passports(db, entity_type, entity_id)

    @router.post("/{entity_id}/decisions", status_code=201, summary="Решение специалиста (журнал без правки)")
    def decide(entity_id: str, body: DecisionIn, p: Principal = Depends(require(*DECIDERS)),
               db: Session = Depends(get_db)):
        e = _get(db, entity_id, p)
        d = body.status_date or latest_date(db, e.district_id)
        x = m.Decision(entity_type=entity_type, entity_id=entity_id, status_date=d, verdict=body.verdict,
                       comment=body.comment, user_id=p.user_id)
        db.add(x)
        db.commit()
        return {"id": x.id, "verdict": x.verdict, "status_date": x.status_date, "created_at": x.created_at}

    return router


cells_router = make_router("cell", "cells")
glaciers_router = make_router("glacier", "glaciers")
