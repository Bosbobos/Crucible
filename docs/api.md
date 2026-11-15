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
