"""Аналитика (раздел 6 ТЗ): сезонная норма (медиана + MAD), устойчивый z-балл, сравнение с соседями,
кластеры, статусы с причинами. Только объяснимая статистика: каждое правило оставляет причину с числами.

Норма строится по данным строго до первой оцениваемой даты, поэтому оцениваемые циклы
не попадают в собственную норму."""
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from app.config import ANALYTICS_VERSION

# Нижняя граница разброса, чтобы почти постоянный ряд не давал огромных z.
MAD_FLOOR = {"displacement_mm": 1.0, "soil_moisture": 0.01, "precip_7d": 3.0, "precip_30d": 5.0,
             "glacier_velocity": 1.0, "snow_cover": 0.05}
# Какое направление отклонения считается сигналом.
DIRECTION = {"displacement_mm": "abs", "soil_moisture": "up", "precip_7d": "up", "precip_30d": "up",
             "glacier_velocity": "up", "snow_cover": "abs"}
PRIMARY = {"cell": "displacement_mm", "glacier": "glacier_velocity"}
CONTEXT = {"cell": ["soil_moisture", "precip_30d", "precip_7d"],
           "glacier": ["precip_30d", "snow_cover"]}
# Осадки одинаковы для всего района (узел NASA POWER ~50 км), поэтому сами по себе жёлтый не дают —
# иначе один дождь окрашивает весь район. Они только подтверждают первичный сигнал для красного.
CONFIRM_ONLY = {"precip_7d", "precip_30d"}


@dataclass
class Series:
    dates: list[date]
    values: list[float | None]
    reliable: list[float | None]

    def at(self, d: date):
        try:
            i = self.dates.index(d)
        except ValueError:
            return None, None
        return self.values[i], self.reliable[i]


def month_window(m: int) -> set[int]:
    return {((m - 2) % 12) + 1, m, (m % 12) + 1}


def robust_baseline(dates, values, month: int, before: date) -> tuple[float, float, int] | None:
    win = month_window(month)
    xs = [v for d, v in zip(dates, values) if v is not None and d < before and d.month in win]
    if not xs:
        return None
    arr = np.asarray(xs, dtype=float)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    return med, mad, len(xs)


def zscore(signal: str, x: float, med: float, mad: float) -> float:
    scale = max(1.4826 * mad, MAD_FLOOR.get(signal, 1e-6))
    return (x - med) / scale


def hit(signal: str, z: float, thr: float) -> bool:
    return abs(z) >= thr if DIRECTION.get(signal) == "abs" else z >= thr


def remove_scene_offset(series: dict[str, Series], min_reliable: float) -> dict[date, float]:
    """Сравнение с «соседями»: общий для всего района сдвиг (атмосфера, орбита) вычитается
    медианой по надёжным ячейкам на каждую дату. Возвращает сдвиг по датам."""
    per_date = defaultdict(list)
    for s in series.values():
        for d, v, r in zip(s.dates, s.values, s.reliable):
            if v is not None and (r or 0) >= min_reliable:
                per_date[d].append(v)
    offset = {d: float(np.median(v)) for d, v in per_date.items() if len(v) >= 5}
    for s in series.values():
        s.values = [None if v is None else round(v - offset.get(d, 0.0), 3)
                    for d, v in zip(s.dates, s.values)]
    return offset


def clusters(hit_cells: set[tuple[int, int]]) -> dict[tuple[int, int], int]:
    """Связные группы соседних ячеек (4-соседство). Возвращает размер группы для каждой ячейки."""
    size, seen = {}, set()
    for start in hit_cells:
        if start in seen:
            continue
        comp, q = [], deque([start])
        seen.add(start)
        while q:
            r, c = q.popleft()
            comp.append((r, c))
            for nb in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if nb in hit_cells and nb not in seen:
                    seen.add(nb)
                    q.append(nb)
        for rc in comp:
            size[rc] = len(comp)
    return size


def _reason(code, text, **kw):
    return {"code": code, "text_ru": text, **{k: (round(v, 3) if isinstance(v, float) else v)
                                              for k, v in kw.items()}}


def evaluate(entity_type: str, entities: list[dict], series: dict[tuple[str, str], Series],
             status_dates: list[date], thr: dict, cycle_days: int) -> tuple[list[dict], list[dict]]:
    """series: ключ (entity_id, signal). entities: dict с id (и row/col для ячеек).
    Возвращает (baselines, statuses)."""
    primary = PRIMARY[entity_type]
    cutoff = min(status_dates)
    max_age = timedelta(days=thr["max_data_age_days"])
    baselines, statuses = [], []
    zcache: dict[tuple, dict] = {}

    # Нормы для хранения и «полосы нормы» на графиках.
    for e in entities:
        for sig in [primary] + CONTEXT[entity_type]:
            s = series.get((e["id"], sig))
            if not s:
                continue
            for m in range(1, 13):
                b = robust_baseline(s.dates, s.values, m, cutoff)
                if b:
                    baselines.append({"entity_type": entity_type, "entity_id": e["id"], "signal": sig,
                                      "month": m, "median": round(b[0], 4), "mad": round(b[1], 4),
                                      "n": b[2], "version": ANALYTICS_VERSION})

    def signal_eval(eid, sig, d):
        key = (eid, sig, d)
        if key in zcache:
            return zcache[key]
        s = series.get((eid, sig))
        res = None
        if s:
            x, rel = s.at(d)
            b = robust_baseline(s.dates, s.values, d.month, cutoff)
            if x is not None and b:
                med, mad, n = b
                res = {"signal": sig, "value": x, "reliable": rel, "median": med, "mad": mad, "n": n,
                       "z": zscore(sig, x, med, mad)}
            elif b:
                res = {"signal": sig, "value": None, "reliable": rel, "median": b[0], "mad": b[1],
                       "n": b[2], "z": None}
        zcache[key] = res
        return res

    rc_of = {e["id"]: (e.get("row"), e.get("col")) for e in entities}
    for di, d in enumerate(sorted(status_dates)):
        prev_d = d - timedelta(days=cycle_days)
        # Первичный сигнал всех объектов на дату — нужен для кластеров.
        prim = {e["id"]: signal_eval(e["id"], primary, d) for e in entities}
        prim_hit = {eid for eid, r in prim.items()
                    if r and r["z"] is not None and (r["reliable"] or 0) >= thr["min_reliable_frac"]
                    and hit(primary, r["z"], thr["z_signal"])}
        csize = clusters({rc_of[eid] for eid in prim_hit}) if entity_type == "cell" else {}

        for e in entities:
            eid, reasons = e["id"], []
            p = prim[eid]
            s = series.get((eid, primary))
            last_obs = max((dd for dd, v in zip(s.dates, s.values) if v is not None and dd <= d),
                           default=None) if s else None
            gray = None
            if last_obs is None or d - last_obs > max_age:
                gray = _reason("stale", "нет свежих данных дольше допустимого срока",
                               last_data=str(last_obs) if last_obs else None,
                               max_age_days=thr["max_data_age_days"])
            elif p is None or p["n"] < thr["min_baseline_n"]:
                gray = _reason("short_history", "мало истории для расчёта нормы",
                               n=p["n"] if p else 0, min_n=thr["min_baseline_n"])
            elif p["value"] is None or (p["reliable"] or 0) < thr["min_reliable_frac"]:
                gray = _reason("low_quality", "мало надёжных пикселей или пар снимков (снег, облака, "
                               "потеря когерентности)",
                               reliable=p["reliable"], min_reliable=thr["min_reliable_frac"])
            if gray:
                statuses.append(_status(entity_type, e, d, "gray", [gray], thr))
                continue

            primary_hit = eid in prim_hit
            if primary_hit:
                reasons.append(_reason("primary_anomaly", "значение выше нормы для этого сезона",
                                       signal=primary, value=p["value"], median=p["median"],
                                       mad=p["mad"], z=p["z"], threshold=thr["z_signal"]))
            prev = signal_eval(eid, primary, prev_d)
            persistent = bool(primary_hit and prev and prev["z"] is not None
                              and (prev["reliable"] or 0) >= thr["min_reliable_frac"]
                              and hit(primary, prev["z"], thr["z_signal"]))
            if persistent:
                reasons.append(_reason("persistent", "отклонение держится второй цикл подряд",
                                       signal=primary, prev_date=str(prev_d), prev_z=prev["z"]))
            cl = csize.get(rc_of[eid], 0)
            clustered = cl >= thr["min_cluster_cells"]
            if primary_hit and clustered:
                reasons.append(_reason("cluster", "соседние ячейки отклоняются вместе",
                                       cluster_cells=cl, min_cells=thr["min_cluster_cells"]))
            elif primary_hit and entity_type == "cell":
                reasons.append(_reason("isolated", "одиночное отклонение без соседей — слабый сигнал",
                                       cluster_cells=cl))

            context_hit, confirm = False, []
            for sig in CONTEXT[entity_type]:
                c = signal_eval(eid, sig, d)
                if not c or c["z"] is None:
                    continue
                if hit(sig, c["z"], thr["z_context"]) and sig not in CONFIRM_ONLY:
                    context_hit = True
                    reasons.append(_reason("context_anomaly", "сопутствующий сигнал выше нормы",
                                           signal=sig, value=c["value"], median=c["median"],
                                           mad=c["mad"], z=c["z"], threshold=thr["z_context"]))
                elif hit(sig, c["z"], thr["z_confirm"]):  # включая сильные осадки (CONFIRM_ONLY)
                    confirm.append(sig)
                    reasons.append(_reason("confirming", "сопутствующий сигнал повышен",
                                           signal=sig, value=c["value"], median=c["median"],
                                           mad=c["mad"], z=c["z"], threshold=thr["z_confirm"]))
            confirmed = context_hit or bool(confirm)

            if primary_hit and (persistent or clustered) and confirmed:
                status = "red"
            elif primary_hit or context_hit:
                status = "yellow"
            else:
                status = "green"
                reasons.append(_reason("within_norm", "все сигналы в пределах нормы",
                                       signal=primary, value=p["value"], median=p["median"], z=p["z"]))
            statuses.append(_status(entity_type, e, d, status, reasons, thr))
    return baselines, statuses


def _status(entity_type, e, d, status, reasons, thr):
    return {"entity_type": entity_type, "entity_id": e["id"], "district_id": e["district_id"],
            "status_date": d, "status": status, "reasons": reasons,
            "analytics_version": ANALYTICS_VERSION, "thresholds_version": thr["version"]}
