# Демонстрационные проверки

Команды запускаются из корня репозитория на уже работающем стенде. Python и зависимости используются из контейнера сервиса; устанавливать их на компьютер для показа не нужно. Для HTTP-сценариев Redis и RabbitMQ нужен Node.js 18+ без дополнительных npm-пакетов.

| Слайд | Проверка | Команда |
|---|---|---|
| 5 | PostgreSQL CRUD | `scripts/demo/postgres-crud` |
| 7 | Redis: miss, hit и GET | `node scripts/demo/redis-cache.mjs` |
| 8 | RabbitMQ: публикация и обработка | `node scripts/demo/rabbitmq-publish-consume.mjs` |

## PostgreSQL CRUD

```sh
scripts/demo/postgres-crud
```

Проверка с SQL-слайда презентации выполняет `INSERT`, `SELECT`, `UPDATE` и `DELETE` над временной записью `plan_drafts` в `learning_db`. Она использует конфигурацию контейнера `learning` и проверяет, что подключение выполнено ролью `learning_runtime`. Вся демонстрация проходит в одной транзакции, которая откатывается и при успехе, и при ошибке.

Для отдельного assessment-стенда:

```sh
CRUCIBLE_ASSESSMENT=1 scripts/demo/postgres-crud
```

Выбор Compose-файлов и имени project выполняет общий `scripts/compose.sh`; поддерживаются те же переменные `CRUCIBLE_ASSESSMENT_PROJECT`, `CRUCIBLE_ASSESSMENT_OVERLAY` и `COMPOSE_PROJECT_NAME`, что у остальных команд проекта.

Исходный Python-код: [postgres_crud.py](postgres_crud.py). Shell-команда передаёт его через stdin в работающий контейнер, поэтому пересобирать образ после изменения демонстрации не требуется.

## Redis

```sh
node scripts/demo/redis-cache.mjs
```

[Сценарий](redis-cache.mjs) удаляет только текущий вычисляемый summary для профиля `owner`, делает два авторизованных запроса `/api/v1/learning/progress` и проверяет `miss`, затем `hit`. Ключ учитывает текущую ревизию и часовой пояс из собственной БД learning. Redis GET из runtime-контейнера сверяет сохранённые `revision` и `generated_at` с HTTP-ответом. Результат выводится в том же формате JSON, что на слайде.

## RabbitMQ

```sh
node scripts/demo/rabbitmq-publish-consume.mjs
```

[Сценарий](rabbitmq-publish-consume.mjs) создаёт новое задание экспорта через Reports API с уникальным `command_id`, ждёт `ready`, затем проверяет в собственной БД reports подтверждение публикации и квитанцию consumer для одного `event_id`. Вывод совпадает по структуре со слайдом. Созданное задание и артефакт остаются в приложении.

Оба HTTP-сценария читают адрес API и токены из `.secrets/operator.json`, а при `CRUCIBLE_ASSESSMENT=1` — из `.secrets/assessment/operator.json`. Токены и DSN не выводятся. Вызовы контейнеров используют общий `scripts/compose.sh`, как CRUD-команда.
