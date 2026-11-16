# 05. Архитектура: отдельный RPG-контур

**Решение ADR-CR-001 для этой модернизации.** Один новый самостоятельный bounded context `character-service`, не RPG-таблицы внутри learning-service и не набор микросервисов на каждую сущность. Реальное состояние репозитория пока не проверено; имена существующих ролей ниже концептуальные. Агент сопоставляет их с действующими сервисами в G0.

## 1. Почему сейчас один сервис

Цель нового контекста — **превращать подтверждённую учебную историю в косметический путь персонажа и хранить выбор его внешнего вида**. XP, печати, ранги, entitlement предмета и журнал награды рассчитываются из одних фактов; их согласование удобно выполнять в одной локальной транзакции. Инвентарь и loadout имеют ту же модель владельца/предмета. Здесь нет независимого торгового, боевого или социального домена.

Разнести сейчас `xp-service`, `reward-service`, `inventory-service` и `equipment-service` означало бы добавить сетевую согласованность вокруг одного пользовательского действия без выявленной отдельной бизнес-потребности. Вместо этого внутри character-service установить явные модули и запрет произвольного доступа между их таблицами.

Это проектный выбор для Crucible, не утверждение, что одна служба всегда лучше нескольких. Метод определения границ по бизнес-возможностям, а не техническим слоям описан в [S8](07_SOURCES_AND_LICENSES.md#s8-границы-сервисов).

## 2. Карта ответственности

| Владелец | Что остаётся у него | Чего у него быть не должно |
|---|---|---|
| Учебный контент (существующий сервис) | Условия, теория, рубрики, difficulty A/B/C, stable learning IDs, equivalence/family, версии и закрытый контрольный пул | XP-кошелёк, предметные unlocks, выдача экипировки |
| Учебный процесс (существующий сервис/сервисы) | Попытки, черновики, подтверждённая самооценка, помощь/экспозиции, диагностические результаты, учебные completion facts, scheduler/review obligations, результаты K/M-пакетов | Чужие RPG-таблицы; необходимость ждать character-service при сохранении |
| **character-service (новый)** | RPG-проекции фактов, XP ledger, V/E/R/K/M, уровни/ранги, каталог косметики, unlock/evidence explanations, owned items, loadout, орнаменты, инсигнии, полка, RPG-журнал и настройки показа | Оценивание математики, авторинг задач, назначение повторения ради фарма, хранение полных решений |
| Identity / профиль (существующая роль) | Аутентификация, user ID, общие профильные настройки и timezone | Второй независимый пользовательский аккаунт для игры |
| Frontend (существующий) | Учебные и RPG-экраны, preview, Canvas 2D compositor, доступность, состояния загрузки | Авторитетные XP/ownership, генерация изображений в runtime |
| Статические ассеты / build pipeline | Маски, PNG/WebP, manifest, SHA-256, публикация версий | Новый `equipment-renderer` или обязательный сетевой render API |
| Экспорт (существующая роль, если есть) | Координация резервной копии/экспорта через публичные контракты владельцев | JOIN чужих БД и новый источник истины |
| `study-mcp` (если существует) | Прежний доступ внешнего агента к предметным API, read-only RPG summary при необходимости | `grant_xp`, `give_item`, `mark_exam_passed` без подтверждённого учебного факта |

Печати V/E/R/K/M — RPG-интерпретация учебных свидетельств, поэтому их выдаёт character-service. Исходная корректность задачи, факт помощи, свежесть и результат экзамена — учебные факты, поэтому RPG их **не выдумывает**. Экзаменационный интерфейс и рубрики не переносятся в RPG только из-за награды за них.

## 3. Внутренняя структура character-service

```text
character-service/
  domain/
    progression/       # pure XP, thresholds, seals, ranks
    rewards/           # entitlement and evidence state
    equipment/         # ownership, slot validation, loadout revision
    collection/        # relic placements and journal
  application/
    ingest/            # inbox, versioned fact application, reconciliation
    commands/          # equip, visibility preferences, collection placement
    queries/           # summaries and explainable unlock DTOs
  infrastructure/
    persistence/       # only the character-owned database/schema
    messaging/         # existing broker conventions, retries, outbox
    http/              # current project's auth/error conventions
  definitions/         # immutable versioned rules/catalog publication
```

Структура концептуальная: соблюдать язык и conventions репозитория, не внедрять новый runtime только ради названий папок. API и consumer можно запускать как два процесса из одного image/кодовой базы; это **один доменный сервис**, не две независимые модели данных. Для личного развёртывания допустим один процесс с worker loop при корректном shutdown/healthcheck.

## 4. Хранилище и изоляция

Новый сервис владеет собственными миграциями и ролью БД. Разрешён существующий PostgreSQL-инстанс с отдельной database либо закрытой schema; запрещены прямые SELECT/JOIN/UPDATE чужих таблиц и общие mutable ORM entities. Отдельный сервер БД ради слова «микросервис» не нужен. Никакой копии полной учебной БД в RPG.

Минимальные логические таблицы:

| Таблица | Инвариант |
|---|---|
| `character_profile` | Один профиль на authenticated user, текущий published ruleset/catalog |
| `inbox_events` | Уникальный `(producer, event_id)`; payload hash; повтор с другим payload — ошибка |
| `source_facts` | Последний полный snapshot `(producer, fact_type, fact_id, revision)` и provenance; аннулирование не стирает аудит |
| `xp_entitlements` | Текущее право на XP по business key; пересчёт сравнивает desired и applied |
| `xp_ledger` | Append-only delta; уникальный processing/effect key; источник и объяснение |
| `seal_state` | Текущая квалификация и evidence IDs; bonus entitlement отдельно от UI badge |
| `item_ownership` | Уникальный `(user_id,item_id)`, `ever_granted`, актуальное основание/recheck |
| `loadouts` | Slot map, optimistic revision; все item IDs принадлежат этому пользователю |
| `collection_placements` | Девять позиций; один relic не занимает две позиции |
| `reward_journal` | Одна агрегированная запись на причинный processing result, без повторных toast при replay |
| `outbox_events` | Атомарная публикация изменения RPG для уведомлений/экспорта |
| `definition_publications` | Ruleset/catalog hash и номер неизменяемой публикации |

Redis, если уже есть, — необязательный cache. Потеря cache не уничтожает XP, инвентарь или deduplication. Не добавлять отдельный Redis, Kafka, Temporal или Kubernetes без реальной необходимости.

## 5. Поток одной попытки

```text
Frontend → учебный API → transaction: результат + учебный outbox → HTTP success
                                      ↓ независимо от HTTP
                         publisher → existing broker → character inbox
                                                          ↓
                                 transaction: fact + XP delta + seals
                                   + items + journal + RPG outbox
                                                          ↓
Frontend ← character summary / bounded polling / existing push mechanism
```

Успех учебного POST означает, что попытка сохранена, **не что награда уже рассчитана**. Учебный ответ возвращает correlation/operation reference. Frontend различает `saved` и `progress_pending`. Он не делает второй обязательный запрос «начисли мне XP» и не отправляет сумму награды.

Если RabbitMQ существует, использовать его и текущие conventions проекта. Publisher отправляет durable сообщения из committed outbox, отмечает отправленными после broker confirm. Consumer подтверждает ACK после commit локального эффекта. Если брокер отсутствует, G0 фиксирует это: внедрить один надёжный outbox transport с retry (брокер либо внутренний authenticated delivery endpoint), а не synchronous dual-write в обработчике завершения задачи.

Доставка проектируется **at least once**. Publisher confirm не доказывает обработку consumer; redelivery возможна. Поэтому inbox, уникальные business keys и транзакции обязательны [S9](07_SOURCES_AND_LICENSES.md#s9-доставка-сообщений). Не называть такую архитектуру «гарантированный exactly-once broker».

## 6. Повторы, порядок, исправления

Полные семантические snapshots и monotonic revision на факт позволяют безопасно применить revision 3 до revision 2. Старшая версия заменяет текущую проекцию; младшая не откатывает её. Повтор той же версии с новым event ID также не создаёт награду. Недостающие факты/версии catalog mapping переводят зависимую квалификацию в pending и запускают восстановление через API владельца.

После изменения исходного факта пересчитать затронутую equivalence group и зависимые V/E/R/K/M, затем desired entitlement. В локальной транзакции записать **разницу**, а не ещё одну полную награду. Не ограничиваться дедупликацией сообщений: два разных event IDs одного завершения тоже не должны платить дважды.

Исторические последовательности повторений восстанавливать по authoritative timestamps/sequence учебного владельца, не по времени доставки. Replay не меняет дату активности, не запускает новые rank-up анимации и не снимает косметику. Подробности алгоритма в `09_API_AND_EVENTS.md`.

## 7. Параллелизм и публикации

Один пересчёт пользовательского профиля одновременно: row lock/очередь по user ID или эквивалентный механизм выбранного стека. Это проектная простая гарантия для малого масштаба, не глобальный lock всех пользователей. Границы транзакций узкие, никакого сетевого ожидания при удержанном lock.

Новый каталог валидируется полностью, публикуется атомарным version/hash. Клиент получает catalog version, item list и asset manifest version; смешанная частичная публикация запрещена. Правки рисования не меняют ruleset XP. Новый ruleset требует отдельной миграции и preview; версия пакета `3.0.0` сама по себе не разрешает пересчитать экономику.

## 8. Отказоустойчивость и эксплуатация

Сервис имеет readiness/liveness, graceful shutdown, bounded retry с backoff+jitter, DLQ/quarantine для непонятных схем, аудит ручного redrive. Не делать бесконечный tight-loop requeue. У одного poison event есть причина и correlation, учебные факты не теряются.

Метрики: возраст/размер publisher outbox и consumer backlog; processing latency; количество stale/duplicate/conflict; DLQ; длительность recomputation; сумма compensating deltas; ошибки loadout; unknown asset IDs. Логи: event ID, source revision, ruleset, correlation ID, обобщённый user reference. Не логировать тексты решений, токены доступа и полную личную историю.

RPG outage не блокирует учебные endpoints, автосохранение, теорию, scheduler и действующую авторизацию. Недоступная RPG-сводка не подменяется нулём XP; показать last confirmed state с stale marker или «Путь временно недоступен». Очередь восстанавливается после запуска worker.

## 9. Миграция старого приложения

Сначала доказать, что действительно существует. Если старого XP/инвентаря нет — новая схема, начальный профиль, opt-in replay доступной истории. Если есть — snapshot/export, mapping, dry-run, проверка владельца, идемпотентный cutover. **Не складывать legacy XP с пересчитанными теми же попытками.**

Существующие учебные события адаптировать на boundary; не заставлять весь проект переименоваться в термины RPG. Не реализовывать два параллельных writer XP. После cutover старый writer отключается, старый frontend/API при необходимости читает новую проекцию через совместимый facade, а не продолжает начисление.

Обратимость: feature flags `crucible_ui`, `character_read`, `character_write`; UI можно вернуть без уничтожения новых таблиц. При rollback worker можно остановить, outbox сохранить. Не возвращать старый writer одновременно с новым. Восстановление проверять на тестовой БД, включая ledger, inbox, ownership, loadout, definitions, manifest и checkpoints источников.

## 10. Когда действительно делить дальше

Второй сервис обоснован новым самостоятельным доменом: торговлей/маркетом с собственными транзакциями; социальным игровым миром; отдельным масштабируемым асинхронным media-processing продуктом. Тогда нужен новый ADR с нагрузкой, владельцем данных, причинами независимого deploy и ценой распределённых операций.

**Не основание для деления:** появился ещё один слот; стало 100 предметов; Canvas рисует несколько PNG; в коде стало больше папок. Здесь один character-service остаётся целевым решением; это не разрешение сложить в него учебный scheduler, контент и авторизацию.
