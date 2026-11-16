# Аудит модернизации Crucible v3

Дата: 16 ноября 2026. Ветка: `codex/crucible-v3`.

Фактически существуют FastAPI/Python 3.11, React 19/TypeScript/Vite, CodeMirror,
KaTeX, nginx, PostgreSQL 17, RabbitMQ и Redis. Учебные владельцы уже разделены:
content публикует неизменяемые материалы, practice хранит попытки/помощь/оценки,
learning рассчитывает план и интервалы, reports формирует экспорт. JWT EdDSA,
cookie-сессия, Origin/CSRF и транзакционные command receipts уже реализованы.
У каждого владельца отдельные PostgreSQL, runtime/migration роли и storage-сеть.

Practice записывает факт и outbox вместе; общий dispatcher использует publisher
confirms, consumer ACK после commit. Для RPG выбран тот же RabbitMQ transport,
отдельная очередь и отдельная БД character. Синхронного вызова RPG из save нет.
Существующие PracticeFact не содержат весов, quality, freshness и reward mapping;
нужен отдельный полный snapshot, а не расширение смысла старого learning event.

XP, inventory, loadout и старого RPG writer в приложении не обнаружено. Автоматического
пересчёта прежней истории не будет. MCP остаётся внешним учебным адаптером.

Рабочее дерево до начала содержало изменения compose и shell wrappers,
неотслеживаемые `Assets/`, пакет v3 и `Task/Paladin_legacy/`. Они сохранены.
Закрытая точка возврата: `.private/backups/crucible-v3-g0/working-tree.tar.gz`,
patch, HEAD, status и manifest с SHA-256. Секреты и исходный vault не публикуются.
На машине работают два проекта: `paladin` (127.0.0.1:28080) и `crucible` (:18080).
Цель текущего checkout — `paladin`; второй стенд не модернизируется.

Baseline: `scripts/test unit` — passed (29 passed, 8 skipped);
`CRUCIBLE_LOCAL_PYTHON=1 scripts/python -m pytest -q -p no:cacheprovider` — тот же результат;
`npm --prefix apps/web run build` — passed. Первые локальные запуски выявили
отсутствующие зависимости; они установлены в `.deps/` и `apps/web/node_modules/`.
Предупреждение Vite о JS bundle >500 KB существовало до модернизации.

Готовность P/D не проверена этим аудитом: firewall/failover/restore/MCP-host
требуют отдельных фактических сценариев. Контрольные условия/holdout не открывались.
