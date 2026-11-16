# Доставка событий

Используются content.catalog.published.v1, practice.learning-facts.changed.v1, learning.progress.updated.v1, report.requested.v1 и report.ready.v1. Метаданный каталог передаётся целиком, без решений; лимит одного события — 512 КБ. Оболочка и закрытая схема фактов экспортированы в JSON Schema.

У каждого сервиса собственный outbox и dispatcher с доступом только к своей БД. После локального commit сообщение публикуется как persistent с publisher confirm и mandatory routing. Сбой оставляет pending-запись. Уже опубликованные события сохраняются; очистки с недостаточным горизонтом нет.

Очереди learning.in, reports.in, character.in и practice.in независимы, durable и quorum. У каждой своя DLQ. Consumer фиксирует receipt и изменение собственной БД вместе, затем ack. Нарушенная схема уходит в DLQ; временная ошибка повторяется без успешного ack. Доставка — at least once, предметный эффект защищён от повторения.

Старый снимок попытки не заменяет новый. Курсор растёт только при наличии следующего непрерывного seq. Redis-ключ зависит от фактических входов, курсоров, настроек и учебной даты. Поэтому даже полученный раньше времени новый снимок не выдаётся за полный префикс истории.

Для потери очереди есть операторский replay всех outbox и перестройка проекций по API владельцев в режиме обслуживания. Нельзя ограничиваться pending: потерянное брокером после confirm событие уже могло быть помечено опубликованным.

## Потоки v3

practice.learning-facts.changed.v1 сохраняет прежний main cursor; optional character_fact содержит полный snapshot результата. practice.character-evidence.changed.v1 доставляет учебные единицы/диагностики/assessment results отдельным stream. content.character-campaign.published.v1 несёт private metadata без текстов/ответов. learning.character-profile.changed.v1 передаёт timezone; learning.review-obligation.registered.v1 — сохранённое обязательство в practice.in.

Character проверяет producer/type/stream, event hash, fact revision/hash. Два event IDs одного факта не платят повторно. Старшая revision заменяет текущий snapshot; компенсация desired−applied записывается в ledger вместе с journal/outbox. character.progress.updated.v1 сообщает об изменении XP или сохранённого косметического состояния; consumer reports инвалидирует экспорт. Broker retry использует bounded exponential backoff с jitter; poison schema уходит в отдельную DLQ.
