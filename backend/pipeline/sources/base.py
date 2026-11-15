"""Общий интерфейс источника сигналов. Источник возвращает паспорт продукта и наблюдения;
конвейер сам пишет их в базу (идемпотентно, upsert по ключу наблюдения)."""
from dataclasses import dataclass, field
from datetime import date


@dataclass
class ProductPassport:
    external_id: str
    source: str
    family: str
    name: str
    version: str
    maturity: str
    license: str
    acq_start: date | None = None
    acq_end: date | None = None
    params: dict = field(default_factory=dict)
    url: str | None = None
    synthetic: bool = False


@dataclass
class Obs:
    entity_type: str
    entity_id: str
    signal: str
    obs_date: date
    value: float | None
    unit: str
    reliable_frac: float | None = None
    quality: dict = field(default_factory=dict)


@dataclass
class SourceResult:
    passport: ProductPassport
    observations: list[Obs]
    notes: list[str] = field(default_factory=list)


# Сигналы и их смысл; используются аналитикой, ИИ-текстами и /sources.
SIGNALS = {
    "displacement_mm": {"unit": "мм", "label_ru": "смещение вдоль луча спутника за цикл",
                        "role": "primary", "entity": "cell"},
    "soil_moisture": {"unit": "м³/м³", "label_ru": "влажность почвы", "role": "context", "entity": "cell"},
    "precip_7d": {"unit": "мм", "label_ru": "осадки за 7 дней", "role": "context", "entity": "any"},
    "precip_30d": {"unit": "мм", "label_ru": "осадки за 30 дней", "role": "context", "entity": "any"},
    "glacier_velocity": {"unit": "м/год", "label_ru": "скорость движения ледника",
                         "role": "primary", "entity": "glacier"},
    "snow_cover": {"unit": "доля", "label_ru": "доля снежного покрова", "role": "context",
                   "entity": "glacier"},
}
