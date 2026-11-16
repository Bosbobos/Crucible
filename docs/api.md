# HTTP-контракты

Актуальные OpenAPI и JSON Schema экспортируются командой `scripts/python scripts/export_contracts.py` в `packages/contracts/schemas/`. Это контракт исполняемого кода; точные модели запросов находятся там, а не в примерных таблицах старого ТЗ.

| Группа | Основные операции |
|---|---|
| `/api/v1/content` | GET catalog; GET problems/{id}?release_id; GET topics/{id}/{core,theory,widget}; POST releases с авторским scope |
| `/api/v1/practice` | current; attempts; PATCH attempts/{id}; complete/help/questions/reviews/proposals; подтверждение предложения и закрытие вопроса |
| `/api/v1/learning` | progress?at_least_practice_seq; today; POST daily-plans; PATCH settings |
| `/api/v1/reports` | POST jobs; GET jobs/{id}; GET jobs/{id}/artifact |

Все изменяющие предметные команды содержат UUID command_id, а команды редактирования — expected_revision. Исключение — технический вход/выход сессии. Идентичность и профиль не берутся из тела запроса. Pydantic запрещает неизвестные поля. Ошибки 401/403 относятся к identity/scopes, 409 — к редакции или повторному использованию ID, 422 — к схеме/предметным ограничениям, 503 — к необходимой зависимости.

Каждый сервис предоставляет `/health/live`, `/health/ready`, `/hello`, собственный OpenAPI и авторизованную диагностику outbox внутри сети. Proxy не публикует внутренние маршруты и служебные схемы. `GET /hello` доступен через web.

Внутренние контракты: content/protected — только practice identity; practice/snapshot — reports; practice/learning-facts — learning для восстановления. Полномочия проверяются самим владельцем. Proxy не заменяет эти проверки.

## Character v3

Префикс `/api/character/v1`, прежняя session/JWT и Origin/CSRF. GET catalog, me/summary, me/inventory, me/items/{id}, me/path, me/journal, me/operations/{correlation_id}; GET/PUT me/loadout и me/collection; GET/PATCH me/preferences. Изменения требуют command_id и expected_revision. Preview локален. Отсутствующий арт не запрещает owned equip; unowned/wrong-slot отклоняются.

В practice добавлены PATCH attempts/{id}/assessment (подтверждение владельцем с причиной), POST learning-evidence/{unit_id}, POST assessments/{blueprint_id}/results. Источник проверяет зарегистрированную content publication и сохраняет ответы в своей БД. В content POST campaign-publications доступен только content:publish; внутренние metadata/assessment routes закрыты от web gateway. Неизвестные привязки означают BLOCKED_CONTENT. Character snapshot доступен reports по отдельному scope; browser/MCP не имеют grant_xp/give_item.
