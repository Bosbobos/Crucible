# Миграция и возврат

1. Сохранить рабочее дерево и закрытый backup БД перед обновлением runtime.
2. Добавить character конфигурацию без замены прежних паролей/ключей; собственные
   миграции и атомарную неизменяемую публикацию definitions.
3. Подключить только новые полные practice snapshots через outbox/RabbitMQ.
   Старые outbox learning events не являются разрешением начислить RPG за историю.
4. Включить чтение/запись персонажа и новый UI независимо; при отказе остановить
   consumer и сохранить backlog, не удалять ledger/ownership/loadout.
5. Исторический импорт — сначала dry-run через owner snapshot+cursor, с перечнем
   недостающих metadata. Live cutover требует подтверждения владельца по G7.
   Legacy XP отсутствует; synthetic результаты не импортируются в личный профиль.
6. Down миграции выполняются только на disposable БД после export. Для рабочего
   rollback используются flags и остановка consumer; разрушение БД не требуется.

Feature flags: `VITE_CRUCIBLE_UI=0` (сборка без White Atlas CSS), `character_read`, `character_write`
(конфигурация character). Отключение RPG не отключает practice или scheduler.
Rollback старого UI не включает второй writer XP: его в baseline нет.

Фактически проверено: `scripts/check_character_rollback.py` на отдельном `crucible-character-test`; read/write возвращают 503, practice save 200, очередь догоняет canonical cursor после включения. Выключенный writer не подписывается на очередь и не переводит полезные факты в DLQ. `VITE_CRUCIBLE_UI=0 npm --prefix apps/web run build` проходит; снятие новой темы не удаляет функциональные экраны.

Dry-run основного профиля: 0 attempts, practice cursor 0, projected XP=confirmed XP=0, live replay отсутствует. Для непустой старой установки нужна отдельная подтверждённая процедура backfill: полный owner snapshot, фиксация checkpoint и replay сохранённого owner outbox с последующим live tail; автоматический импорт без подтверждения не реализован. Начальный checkpoint нельзя выбирать как максимальный увиденный event seq.
