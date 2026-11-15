# Проверенная совместимость

Дата проверки: 13 ноября 2026. Python 3.11 в conda IAD, официальный пакет mcp 2.3.0. Сервер использует MCPServer, клиент — Client и StdioServerParameters. Транспорт stdio; JSON-RPC и negotiation реализует SDK.

`CRUCIBLE_INTEGRATION=1 scripts/python -m pytest tests/integration/test_mcp.py -q` запускает отдельный реальный процесс сервера, получает инструменты, читает контекст, дважды отправляет один комментарий и проверяет отсутствие повторного эффекта и изменения черновика. Structured output включён явно.

Этот результат подтверждает совместимость с клиентом SDK. Интерактивная регистрация и использование в конкретном desktop/IDE-host пользователя пока не подтверждены. Resources/prompts второго host, HTTP transport и OAuth не заявляются проверенными.

Основание выбора SDK: [официальный Python SDK](https://github.com/modelcontextprotocol/python-sdk). Устаревший HTTP+SSE и самописный протокол не используются.

## Контейнерный запуск 14 ноября

`scripts/test integration` запускает SDK-клиент и отдельный процесс адаптера внутри тестового контейнера. `scripts/operator scripts/check_mcp.py` отдельно проверяет настоящий `scripts/study-mcp` → Docker Compose → MCP image: initialize/list_tools и чтение через scoped API, без изменяющих вызовов. Успех контейнерного SDK smoke не означает регистрации в desktop/IDE-host. Python остаётся версии 3.11 внутри образов; SDK зафиксирован requirements.lock.

На основном project дополнительно подтверждены 9 tools и чтение get_progress_summary через настоящий Docker stdio entrypoint. Вызовов, меняющих учебные факты, этот smoke не выполнял. Свидетельство — docs/obsidian-demo/attachments/mcp-container-2026-11-14.json; desktop registration по-прежнему не подтверждена.
