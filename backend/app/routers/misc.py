"""Бюллетени, решения, выгрузки, источники, здоровье, админ-панель."""
import csv
import io
import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.auth import Principal, get_principal, require
from app.config import ANALYTICS_VERSION, PIPELINE_VERSION, get_settings, thresholds
from app.db import get_db
from app.routers.common import latest_date, passport
from pipeline.sources.base import SIGNALS

router = APIRouter(prefix="/api/v1", tags=["misc"])
STAFF = ("admin_district", "emercom", "sysadmin")
APPROVERS = ("admin_district", "emercom")


# --- бюллетени -------------------------------------------------------------------------------------
@router.get("/bulletins", tags=["bulletins"])
def list_bulletins(district_id: str | None = None, entity_type: str | None = None, entity_id: str | None = None,
                   approval: str | None = Query(None, pattern="^(draft|approved)$"), mode: str | None = None,
                   limit: int = Query(200, le=2000), p: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    """Сотрудники видят черновики и утверждённые тексты своего района; исследователи и публичный
    уровень — только утверждённые тексты (публичный — без детализации по объектам)."""
    q = select(m.Bulletin)
    district_id = p.district_scope() or district_id
    if district_id:
        q = q.where(m.Bulletin.district_id == district_id)
    if entity_type:
        q = q.where(m.Bulletin.entity_type == entity_type)
    if entity_id:
        q = q.where(m.Bulletin.entity_id == entity_id)
    if mode:
        q = q.where(m.Bulletin.mode == mode)
    if p.role not in APPROVERS + ("sysadmin",):
        q = q.where(m.Bulletin.approval == "approved")
        if p.role == "public":
            q = q.where(m.Bulletin.entity_type == "district")
    elif approval:
        q = q.where(m.Bulletin.approval == approval)
    rows = db.scalars(q.order_by(m.Bulletin.status_date.desc(), m.Bulletin.id).limit(limit)).all()
    return [{"id": b.id, "entity_type": b.entity_type, "entity_id": b.entity_id, "district_id": b.district_id,
             "status_date": b.status_date, "mode": b.mode, "lang": b.lang, "status": b.facts.get("status"),
             "text": b.text, "generator": b.generator, "ai_generated": b.generator != "template",
             "check": b.check, "approval": b.approval} for b in rows]


@router.post("/bulletins/{bulletin_id}/approve", tags=["bulletins"])
def approve(bulletin_id: int, p: Principal = Depends(require(*APPROVERS)), db: Session = Depends(get_db)):
    b = db.get(m.Bulletin, bulletin_id)
    if not b:
        raise HTTPException(404, "бюллетень не найден")
    if p.district_scope() and p.district_scope() != b.district_id:
        raise HTTPException(403, "нет доступа к этому району")
    if not b.check.get("ok"):
        raise HTTPException(409, "текст не прошёл автоматическую проверку и не может быть утверждён")
    b.approval, b.approved_by = "approved", p.user_id
    db.commit()
    return {"id": b.id, "approval": b.approval}


@router.get("/decisions", tags=["decisions"])
def decisions(district_id: str | None = None, limit: int = Query(200, le=2000),
              p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    """Журнал решений специалистов (только чтение; правка запрещена на уровне БД)."""
    q = select(m.Decision, m.User.username).join(m.User, m.User.id == m.Decision.user_id)
    district_id = p.district_scope() or district_id
    if district_id:
        cell_ids = select(m.Cell.id).where(m.Cell.district_id == district_id)
        gl_ids = select(m.Glacier.id).where(m.Glacier.district_id == district_id)
        q = q.where(m.Decision.entity_id.in_(cell_ids.union(gl_ids)))
    rows = db.execute(q.order_by(m.Decision.created_at.desc()).limit(limit)).all()
    return [{"id": d.id, "entity_type": d.entity_type, "entity_id": d.entity_id, "status_date": d.status_date,
             "verdict": d.verdict, "comment": d.comment, "by": u, "created_at": d.created_at} for d, u in rows]


# --- выгрузки --------------------------------------------------------------------------------------
def _csv(rows: list[dict], name: str, meta: dict) -> StreamingResponse:
    buf = io.StringIO()
    buf.write("".join(f"# {k}: {v}\n" for k, v in meta.items()))
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


@router.get("/export", tags=["export"])
def export(dataset: str = Query("district_summary", pattern="^(district_summary|statuses|observations)$"),
           district_id: str | None = None, entity_type: str = Query("cell", pattern="^(cell|glacier)$"),
           start: date | None = None, end: date | None = None,
           fmt: str = Query("csv", alias="format", pattern="^(csv|json)$"),
           p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """district_summary — публично (агрегаты по району и циклу); statuses и observations — исследователи
    по ключу и сотрудники. В шапке — версии данных и ссылка на паспорта (/api/v1/sources)."""
    if dataset != "district_summary" and p.role == "public":
        raise HTTPException(401, "детальные выгрузки доступны по ключу API")
    district_id = p.district_scope() or district_id
    meta = {"generated_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": PIPELINE_VERSION,
            "analytics_version": ANALYTICS_VERSION, "thresholds_version": thresholds()["version"],
            "passports": "/api/v1/sources", "license": "уточняется заказчиком (например, CC BY 4.0)",
            "cite": "NASA Space Monitor (prototype), данные NASA и OSM; см. паспорта продуктов"}
    if dataset == "district_summary":
        q = select(m.Status.district_id, m.Status.entity_type, m.Status.status_date, m.Status.status,
                   func.count()).group_by(m.Status.district_id, m.Status.entity_type, m.Status.status_date,
                                          m.Status.status)
        if district_id:
            q = q.where(m.Status.district_id == district_id)
        rows = [{"district_id": a, "entity_type": b, "date": c, "status": s, "count": n}
                for a, b, c, s, n in db.execute(q.order_by(m.Status.status_date))]
    elif dataset == "statuses":
        q = select(m.Status).where(m.Status.entity_type == entity_type)
        if district_id:
            q = q.where(m.Status.district_id == district_id)
        rows = [{"entity_id": s.entity_id, "district_id": s.district_id, "date": s.status_date, "status": s.status,
                 "reason_codes": ";".join(r["code"] for r in s.reasons),
                 "analytics_version": s.analytics_version} for s in db.scalars(q)]
    else:
        if not district_id:
            raise HTTPException(400, "для observations укажите district_id")
        model = m.Cell if entity_type == "cell" else m.Glacier
        q = (select(m.Observation).join(model, model.id == m.Observation.entity_id)
             .where(m.Observation.entity_type == entity_type, model.district_id == district_id))
        if start:
            q = q.where(m.Observation.obs_date >= start)
        if end:
            q = q.where(m.Observation.obs_date <= end)
        rows = [{"entity_id": o.entity_id, "signal": o.signal, "date": o.obs_date, "value": o.value,
                 "unit": o.unit, "reliable_frac": o.reliable_frac, "family": o.family, "product_id": o.product_id}
                for o in db.scalars(q.limit(500_000))]
    if fmt == "json":
        return {"meta": meta, "rows": rows}
    return _csv(rows, f"{dataset}_{district_id or 'all'}", meta)


# --- источники, здоровье, админ --------------------------------------------------------------------
@router.get("/sources", tags=["sources"])
def sources(db: Session = Depends(get_db)):
    """Источники, лицензии, даты последнего обновления; синтетические заглушки помечены явно."""
    rows = db.scalars(select(m.Product).order_by(m.Product.source, m.Product.acq_end.desc())).all()
    by = {}
    for p in rows:
        s = by.setdefault(p.family, {"source": p.source, "family": p.family, "name": p.name, "license": p.license,
                                     "maturity": p.maturity, "synthetic": p.synthetic, "products": 0,
                                     "last_acq": None, "replaces": (p.params or {}).get("replaces")})
        s["products"] += 1
        if p.acq_end and (s["last_acq"] is None or p.acq_end > s["last_acq"]):
            s["last_acq"] = p.acq_end
    return {"families": list(by.values()), "signals": SIGNALS,
            "boundaries": "geoBoundaries KGZ ADM2 (2010), CC BY-SA 3.0",
            "glacier_outlines": "© OpenStreetMap contributors, ODbL 1.0 (временно; далее RGI 7 / GLIMS)"}


@router.get("/products/{product_id}", tags=["sources"])
def product(product_id: int, db: Session = Depends(get_db)):
    p = db.get(m.Product, product_id)
    if not p:
        raise HTTPException(404, "продукт не найден")
    return passport(p)


@router.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    run = db.scalar(select(m.PipelineRun).where(m.PipelineRun.status == "ok").order_by(m.PipelineRun.id.desc()))
    latest = latest_date(db)
    age = (date.today() - latest).days if latest else None
    return {"status": "ok", "pipeline_version": PIPELINE_VERSION, "analytics_version": ANALYTICS_VERSION,
            "last_pipeline_run": run.finished_at if run else None, "latest_cycle": latest,
            "data_age_days": age,
            "stale": age is None or age > thresholds()["max_data_age_days"],
            "llm_enabled": get_settings().llm_provider != "none"}


@router.get("/admin/pipeline", tags=["admin"])
def admin_pipeline(limit: int = 20, p: Principal = Depends(require("sysadmin")), db: Session = Depends(get_db)):
    runs = db.scalars(select(m.PipelineRun).order_by(m.PipelineRun.id.desc()).limit(limit)).all()
    return [{"id": r.id, "started_at": r.started_at, "finished_at": r.finished_at, "status": r.status,
             "districts": r.districts, "stats": r.stats, "log": r.log} for r in runs]


@router.get("/admin/thresholds", tags=["admin"])
def admin_thresholds(p: Principal = Depends(require("sysadmin"))):
    return thresholds()


@router.get("/notifications", tags=["notifications"])
def notifications(p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    """Переходы на жёлтый/красный в последнем цикле (канал доставки — email/Telegram — по согласованию)."""
    run = db.scalar(select(m.PipelineRun).where(m.PipelineRun.status == "ok").order_by(m.PipelineRun.id.desc()))
    items = (run.stats or {}).get("notifications", []) if run else []
    scope = p.district_scope()
    return [n for n in items if not scope or n["district_id"] == scope]
