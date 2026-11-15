# Сети и firewall

Единственный публикуемый порт основного стенда — 127.0.0.1:18080. PostgreSQL, Redis, RabbitMQ и служебные HTTP-маршруты не публикуются. В assessment web использует 18081; восстановление выполняется в новом project на 18082.

Сегменты: edge для входа web; отдельные content_api/practice_api/learning_api/reports_api; storage для PostgreSQL; messages для AMQP; cache только для learning и Redis. Все внутренние сети имеют internal=true. Web не входит в storage/messages/cache. Сами Docker-сети не выдаются за полную межсервисную allowlist.

| Источник | Разрешённый исходящий поток |
|---|---|
| web | четыре API:8000 |
| content | свой PostgreSQL-кластер:5432, RabbitMQ:5672 |
| practice | PostgreSQL:5432, RabbitMQ:5672, content:8000 |
| learning | PostgreSQL:5432, RabbitMQ:5672, Redis:6379 |
| reports | PostgreSQL:5432, RabbitMQ:5672, practice/learning:8000 |

Bootstrap/rebuild learning запускается в явном режиме обслуживания и временно нуждается в сетях practice_api/content_api; обычный планировщик туда не ходит. Для scoped восстановления оператор подключает learning к этим сетям на время команды и затем отключает их.

## Применение и проверка Linux firewall

`scripts/deploy` собирает `crucible-probe:0.2.0`, актуализирует правила до ожидания готовности API и повторно после запуска всего стека. `scripts/doctor` сверяет реальную цепь каждого приложения с текущими адресами Compose; отсутствие/устаревание политики даёт ненулевой код завершения. Сами файлы Compose не являются постоянно работающим контроллером firewall: после ручного recreate используйте `scripts/deploy`.

```sh
scripts/firewall show
scripts/firewall check
CRUCIBLE_DEMO=1 scripts/firewall test
scripts/doctor
```

Обычный deploy использует POSIX shell и Docker CLI на хосте. Административные Python-процедуры могут вызывать тот же wrapper из отдельного operator с Docker socket; приложения и probe socket не получают. Один probe в namespace конкретного приложения получает только NET_ADMIN; приложения работают без этой capability. Ни probe, ни приложения не получают Docker socket или privileged. Firewall — Linux netfilter в VM Docker Desktop; правила macOS и других проектов не меняются.

Правила и TCP-пробы относятся к IPv4-сетям текущего Compose.

Политика допускает loopback и ESTABLISHED/RELATED, перечисленные потоки и запрещает остальные исходящие соединения. Обновление содержимого собственной цепи выполняется через `iptables-restore --noflush`, без очистки чужих цепей. Проверка учитывает единственный первый переход OUTPUT→CRUCIBLE_EGRESS, полный состав правил и актуальные адреса.

14 ноября новый тест проверил 26 сценариев daily: 16 разрешённых TCP-путей, 9 запрещённых и HTTP-сценарий learning. Для запретов внутри общей сети дополнительно проверяется рост счётчика REJECT: отсутствие маршрута не выдаётся за доказательство работы правила. Web→storage/cache отдельно демонстрирует сегментацию.

При запрете всех путей learning→PostgreSQL настоящий `GET /api/v1/learning/progress` проходит состояния HTTP 200→500→200. В assessment блокируются также адреса standby. `test` в finally восстанавливает прежнюю собственную цепь и позиции её OUTPUT-переходов, проверяет совпадение политики; посторонние правила не восстанавливаются глобальным snapshot. При отсутствии прежней цепи тест оставляет её отсутствующей. Счётчики пакетов не сохраняются как часть политики. SIGINT/SIGTERM проходят через откат; SIGKILL не позволяет выполнить finally.

Датированные отчёты и исходные результаты каждого namespace находятся в `.private/evidence/firewall-*`. `show` выводит полный ruleset и счётчики; остальные команды — краткий итог и путь к полному JSON. `rollback` явно удаляет только собственную цепь. Совместимый `scripts/python scripts/firewall.py ...` вызывает тот же Docker CLI wrapper.

Для общего IP PostgreSQL firewall разрешает порт сервера, а CONNECT ACL запрещает чужую логическую БД. Это разные доказательства: `scripts/python scripts/check_sql_isolation.py` проверил 4 разрешённых и 12 запрещённых соединений.

Proxy удаляет внешние X-Session-Assertion и выдаёт доверенное утверждение после проверки opaque cookie. Bearer-токены проверяются сервисами локально, без вызова practice. Ошибка 403 не называется блокировкой TCP.
