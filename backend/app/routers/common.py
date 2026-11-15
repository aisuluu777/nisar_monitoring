from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m

ENTITY = {"cell": m.Cell, "glacier": m.Glacier}


def latest_date(db: Session, district_id: str | None = None) -> date | None:
    q = select(func.max(m.Status.status_date))
    if district_id:
        q = q.where(m.Status.district_id == district_id)
    return db.scalar(q)


def status_dates(db: Session, district_id: str | None = None) -> list[date]:
    q = select(m.Status.status_date).distinct().order_by(m.Status.status_date)
    if district_id:
        q = q.where(m.Status.district_id == district_id)
    return list(db.scalars(q))


def get_district(db: Session, district_id: str) -> m.District:
    d = db.get(m.District, district_id)
    if not d:
        raise HTTPException(404, "район не найден")
    return d


def product_passports(db: Session, entity_type: str, entity_id: str) -> list[dict]:
    rows = db.execute(
        select(m.Product).where(m.Product.id.in_(
            select(m.Observation.product_id).where(m.Observation.entity_type == entity_type,
                                                   m.Observation.entity_id == entity_id).distinct()))
    ).scalars().all()
    return [passport(p) for p in rows]


def passport(p: m.Product) -> dict:
    return {"id": p.id, "source": p.source, "family": p.family, "name": p.name, "version": p.version,
            "maturity": p.maturity, "acq_start": p.acq_start, "acq_end": p.acq_end, "license": p.license,
            "url": p.url, "synthetic": p.synthetic, "pipeline_version": p.pipeline_version,
            "params": p.params}
