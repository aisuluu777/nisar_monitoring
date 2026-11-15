from datetime import date, timedelta

import numpy as np

from analytics.engine import Series, clusters, evaluate
from app.config import thresholds

THR = thresholds()
DATES = [date(2024, 1, 1) + timedelta(days=12 * i) for i in range(88)]
STATUS_DATES = DATES[-3:]


def _flat(value=0.0, reliable=0.8, noise=0.5, seed=0):
    rng = np.random.default_rng(seed)
    vals = [float(value + rng.normal(0, noise)) for _ in DATES]
    vals[-1] = vals[-2] = value   # оцениваемые циклы — ровно в норме
    return Series(list(DATES), vals, [reliable] * len(DATES))


def _grid(n=4):
    return [{"id": f"d-{r}-{c}", "district_id": "d", "row": r, "col": c} for r in range(n) for c in range(n)]


def _base_series(cells):
    s = {}
    for c in cells:
        s[(c["id"], "displacement_mm")] = _flat()
        s[(c["id"], "soil_moisture")] = _flat(0.15, 1.0, 0.005)
        s[(c["id"], "precip_30d")] = _flat(40, None, 5)
    return s


def _latest(statuses, eid):
    return next(s for s in statuses if s["entity_id"] == eid and s["status_date"] == STATUS_DATES[-1])


def test_all_normal_is_green():
    cells = _grid()
    _, st = evaluate("cell", cells, _base_series(cells), STATUS_DATES, THR, 12)
    assert {s["status"] for s in st} == {"green"}


def test_low_quality_is_gray_not_green():
    cells = _grid()
    series = _base_series(cells)
    series[("d-0-0", "displacement_mm")].reliable[-1] = 0.05
    _, st = evaluate("cell", cells, series, STATUS_DATES, THR, 12)
    s = _latest(st, "d-0-0")
    assert s["status"] == "gray" and s["reasons"][0]["code"] == "low_quality"


def test_short_history_is_gray():
    cells = _grid(1)
    series = {("d-0-0", "displacement_mm"): Series(DATES[-4:], [0.1, 0.2, 0.1, 0.3], [0.8] * 4)}
    _, st = evaluate("cell", cells, series, STATUS_DATES, THR, 12)
    assert _latest(st, "d-0-0")["status"] == "gray"


def test_single_outlier_is_yellow_isolated():
    cells = _grid()
    series = _base_series(cells)
    series[("d-1-1", "displacement_mm")].values[-1] = -20
    _, st = evaluate("cell", cells, series, STATUS_DATES, THR, 12)
    s = _latest(st, "d-1-1")
    codes = {r["code"] for r in s["reasons"]}
    assert s["status"] == "yellow" and "isolated" in codes


def test_persistent_cluster_with_moisture_is_red():
    cells = _grid()
    series = _base_series(cells)
    for eid in ("d-1-1", "d-1-2", "d-2-1"):
        series[(eid, "displacement_mm")].values[-1] = -20
        series[(eid, "displacement_mm")].values[-2] = -18
        series[(eid, "soil_moisture")].values[-1] = 0.3
    _, st = evaluate("cell", cells, series, STATUS_DATES, THR, 12)
    s = _latest(st, "d-1-1")
    codes = {r["code"] for r in s["reasons"]}
    assert s["status"] == "red"
    assert {"primary_anomaly", "persistent", "cluster"} <= codes
    reason = next(r for r in s["reasons"] if r["code"] == "primary_anomaly")
    assert reason["value"] == -20 and reason["z"] < -THR["z_signal"]   # причина содержит числа


def test_red_requires_confirming_signal():
    cells = _grid()
    series = _base_series(cells)
    for eid in ("d-1-1", "d-1-2", "d-2-1"):
        series[(eid, "displacement_mm")].values[-1] = -20
        series[(eid, "displacement_mm")].values[-2] = -18
    _, st = evaluate("cell", cells, series, STATUS_DATES, THR, 12)
    assert _latest(st, "d-1-1")["status"] == "yellow"


def test_rain_alone_does_not_make_yellow():
    cells = _grid()
    series = _base_series(cells)
    for c in cells:
        series[(c["id"], "precip_30d")].values[-1] = 200
    _, st = evaluate("cell", cells, series, STATUS_DATES, THR, 12)
    assert _latest(st, "d-0-0")["status"] == "green"


def test_glacier_surge_two_cycles_with_snow_anomaly_is_red():
    gl = [{"id": "g1", "district_id": "d"}]
    series = {("g1", "glacier_velocity"): _flat(30, 0.8, 1.0), ("g1", "snow_cover"): _flat(0.5, 0.9, 0.02),
              ("g1", "precip_30d"): _flat(40, None, 5)}
    series[("g1", "glacier_velocity")].values[-1] = 80
    series[("g1", "glacier_velocity")].values[-2] = 75
    series[("g1", "precip_30d")].values[-1] = 90
    _, st = evaluate("glacier", gl, series, STATUS_DATES, THR, 12)
    assert _latest(st, "g1")["status"] == "red"


def test_clusters_sizes():
    size = clusters({(0, 0), (0, 1), (1, 1), (5, 5)})
    assert size[(0, 0)] == 3 and size[(5, 5)] == 1
