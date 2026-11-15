"""Контуры ледников из OpenStreetMap (natural=glacier) через Overpass API, лицензия ODbL.
Временный каталог для прототипа: позже заменяется на RGI 7 / GLIMS (NSIDC, нужен Earthdata).
Ответ кэшируется на диск, повторный запуск не ходит в сеть."""
import json
import logging
import time

import httpx
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid

from app.config import DATA_DIR
from pipeline.grid import area_km2

log = logging.getLogger(__name__)
ENDPOINT = "https://overpass-api.de/api/interpreter"
CACHE = DATA_DIR / "cache" / "glaciers"
LICENSE = "© OpenStreetMap contributors, ODbL 1.0"
MIN_AREA_KM2 = 0.1


def _query(bbox) -> dict | None:
    minx, miny, maxx, maxy = bbox
    q = (f'[out:json][timeout:120];(way["natural"="glacier"]({miny},{minx},{maxy},{maxx});'
         f'relation["natural"="glacier"]({miny},{minx},{maxy},{maxx}););out geom;')
    for attempt in range(4):
        try:
            r = httpx.post(ENDPOINT, data={"data": q}, timeout=180,
                           headers={"User-Agent": "nasa-space-monitor/0.1 (prototype)"})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning("Overpass попытка %d: %s", attempt + 1, e)
            time.sleep(5 * (attempt + 1))
    return None


def _ring(geometry: list[dict]) -> list[tuple]:
    return [(p["lon"], p["lat"]) for p in geometry]


def _to_polygon(el: dict):
    if el["type"] == "way":
        pts = _ring(el.get("geometry", []))
        return Polygon(pts) if len(pts) >= 4 and pts[0] == pts[-1] else None
    outers = [Polygon(_ring(m["geometry"])) for m in el.get("members", [])
              if m.get("role") == "outer" and len(m.get("geometry", [])) >= 4
              and m["geometry"][0] == m["geometry"][-1]]
    inners = [Polygon(_ring(m["geometry"])) for m in el.get("members", [])
              if m.get("role") == "inner" and len(m.get("geometry", [])) >= 4
              and m["geometry"][0] == m["geometry"][-1]]
    if not outers:
        return None
    geom = unary_union(outers)
    if inners:
        geom = geom.difference(unary_union(inners))
    return geom


def fetch(district: dict) -> tuple[list[dict], str | None]:
    """Ледники, центр которых лежит внутри района. Возвращает (ледники, ошибка)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{district['id']}.json"
    if path.exists():
        raw = json.loads(path.read_text())
    else:
        raw = _query(district["geom"].bounds)
        if raw is None:
            return [], "Overpass недоступен"
        path.write_text(json.dumps(raw))
    out = []
    for el in raw.get("elements", []):
        geom = _to_polygon(el)
        if geom is None:
            continue
        geom = make_valid(geom)
        if not district["geom"].contains(geom.representative_point()):
            continue
        polys = [g for g in getattr(geom, "geoms", [geom]) if isinstance(g, Polygon)]
        if not polys:
            continue
        geom = MultiPolygon(polys)
        a = area_km2(geom)
        if a < MIN_AREA_KM2:
            continue
        tags = el.get("tags", {})
        out.append({
            "id": f"osm-{el['type'][0]}{el['id']}",
            "district_id": district["id"],
            "catalog": "OSM", "catalog_id": f"{el['type']}/{el['id']}",
            "name": tags.get("name:ru") or tags.get("name") or tags.get("name:ky"),
            "area_km2": round(a, 3), "synthetic": False, "geom": geom,
            "attrs": {"license": LICENSE, "osm_tags": {k: v for k, v in tags.items()
                                                       if k.startswith(("name", "glacier", "ele"))}},
        })
    return out, None
