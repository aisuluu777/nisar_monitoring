"""Генерация бюллетеня: LLM (если подключён) → проверка → одна перегенерация → шаблон."""
from ai import templates, validator
from ai.provider import SYSTEM_PROMPT, LLMProvider, bulletin_prompt


def generate(facts: dict, mode: str, provider: LLMProvider) -> dict:
    attempts = []
    if provider.enabled:
        for _ in range(2):
            text = provider.complete(SYSTEM_PROMPT, bulletin_prompt(facts, mode))
            if text is None:
                attempts.append({"error": "provider_unavailable"})
                break
            res = validator.check(text, facts)
            attempts.append(res)
            if res["ok"]:
                return {"text": text, "generator": provider.name, "check": {"ok": True, "attempts": attempts}}
    text = templates.render(facts, mode)
    res = validator.check(text, facts)
    return {"text": text, "generator": "template",
            "check": {**res, "llm_attempts": attempts, "fallback": provider.enabled}}
