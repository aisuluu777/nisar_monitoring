"""Таблицы базы (раздел 5 ТЗ). Ячейки и ледники — два типа объектов наблюдения
(entity_type = "cell" | "glacier"); их ряды, нормы и статусы лежат в общих таблицах."""
from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class District(Base):
    __tablename__ = "districts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    name_ru: Mapped[str] = mapped_column(String(80))
    oblast: Mapped[str] = mapped_column(String(80), index=True)
    area_km2: Mapped[float] = mapped_column(Float)
    boundary_source: Mapped[str] = mapped_column(String(200))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True))


class Cell(Base):
    __tablename__ = "cells"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)  # <district>-<row>-<col>
    district_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    row: Mapped[int] = mapped_column(Integer)
    col: Mapped[int] = mapped_column(Integer)
    size_km: Mapped[float] = mapped_column(Float)
    inside_frac: Mapped[float] = mapped_column(Float)  # доля ячейки внутри района
    attrs: Mapped[dict] = mapped_column(JSON, default=dict)  # уклон, покрытие, село (когда появятся)
    geom = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=True))


class Glacier(Base):
    __tablename__ = "glaciers"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    district_id: Mapped[str] = mapped_column(ForeignKey("districts.id"), index=True)
    catalog: Mapped[str] = mapped_column(String(40))        # GLIMS | RGI7 | synthetic
    catalog_id: Mapped[str] = mapped_column(String(60))
    name: Mapped[str | None] = mapped_column(String(120))
    area_km2: Mapped[float] = mapped_column(Float)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    attrs: Mapped[dict] = mapped_column(JSON, default=dict)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True))


class Product(Base):
    """Паспорт исходного продукта: откуда взялось каждое число."""
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(300), unique=True)
    source: Mapped[str] = mapped_column(String(60), index=True)    # NISAR_GUNW | NASA_POWER | ITS_LIVE | SYNTHETIC ...
    family: Mapped[str] = mapped_column(String(60))                # ряды сравниваются только внутри семейства
    name: Mapped[str] = mapped_column(String(300))
    version: Mapped[str] = mapped_column(String(60))
    maturity: Mapped[str] = mapped_column(String(30))              # BETA | PROVISIONAL | VALIDATED | SYNTHETIC
    acq_start: Mapped[date | None] = mapped_column(Date)
    acq_end: Mapped[date | None] = mapped_column(Date)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    pipeline_version: Mapped[str] = mapped_column(String(40))
    license: Mapped[str] = mapped_column(String(120))
    url: Mapped[str | None] = mapped_column(String(500))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "signal", "obs_date", "family",
                                       name="uq_observation"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(10))
    entity_id: Mapped[str] = mapped_column(String(60), index=True)
    signal: Mapped[str] = mapped_column(String(40))
    obs_date: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    reliable_frac: Mapped[float | None] = mapped_column(Float)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    family: Mapped[str] = mapped_column(String(60))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))


class Baseline(Base):
    __tablename__ = "baselines"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "signal", "month", "version",
                                       name="uq_baseline"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(10))
    entity_id: Mapped[str] = mapped_column(String(60), index=True)
    signal: Mapped[str] = mapped_column(String(40))
    month: Mapped[int] = mapped_column(Integer)   # сезонная норма: окно ±1 месяц вокруг month
    median: Mapped[float] = mapped_column(Float)
    mad: Mapped[float] = mapped_column(Float)
    n: Mapped[int] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(String(40))


class Status(Base):
    __tablename__ = "statuses"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "status_date", name="uq_status"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(10))
    entity_id: Mapped[str] = mapped_column(String(60), index=True)
    district_id: Mapped[str] = mapped_column(String(40), index=True)
    status_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(10))  # green | yellow | red | gray
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    analytics_version: Mapped[str] = mapped_column(String(40))
    thresholds_version: Mapped[str] = mapped_column(String(40))


class Decision(Base):
    """Журнал решений специалистов. Правка и удаление запрещены триггером (см. app/init_db.py)."""
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(10))
    entity_id: Mapped[str] = mapped_column(String(60), index=True)
    status_date: Mapped[date | None] = mapped_column(Date)
    verdict: Mapped[str] = mapped_column(String(20))  # confirmed | false_alarm
    comment: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Bulletin(Base):
    __tablename__ = "bulletins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(10))   # cell | glacier | district
    entity_id: Mapped[str] = mapped_column(String(60), index=True)
    district_id: Mapped[str] = mapped_column(String(40), index=True)
    status_date: Mapped[date] = mapped_column(Date)
    mode: Mapped[str] = mapped_column(String(20))   # plain | expert
    lang: Mapped[str] = mapped_column(String(5))
    facts: Mapped[dict] = mapped_column(JSON)
    text: Mapped[str] = mapped_column(Text)
    generator: Mapped[str] = mapped_column(String(60))   # template | llm:<model>
    check: Mapped[dict] = mapped_column(JSON, default=dict)
    approval: Mapped[str] = mapped_column(String(20), default="draft")  # draft | approved
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "status_date", "mode", "lang",
                                       name="uq_bulletin"),)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))   # admin_district | emercom | sysadmin
    district_id: Mapped[str | None] = mapped_column(ForeignKey("districts.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default="researcher")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")
    districts: Mapped[list] = mapped_column(JSON, default=list)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    log: Mapped[str] = mapped_column(Text, default="")
