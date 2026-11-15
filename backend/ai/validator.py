"""Проверка текстов (раздел 7, «Защита от ошибок»): числа только из пакета фактов,
запретные утверждения, обязательные блоки и оговорки о качестве данных."""
import re
from datetime import date

from ai.templates import BLOCK_BASIS, BLOCK_SEEN, BLOCK_UNKNOWN

# Дополняется вместе с МЧС.
FORBIDDEN = [
    r"оползень\s+(будет|произойд|случится|сойд)", r"безопас(н|ен)", r"эвакуац", r"\bопасн[оаы]\b",
    r"гарантир", r"(?<!не )\bпрогноз(?!ом не)", r"вероятность\s+схода",
]
NUM = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?")


def _collect(obj, out: set[float]):
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        try:
            d = date.fromisoformat(obj[:10])
            out.update({d.year, d.month, d.day})
        except ValueError:
            pass
        for m in NUM.findall(obj):
            out.add(float(m.replace(",", ".")))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect(v, out)


def allowed_numbers(facts: dict) -> set[float]:
    nums: set[float] = set()
    _collect(facts, nums)
    return nums | {abs(x) for x in nums}


def _matches(x: float, allowed: set[float]) -> bool:
    for a in allowed:
        tol = max(0.051, abs(a) * 0.01)
        if abs(x - a) <= tol or abs(abs(x) - abs(a)) <= tol or round(a) == x:
            return True
    return False


def check(text: str, facts: dict) -> dict:
    problems = []
    allowed = allowed_numbers(facts)
    bad_numbers = [m for m in NUM.findall(text)
                   if not _matches(float(m.replace(",", ".")), allowed)]
    if bad_numbers:
        problems.append({"code": "numbers_not_in_facts", "values": bad_numbers})
    low = text.lower()
    hits = [p for p in FORBIDDEN if re.search(p, low)]
    if hits:
        problems.append({"code": "forbidden_phrases", "patterns": hits})
    missing = [b for b in (BLOCK_SEEN, BLOCK_UNKNOWN, BLOCK_BASIS) if b.lower() not in low]
    if missing:
        problems.append({"code": "missing_blocks", "blocks": missing})
    q = facts["quality"]
    if q["synthetic"] and "синтетич" not in low:
        problems.append({"code": "missing_synthetic_note"})
    if q["provisional"] and "предварительн" not in low and "provisional" not in low:
        problems.append({"code": "missing_provisional_note"})
    if facts["status"] == "gray" and "недостаточно" not in low:
        problems.append({"code": "gray_without_insufficient_note"})
    return {"ok": not problems, "problems": problems}
