"""Шаблонные тексты — резерв без ИИ (раздел 7, «Защита от ошибок», п. 4).
Все числа подставляются из пакета фактов. Три обязательных блока в каждом тексте."""

BLOCK_SEEN, BLOCK_UNKNOWN, BLOCK_BASIS = "Что мы видим", "Чего мы не знаем", "На чём основано"


def _n(x, nd=1):
    if x is None:
        return "—"
    return f"{abs(x):.{nd}f}".rstrip("0").rstrip(".") if nd else f"{abs(x):.0f}"


def _subject(f):
    if f["entity_type"] == "glacier":
        name = f.get("entity_name")
        return f"ледник «{name}»" if name else "этот ледник"
    return "эта ячейка"


def _sources(f):
    parts = []
    for s in f["sources"]:
        tag = " — СИНТЕТИЧЕСКИЕ данные-заглушка" if s["synthetic"] else f", статус продукта {s['maturity']}"
        parts.append(f"{s['name']} (версия {s['version']}, данные до {s['acq_end']}{tag})")
    return "; ".join(parts) if parts else "—"


def _limits(f):
    out = []
    if f["quality"]["synthetic"]:
        out.append("Часть рядов синтетическая (заглушка до подключения данных NASA), выводы по ним делать нельзя.")
    if f["quality"]["provisional"]:
        out.append("Часть данных имеет предварительный статус (Provisional) и может быть пересчитана.")
    if f["entity_type"] == "cell":
        out.append("Спутник измеряет смещение только вдоль своего луча, а не полное движение склона.")
    else:
        out.append("Скорость ледника измеряется только по парам снимков без облаков.")
    out.append("Система не знает, произойдёт ли сход, и не оценивает опасность — это решает специалист.")
    return " ".join(out)


def _seen_plain(f):
    st, sig = f["status"], f["signals"]
    if st == "gray":
        why = next((r["text_ru"] for r in f["reasons"]), "")
        return f"Данных недостаточно, чтобы сравнить {_subject(f)} с нормой: {why}. Это не значит, что всё в порядке."
    lines = []
    if f["entity_type"] == "cell" and "displacement_mm" in sig:
        d = sig["displacement_mm"]
        lines.append(f"За последний цикл ({f['cycle_days']} дней, до {f['status_date']}) поверхность "
                     f"сместилась на {_n(d['value'])} мм вдоль луча спутника. "
                     f"Обычно в это время года бывает около {_n(d['norm_median'])} мм.")
    if f["entity_type"] == "glacier" and "glacier_velocity" in sig:
        v = sig["glacier_velocity"]
        lines.append(f"Ледник движется со скоростью около {_n(v['value'], 0)} м/год; "
                     f"обычно в это время года около {_n(v['norm_median'], 0)} м/год.")
    codes = {r["code"] for r in f["reasons"]}
    if "persistent" in codes:
        lines.append("Отклонение держится второй цикл подряд.")
    if "cluster" in codes:
        lines.append("Соседние участки отклоняются вместе.")
    if "isolated" in codes:
        lines.append("Отклонение одиночное, соседи в норме — сигнал слабый.")
    if "precip_30d" in sig and any(r.get("signal") == "precip_30d" and r["code"] != "within_norm"
                                    for r in f["reasons"]):
        lines.append("Дождей было больше обычного.")
    if "soil_moisture" in sig and any(r.get("signal") == "soil_moisture" for r in f["reasons"]):
        lines.append("Почва влажнее обычного.")
    if st == "green":
        lines.append("Все сигналы в пределах нормы для этого сезона.")
    else:
        lines.append("Это не прогноз — участок стоит передать специалисту для проверки.")
    return " ".join(lines)


def _seen_expert(f):
    if f["status"] == "gray":
        r = f["reasons"][0]
        extra = ", ".join(f"{k}={v}" for k, v in r.items() if k not in ("code", "text_ru"))
        return f"Статус: {f['status_ru']}. Правило: {r['code']} ({r['text_ru']}; {extra})."
    rows = []
    for r in f["reasons"]:
        if "z" in r and r.get("z") is not None:
            unit = f["signals"].get(r["signal"], {}).get("unit", "")
            rows.append(f"{r['code']}: {r['signal']} = {r['value']} {unit}, норма {r['median']}, "
                        f"MAD {r.get('mad')}, z = {round(r['z'], 2)}"
                        + (f", порог {r['threshold']}" if "threshold" in r else ""))
        else:
            extra = ", ".join(f"{k}={v}" for k, v in r.items() if k not in ("code", "text_ru"))
            rows.append(f"{r['code']}: {r['text_ru']}" + (f" ({extra})" if extra else ""))
    return f"Статус: {f['status_ru']} на {f['status_date']}. Сработавшие правила: " + "; ".join(rows) + "."


def render(f: dict, mode: str = "plain") -> str:
    seen = _seen_expert(f) if mode == "expert" else _seen_plain(f)
    return (f"{BLOCK_SEEN}. {seen}\n\n"
            f"{BLOCK_UNKNOWN}. {_limits(f)}\n\n"
            f"{BLOCK_BASIS}. {_sources(f)}.")


def render_district(f: dict) -> str:
    """Сводка по району на цикл (раздел 7, задача 2)."""
    parts = []
    for key, label in (("cell", "участков"), ("glacier", "ледников")):
        c, p = f["counts"].get(key), f["prev_counts"].get(key, {})
        if not c:
            continue
        parts.append(f"Из {sum(c.values())} {label}: красных {c.get('red', 0)} (в прошлом цикле {p.get('red', 0)}), "
                     f"жёлтых {c.get('yellow', 0)} (было {p.get('yellow', 0)}), "
                     f"серых — данных недостаточно — {c.get('gray', 0)}.")
    if f["top"]:
        parts.append("В первую очередь стоит передать специалисту: " +
                     ", ".join(f"{t['entity_id']} ({t['status']})" for t in f["top"]) + ".")
    else:
        parts.append("Участков с устойчивым отклонением нет.")
    limits = ("Часть рядов синтетическая (заглушка до подключения данных NASA), выводы по ним делать нельзя. "
              if f["quality"]["synthetic"] else "")
    limits += "Статусы показывают отклонение от нормы, а не оценку опасности; система не знает, произойдёт ли сход."
    src = "; ".join(f"{s['name']} (версия {s['version']}, данные до {s['acq_end']})" for s in f["sources"])
    return (f"{BLOCK_SEEN}. Район {f['district']['name_ru']}, цикл до {f['status_date']}. " + " ".join(parts) +
            f"\n\n{BLOCK_UNKNOWN}. {limits}\n\n{BLOCK_BASIS}. {src}.")
