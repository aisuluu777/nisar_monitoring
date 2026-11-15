"""Пакет фактов (раздел 7 ТЗ): единственный вход для текстов. Только посчитанные числа,
никаких персональных данных и сырых снимков."""
from pipeline.sources.base import SIGNALS

STATUS_RU = {"green": "в пределах нормы", "yellow": "нужна проверка (жёлтый)",
             "red": "нужна проверка специалиста (красный)", "gray": "недостаточно данных"}


def build(entity: dict, status: dict, prev_status: str | None, products: list[dict],
          cycle_days: int) -> dict:
    signals = {}
    for r in status["reasons"]:
        sig = r.get("signal")
        if sig and "value" in r and sig not in signals:
            signals[sig] = {"label_ru": SIGNALS[sig]["label_ru"], "unit": SIGNALS[sig]["unit"],
                            "value": r.get("value"), "norm_median": r.get("median"), "z": r.get("z")}
    maturities = sorted({p["maturity"] for p in products})
    return {
        "entity_type": entity["entity_type"],
        "entity_id": entity["id"],
        "entity_name": entity.get("name"),
        "glacier_area_km2": entity.get("area_km2") if entity["entity_type"] == "glacier" else None,
        "district": {"id": entity["district_id"], "name_ru": entity.get("district_name_ru"),
                     "oblast": entity.get("oblast")},
        "status_date": str(status["status_date"]),
        "cycle_days": cycle_days,
        "status": status["status"],
        "status_ru": STATUS_RU[status["status"]],
        "prev_status": prev_status,
        "reasons": status["reasons"],
        "signals": signals,
        "quality": {
            "synthetic": any(p["synthetic"] for p in products),
            "maturities": maturities,
            "provisional": any(m in ("PROVISIONAL", "BETA") for m in maturities),
        },
        "sources": [{"source": p["source"], "name": p["name"], "version": p["version"],
                     "maturity": p["maturity"], "acq_end": str(p["acq_end"]) if p["acq_end"] else None,
                     "synthetic": p["synthetic"]} for p in products],
    }
