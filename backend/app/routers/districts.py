"""Районы и сводки. Публичный уровень — только агрегаты (раздел 2 ТЗ)."""
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.auth import Principal, get_principal
from app.db import get_db
from app.routers.common import get_district, latest_date

router = APIRouter(prefix="/api/v1/districts", tags=["districts"])
STATUSES = ("green", "yellow", "red", "gray")


@router.get("")
def list_districts(geometry: bool = False, db: Session = Depends(get_db)):
    cols = [m.District.id, m.District.name, m.District.name_ru, m.District.oblast, m.District.area_km2,
            m.District.boundary_source]
    if geometry:
        cols.append(func.ST_AsGeoJSON(func.ST_SimplifyPreserveTopology(m.District.geom, 0.002), 5))
    out = []
    for r in db.execute(select(*cols).order_by(m.District.oblast, m.District.id)):
        item = {"id": r[0], "name": r[1], "name_ru": r[2], "oblast": r[3], "area_km2": r[4],
                "boundary_source": r[5]}
        if geometry:
            item["geometry"] = json.loads(r[6])
        out.append(item)
    return out


def _counts(db, district_ids: list[str], entity_type: str, d):
    rows = db.execute(select(m.Status.status, func.count()).where(
        m.Status.district_id.in_(district_ids), m.Status.entity_type == entity_type,
        m.Status.status_date == d).group_by(m.Status.status)).all()
    c = {s: 0 for s in STATUSES}
    c.update({s: n for s, n in rows})
    return c


def _dynamics(db, district_ids: list[str], entity_type: str):
    rows = db.execute(select(m.Status.status_date, m.Status.status, func.count()).where(
        m.Status.district_id.in_(district_ids), m.Status.entity_type == entity_type)
        .group_by(m.Status.status_date, m.Status.status).order_by(m.Status.status_date)).all()
    by = {}
    for d, s, n in rows:
        by.setdefault(str(d), {k: 0 for k in STATUSES})[s] = n
    return [{"date": d, **c} for d, c in by.items()]


@router.get("/oblasts/summary")
def oblasts_summary(db: Session = Depends(get_db)):
    """Агрегаты по областям (для панели МЧС и публичного уровня)."""
    out = []
    oblasts = db.execute(select(m.District.oblast, func.array_agg(m.District.id)).group_by(m.District.oblast)).all()
    latest = latest_date(db)
    for oblast, ids in oblasts:
        out.append({"oblast": oblast, "districts": sorted(ids), "latest_cycle": latest,
                    "cells": _counts(db, ids, "cell", latest), "glaciers": _counts(db, ids, "glacier", latest)})
    return out


@router.get("/{district_id}/summary")
def summary(district_id: str, db: Session = Depends(get_db), p: Principal = Depends(get_principal)):
    """Сводка по району: число ячеек и ледников по уровням и динамика. Доступна всем (агрегаты)."""
    d = get_district(db, district_id)
    latest = latest_date(db, district_id)
    synthetic = db.scalar(select(func.bool_or(m.Product.synthetic)).where(m.Product.id.in_(
        select(m.Observation.product_id).join(m.Cell, m.Cell.id == m.Observation.entity_id)
        .where(m.Cell.district_id == district_id).distinct())))
    out = {
        "district": {"id": d.id, "name_ru": d.name_ru, "oblast": d.oblast, "area_km2": d.area_km2},
        "latest_cycle": latest,
        "cells": {"latest": _counts(db, [district_id], "cell", latest), "dynamics": _dynamics(db, [district_id], "cell")},
        "glaciers": {"latest": _counts(db, [district_id], "glacier", latest),
                     "dynamics": _dynamics(db, [district_id], "glacier")},
        "data_note": "Часть рядов синтетическая (заглушка до подключения данных NASA)" if synthetic else None,
        "disclaimer": "Статус показывает отклонение от нормы и необходимость проверки специалистом; это не прогноз.",
    }
    if p.is_staff:
        b = db.scalar(select(m.Bulletin).where(m.Bulletin.entity_type == "district",
                                               m.Bulletin.entity_id == district_id)
                      .order_by(m.Bulletin.status_date.desc()))
        out["ai_summary"] = b.text if b else None
    return out
