"""Районы и сетка ячеек. Сетка строится в UTM 43N (метры), хранится в WGS84."""
import json
import math

from pyproj import Geod, Transformer
from shapely.geometry import MultiPolygon, box, mapping, shape
from shapely.ops import transform
from shapely.prepared import prep

from app.config import DATA_DIR, districts_config

BOUNDARY_FILE = DATA_DIR / "boundaries" / "adm2.geojson"
BOUNDARY_SOURCE = "geoBoundaries KGZ ADM2 (2010), CC BY-SA 3.0"

_to_utm = Transformer.from_crs(4326, 32643, always_xy=True).transform
_to_wgs = Transformer.from_crs(32643, 4326, always_xy=True).transform
_geod = Geod(ellps="WGS84")


def area_km2(geom) -> float:
    return abs(_geod.geometry_area_perimeter(geom)[0]) / 1e6


def load_districts() -> list[dict]:
    """Пилотные районы из config/districts.yaml с геометрией из geoBoundaries."""
    cfg = districts_config()
    features = {f["properties"]["shapeName"]: f
                for f in json.loads(BOUNDARY_FILE.read_text(encoding="utf-8"))["features"]}
    out = []
    for d in cfg["districts"]:
        if d["name"] not in features:
            raise ValueError(f"район {d['name']} не найден в {BOUNDARY_FILE.name}")
        geom = shape(features[d["name"]]["geometry"])
        if geom.geom_type == "Polygon":
            geom = MultiPolygon([geom])
        out.append({**d, "geom": geom, "area_km2": area_km2(geom)})
    return out


def build_cells(district: dict, size_km: float) -> list[dict]:
    """Квадратные ячейки, пересекающие район. row/col нужны для поиска соседей."""
    utm = transform(_to_utm, district["geom"])
    minx, miny, maxx, maxy = utm.bounds
    step = size_km * 1000
    x0, y0 = math.floor(minx / step) * step, math.floor(miny / step) * step
    prepared = prep(utm)
    cells = []
    for r in range(int((maxy - y0) // step) + 1):
        for c in range(int((maxx - x0) // step) + 1):
            sq = box(x0 + c * step, y0 + r * step, x0 + (c + 1) * step, y0 + (r + 1) * step)
            if not prepared.intersects(sq):
                continue
            frac = sq.intersection(utm).area / sq.area
            if frac < 0.05:
                continue
            wgs = transform(_to_wgs, sq)
            cells.append({
                "id": f"{district['id']}-{r}-{c}",
                "district_id": district["id"],
                "row": r, "col": c, "size_km": size_km,
                "inside_frac": round(frac, 3),
                "geom": wgs,
                "centroid": (wgs.centroid.x, wgs.centroid.y),
            })
    return cells


def to_geojson(geom) -> dict:
    return mapping(geom)
