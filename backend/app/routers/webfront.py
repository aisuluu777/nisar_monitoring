"""Контракт веб-клиента (frontend/openapi.json) поверх данных этого бэкенда.

Клиент рассчитан на один район и свои названия ролей/статусов, поэтому здесь адаптер:
  gray -> grey, admin_district -> district_admin, emercom -> mchs; район = район учётки,
  для остальных DEFAULT_DISTRICT. Подключается в main.py ДО родных роутеров и перекрывает
  одинаковые пути (/cells, /cells/{id}, /series, /products, /decisions, summary, sources, health, auth).
Чего в данных нет, отдаём как null / пусто (деревни, рельеф, события, вегетация), а не выдумываем.
"""
import json
import os
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.auth import Principal, check_district, create_token, get_principal, require, verify_password
from app.db import get_db
from app.routers.common import latest_date, passport, product_passports, status_dates
from app.routers.entities import DECIDERS, STAFF
from app.routers.misc import APPROVERS

router = APIRouter(prefix="/api/v1", tags=["webfront"])

DEFAULT_DISTRICT = "jeti-oguz"
ROLE_OUT = {"admin_district": "district_admin", "emercom": "mchs"}
DISPLAY = {"sysadmin": "Системный администратор", "emercom": "МЧС"}
MAD_K = 1.4826
SIG_DISP, SIG_P30, SIG_SM = "displacement_mm", "precip_30d", "soil_moisture"
DEMO_NOTE = ("Демонстрационные данные: смещение и влажность почвы синтетические (заглушка до подключения "
             "NISAR/HyP3); осадки — реальные, NASA POWER.")


def role_out(r: str) -> str:
    return ROLE_OUT.get(r, r)


def st_out(s: str | None) -> str:
    return "grey" if s in (None, "gray") else s


def scope(p: Principal) -> str:
    return p.district_scope() or DEFAULT_DISTRICT


def _ds(d) -> str | None:
    return str(d) if d else None


def _user_out(u: m.User) -> dict:
    name = DISPLAY.get(u.username) or f"Администрация: {u.district_id}"
    return {"id": u.id, "username": u.username, "display_name": name, "role": role_out(u.role),
            "district_id": u.district_id}


def _district_info(db: Session, d: m.District) -> dict:
    x0, y0, x1, y1 = db.execute(select(func.ST_XMin(d.geom), func.ST_YMin(d.geom), func.ST_XMax(d.geom),
                                       func.ST_YMax(d.geom))).one()
    return {"id": d.id, "name_ru": d.name_ru, "name_ky": d.name_ru, "name_en": d.name,
            "bbox": [x0, y0, x1, y1], "area_km2": d.area_km2}


def _district(db: Session, did: str) -> m.District:
    d = db.get(m.District, did)
    if not d:
        raise HTTPException(404, "район не найден")
    return d


def _versions(db: Session) -> tuple[str, str]:
    av = db.scalar(select(m.Status.analytics_version).order_by(m.Status.status_date.desc()).limit(1)) or "-"
    pv = db.scalar(select(m.Product.pipeline_version).order_by(m.Product.id.desc()).limit(1)) or "-"
    return av, pv


def _counts(db: Session, did: str, d) -> dict:
    rows = db.execute(select(m.Status.status, func.count()).where(
        m.Status.district_id == did, m.Status.entity_type == "cell", m.Status.status_date == d)
        .group_by(m.Status.status)).all()
    c = {"green": 0, "yellow": 0, "red": 0, "grey": 0}
    for s, n in rows:
        c[st_out(s)] += n
    return c


def _strength(reasons: list) -> float:
    return max((abs(r.get("z") or 0) for r in reasons or [] if r.get("code") == "primary_anomaly"), default=0.0)


def _phrase(reasons: list) -> str:
    prim = next((r for r in reasons or [] if r.get("code") == "primary_anomaly"), None)
    if prim:
        out = (f"Смещение {prim['value'] / 10:+.1f} см за цикл при норме {prim['median'] / 10:+.1f} см "
               f"(отклонение z = {prim['z']:+.1f})")
        cl = next((r for r in reasons if r.get("code") == "cluster"), None)
        return out + (f"; рядом отклоняются ещё {cl['cluster_cells'] - 1} ячеек" if cl else "")
    return (reasons[0].get("text_ru") if reasons else "Требует проверки специалистом").capitalize()


def _baseline_z(base: dict, key, month: int, value):
    b = base.get((key, month))
    if value is None or not b or not b[1]:
        return None
    return round((value - b[0]) / (MAD_K * b[1]), 2)


# ---------- служебное ----------

@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    d = _district(db, DEFAULT_DISTRICT)
    cycles = [str(x) for x in status_dates(db, DEFAULT_DISTRICT)]
    av, pv = _versions(db)
    return {"data_mode": "demo", "synthetic": True, "available_modes": ["demo"], "object_kind": "cell",
            "data_note": DEMO_NOTE, "levels_published": True, "reference_date": str(date.today()),
            "district": _district_info(db, d), "cycles": cycles, "primary_family": "SYNTHETIC_INSAR",
            "analytics_version": av, "pipeline_version": pv, "max_data_age_days": 36,
            "explainer": "template"}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    run = db.scalar(select(m.PipelineRun).order_by(m.PipelineRun.id.desc()).limit(1))
    last = latest_date(db)
    av, pv = _versions(db)
    age = (date.today() - last).days if last else None
    return {"status": "ok" if age is not None and age <= 36 else "degraded", "data_mode": "demo",
            "pipeline_version": pv, "analytics_version": av, "last_cycle": _ds(last), "data_age_days": age,
            "last_pipeline_run": run.started_at.isoformat() if run else None,
            "last_pipeline_status": run.status if run else None}


@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    rows = db.execute(select(m.Product.family, m.Product.source, func.min(m.Product.name),
                             func.max(m.Product.maturity), func.min(m.Product.license),
                             func.min(m.Product.acq_start), func.max(m.Product.acq_end), func.count())
                      .group_by(m.Product.family, m.Product.source)).all()
    out = []
    for fam, src, name, mat, lic, a, b, n in rows:
        age = (date.today() - b).days if b else 0
        out.append({"family": fam, "source": src, "name": name, "maturity": mat, "license": lic,
                    "first_date": _ds(a) or "", "last_date": _ds(b) or "", "products": n, "age_days": age,
                    "stale": age > 36})
    return out


# ---------- вход ----------

class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(m.User).where(m.User.username == body.username))
    if not u or not u.active or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "неверный логин или пароль")
    return {"access_token": create_token(u), "token_type": "bearer", "user": _user_out(u)}


@router.get("/auth/me")
def me(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    u = db.get(m.User, p.user_id) if p.user_id else None
    if not u:
        raise HTTPException(401, "не выполнен вход")
    return _user_out(u)


@router.get("/auth/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """Только для демо: клиент показывает кнопки быстрого входа."""
    pw = os.environ.get("DEMO_PASSWORD", "demo12345")
    return [{"username": u.username, "display_name": _user_out(u)["display_name"], "role": role_out(u.role),
             "password": pw} for u in db.scalars(select(m.User).where(m.User.active.is_(True)).order_by(m.User.id))]


# ---------- район ----------

@router.get("/districts/{district_id}/summary")
def summary(district_id: str, db: Session = Depends(get_db)):
    d = _district(db, district_id)
    dates = status_dates(db, district_id)
    last = dates[-1] if dates else None
    n_cells = db.scalar(select(func.count()).select_from(m.Cell).where(m.Cell.district_id == district_id))
    rows = db.execute(select(m.Status.status_date, m.Status.status, func.count()).where(
        m.Status.district_id == district_id, m.Status.entity_type == "cell")
        .group_by(m.Status.status_date, m.Status.status).order_by(m.Status.status_date)).all()
    dyn: dict = {}
    for dt, s, n in rows:
        dyn.setdefault(str(dt), {"green": 0, "yellow": 0, "red": 0, "grey": 0})[st_out(s)] += n
    return {"district": _district_info(db, d), "n_cells": n_cells, "last_cycle": _ds(last),
            "data_age_days": (date.today() - last).days if last else None, "levels_published": True,
            "levels_visible": True, "counts": _counts(db, district_id, last) if last else None,
            "dynamics": [{"date": k, "counts": v} for k, v in dyn.items()], "villages": []}


@router.get("/districts/{district_id}/outline")
def outline(district_id: str, db: Session = Depends(get_db)):
    d = _district(db, district_id)
    gj = db.scalar(select(func.ST_AsGeoJSON(func.ST_SimplifyPreserveTopology(d.geom, 0.002), 5)))
    return {"type": "Feature", "id": d.id, "properties": {"id": d.id, "name_ru": d.name_ru},
            "geometry": json.loads(gj)}


# ---------- карта ----------

@router.get("/cells")
def cells(on: date | None = Query(None, alias="date"), status: str | None = None, village: str | None = None,
          p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    did = scope(p)
    d = on or latest_date(db, did)
    q = (select(m.Cell.id, m.Status.status, func.ST_AsGeoJSON(m.Cell.geom, 5))
         .join(m.Status, (m.Status.entity_id == m.Cell.id) & (m.Status.entity_type == "cell")
               & (m.Status.status_date == d), isouter=True)
         .where(m.Cell.district_id == did))
    if status:
        q = q.where(m.Status.status == ("gray" if status == "grey" else status))
    obs = {(e, s): (v, rf) for e, s, v, rf in db.execute(
        select(m.Observation.entity_id, m.Observation.signal, m.Observation.value, m.Observation.reliable_frac)
        .join(m.Cell, m.Cell.id == m.Observation.entity_id)
        .where(m.Observation.entity_type == "cell", m.Cell.district_id == did, m.Observation.obs_date == d))}
    cum = dict(db.execute(
        select(m.Observation.entity_id, func.sum(m.Observation.value))
        .join(m.Cell, m.Cell.id == m.Observation.entity_id)
        .where(m.Observation.entity_type == "cell", m.Observation.signal == SIG_DISP, m.Cell.district_id == did,
               m.Observation.obs_date <= d).group_by(m.Observation.entity_id)).all())
    base = {((e, s), mo): (md, mad) for e, s, mo, md, mad in db.execute(
        select(m.Baseline.entity_id, m.Baseline.signal, m.Baseline.month, m.Baseline.median, m.Baseline.mad)
        .join(m.Cell, m.Cell.id == m.Baseline.entity_id)
        .where(m.Baseline.entity_type == "cell", m.Cell.district_id == did, m.Baseline.month == (d.month if d else 0)))}
    feats = []
    for cid, s, gj in db.execute(q):
        disp, rf = obs.get((cid, SIG_DISP), (None, None))
        p30 = obs.get((cid, SIG_P30), (None, None))[0]
        sm = obs.get((cid, SIG_SM), (None, None))[0]
        feats.append({"type": "Feature", "id": cid, "geometry": json.loads(gj), "properties": {
            "id": cid, "village": None, "status": st_out(s), "stale": False,
            "disp_cm": None if disp is None else round(disp / 10, 3),
            "disp_z": _baseline_z(base, (cid, SIG_DISP), d.month, disp),
            "cum_cm": None if cum.get(cid) is None else round(cum[cid] / 10, 2),
            "precip_mm": p30, "precip_z": _baseline_z(base, (cid, SIG_P30), d.month, p30),
            "sm": sm, "veg": None, "valid_frac": rf, "elev": 0, "slope": 0}})
    return {"type": "FeatureCollection", "features": feats, "cycle": _ds(d),
            "stale_days": (date.today() - d).days if d else None}


@router.get("/events")
def events(p: Principal = Depends(require(*STAFF))):
    """Каталога известных событий (сходов) в данных нет — пустая коллекция."""
    return {"type": "FeatureCollection", "features": []}


# ---------- «Сегодня» ----------

@router.get("/today")
def today(p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    did = scope(p)
    dates = status_dates(db, did)
    if not dates:
        raise HTTPException(404, "нет данных")
    d, prev = dates[-1], (dates[-2] if len(dates) > 1 else None)
    rows = db.execute(
        select(m.Status.entity_id, m.Status.status, m.Status.reasons, func.ST_X(func.ST_Centroid(m.Cell.geom)),
               func.ST_Y(func.ST_Centroid(m.Cell.geom)))
        .join(m.Cell, m.Cell.id == m.Status.entity_id)
        .where(m.Status.district_id == did, m.Status.entity_type == "cell", m.Status.status_date == d,
               m.Status.status.in_(("red", "yellow")))).all()
    prev_flag = set(db.scalars(select(m.Status.entity_id).where(
        m.Status.district_id == did, m.Status.entity_type == "cell", m.Status.status_date == prev,
        m.Status.status.in_(("red", "yellow"))))) if prev else set()
    rows.sort(key=lambda r: (r[1] != "red", -_strength(r[2])))
    top = rows[:40]
    ids = [r[0] for r in top]
    spark: dict = {}
    for e, v in db.execute(select(m.Observation.entity_id, m.Observation.value).where(
            m.Observation.entity_type == "cell", m.Observation.entity_id.in_(ids), m.Observation.signal == SIG_DISP,
            m.Observation.obs_date <= d).order_by(m.Observation.obs_date)):
        spark.setdefault(e, []).append(None if v is None else round(v / 10, 3))
    handed = set(db.scalars(select(m.Decision.entity_id).where(m.Decision.entity_id.in_(ids),
                                                               m.Decision.verdict == "handoff")))
    tasks = []
    for cid, s, reasons, lon, lat in top:
        prim = next((r for r in reasons if r.get("code") == "primary_anomaly"), None)
        tasks.append({"cell_id": cid, "village": None, "status": s, "is_new": cid not in prev_flag,
                      "phrase": _phrase(reasons), "spark": spark.get(cid, [])[-8:],
                      "disp_cm": None if not prim else round(prim["value"] / 10, 3),
                      "z": None if not prim else prim["z"], "handed_off": cid in handed, "lon": lon, "lat": lat,
                      "nearby": {}, "score": round(_strength(reasons), 2)})
    return {"latest_cycle": str(d), "shown_cycle": str(d), "off_season": False,
            "stale_days": (date.today() - d).days, "reference_date": str(date.today()),
            "counts": _counts(db, did, d), "to_check": len(rows),
            "new_since_prev": sum(1 for r in rows if r[0] not in prev_flag),
            "next_expected": str(d + timedelta(days=12)), "season_note": None, "tasks": tasks}


# ---------- карточка ----------

def _cell(db: Session, cid: str, p: Principal) -> m.Cell:
    c = db.get(m.Cell, cid)
    if not c:
        raise HTTPException(404, "ячейка не найдена")
    check_district(p, c.district_id)
    return c


def _reason(r: dict) -> dict:
    code = r.get("code", "")
    val = r.get("z") if r.get("z") is not None else (r.get("prev_z") if code == "persistent"
                                                      else r.get("cluster_cells"))
    thr = r.get("threshold") if r.get("threshold") is not None else r.get("min_cells")
    unit = "ячеек" if code == "cluster" else "z"
    return {"rule": code, "signal": r.get("signal") or "", "value": val, "threshold": thr, "op": ">=",
            "unit": unit, "triggered": True, "family": None, "product_ids": [], "details": r}


def _bulletin(db: Session, cid: str, lang: str) -> dict:
    b = db.scalar(select(m.Bulletin).where(m.Bulletin.entity_type == "cell", m.Bulletin.entity_id == cid,
                                           m.Bulletin.mode == "plain", m.Bulletin.lang == "ru")
                  .order_by(m.Bulletin.status_date.desc()))
    if not b:
        return {"mode": "plain", "lang": "ru", "see": [], "basis": [], "generator": "template",
                "unknown": ["Бюллетень для этой ячейки не сформирован."], "review_status": "on_the_fly",
                "needs_native_review": False, "checks_ok": True}
    blocks = {"see": [], "unknown": [], "basis": []}
    keys = {"Что мы видим.": "see", "Чего мы не знаем.": "unknown", "На чём основано.": "basis"}
    for para in b.text.split("\n\n"):
        for label, k in keys.items():
            if para.startswith(label):
                blocks[k] = [x.strip() for x in para[len(label):].split(";") if x.strip()] if k == "basis" \
                    else [para[len(label):].strip()]
    return {"mode": b.mode, "lang": b.lang, **blocks, "generator": "template" if b.generator == "template" else "llm",
            "review_status": "approved" if b.approval == "approved" else "draft",
            "needs_native_review": False, "checks_ok": bool((b.check or {}).get("ok", True))}


def _passports(db: Session, cid: str) -> list[dict]:
    return [{"product_id": x["id"], "source": x["source"], "name": x["name"], "family": x["family"],
             "version": x["version"], "maturity": x["maturity"], "acq_start": _ds(x["acq_start"]) or "",
             "acq_end": _ds(x["acq_end"]) or "", "license": x["license"], "pipeline_version": x["pipeline_version"],
             "processing_params": x["params"], "url": x["url"]} for x in product_passports(db, "cell", cid)]


@router.get("/cells/{cell_id}")
def card(cell_id: str, on: date | None = Query(None, alias="date"), lang: str = "ru",
         p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    c = _cell(db, cell_id, p)
    hist = db.scalars(select(m.Status).where(m.Status.entity_type == "cell", m.Status.entity_id == cell_id)
                      .order_by(m.Status.status_date)).all()
    cur = next((s for s in reversed(hist) if on is None or s.status_date <= on), None)
    x, y, gj = db.execute(select(func.ST_X(func.ST_Centroid(m.Cell.geom)), func.ST_Y(func.ST_Centroid(m.Cell.geom)),
                                 func.ST_AsGeoJSON(m.Cell.geom, 5)).where(m.Cell.id == cell_id)).one()
    decs = db.execute(select(m.Decision, m.User.username).join(m.User, m.User.id == m.Decision.user_id)
                      .where(m.Decision.entity_id == cell_id).order_by(m.Decision.created_at)).all()
    grey = cur is None or cur.status == "gray"
    av, _ = _versions(db)
    return {
        "cell": {"id": c.id, "district_id": c.district_id, "village": None, "lon": x, "lat": y, "elev_mean": 0,
                 "slope_mean": 0, "slope_max": 0, "aspect": 0, "frac_forest": 0, "frac_water": 0, "frac_built": 0,
                 "geometry": json.loads(gj)},
        "cycle": str(cur.status_date) if cur else "", "status": st_out(cur.status if cur else None),
        "stored_status": st_out(cur.status if cur else None),
        "stale_days": (date.today() - cur.status_date).days if cur else None, "family": "SYNTHETIC_INSAR",
        "analytics_version": cur.analytics_version if cur else av,
        "reasons": [_reason(r) for r in (cur.reasons if cur else [])],
        "history": [{"date": str(s.status_date), "status": st_out(s.status)} for s in hist],
        "bulletin": _bulletin(db, cell_id, lang),
        "decisions": [{"id": d.id, "verdict": d.verdict, "comment": d.comment, "created_at": d.created_at.isoformat(),
                       "user": u} for d, u in decs if d.verdict != "handoff"],
        "handoffs": [{"ts": d.created_at.isoformat(), "user": u, "comment": d.comment,
                      "cycle": _ds(d.status_date)} for d, u in decs if d.verdict == "handoff"],
        "steps": [{"key": "data", "state": "done"}, {"key": "qc", "state": "done"},
                  {"key": "baseline", "state": "blocked" if grey else "done"},
                  {"key": "deviation", "state": "blocked" if grey else "done"},
                  {"key": "status", "state": "done" if cur else "pending"},
                  {"key": "decision", "state": "done" if any(d.verdict != "handoff" for d, _ in decs) else "pending"}],
        "passports": _passports(db, cell_id)}


@router.get("/cells/{cell_id}/series")
def series(cell_id: str, p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    _cell(db, cell_id, p)
    obs: dict = {}
    for o in db.scalars(select(m.Observation).where(m.Observation.entity_type == "cell",
                                                    m.Observation.entity_id == cell_id)
                        .order_by(m.Observation.obs_date)):
        obs.setdefault(o.signal, []).append(o)
    base = {(b.signal, b.month): (b.median, b.mad) for b in db.scalars(select(m.Baseline).where(
        m.Baseline.entity_type == "cell", m.Baseline.entity_id == cell_id))}
    stat = {s.status_date: st_out(s.status) for s in db.scalars(select(m.Status).where(
        m.Status.entity_type == "cell", m.Status.entity_id == cell_id))}
    mat = {pid: mt for pid, mt in db.execute(select(m.Product.id, m.Product.maturity))}
    av, pv = _versions(db)

    def line(sig: str, unit: str):
        rows = obs.get(sig)
        if not rows:
            return None
        return {"family": rows[0].family, "signal": sig, "unit": unit, "maturity": mat.get(rows[0].product_id, ""),
                "dates": [str(o.obs_date) for o in rows], "values": [o.value for o in rows], "flags": [[] for _ in rows]}

    dr = obs.get(SIG_DISP, [])
    cm = lambda v: None if v is None else round(v / 10, 3)  # noqa: E731
    med = [cm(base[(SIG_DISP, o.obs_date.month)][0]) if (SIG_DISP, o.obs_date.month) in base else None for o in dr]
    sig = [round(2 * MAD_K * base[(SIG_DISP, o.obs_date.month)][1] / 10, 3) if (SIG_DISP, o.obs_date.month) in base
           else None for o in dr]
    p30 = obs.get(SIG_P30, [])
    return {"cell_id": cell_id, "analytics_version": av, "pipeline_version": pv,
            "displacement": {"family": dr[0].family if dr else "", "unit": "cm",
                             "note": "Синтетический ряд (заглушка до подключения NISAR/HyP3)",
                             "dates": [str(o.obs_date) for o in dr], "raw": [cm(o.value) for o in dr],
                             "corrected": [cm(o.value) for o in dr], "median": med, "sigma": sig,
                             "status": [stat.get(o.obs_date, "grey") for o in dr]},
            "other_displacement": [], "precip_30d": line(SIG_P30, "мм"),
            "precip_norm": [base[(SIG_P30, o.obs_date.month)][0] if (SIG_P30, o.obs_date.month) in base else None
                            for o in p30],
            "soil_moisture": line(SIG_SM, "м³/м³"), "veg_disturbance": None, "events": []}


@router.get("/cells/{cell_id}/products")
def products(cell_id: str, limit: int = 50, p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    _cell(db, cell_id, p)
    return _passports(db, cell_id)[:limit]


# ---------- решения ----------

class DecisionIn(BaseModel):
    verdict: str
    comment: str
    cycle: str | None = None


class HandoffIn(BaseModel):
    comment: str = ""
    cycle: str | None = None


def _save(db: Session, cid: str, p: Principal, verdict: str, comment: str, cycle: str | None):
    c = _cell(db, cid, p)
    d = date.fromisoformat(cycle) if cycle else latest_date(db, c.district_id)
    x = m.Decision(entity_type="cell", entity_id=cid, status_date=d, verdict=verdict, comment=comment,
                   user_id=p.user_id)
    db.add(x)
    db.commit()
    return x


@router.post("/cells/{cell_id}/decisions", status_code=201)
def decide(cell_id: str, body: DecisionIn, p: Principal = Depends(require(*DECIDERS)), db: Session = Depends(get_db)):
    if body.verdict not in ("confirmed", "false_alarm"):
        raise HTTPException(422, "verdict: confirmed | false_alarm")
    x = _save(db, cell_id, p, body.verdict, body.comment, body.cycle)
    return {"id": x.id, "verdict": x.verdict, "comment": x.comment, "created_at": x.created_at.isoformat(),
            "user": p.username}


@router.post("/cells/{cell_id}/handoff", status_code=201)
def handoff(cell_id: str, body: HandoffIn, p: Principal = Depends(require(*DECIDERS)), db: Session = Depends(get_db)):
    x = _save(db, cell_id, p, "handoff", body.comment, body.cycle)
    return {"ts": x.created_at.isoformat(), "user": p.username, "comment": x.comment, "cycle": _ds(x.status_date)}


@router.post("/cells/{cell_id}/bulletin/approve")
def approve_bulletin(cell_id: str, cycle: str | None = None, lang: str = "ru",
                     p: Principal = Depends(require(*APPROVERS)), db: Session = Depends(get_db)):
    """Утверждает тексты ячейки за цикл. Бюллетени есть только на русском, поэтому lang не фильтрует."""
    c = _cell(db, cell_id, p)
    d = date.fromisoformat(cycle) if cycle else latest_date(db, c.district_id)
    rows = db.scalars(select(m.Bulletin).where(m.Bulletin.entity_type == "cell", m.Bulletin.entity_id == cell_id,
                                               m.Bulletin.status_date == d)).all()
    if not rows:
        raise HTTPException(404, "для этой ячейки и цикла нет бюллетеня")
    if not all((b.check or {}).get("ok") for b in rows):
        raise HTTPException(409, "текст не прошёл автоматическую проверку и не может быть утверждён")
    for b in rows:
        b.approval, b.approved_by = "approved", p.user_id
    db.commit()
    return {"approved": [b.id for b in rows], "cycle": str(d)}


@router.get("/admin/pipeline-runs")
def pipeline_runs(p: Principal = Depends(require("sysadmin")), db: Session = Depends(get_db)):
    out = []
    for r in db.scalars(select(m.PipelineRun).order_by(m.PipelineRun.id.desc()).limit(50)):
        last = latest_date(db)
        out.append({"id": r.id, "district_id": ",".join(r.districts or []) or "all", "mode": "demo",
                    "started_at": r.started_at.isoformat(),
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None, "status": r.status,
                    "new_products": int((r.stats or {}).get("new_products", 0)),
                    "data_age_days": (date.today() - last).days if last else None,
                    "message": (r.log or "")[-200:]})
    return out
