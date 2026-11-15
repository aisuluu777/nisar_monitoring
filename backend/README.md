# NASA Space Monitor — бэкенд (прототип)

Мониторинг склонов и ледников Кыргызстана на открытых данных. Система показывает, где поведение участка
отличается от его собственной нормы, и **не прогнозирует** сходы. ТЗ — `../plan.md`, план — `../backend_plan.md`.

## Запуск

```bash
cp .env.example .env                 # секреты только здесь; .env в .gitignore
docker compose up -d db              # PostGIS на localhost:5433
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m pipeline run     # все 14 районов; один район: --district jeti-oguz
.venv/bin/uvicorn app.main:app --port 8010   # OpenAPI: http://localhost:8010/docs
.venv/bin/pytest                     # юнит-тесты + интеграционные (нужна БД с данными)
```

Полностью в Docker: `docker compose up -d --build` (API на :8010), затем
`docker compose exec api python -m pipeline run`.

Повторный запуск конвейера в тот же день не меняет базу (upsert по естественным ключам, детерминированные расчёты).
Ответы внешних API кэшируются в `data/cache/`.

## Демо-доступ (только прототип)

| Логин | Роль | Видит |
|---|---|---|
| `sysadmin` | администратор системы | всё + `/admin/*` |
| `emercom` | МЧС и государство | все районы, журнал решений, утверждение текстов |
| `admin_jeti_oguz`, `admin_at_bashy` | администрация района | только свой район (фильтр на сервере) |

Пароль — `DEMO_PASSWORD` из окружения (по умолчанию `demo12345`). Ключ исследователя печатается один раз при первом
`python -m app.init_db` / прогоне конвейера; передаётся заголовком `X-API-Key`. Без входа — публичный уровень
(только агрегаты).

## Что реально, а что заглушка

| Данные | Источник сейчас | Статус |
|---|---|---|
| Границы районов | geoBoundaries KGZ ADM2 (2010), CC BY-SA 3.0 | реальные, нужно заменить на официальные |
| Контуры ледников | OpenStreetMap `natural=glacier` (ODbL) | реальные, далее RGI 7 / GLIMS |
| Осадки 7 и 30 дней | NASA POWER (PRECTOTCORR) | реальные; при недоступности — синтетика с пометкой |
| Смещение, влажность почвы | синтетика (`SYNTHETIC_INSAR`) | заглушка до токена Earthdata (NISAR GUNW, HyP3, SME2) |
| Скорость ледников, снег | синтетика (`SYNTHETIC_GLACIER`) | заглушка до ITS_LIVE и MODIS/VIIRS |

Все синтетические продукты имеют `synthetic=true` и `maturity=SYNTHETIC` в паспортах (`/api/v1/sources`,
`/cells/{id}/products`), а тексты бюллетеней обязаны об этом сказать (проверяется кодом).
В синтетику вшиты проверочные аномалии (кластер ускоряющегося смещения, одиночный выброс, подвижка ледника),
список — в `params` паспорта.

## Аналитика (раздел 6 ТЗ)

Норма — медиана и MAD по окну ±1 месяц, только по данным **до** оцениваемых циклов. Отклонение — устойчивый z.
Общий для района сдвиг смещения вычитается (сравнение с соседями). Пороги — `config/thresholds.yaml`.

| Статус | Правило |
|---|---|
| серый | нет свежих данных > 36 дней, мало истории (< 6 точек) или мало надёжных пикселей (< 0.3) |
| жёлтый | первичный сигнал (смещение / скорость ледника) \|z\| ≥ 3 **или** влажность почвы / снег z ≥ 2.5 |
| красный | первичный сигнал ≥ 3, устойчиво 2 цикла **или** кластер ≥ 3 соседних ячеек, **и** подтверждение (влажность, осадки, снег z ≥ 1.5) |

Отклонение от ТЗ: осадки сами по себе жёлтый не дают — они одинаковы для всего района (узел POWER ~50 км)
и окрашивали бы весь район; они только подтверждают первичный сигнал. Требует согласования с МЧС.

## ИИ (раздел 7 ТЗ)

Сейчас работает шаблонный режим. Чтобы подключить LLM, в `.env`:
```
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://<провайдер>/v1
LLM_API_KEY=...
LLM_MODEL=...
```
Каждый текст проверяется: числа только из пакета фактов, запретные фразы, три блока, оговорки о синтетике,
Provisional и сером статусе. Не прошёл дважды — шаблон. Утвердить можно только текст, прошедший проверку.
Кыргызский язык пока не включён: тексты должен проверить носитель (ТЗ, раздел 7).

## API (кратко; полная схема — `/docs`)

| Путь | Доступ |
|---|---|
| `POST /api/v1/auth/login`, `GET /api/v1/auth/me` | все |
| `GET /api/v1/districts[?geometry=true]`, `/districts/oblasts/summary`, `/districts/{id}/summary` | публично (агрегаты) |
| `GET /api/v1/cells`, `/glaciers` (GeoJSON, `?district_id&oblast&status&on=YYYY-MM-DD`) | сотрудники |
| `GET /api/v1/{cells,glaciers}/ranking` | сотрудники |
| `GET /api/v1/{cells,glaciers}/{id}` — карточка | сотрудники |
| `GET /api/v1/{cells,glaciers}/{id}/series`, `/products` | сотрудники, исследователи |
| `POST /api/v1/{cells,glaciers}/{id}/decisions` | МЧС, администрация |
| `GET /api/v1/decisions` | сотрудники |
| `GET /api/v1/bulletins`, `POST /api/v1/bulletins/{id}/approve` | по ролям / МЧС, администрация |
| `POST /api/v1/assistant/ask` | сотрудники |
| `GET /api/v1/export?dataset=district_summary\|statuses\|observations&format=csv\|json` | публично только `district_summary` |
| `GET /api/v1/sources`, `/products/{id}`, `/health` | публично |
| `GET /api/v1/notifications`, `/admin/pipeline`, `/admin/thresholds` | сотрудники / sysadmin |

## Что дальше

1. Токен Earthdata → `AsfGunwSource` (NISAR GUNW) и HyP3 вместо синтетики смещения; SME2 для влажности.
2. ITS_LIVE и MODIS/VIIRS для ледников; RGI 7 вместо OSM.
3. Официальные границы районов, ретроспектива по COOLR и данным МЧС (этап 3), подбор порогов.
4. Доставка уведомлений (email / Telegram), выгрузки Parquet и GeoTIFF, PDF-отчёты.
