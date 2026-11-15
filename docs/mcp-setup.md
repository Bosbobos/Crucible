# Внешний агент

Основной транспорт — stdio. Запускаемый процесс: `scripts/study-mcp` (shell → Docker Compose → отдельный Python-контейнер); конфигурация и scoped credentials берутся из `.secrets/mcp.json`. Для хоста нужны Docker CLI и работающий Engine, Python/conda не требуются. `docker compose build study-mcp` заранее готовит образ; при первом вызове wrapper может собрать его, направляя build-логи только в stderr. Stdout занят протоколом, диагностические логи идут в stderr. У процесса нет DSN или доступа к брокеру.

Для MCP-host, который принимает JSON-конфигурацию процессов, запись имеет вид:

```json
{"mcpServers":{"study-prep":{"command":"/path/to/repository/scripts/study-mcp"}}}
```

Формат регистрации зависит от конкретного host. Глобальные настройки IDE/desktop при разработке не изменялись. Доступность tools в текущем пользовательском host должна быть подтверждена отдельно; SDK smoke-тест этого не заменяет.

Пять инструментов P: get_study_context, list_review_queue, begin_tutoring, append_review, propose_progress_correction. Дополнительно доступны get_material, get_progress_summary, request_export и get_job. Resource study://attempts/{id} использует тот же обработчик контекста. HTTP MCP-профиль не реализован и не нужен локальному stdio-сценарию.

Контекст показывает подтверждённый черновик, закреплённое условие, вопросы, комментарии, помощь, ревизию и learning cursor. Недоступный learning обозначается missing_sections. Скрытых решений нет. Математический диалог по активной попытке начинается явным begin_tutoring. Разбор завершённой попытки не переписывает её самостоятельность.

Агент может предложить исправление, но не подтверждает его: агентский токен не содержит correction:approve или question:resolve. Владелец подтверждает предложение в UI, с проверкой исходной редакции.

При неизвестном исходе записи host повторяет прежний command_id. Для резервного JSON-ответа доступен `scripts/operator scripts/import_review.py response.json`; это тот же practice API и те же правила, без inbox watcher.

Токены bootstrap имеют audience конкретного сервиса и срок 30 дней. В этом срезе автоматическое продление и немедленный отзыв агентского токена ещё не реализованы. Учебный host с полным shell-доступом к авторскому репозиторию может прочитать исходные решения; MCP-ограничения не являются изоляцией ОС.

MCP-образ содержит только SDK и apps/study_mcp, работает от UID 10001, читает один mcp.json и обращается к web:8080 по API-сети. Docker socket, DSN, content-файлы, backups и checkout внутрь MCP не монтируются. Это отдельная доверительная граница от operator, который нужен только владельцу для административных процедур.
