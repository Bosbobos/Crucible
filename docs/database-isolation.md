# Отдельный PostgreSQL для каждого сервиса

| Владелец | PostgreSQL | БД | Volume | Внутренняя сеть |
|---|---|---|---|---|
| content | postgres-content | content_db | postgres-content-data | content_storage |
| practice | postgres-practice | practice_db | postgres-practice-data | practice_storage |
| learning | postgres-learning | learning_db | postgres-learning-data | learning_storage |
| reports | postgres-reports | reports_db | postgres-reports-data | reports_storage |
| character | postgres-character | character_db | postgres-character-data | character_storage |

Каждый экземпляр получает отдельный административный пароль. В нём создаются только собственные runtime/migration-роли. Runtime не имеет superuser, CREATEDB, CREATEROLE, CREATE в public или CONNECT к служебной БД postgres. Конфигурация приложения не содержит административного пароля. PostgreSQL не публикует порт на хосте.

Runtime входит только в свою storage-сеть. Firewall разрешает собственный PostgreSQL:5432 и заканчивается REJECT. Межсервисное взаимодействие идёт через API/события. Web и MCP не подключены к storage. Одноразовый административный migration job подключён ко всем пяти сетям и получает только migration credentials.

В assessment у каждого владельца отдельный `<postgres-owner>-standby` с собственным volume в той же storage-сети. Multi-host DSN содержит только свою пару. Репликационные пароли различаются между доменами. Это изоляция процессов и управления БД; Docker-хост, ядро и физический диск остаются общими.

## Исторический перенос четырёх учебных БД до v3

```sh
scripts/split-databases
```

Процедура останавливает приложения, publishers/consumers и одноразовые задачи. В `.private/database-split/` сохраняются исходные секреты и четыре дампа с SHA-256. Для каждой публичной таблицы сверяются количество и MD5 упорядоченного содержимого строк. Runtime-пароли, пароль входа и токены сохраняются; административные пароли новых экземпляров генерируются независимо. Новые контейнеры и volumes создаются отдельно от прежнего `postgres-data`.

После успешной сверки старый PostgreSQL останавливается, его контейнер и volume сохраняются. Затем выполняется обычный deploy с миграциями, firewall и doctor. Повторный запуск продолжает незавершённый перенос по `.private/database-split/state.json`; при несовпадении данных приложения остаются остановленными. Не удаляйте исходный volume или приватную копию до принятия результата.

Старый volume является точкой отката на момент переноса. После новых записей откат на него потеряет эти записи; для возврата потребуется новый согласованный перенос из четырёх экземпляров. Не запускайте старые и новые приложения параллельно. Прежняя конфигурация сохранена в `.private/database-split/original-secrets/`; её секреты и дампы не публикуются.

## Проверки

```sh
scripts/doctor
scripts/operator scripts/check_sql_isolation.py
CRUCIBLE_DEMO=1 scripts/firewall test
scripts/test integration
```

SQL-проверка подтверждает отдельный состав БД/ролей каждого экземпляра, пять собственных подключений, двадцать запрещённых TCP-путей к чужим PostgreSQL, пять запретов CONNECT к postgres и CRUD временного черновика learning. Firewall отдельно проверяет allowlist и временную блокировку собственной БД: progress возвращает 200 → 500/503 → 200, после чего исходные правила восстанавливаются.

Для синтетического assessment:

```sh
scripts/assessment up
scripts/assessment postgres-failover --service practice
scripts/assessment rejoin --service practice
```

Повторите пару failover/rejoin для content, learning и reports. В каждом случае проверяются fencing, promotion, подтверждённый маркер, новая API-запись именно выбранного владельца, пересчёт learning и экспорт. Старый primary возвращается только как реплика. Backup/restore работают с пятью отдельными экземплярами; команды приведены в [руководстве по надёжности](reliability.md).

Старые датированные JSON и скриншоты общего PostgreSQL остаются историческими свидетельствами. Свежие локальные результаты сохраняются в `.private/evidence/`; полной готовности P/D эти проверки сами по себе не объявляют.

В v3 character добавляется отдельно через аддитивное расширение bootstrap-конфигурации и собственные миграции. Повторять прежний split для уже разделённого стенда не требуется. Проверки нового контура и точные команды находятся в [отчёте v3](crucible/release-report.md).
