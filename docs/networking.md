# Сети и firewall

Единственный публикуемый порт основного стенда — 127.0.0.1:28080. PostgreSQL, Redis, RabbitMQ и служебные HTTP-маршруты не публикуются. В assessment web использует 18081; восстановление выполняется в новом project на 18082.

Сегменты: edge для входа web; отдельные content_api/practice_api/learning_api/reports_api/character_api; пять content_storage/practice_storage/learning_storage/reports_storage/character_storage для PostgreSQL; messages для AMQP; cache только для learning и Redis. Все внутренние сети имеют internal=true. Web не входит ни в одну storage-сеть, messages или cache. Каждый runtime подключён только к собственной storage-сети. Сами Docker-сети не выдаются за полную межсервисную allowlist.

| Источник | Разрешённый исходящий поток |
|---|---|
| web | пять API:8000 |
| content | postgres-content:5432, RabbitMQ:5672 |
| practice | postgres-practice:5432, RabbitMQ:5672, content:8000 |
| learning | postgres-learning:5432, RabbitMQ:5672, Redis:6379 |
| reports | postgres-reports:5432, RabbitMQ:5672, practice/learning/character:8000 |
| character | postgres-character:5432, RabbitMQ:5672 |

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

Текущий daily-тест включает 41 сценарий: 16 разрешённых TCP-путей, 24 запрещённых (в том числе 12 межсервисных путей к чужим PostgreSQL) и HTTP-сценарий learning. Датированные отчёты прежней топологии с 26 сценариями остаются историческими. Для запретов внутри общей сети дополнительно проверяется рост счётчика REJECT: отсутствие маршрута не выдаётся за доказательство работы правила. Web→storage/cache отдельно демонстрирует сегментацию.

При запрете всех путей learning→PostgreSQL настоящий `GET /api/v1/learning/progress` проходит состояния HTTP 200→500→200. В assessment блокируются также адреса standby. `test` в finally восстанавливает прежнюю собственную цепь и позиции её OUTPUT-переходов, проверяет совпадение политики; посторонние правила не восстанавливаются глобальным snapshot. При отсутствии прежней цепи тест оставляет её отсутствующей. Счётчики пакетов не сохраняются как часть политики. SIGINT/SIGTERM проходят через откат; SIGKILL не позволяет выполнить finally.

Датированные отчёты и исходные результаты каждого namespace находятся в `.private/evidence/firewall-*`. `show` выводит полный ruleset и счётчики; остальные команды — краткий итог и путь к полному JSON. `rollback` явно удаляет только собственную цепь. Совместимый `scripts/python scripts/firewall.py ...` вызывает тот же Docker CLI wrapper.

У каждого PostgreSQL свой IP и storage-сеть. `scripts/operator scripts/check_sql_isolation.py` проверяет 5 собственных подключений, 20 недоступных чужих PostgreSQL по фактическим IP, ограниченные runtime-роли и 5 запретов CONNECT к служебной postgres. SQL-ACL проверяется внутри собственного экземпляра; запрет чужого TCP проверяется отдельно. В assessment allowlist добавляет только собственную реплику сервиса.

Proxy удаляет внешние X-Session-Assertion и выдаёт доверенное утверждение после проверки opaque cookie. Bearer-токены проверяются сервисами локально, без вызова practice. Ошибка 403 не называется блокировкой TCP.

## Оригинальный журнал пакетов

```sh
CRUCIBLE_DEMO=1 scripts/firewall-capture
```

Перед ACCEPT и финальным REJECT правила NFLOG записывают начальный TCP SYN с префиксом `ALLOW_<service>` или `DENY_<service>`. Частота ограничена только для журналирования; решения ACCEPT/REJECT не ограничиваются этим счётчиком. Одноразовый ulogd2 читает NFLOG group 100 и штатным LOGEMU пишет `firewall.log`: время, источник, назначение, TCP-порты и флаги. Содержимое журнала не формируется Python-скриптом. Оригинальные `iptables.rules`, счётчики и журнал каждого из пяти namespaces сохраняются в `.private/evidence/firewall-capture.*/`.

В internal-сетях без default route пакет к чужой сети может не дойти до OUTPUT. Только во время диагностических проб добавляются /32 маршруты через собственный интерфейс: это позволяет отдельно наблюдать NFLOG и финальный REJECT для чужих PostgreSQL. Членство контейнеров в сетях и разрешения ACCEPT не расширяются; до выхода из namespace SYN блокируется. Маршруты и прежняя политика восстанавливаются в finally. В журнале подтверждается каждый разрешённый и запрещённый маршрут, включая все 12 межсервисных попыток к чужим БД.

Документация механизмов: [iptables NFLOG](https://manpages.debian.org/trixie/iptables/iptables-extensions.8.en.html#NFLOG), [штатная конфигурация ulogd2 NFLOG → LOGEMU](https://sources.debian.org/src/ulogd2/2.0.9-1/ulogd.conf.in/).

Character не подключён к учебным API/storage/cache. Новые факты и review obligations доставляются через разрешённые topic routes; practice не получает HTTP-зависимости от scheduler для старта или сохранения. SVG topology обновлён для пяти владельцев БД.
