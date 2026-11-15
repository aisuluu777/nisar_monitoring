"""Запасной источник: детерминированные синтетические ряды там, где реальных данных пока нет
(нет токена Earthdata, нет покрытия). Каждый продукт помечен synthetic=true и maturity=SYNTHETIC,
поэтому в API, паспортах и текстах эти данные никогда не выдаются за наблюдения NASA.

В ряды вшиты проверочные аномалии: кластер ускоряющегося смещения (с ростом влажности),
одиночный выброс, общий для района «атмосферный» сдвиг и зимняя потеря когерентности,
а у части ледников — подвижка (резкое ускорение)."""
import math
import zlib
from datetime import date, timedelta

import numpy as np

from pipeline.sources.base import Obs, ProductPassport, SourceResult


def _rng(*keys) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32("|".join(map(str, keys)).encode()))


def _season(d: date) -> float:
    return math.sin(2 * math.pi * (d.timetuple().tm_yday - 80) / 365.25)  # пик ~ конец июня


def _winter(d: date) -> bool:
    return d.month in (12, 1, 2, 3)


def anomaly_plan(district_id: str, cells: list[dict]) -> dict:
    """Какие ячейки получают проверочную аномалию. Детерминировано по району."""
    rng = _rng("plan", district_id)
    by_rc = {(c["row"], c["col"]): c["id"] for c in cells}
    interior = [c for c in cells if c["inside_frac"] > 0.9]
    plan = {"cluster": set(), "single": set()}
    if len(interior) < 10:
        return plan
    seed = interior[int(rng.integers(len(interior)))]
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if abs(dr) + abs(dc) <= 1 and (seed["row"] + dr, seed["col"] + dc) in by_rc:
                plan["cluster"].add(by_rc[(seed["row"] + dr, seed["col"] + dc)])
    single = interior[int(rng.integers(len(interior)))]
    if single["id"] not in plan["cluster"]:
        plan["single"].add(single["id"])
    return plan


def cells_fetch(district_id: str, cells: list[dict], dates: list[date]) -> SourceResult:
    plan = anomaly_plan(district_id, cells)
    atm = _rng("atm", district_id).normal(0, 3.0, len(dates))  # общий для сцены сдвиг
    last = len(dates) - 1
    obs = []
    for c in cells:
        rng = _rng("cell", c["id"])
        high = rng.random() < 0.4               # «высокогорная» ячейка: зимой теряет когерентность
        sm_base = 0.12 + 0.08 * rng.random()
        for i, d in enumerate(dates):
            winter = _winter(d)
            reliable = float(np.clip(rng.normal(0.75, 0.08), 0, 1))
            if winter and high:
                reliable = float(np.clip(rng.normal(0.15, 0.05), 0, 1))
            disp = 1.5 * _season(d) + rng.normal(0, 1.5) + atm[i]
            moisture = None if (winter and high) else sm_base + 0.06 * max(_season(d + timedelta(days=60)), 0) \
                + rng.normal(0, 0.012)
            if c["id"] in plan["cluster"] and i >= last - 2:
                disp -= 12 + 6 * (i - (last - 2))   # ускорение последние три цикла
                if moisture is not None:
                    moisture += 0.08
                reliable = max(reliable, 0.6)
            if c["id"] in plan["single"] and i == last:
                disp -= 14
                reliable = max(reliable, 0.6)
            q = {"coherence_mean": round(reliable, 3), "scene_offset_mm": round(float(atm[i]), 2)}
            obs.append(Obs("cell", c["id"], "displacement_mm", d, round(float(disp), 2), "мм",
                           round(reliable, 3), q))
            obs.append(Obs("cell", c["id"], "soil_moisture", d,
                           None if moisture is None else round(float(moisture), 4), "м³/м³",
                           None if moisture is None else 1.0,
                           {"reason": "snow_or_frozen"} if moisture is None else {}))
    passport = ProductPassport(
        external_id=f"SYNTHETIC:cells:{district_id}:{dates[0]}:{dates[-1]}",
        source="SYNTHETIC", family="SYNTHETIC_INSAR", name="Синтетическое смещение и влажность (заглушка)",
        version="0.1", maturity="SYNTHETIC", license="—", acq_start=dates[0], acq_end=dates[-1],
        params={"replaces": ["NISAR_GUNW", "SENTINEL1_HYP3", "NISAR_SME2"],
                "anomaly_cluster": sorted(plan["cluster"]), "anomaly_single": sorted(plan["single"])},
        synthetic=True)
    return SourceResult(passport, obs, ["смещение и влажность синтетические: нет токена Earthdata"])


def glaciers_fetch(district_id: str, glaciers: list[dict], dates: list[date]) -> SourceResult:
    last = len(dates) - 1
    surge = {g["id"] for g in glaciers if _rng("surge", g["id"]).random() < 0.03}
    obs = []
    for g in glaciers:
        rng = _rng("glacier", g["id"])
        v0 = 8 + 50 * rng.random() * min(1.0, math.sqrt(g["area_km2"]) / 3)
        for i, d in enumerate(dates):
            cloudy = rng.random() < (0.45 if _winter(d) else 0.25)   # нет пары без облаков
            v = v0 * (1 + 0.2 * _season(d)) * (1 + rng.normal(0, 0.06))
            if g["id"] in surge and i >= last - 1:
                v *= 2.5
                cloudy = False
            snow = float(np.clip(0.55 - 0.4 * _season(d) + rng.normal(0, 0.06), 0, 1))
            obs.append(Obs("glacier", g["id"], "glacier_velocity", d,
                           None if cloudy else round(float(v), 2), "м/год",
                           0.1 if cloudy else 0.8, {"reason": "cloud"} if cloudy else {}))
            obs.append(Obs("glacier", g["id"], "snow_cover", d, round(snow, 3), "доля", 0.9, {}))
    passport = ProductPassport(
        external_id=f"SYNTHETIC:glaciers:{district_id}:{dates[0]}:{dates[-1]}",
        source="SYNTHETIC", family="SYNTHETIC_GLACIER", name="Синтетическая скорость ледников и снег (заглушка)",
        version="0.1", maturity="SYNTHETIC", license="—", acq_start=dates[0], acq_end=dates[-1],
        params={"replaces": ["ITS_LIVE", "MODIS_VIIRS_SNOW"], "surge": sorted(surge)}, synthetic=True)
    return SourceResult(passport, obs, ["скорость ледников и снег синтетические"])


def precip_fetch(district_id: str, entities: list[tuple], dates: list[date]) -> SourceResult:
    """Только если NASA POWER недоступен: осадки по району с вшитым влажным периодом."""
    rng = _rng("precip", district_id)
    last = len(dates) - 1
    obs = []
    for i, d in enumerate(dates):
        base30 = max(0.0, 35 + 25 * _season(d + timedelta(days=-60)) + rng.normal(0, 8))
        if i >= last - 2:
            base30 *= 1.8
        p30, p7 = round(base30, 1), round(base30 * 0.25 * (0.6 + 0.8 * rng.random()), 1)
        for et, eid, *_ in entities:
            obs.append(Obs(et, eid, "precip_7d", d, p7, "мм", None, {}))
            obs.append(Obs(et, eid, "precip_30d", d, p30, "мм", None, {}))
    passport = ProductPassport(
        external_id=f"SYNTHETIC:precip:{district_id}:{dates[0]}:{dates[-1]}",
        source="SYNTHETIC", family="SYNTHETIC_PRECIP", name="Синтетические осадки (NASA POWER недоступен)",
        version="0.1", maturity="SYNTHETIC", license="—", acq_start=dates[0], acq_end=dates[-1],
        params={"replaces": ["NASA_POWER"]}, synthetic=True)
    return SourceResult(passport, obs, ["осадки синтетические: NASA POWER недоступен"])

