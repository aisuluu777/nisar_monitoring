"""Цикл конвейера (раздел 5 ТЗ). Все шаги идемпотентны: повторный запуск на тех же данных даёт
ту же базу (upsert по естественным ключам, детерминированные расчёты)."""
import io
import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from ai import bulletins as bulletin_gen
from ai import facts as facts_mod
from ai.provider import get_provider
from analytics.engine import Series, evaluate, remove_scene_offset
from app import models as m
from app.config import PIPELINE_VERSION, districts_config, get_settings, thresholds
from app.db import SessionLocal, engine
from app.init_db import create_schema, seed_users
from pipeline import grid
from pipeline.sources import glaciers_osm, nasa_power, synthetic
from pipeline.sources.base import SourceResult

log = logging.getLogger("pipeline")
STATUS_CYCLES = 10   # сколько последних циклов получают статусы (ползунок на карте)


def cycle_dates(today: date | None = None) -> list[date]:
    s = get_settings()
    start, today = date.fromisoformat(s.history_start), today or date.today()
    out, d = [], start
    while d <= today:
        out.append(d)
        d += timedelta(days=s.cycle_days)
    return out


def _wkt(geom) -> str:
    return f"SRID=4326;{geom.wkt}"


def upsert_districts(db, districts):
    for d in districts:
        stmt = insert(m.District).values(id=d["id"], name=d["name"], name_ru=d["name_ru"], oblast=d["oblast"],
                                         area_km2=round(d["area_km2"], 1), boundary_source=grid.BOUNDARY_SOURCE,
                                         geom=_wkt(d["geom"]))
        db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_={
            "name_ru": stmt.excluded.name_ru, "oblast": stmt.excluded.oblast,
            "area_km2": stmt.excluded.area_km2, "geom": stmt.excluded.geom}))


def upsert_entities(db, model, rows, fields):
    for i in range(0, len(rows), 2000):
        chunk = [{**{f: r[f] for f in fields}, "geom": _wkt(r["geom"])} for r in rows[i:i + 2000]]
        stmt = insert(model).values(chunk)
        db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_={
            f: getattr(stmt.excluded, f) for f in fields if f != "id"} | {"geom": stmt.excluded.geom}))


def upsert_product(db, p) -> int:
    vals = dict(external_id=p.external_id, source=p.source, family=p.family, name=p.name, version=p.version,
                maturity=p.maturity, acq_start=p.acq_start, acq_end=p.acq_end, params=p.params,
                pipeline_version=PIPELINE_VERSION, license=p.license, url=p.url, synthetic=p.synthetic)
    stmt = insert(m.Product).values(**vals)
    stmt = stmt.on_conflict_do_update(index_elements=["external_id"],
                                      set_={k: v for k, v in vals.items() if k != "external_id"})
    return db.execute(stmt.returning(m.Product.id)).scalar_one()


def write_observations(db, result: SourceResult) -> int:
    """COPY во временную таблицу + INSERT ... ON CONFLICT DO UPDATE: быстро и без дублей."""
    pid = upsert_product(db, result.passport)
    fam = result.passport.family
    buf = io.StringIO()
    for o in result.observations:
        val = "\\N" if o.value is None else repr(o.value)
        rel = "\\N" if o.reliable_frac is None else repr(o.reliable_frac)
        q = json.dumps(o.quality, ensure_ascii=False).replace("\\", "\\\\").replace("\t", " ")
        buf.write(f"{o.entity_type}\t{o.entity_id}\t{o.signal}\t{o.obs_date}\t{val}\t{o.unit}\t{rel}\t{q}\n")
    buf.seek(0)
    conn = db.connection().connection  # psycopg connection
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS obs_stage (entity_type text, entity_id text, signal text,"
                    " obs_date date, value double precision, unit text, reliable_frac double precision,"
                    " quality text) ON COMMIT DELETE ROWS")
        cur.execute("TRUNCATE obs_stage")
        with cur.copy("COPY obs_stage FROM STDIN") as cp:
            cp.write(buf.getvalue())
        cur.execute(
            "INSERT INTO observations (entity_type, entity_id, signal, obs_date, value, unit, reliable_frac,"
            " quality, family, product_id) SELECT entity_type, entity_id, signal, obs_date, value, unit,"
            " reliable_frac, quality::json, %s, %s FROM obs_stage "
            "ON CONFLICT ON CONSTRAINT uq_observation DO UPDATE SET value = EXCLUDED.value,"
            " reliable_frac = EXCLUDED.reliable_frac, quality = EXCLUDED.quality, unit = EXCLUDED.unit,"
            " product_id = EXCLUDED.product_id", (fam, pid))
    return len(result.observations)


def _series(result_list: list[SourceResult]) -> dict:
    out = {}
    for r in result_list:
        for o in r.observations:
            s = out.setdefault((o.entity_id, o.signal), Series([], [], []))
            s.dates.append(o.obs_date)
            s.values.append(o.value)
            s.reliable.append(o.reliable_frac)
    return out


def scene_correct(res: SourceResult, min_rel: float) -> dict:
    """Шаг 3 ТЗ: общий для района сдвиг (атмосфера/орбита) вычитается по медиане надёжных ячеек."""
    disp = {}
    for o in res.observations:
        if o.signal == "displacement_mm":
            s = disp.setdefault(o.entity_id, Series([], [], []))
            s.dates.append(o.obs_date)
            s.values.append(o.value)
            s.reliable.append(o.reliable_frac)
    offset = remove_scene_offset(disp, min_rel)
    for o in res.observations:
        if o.signal == "displacement_mm" and o.value is not None:
            o.value = round(o.value - offset.get(o.obs_date, 0.0), 3)
            o.quality["scene_offset_removed_mm"] = round(offset.get(o.obs_date, 0.0), 3)
    return offset


def write_analytics(db, district_id, entity_type, baselines, statuses, status_dates):
    ids = list({s["entity_id"] for s in statuses})
    db.execute(delete(m.Baseline).where(m.Baseline.entity_type == entity_type,
                                        m.Baseline.entity_id.in_(ids)))
    db.execute(delete(m.Status).where(m.Status.entity_type == entity_type, m.Status.district_id == district_id,
                                      m.Status.status_date.in_(status_dates)))
    for i in range(0, len(baselines), 5000):
        db.execute(insert(m.Baseline), baselines[i:i + 5000])
    for i in range(0, len(statuses), 5000):
        db.execute(insert(m.Status), statuses[i:i + 5000])


def write_bulletins(db, district, entity_type, entities, statuses, products, provider, latest, prev_date):
    by = {(s["entity_id"], s["status_date"]): s for s in statuses}
    made, notify, keep = 0, [], set()
    for e in entities:
        cur, prev = by.get((e["id"], latest)), by.get((e["id"], prev_date))
        if not cur:
            continue
        changed = prev is None or prev["status"] != cur["status"]
        if cur["status"] in ("yellow", "red") and changed:
            notify.append({"entity_type": entity_type, "entity_id": e["id"], "status": cur["status"],
                           "prev": prev["status"] if prev else None})
        if not (cur["status"] in ("yellow", "red") or changed):
            continue
        keep.add(e["id"])
        entity = {**e, "entity_type": entity_type, "district_name_ru": district["name_ru"],
                  "oblast": district["oblast"]}
        f = facts_mod.build(entity, cur, prev["status"] if prev else None, products, get_settings().cycle_days)
        for mode in ("plain", "expert"):
            existing = db.scalar(select(m.Bulletin).where(
                m.Bulletin.entity_type == entity_type, m.Bulletin.entity_id == e["id"],
                m.Bulletin.status_date == latest, m.Bulletin.mode == mode, m.Bulletin.lang == "ru"))
            if existing and existing.facts == json.loads(json.dumps(f, default=str)):
                continue   # кэш: факты не изменились — текст и утверждение сохраняются
            g = bulletin_gen.generate(f, mode, provider)
            vals = dict(entity_type=entity_type, entity_id=e["id"], district_id=district["id"],
                        status_date=latest, mode=mode, lang="ru", facts=json.loads(json.dumps(f, default=str)),
                        text=g["text"], generator=g["generator"], check=g["check"], approval="draft",
                        approved_by=None)
            stmt = insert(m.Bulletin).values(**vals)
            db.execute(stmt.on_conflict_do_update(constraint="uq_bulletin", set_={
                k: v for k, v in vals.items() if k not in ("entity_type", "entity_id", "status_date", "mode",
                                                           "lang")}))
            made += 1
    # повторный прогон того же цикла: бюллетени объектов, которые больше не требуют текста, устаревают
    db.execute(delete(m.Bulletin).where(m.Bulletin.entity_type == entity_type,
                                        m.Bulletin.district_id == district["id"],
                                        m.Bulletin.status_date == latest, m.Bulletin.entity_id.not_in(keep)))
    return made, notify


def write_district_bulletin(db, district, latest, prev_date, provider, products):
    from sqlalchemy import func as sfunc
    counts, prev_counts = {}, {}
    for target, day in ((counts, latest), (prev_counts, prev_date)):
        for et, stt, n in db.execute(select(m.Status.entity_type, m.Status.status, sfunc.count()).where(
                m.Status.district_id == district["id"], m.Status.status_date == day)
                .group_by(m.Status.entity_type, m.Status.status)):
            target.setdefault(et, {})[stt] = n
    top_rows = db.scalars(select(m.Status).where(m.Status.district_id == district["id"],
                                                 m.Status.status_date == latest, m.Status.status == "red")
                         .order_by(m.Status.entity_type, m.Status.entity_id)).all()
    top = [{"entity_id": s.entity_id, "status": s.status} for s in top_rows[:5]]
    f = {"entity_type": "district", "district": {"id": district["id"], "name_ru": district["name_ru"],
                                                 "oblast": district["oblast"]},
         "status_date": str(latest), "status": "summary", "counts": counts, "prev_counts": prev_counts, "top": top,
         "totals": {et: sum(c.values()) for et, c in counts.items()},
         "quality": {"synthetic": any(p["synthetic"] for p in products),
                     "provisional": any(p["maturity"] in ("PROVISIONAL", "BETA") for p in products)},
         "sources": [{"name": p["name"], "version": p["version"], "acq_end": str(p["acq_end"])} for p in products]}
    from ai import templates as tpl, validator as val
    text = tpl.render_district(f)
    chk = val.check(text, f)
    vals = dict(entity_type="district", entity_id=district["id"], district_id=district["id"], status_date=latest,
                mode="plain", lang="ru", facts=f, text=text, generator="template", check=chk, approval="draft",
                approved_by=None)
    existing = db.scalar(select(m.Bulletin).where(m.Bulletin.entity_type == "district",
                                                  m.Bulletin.entity_id == district["id"],
                                                  m.Bulletin.status_date == latest, m.Bulletin.mode == "plain"))
    if existing and existing.facts == f:
        return
    stmt = insert(m.Bulletin).values(**vals)
    db.execute(stmt.on_conflict_do_update(constraint="uq_bulletin", set_={
        k: v for k, v in vals.items() if k not in ("entity_type", "entity_id", "status_date", "mode", "lang")}))


def _products_for(db, external_ids: set[str]) -> list[dict]:
    # по external_id, а не по семейству: синтетические продукты свои у каждого района
    rows = db.scalars(select(m.Product).where(m.Product.external_id.in_(external_ids))
                      .order_by(m.Product.family, m.Product.source, m.Product.name)).all()
    return [{"source": p.source, "name": p.name, "version": p.version, "maturity": p.maturity,
             "acq_end": p.acq_end, "synthetic": p.synthetic, "family": p.family} for p in rows]


def run(district_ids: list[str] | None = None, today: date | None = None) -> dict:
    create_schema()
    thr = thresholds()
    cfg = districts_config()
    dates = cycle_dates(today)
    status_dates = dates[-STATUS_CYCLES:]
    latest, prev_date = dates[-1], dates[-2]
    provider = get_provider()
    districts = [d for d in grid.load_districts() if not district_ids or d["id"] in district_ids]
    if not districts:
        raise SystemExit(f"нет районов {district_ids}; доступны: {[d['id'] for d in cfg['districts']]}")

    with SessionLocal() as db:
        run_row = m.PipelineRun(districts=[d["id"] for d in districts], stats={})
        db.add(run_row)
        upsert_districts(db, districts)
        db.commit()
        run_id = run_row.id
    new_key = seed_users()

    stats, notes, notifications = {}, [], []
    for d in districts:
        st = {}
        with SessionLocal() as db:
            cells = grid.build_cells(d, cfg["cell_size_km"])
            upsert_entities(db, m.Cell, cells, ["id", "district_id", "row", "col", "size_km", "inside_frac"])
            glaciers, gerr = glaciers_osm.fetch(d)
            if gerr:
                notes.append(f"{d['id']}: ледники не загружены ({gerr})")
            if glaciers:
                upsert_entities(db, m.Glacier, glaciers,
                                ["id", "district_id", "catalog", "catalog_id", "name", "area_km2", "synthetic",
                                 "attrs"])
            st.update(cells=len(cells), glaciers=len(glaciers))

            # Источники. Смещение/влажность и ледники пока синтетические (нет токена Earthdata).
            cell_res = synthetic.cells_fetch(d["id"], cells, dates)
            scene_correct(cell_res, thr["min_reliable_frac"])
            results_cells, results_gl = [cell_res], []
            if glaciers:
                results_gl.append(synthetic.glaciers_fetch(d["id"], glaciers, dates))
            ents = [("cell", c["id"], *c["centroid"]) for c in cells] + \
                   [("glacier", g["id"], g["geom"].centroid.x, g["geom"].centroid.y) for g in glaciers]
            precip = nasa_power.fetch(ents, dates) or synthetic.precip_fetch(d["id"], ents, dates)
            notes.extend(f"{d['id']}: {n}" for n in cell_res.notes + precip.notes)

            n_obs = sum(write_observations(db, r) for r in [cell_res, precip] + results_gl)
            st["observations"] = n_obs
            db.commit()

            precip_cells = SourceResult(precip.passport, [o for o in precip.observations if o.entity_type == "cell"])
            precip_gl = SourceResult(precip.passport, [o for o in precip.observations if o.entity_type == "glacier"])

            for etype, ents_, res in (("cell", cells, results_cells + [precip_cells]),
                                      ("glacier", glaciers, results_gl + [precip_gl])):
                if not ents_:
                    continue
                series = _series(res)
                baselines, statuses = evaluate(etype, ents_, series, status_dates, thr, get_settings().cycle_days)
                write_analytics(db, d["id"], etype, baselines, statuses, status_dates)
                counts = {}
                for s in statuses:
                    if s["status_date"] == latest:
                        counts[s["status"]] = counts.get(s["status"], 0) + 1
                st[f"{etype}_statuses_latest"] = counts
                products = _products_for(db, {r.passport.external_id for r in res})
                made, notify = write_bulletins(db, d, etype, ents_, statuses, products, provider, latest,
                                               prev_date)
                st[f"{etype}_bulletins"] = made
                notifications.extend({**n, "district_id": d["id"]} for n in notify)
            write_district_bulletin(db, d, latest, prev_date, provider,
                                    _products_for(db, {r.passport.external_id for r in results_cells + [precip]}))
            db.commit()
        stats[d["id"]] = st
        log.info("%s: %s", d["id"], st)

    with SessionLocal() as db:
        r = db.get(m.PipelineRun, run_id)
        r.finished_at = datetime.now(timezone.utc)
        r.status = "ok"
        r.stats = {"districts": stats, "latest_cycle": str(latest), "notifications": notifications}
        r.log = "\n".join(notes)
        db.commit()
    out = {"latest_cycle": str(latest), "districts": stats, "notes": notes, "notifications": len(notifications)}
    if new_key:
        out["researcher_key_shown_once"] = new_key
    return out


def health_snapshot() -> dict:
    with engine.connect() as c:
        row = c.execute(text("SELECT finished_at, status, stats->>'latest_cycle' FROM pipeline_runs "
                             "WHERE status='ok' ORDER BY id DESC LIMIT 1")).first()
    return {"last_run": str(row[0]) if row else None, "latest_cycle": row[2] if row else None}
