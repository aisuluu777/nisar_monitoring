from datetime import date

import pytest

from ai import bulletins, facts, templates, validator
from ai.provider import LLMProvider

PRODUCTS = [{"source": "SYNTHETIC", "name": "Синтетика", "version": "0.1", "maturity": "SYNTHETIC",
             "acq_end": date(2026, 11, 10), "synthetic": True},
            {"source": "NISAR_GUNW", "name": "NISAR GUNW", "version": "0.9", "maturity": "PROVISIONAL",
             "acq_end": date(2026, 11, 10), "synthetic": False}]
ENTITY = {"id": "jeti-oguz-1-1", "district_id": "jeti-oguz", "entity_type": "cell",
          "district_name_ru": "Джети-Огузский", "oblast": "Иссык-Кульская"}


def _status(status, reasons):
    return {"status": status, "status_date": date(2026, 11, 10), "reasons": reasons}


RED = _status("red", [
    {"code": "primary_anomaly", "text_ru": "x", "signal": "displacement_mm", "value": -24.72, "median": 0.095,
     "mad": 0.495, "z": -24.82, "threshold": 3.0},
    {"code": "persistent", "text_ru": "x", "signal": "displacement_mm", "prev_date": "2026-10-29", "prev_z": -10.2},
    {"code": "cluster", "text_ru": "x", "cluster_cells": 5, "min_cells": 3},
    {"code": "confirming", "text_ru": "x", "signal": "precip_30d", "value": 75.7, "median": 40.4, "mad": 12.5,
     "z": 1.91, "threshold": 1.5},
])
GRAY = _status("gray", [{"code": "low_quality", "text_ru": "мало надёжных пикселей", "reliable": 0.1,
                         "min_reliable": 0.3}])


@pytest.mark.parametrize("st", [RED, GRAY])
@pytest.mark.parametrize("mode", ["plain", "expert"])
def test_templates_pass_checks(st, mode):
    f = facts.build(ENTITY, st, "green", PRODUCTS, 12)
    text = templates.render(f, mode)
    assert validator.check(text, f) == {"ok": True, "problems": []}


def test_gray_says_insufficient_not_ok():
    f = facts.build(ENTITY, GRAY, None, PRODUCTS, 12)
    t = templates.render(f, "plain")
    assert "недостаточно" in t.lower() and "не значит, что всё в порядке" in t


def test_validator_catches_invented_number():
    f = facts.build(ENTITY, RED, None, PRODUCTS, 12)
    bad = templates.render(f, "plain").replace("24.7 мм", "57 мм")
    res = validator.check(bad, f)
    assert not res["ok"] and res["problems"][0]["code"] == "numbers_not_in_facts"


@pytest.mark.parametrize("phrase", ["Оползень будет через неделю.", "Участок безопасен.",
                                    "Рекомендуем эвакуацию.", "Наш прогноз: сход."])
def test_validator_catches_forbidden(phrase):
    f = facts.build(ENTITY, RED, None, PRODUCTS, 12)
    res = validator.check(templates.render(f, "plain") + " " + phrase, f)
    assert any(p["code"] == "forbidden_phrases" for p in res["problems"])


def test_validator_requires_data_caveats():
    f = facts.build(ENTITY, RED, None, PRODUCTS, 12)
    text = ("Что мы видим. Смещение 24.7 мм. Чего мы не знаем. Ничего. На чём основано. NISAR.")
    codes = {p["code"] for p in validator.check(text, f)["problems"]}
    assert {"missing_synthetic_note", "missing_provisional_note"} <= codes


class BadLLM(LLMProvider):
    name = "llm:bad"
    enabled = True

    def complete(self, system, user):
        return "Что мы видим. Сдвиг 99 мм, оползень будет. Чего мы не знаем. На чём основано."


def test_bad_llm_falls_back_to_template():
    f = facts.build(ENTITY, RED, None, PRODUCTS, 12)
    g = bulletins.generate(f, "plain", BadLLM())
    assert g["generator"] == "template" and g["check"]["ok"] and len(g["check"]["llm_attempts"]) == 2
