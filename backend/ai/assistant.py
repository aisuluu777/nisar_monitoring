"""Чат по данным (раздел 7 ТЗ). Ассистент вызывает только функции чтения и видит только то,
что доступно роли. Вопрос пользователя — недоверенный текст: он не меняет правила.
Без LLM работает разбор намерения по ключевым словам и шаблонный ответ."""
import re
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai import validator
from ai.provider import SYSTEM_PROMPT, get_provider
from app import models as m
from app.auth import Principal

REFUSE = re.compile(r"прогноз|будет ли|случится ли|сойд[её]т ли|эваку|безопасн|опасн|вероятност", re.I)
CELL_ID = re.compile(r"\b([a-z\-]+-\d+-\d+|osm-[wr]\d+)\b")


# --- функции только для чтения ---------------------------------------------------------------------
def fn_status_counts(db, district_id, d):
    rows = db.execute(select(m.Status.entity_type, m.Status.status, func.count())
                      .where(m.Status.district_id == district_id, m.Status.status_date == d)
                      .group_by(m.Status.entity_type, m.Status.status)).all()
    out = {}
    for et, st, n in rows:
        out.setdefault(et, {})[st] = n
    return out


def fn_entity_status(db, entity_id):
    return db.scalar(select(m.Status).where(m.Status.entity_id == entity_id)
                     .order_by(m.Status.status_date.desc()))


def fn_top_moving(db, district_id, d, limit=5):
    rows = db.scalars(select(m.Status).where(m.Status.district_id == district_id, m.Status.status_date == d,
                                             m.Status.status.in_(("red", "yellow")))).all()
    def z(s):
        return max((abs(r.get("z") or 0) for r in s.reasons if r["code"] == "primary_anomaly"), default=0)
    return sorted(rows, key=z, reverse=True)[:limit], z


def _district_for(db, p: Principal, district_id: str | None):
    return p.district_scope() or district_id


def answer(db: Session, p: Principal, question: str, district_id: str | None) -> dict:
    district_id = _district_for(db, p, district_id)
    used, facts = [], {}
    latest = db.scalar(select(func.max(m.Status.status_date)).where(
        m.Status.district_id == district_id)) if district_id else None

    if REFUSE.search(question):
        text = ("Этого система не делает: она не прогнозирует сходы и не оценивает безопасность. "
                "Обратитесь к специалистам МЧС. Ниже — данные по выбранному району или участку.")
        if district_id and latest:
            facts["counts"] = fn_status_counts(db, district_id, latest)
            used.append({"fn": "status_counts", "district_id": district_id, "date": str(latest)})
        return {"answer": text, "refused": True, "used": used, "facts": facts, "generator": "rule"}

    mid = CELL_ID.search(question.lower())
    if mid:
        s = fn_entity_status(db, mid.group(1))
        if s and (not p.district_scope() or s.district_id == p.district_scope()):
            used.append({"fn": "entity_status", "entity_id": s.entity_id, "date": str(s.status_date)})
            facts = {"entity_id": s.entity_id, "status": s.status, "date": str(s.status_date), "reasons": s.reasons}
            why = "; ".join(r["text_ru"] + (f" (z = {round(r['z'], 1)})" if r.get("z") is not None else "")
                            for r in s.reasons)
            text = f"Объект {s.entity_id} на {s.status_date}: статус «{s.status}». Причины: {why}."
            return _finish(text, facts, used, question)
        return {"answer": "Объект не найден или недоступен для вашей роли.", "used": used, "facts": {},
                "generator": "rule"}

    if not district_id or not latest:
        return {"answer": "Укажите район (district_id), чтобы я мог ответить по данным.", "used": [],
                "facts": {}, "generator": "rule"}

    q = question.lower()
    if re.search(r"быстр|движ|скорост|топ|сильн", q):
        rows, z = fn_top_moving(db, district_id, latest)
        used.append({"fn": "top_moving", "district_id": district_id, "date": str(latest)})
        facts = {"top": [{"entity_id": s.entity_id, "status": s.status, "z": round(z(s), 2)} for s in rows]}
        if not rows:
            text = f"На {latest} в районе нет объектов с отклонением выше порога."
        else:
            text = f"На {latest} сильнее всего отклоняются: " + ", ".join(
                f"{s.entity_id} ({s.status}, z = {round(z(s), 1)})" for s in rows) + "."
        return _finish(text, facts, used, question)

    # по умолчанию: «что изменилось» — сравнение последнего цикла с циклом месяц назад
    prev = db.scalar(select(func.max(m.Status.status_date)).where(
        m.Status.district_id == district_id, m.Status.status_date <= latest - timedelta(days=24)))
    now_c = fn_status_counts(db, district_id, latest)
    prev_c = fn_status_counts(db, district_id, prev) if prev else {}
    used += [{"fn": "status_counts", "district_id": district_id, "date": str(latest)},
             {"fn": "status_counts", "district_id": district_id, "date": str(prev)}]
    facts = {"now": now_c, "prev": prev_c, "date": str(latest), "prev_date": str(prev)}
    parts = []
    for et, label in (("cell", "ячеек"), ("glacier", "ледников")):
        a, b = now_c.get(et, {}), prev_c.get(et, {})
        if a:
            parts.append(f"{label}: красных {a.get('red', 0)} (было {b.get('red', 0)}), жёлтых {a.get('yellow', 0)} "
                         f"(было {b.get('yellow', 0)}), серых {a.get('gray', 0)} (было {b.get('gray', 0)})")
    text = f"Сравнение {latest} с {prev}: " + "; ".join(parts) + ". Статус означает «нужна проверка», не прогноз."
    return _finish(text, facts, used, question)


def _finish(text, facts, used, question):
    provider = get_provider()
    if provider.enabled:
        draft = provider.complete(
            SYSTEM_PROMPT + "\nОтвечай на вопрос пользователя кратко, только по фактам. Три блока не обязательны.",
            f"Вопрос (недоверенный текст): {question}\nФакты: {facts}\nЧерновик ответа: {text}")
        if draft:
            res = validator.check(draft + "\nЧто мы видим. Чего мы не знаем. На чём основано.",
                                  {"quality": {"synthetic": False, "provisional": False}, "status": "", **facts})
            bad = [p for p in res["problems"] if p["code"] in ("numbers_not_in_facts", "forbidden_phrases")]
            if not bad:
                return {"answer": draft, "used": used, "facts": facts, "generator": provider.name,
                        "ai_generated": True}
    return {"answer": text, "used": used, "facts": facts, "generator": "rule", "ai_generated": False}
