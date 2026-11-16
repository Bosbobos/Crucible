# Данные

SQL создания находится в `migrations/{content,practice,learning,reports,character}/001_initial.sql`. Миграции применяются с checksums и собственными migration credentials; редактирование уже применённой миграции отвергается.

Попытка имеет UUID, профиль, редакцию и состояние running/paused/completed/abandoned. Разрешённый immutable снимок задачи и пользовательские факты находятся в JSONB; каждая редакция сохраняется отдельно. Частичный уникальный индекс допускает только одну незавершённую попытку профиля. Запись с неверной ожидаемой редакцией возвращает 409.

Таймер накапливает неперекрывающиеся интервалы решения, теории и помощи. Один heartbeat подтверждает максимум 45 секунд; остальное отмечается неподтверждённым. Клиент не отправляет heartbeat в скрытой/неактивной вкладке. Исторические legacy timestamps без часового пояса не реконструируются.

Квитанция идентифицируется actor и command_id, содержит hash операции/ресурса/payload и устойчивый ответ. Изменение payload с прежним ID вызывает 409. Повтор той же команды возвращает прежний ответ до повторной проверки текущей редакции.

У practice есть транзакционно блокируемый source_stream профиля. Значимые изменения увеличивают seq вместе с попыткой и outbox. Learning хранит inbox_receipts с уникальными event_id и source+seq, последнюю редакцию фактов и непрерывные source_cursors. Планы сохраняют дату, IANA timezone, seed, версию политики, настройки и входные курсоры.

Сами learning_db и reports_db не являются одноразовыми кэшами: планы, настройки, задания и manifests входят в backup. В текущем срезе переносимый артефакт хранится в reports_db и скачивается авторизованным API, а не из открытой папки.

## Косметический контур v3

Character хранит immutable definitions/campaign publications, inbox, полные source snapshots и их историю, desired XP entitlements и append-only ledger deltas, current/ever_granted seals, ownership с evidence_recheck, optimistic loadouts, девять collection positions, preferences, journal, operations, source checkpoints и outbox. Изменять ledger/историю/publications через UPDATE/DELETE запрещают триггеры.

Source stream разделяет main, character-evidence, character-campaign, character-profile и review-obligations. Revision факта не равна порядковому номеру сообщения или версии ruleset. Practice хранит учебные ответы; RPG получает только числовые оценки и flags. Кривые 60 уровней и 59 предметов зафиксированы публикацией crucible-v1 / catalog 3.0.0 с hash.
