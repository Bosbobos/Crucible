# 09. Контракты RPG-сервиса и учебной интеграции

**Целевые, ещё не существующие контракты.** Примеры в `contracts/` синтетические, не реальные пользовательские результаты. URL-префиксы и формат ошибок адаптировать к фактическому gateway один раз в G0. Предметная семантика, идемпотентность и ограничения не меняются.

## 1. Авторитетность и версии

Учебный владелец подтверждает результат/self-assessment, помощь, exposure до начала попытки и review obligation. Content-владелец задаёт difficulty, equivalence/family, mapping и rubric version. Character-service принимает только внутренние authenticated сообщения от разрешённого producer; browser event или текст агента не считаются доказательством.

Envelope (`contracts/event-envelope.schema.json`):

```json
{
  "schema_version": 1,
  "event_id": "a90d881c-764e-42b8-98d8-763bef9b49d0",
  "event_type": "learning.fact.upserted.v1",
  "producer": "learning-owner",
  "user_id": "synthetic-test-user",
  "fact_type": "attempt_result",
  "fact_id": "synthetic-attempt-B-001",
  "revision": 1,
  "occurred_at": "2026-11-16T09:00:00Z",
  "recorded_at": "2026-11-16T09:00:03Z",
  "correlation_id": "synthetic-op-001",
  "payload": {"status": "confirmed", "snapshot": {"fixture": "see complete example file"}}
}
```

Это иллюстрация envelope; полный валидируемый attempt snapshot в `contracts/attempt-result.example.json`. В production `snapshot` не может состоять из `fixture`.

`revision` монотонна у владельца конкретного факта. `occurred_at` — когда произошло учебное действие; новая correction имеет собственное recorded time, но original completion time хранится в snapshot. `source_sequence` служит дополнительным устойчивым tie-breaker. `schema_version` — версия формата, `revision` — версия факта, `ruleset` — версия начисления, `catalog_version` — версия предметов: это не одно поле.

`status=revoked` передаёт аннулирование с reason и source reference. Отсутствие нового сообщения не означает удаления. Unknown schema version не обрабатывается приблизительно.

## 2. Нормализованные факты

| `fact_type` | Обязательный смысл snapshot |
|---|---|
| `attempt_result` | Stable attempt/problem IDs; content/rubric version; difficulty; reward_equivalence_id; family_id; дисциплина/фиксированный reward mapping; пункты с весом, outcome, quality, note flag; источник оценки и подтверждение; began/completed times; exposure и помощь; review context |
| `learning_unit_completed` | Stable unit ID, вид section/core/lab/final_check, том, версия содержания, явное завершение, сохранённые ответы/прогноз/объяснение, критерии конечной проверки; provenance |
| `diagnostic_result` | Том, фиксированный check ID/version, score/total, подтверждение и время; не псевдоотметка «знал раньше» |
| `assessment_result` | Registered K/M variant ID и publication; четыре/шесть фиксированных заданий с весами и IDs попыток; баллы, самостоятельность, freshness at start, elapsed time, подтверждение |

`review_context` включает obligation ID, scheduled due time, владельца scheduler, дату предыдущего засчитанного учебного события и подтверждение того, что это не вручную созданный повтор ради награды. `unknown` — отдельное значение, не `true`.

Для свежести хранить `statement_seen_before_attempt`, `solution_seen_before_attempt`, `worked_example_seen_before_attempt` и их происхождение; открытие условия как часть **начала новой холодной попытки** не делает её несвежей. Помощь после завершения не ретроактивно превращает предшествующий независимый результат в assisted, если не исправлен сам записанный факт.

Внешнюю помощь, которую приложение не наблюдает, не обещать автоматически детектировать. Self-assessment явно помечен; владелец подтверждает существенные изменения. Полные заметки/решения RPG не нужны: достаточно flags, ссылок и verifiable provenance. Public DTO не раскрывает скрытые family labels/ответы до попытки.

## 3. Получение metadata без общей БД

Producer создаёт полный снимок факта со stable metadata из принятой версии контента либо character-service использует собственную read-only проекцию опубликованных metadata. Если metadata ещё не доставлены, сохранить факт в pending, запросить версию через API и повторить пересчёт. Запрещено брать difficulty из заголовка или семейство из regex по тексту задачи.

Private `campaign-bindings` остаются у content/assessment владельца. Character-service получает достаточные серверные ID/версии и evidence, но не ответы. Для frontend отдавать безопасные названия томов и агрегаты требований. Обычный поиск/MCP не должны раскрывать holdout.

## 4. Транзакционный обработчик

1. Проверить authentication, schema, producer/fact ownership, hashes и допустимые значения.
2. Открыть транзакцию, вставить inbox `(producer,event_id)`; при повторе сравнить hash. Different payload under same ID → quarantine, не молчаливый ignore.
3. Взять профильный lock. Если revision ниже текущей — отметить stale и завершить без изменения проекции. Если revision равна, но snapshot отличается — конфликт источника. Одинаковая revision/snapshot под новым event ID — семантический duplicate.
4. Записать актуальный snapshot либо tombstone. Собрать только нужные зависимости этого пользователя.
5. Пересчитать права XP и печати детерминированно по source facts. Рассчитать `delta = desired_entitlement − applied_entitlement`, записать ledger с уникальным effect key. Внутри одной ревизии нет нескольких выплат за один business key.
6. Пересчитать current qualifications и предметы. Новый owned item выдаётся один раз; не автопереодевать. Уже выданное право сохраняется с `evidence_recheck`, когда основание аннулировано.
7. Записать summary revision, объяснение/журнал и RPG outbox в той же транзакции. Commit. Только затем broker ACK.

При падении до commit redelivery повторяет всё безопасно. При падении после commit до ACK inbox делает повтор noop. Уникальные business keys защищают также от различающихся событий одного результата.

### Первичное освоение и correction

`primary:{user}:{reward_equivalence_id}:{ruleset}` хранит максимум candidate XP по **актуальным валидным** попыткам группы. Review note/quality тоже ревизуемы. Изменение максимума 80→56 даёт −24, не скрытое удаление записи. Если другая действительная попытка даёт 80, отрицательного delta нет.

### Повторения: не зависеть от порядка RabbitMQ

Для equivalence group проиграть действительные завершения по `completed_at`, затем authoritative `source_sequence`/stable attempt ID. Для каждого шага:

- Новое/улучшенное первичное освоение → только положительное увеличение primary maximum в этой попытке; repeat не присуждать одновременно.
- Без primary gain → repeat допустим лишь с действительным scheduler obligation, наступившим due, ≥168 часов с последнего **засчитанного** освоения/repeat, raw weighted rubric quality ≥80%, подтверждённым итогом independent/assisted и лимитом 3. У пропущенных/разобранных пунктов нет вклада в repeat; один полностью reviewed результат не подходит.
- Repeat XP = `floor(base × 0.30 × weighted contribution)`; assistance учитывается, reviewed не оплачивается как repeat. Оценка качества ≥80% и коэффициент помощи — разные проверки. При частичном решении качество для этого gate берётся по самостоятельно/с помощью выполненной работе, а не повышается чтением разбора; reviewed/skipped пункты дают 0 в числителе, но их веса остаются в знаменателе.
- Для точности использовать Decimal/rational, не `floor` от неточного binary floating-point результата на границе.

Пересчёт по corrected snapshots может изменить, какая конкретно попытка получила repeat. Старые entitlement deltas компенсируются, новый valid entitlement применяется; общий лимит остаётся 3. Primary summary равен финальному максимуму; replay временных приращений не добавляется к нему второй раз. Пауза проверяется по source time, а не arrival time. Математические правила из `03_PROGRESSION.md` остаются прежними.

### Печати, unlock и причинный порядок

V/E/R/K/M получают отдельные стабильные entitlement keys; их условия проверяют действительные evidence IDs. Seal XP вычисляется прежде зависимых только от уровня item unlocks. Ранги/предметы/инсигнии/орнаменты не дают нового XP, поэтому цепь не образует эмиссионного цикла.

`current_qualified`, `ever_granted`, `evidence_recheck`, `xp_entitlement` — разные поля. Сохраняется ранее полученная косметика, но UI не заявляет, что исправленная печать сейчас подтверждена. Повторное подтверждение восстановленного основания не дублирует historical item grant.

## 5. Публичный API character-service

Все `/me` endpoints определяют user ID из действующей authenticated session/JWT, не из произвольного тела запроса. Mutation endpoints требуют текущую авторизацию/CSRF-политику проекта.

| Метод | Путь | Смысл |
|---|---|---|
| GET | `/api/character/v1/me/summary` | XP, level, current rank, next reward, source freshness, summary revision |
| GET | `/api/character/v1/catalog` | Публичный опубликованный каталог и версии, без holdout |
| GET | `/api/character/v1/me/inventory` | Ownership + qualification + art status, фильтры и pagination |
| GET | `/api/character/v1/me/items/{id}` | Требования, разрешённые evidence ссылки, ownership |
| GET | `/api/character/v1/me/loadout` | Текущая slot map, rig/manifest versions и revision |
| PUT | `/api/character/v1/me/loadout` | Полная atomic slot map; `expected_revision`, `command_id` |
| GET | `/api/character/v1/me/path` | V/E/R/K/M, ранги, тома, blocked_content, safe evidence |
| GET | `/api/character/v1/me/journal` | Журнал причин наград/корректировок с cursor |
| GET/PUT | `/api/character/v1/me/collection` | Девять позиций реликвий, optimistic revision |
| GET/PATCH | `/api/character/v1/me/preferences` | RPG visible/focus, pinned reward; timezone остаётся у profile owner |
| GET | `/api/character/v1/me/operations/{correlation_id}` | pending/applied/failed для принадлежащего пользователю действия |

`preview` выполняется локально с явной подписью, не вызывает equip API и не выдаёт право. Закрытый предмет разрешено визуально примерить только в этом режиме. `equip` проверяет owned и совпадение slot, а не наличие PNG: право и выбранный loadout могут существовать при `art_status=missing`.

Пример команды:

```json
{
  "command_id": "0ed5dc12-8f22-4cf0-82bf-c4658823e7c3",
  "expected_revision": 7,
  "slots": {
    "chest": "armor-0-chest", "shoulders": "armor-0-shoulders",
    "bracers": "armor-0-bracers", "legs": "armor-0-legs",
    "sword": "sword-0", "shield": null, "cloak": null,
    "back_ornament": null, "insignia": null
  }
}
```

Повтор command_id с тем же payload возвращает тот же результат; с другим payload — conflict. Revision conflict → HTTP 409 и актуальная revision, UI предлагает обновить состояние, не молча перетирает другой tab. Unowned/wrong-slot/unknown ID отвергаются согласно error conventions; ownership нельзя обойти изменением client catalog.

Ошибки содержат machine-readable `code`, человеческий текст и correlation ID, без stack trace/SQL. `art_missing` не маскируется под отсутствие ownership. `BLOCKED_CONTENT` не маскируется под недостаточную подготовку пользователя.

## 6. Freshness и frontend

Summary содержит `computed_at`, `summary_revision`, `ruleset_version`, `catalog_version`, `source_checkpoints` по producer и статус `current | pending | stale | unavailable`. В распределённой системе нет автоматически общего последовательного cursor для всех источников: не придумывать его.

После учебного сохранения frontend знает correlation и может использовать existing push либо ограниченный polling с backoff. По истечении ограниченного ожидания оставляет pending-индикатор; не крутит polling бесконечно с коротким интервалом. Восстановление страницы получает подтверждённую сводку. Нет ложного нуля XP при network error и нет оптимистической выдачи предмета до commit RPG.

## 7. Внутренние API и backfill

Внутренние ingestion/reconciliation/export endpoints закрыты от браузера, имеют service identity и ограничения scope. Backfill читает snapshot+cursor через владельца учебной истории, затем live tail с дедупликацией; фиксирует начальный checkpoint. Нельзя делать только «прочитать всё и потом подписаться», потеряв события между шагами.

Сначала dry-run на изолированном profile: сколько facts пригодны, какие неизвестны, projected XP, печати, ownership и source gaps. Пользователь подтверждает cutover. Unknown independence/freshness/family/timing не дополняются угадыванием; такой факт остаётся в учебной истории, но не даёт строгую E/R/K/M-квалификацию.

Import batch имеет ID и checkpoint; повтор запуска — no additional rewards. Начисления старой системы не суммируются с новой оценкой той же истории. Legacy total остаётся в export. Replay не пишет сегодняшнюю активность и не отправляет десятки уведомлений о старых наградах.

## 8. Security и конфиденциальность

Object-level authorization обязательна для summary/evidence/journal/operations. Одна тестовая учётная запись не оправдывает API, позволяющее указать чужой user ID. Клиенту не раскрывать детали будущей холодной задачи по названию reward. Не давать MCP административную выдачу XP. Static manifest не содержит секретов и персональной истории.

Принятые asset paths относительные и из доверенного manifest, а не произвольный URL из пользовательской команды. SVG допускается только контролируемый/санитизированный; не отображать непроверенный SVG как произвольный HTML. Не читать локальные пути, переданные клиентом.
