"""NASA POWER: суточные осадки (PRECTOTCORR) по узлам сетки POWER (0.5° × 0.625°).
Без ключа. Ответы кэшируются на диск, повторный запуск не ходит в сеть."""
import json
import logging
import time
from datetime import date, timedelta

import httpx

from app.config import DATA_DIR
from pipeline.sources.base import Obs, ProductPassport, SourceResult

log = logging.getLogger(__name__)
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
CACHE = DATA_DIR / "cache" / "power"
FILL = -999.0


def node_for(lon: float, lat: float) -> tuple[float, float]:
    return round(round(lon / 0.625) * 0.625, 4), round(round(lat * 2) / 2, 2)


def _fetch_node(lon: float, lat: float, start: date, end: date) -> dict[date, float] | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{lon}_{lat}_{start:%Y%m%d}_{end:%Y%m%d}.json"
    if path.exists():
        raw = json.loads(path.read_text())
    else:
        params = {"parameters": "PRECTOTCORR", "community": "AG", "longitude": lon, "latitude": lat,
                  "start": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}", "format": "JSON"}
        raw = None
        for attempt in range(4):
            try:
                r = httpx.get(URL, params=params, timeout=120,
                              headers={"User-Agent": "nasa-space-monitor/0.1"})
                r.raise_for_status()
                raw = r.json()
                break
            except Exception as e:  # сеть нестабильна — несколько попыток, затем отказ
                log.warning("POWER %s,%s попытка %d: %s", lon, lat, attempt + 1, e)
                time.sleep(2 * (attempt + 1))
        if raw is None:
            return None
        path.write_text(json.dumps(raw))
    series = raw["properties"]["parameter"]["PRECTOTCORR"]
    out = {}
    for k, v in series.items():
        d = date(int(k[:4]), int(k[4:6]), int(k[6:]))
        out[d] = None if v == FILL else float(v)
    return out


def _window_sum(daily: dict, d: date, days: int) -> float | None:
    vals = [daily.get(d - timedelta(days=i)) for i in range(days)]
    vals = [v for v in vals if v is not None]
    return round(sum(vals), 2) if len(vals) >= days * 0.8 else None


def fetch(entities: list[tuple[str, str, float, float]], obs_dates: list[date]) -> SourceResult | None:
    """entities: (entity_type, entity_id, lon, lat). Возвращает None, если POWER недоступен."""
    start, end = min(obs_dates) - timedelta(days=31), max(obs_dates)
    by_node: dict[tuple, list] = {}
    for et, eid, lon, lat in entities:
        by_node.setdefault(node_for(lon, lat), []).append((et, eid))
    obs, failed = [], []
    for (lon, lat), members in by_node.items():
        daily = _fetch_node(lon, lat, start, end)
        if daily is None:
            failed.append((lon, lat))
            continue
        for d in obs_dates:
            p7, p30 = _window_sum(daily, d, 7), _window_sum(daily, d, 30)
            for et, eid in members:
                q = {"power_node": [lon, lat]}
                obs.append(Obs(et, eid, "precip_7d", d, p7, "мм", None, q))
                obs.append(Obs(et, eid, "precip_30d", d, p30, "мм", None, q))
    if not obs:
        return None
    passport = ProductPassport(
        external_id=f"NASA_POWER:PRECTOTCORR:{start}:{end}",
        source="NASA_POWER", family="NASA_POWER_DAILY", name="POWER Daily PRECTOTCORR (MERRA-2/IMERG)",
        version="v2", maturity="VALIDATED", license="NASA open data, ссылка на источник обязательна",
        acq_start=start, acq_end=end, url=URL,
        params={"nodes": len(by_node), "failed_nodes": failed, "grid": "0.5x0.625 deg"})
    notes = [f"POWER: {len(failed)} узлов недоступно"] if failed else []
    return SourceResult(passport, obs, notes)
