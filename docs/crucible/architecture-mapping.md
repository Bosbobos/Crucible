# Карта владельцев и изменений

| Требование | Реальный owner / файл / API | Изменение | Риск и проверка |
|---|---|---|---|
| Результат и помощь | practice, `apps/practice_service/main.py` | Полный RPG snapshot в собственном outbox | Save при RPG outage, correction |
| Версия и metadata | content, `packages/contracts/content.py` | Явные веса/эквивалентность; unknown campaign mapping | Не выводить family из названия; не раскрывать holdout |
| Scheduler | learning, `apps/learning_service/policy.py` | Сохраняет прежнее владение | Учебный regression |
| RPG | новый `apps/character_service/` | Definitions, inbox, ledger, ownership, loadout, collection | Duplicate/stale/conflict и atomic commit |
| Авторизация | practice auth check + nginx | Audience/scopes character, прежние CSRF/Origin | Unauthorized, wrong scope, object access |
| Доставка | `platformkit.runtime.broker_loop` | Отдельная character.in / DLQ | Отказ, backlog, ACK после commit |
| Хранение | compose + `migrations/character/` | Отдельный PostgreSQL/role/network | Migration/rollback, isolation |
| UI/математика | `apps/web/src/` | Токены Белого Атласа и RPG экраны | Draft, KaTeX, viewport, keyboard |
| Арт | references → offline pipeline → manifest | Alpha, paint/hide-base и QA отдельных частей | Не применять маску без загруженного paint |
| Экспорт | reports API | Snapshot character через API владельца | Нет чужого SQL |
| Внешний агент | `apps/study_mcp/` | Не получает grant/equip полномочий | Прежний review workflow |

Public RPG prefix: `/api/character/v1`; transport envelope сохраняет conventions
существующего Event (profile_id/source_seq/aggregate_id/aggregate_revision).
В payload — versioned semantic fact_type/status/snapshot. Это явный boundary
adapter целевого envelope из пакета; доменная семантика revisions не меняется.
