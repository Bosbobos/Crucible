# 11. Приёмка и проверяемые сценарии

Каждый пункт в отчёте имеет `passed | failed | not_run`, дату/версию, команду или screenshot/trace path. Этот файл — **план тестов приложения**, а не утверждение, что приложение уже проверено. Проверки самого пакета описаны отдельно в `qa/PACK_VALIDATION.md`.

## A. Архитектура и сохранность

| ID | Сценарий / ожидаемый результат |
|---|---|
| A01 | Найден и описан фактический стек/сервисы, baseline учебного цикла сохранён |
| A02 | character-service имеет свои миграции/DB role, нет SQL/ORM-доступа к чужим таблицам |
| A03 | Запись попытки при остановленном character-service успешна; source outbox сохраняется |
| A04 | Outbox publish сбой/retry и consumer redelivery не теряют и не удваивают результат |
| A05 | Падение до commit / после commit до ACK проверено на integration test |
| A06 | Unknown schema/poison payload → quarantine/DLQ, нет tight-loop, остальные факты обрабатываются |
| A07 | Readiness/graceful shutdown, backlog/lag/duplicate/error метрики и корреляционные логи работают |
| A08 | Нет лишнего renderer/xp/inventory микросервиса и обязательной runtime LLM |
| A09 | Только authenticated producer пишет facts; browser/MCP не выдаёт XP/предметы напрямую |
| A10 | Object-level authorization: чужие inventory/evidence/operation IDs не доступны |

## B. Прогрессия

| ID | Сценарий / ожидаемый результат |
|---|---|
| B01 | Все 60 порогов совпадают; level 60 начинается с 33 276; next-cost null у cap |
| B02 | A/B/C = 40/80/120; B+ adapter не создаёт новый тариф |
| B03 | B с 1 independent + 1 assisted равного веса = 68; B×90% =72; reviewed с note =28 |
| B04 | Reviewed без note, skipped, view/scroll/time/streak/equip дают 0 |
| B05 | 28→56→80 в одной equivalence group: deltas 28/28/24; сумма80 |
| B06 | Новые event IDs одного fact/revision, одинаковый command retry, duplicate delivery — no double count |
| B07 | Revision3 раньше revision2; stale revision не откатывает результат |
| B08 | Тот же event ID с другим payload / та же revision с другим snapshot → конфликт, не тихое принятие |
| B09 | Correction 80→56 даёт −24, если другой валидный максимум группы не сохраняет80 |
| B10 | Повтор при exact168h допустим, раньше — нет; due/obligation обязательны |
| B11 | Raw quality≥80% проверяется отдельно от assistance; repeat цены12/24/36 при full independent |
| B12 | Не больше3 repeat entitlement на equivalence; четвертый полезен учёбе, не эмитирует RPG XP |
| B13 | Primary gain в попытке исключает repeat; новый equivalence исключает repeat old item |
| B14 | Replay в другом arrival order даёт тот же ledger total/entitlements и не сегодняшний rhythm |
| B15 | V: чтение и известная тема через диагностику равноценны; непрочитанные разделы не оплачены |
| B16 | E не выдаётся за assistance, знакомую постановку, два числовых клона/одно семейство |
| B17 | R: E существует, новое третье семейство, 168h от первого E-evidence; нет контента → BLOCKED_CONTENT |
| B18 | K: E5/R3, четыре свежих условия, ≥3 family, веса20/25/25/30, ≥80 суммарно, C≥50% |
| B19 | M: три разных зарегистрированных варианта, веса15×5+25, quality/freshness/independence, disjoint family |
| B20 | Одна задача не подтверждает несколько E-томов из-за множества tags; V может использовать то же evidence без двойной оплаты задачи |
| B21 | First fresh independent C≥80% даёт ровно1 insignia по дисциплине, без дополнительного XP |
| B22 | Seal correction обновляет current qualification/XP, сохраняет item ever_granted с recheck |
| B23 | Повторное подтверждение recheck не даёт второй item/лишний seal XP |
| B24 | Ранг и предметы не создают XP-цикл; milestones доступны без ручного claim |
| B25 | После cap каждые2000 XP дают номер Хроники, нет reset/обещания бесконечного уникального арта |
| B26 | Timezone change/DST не меняют source timestamps и начисления; rhythm по профилю |
| B27 | Negative weight, zero sum, duplicate part ID, unknown difficulty/outcome, NaN/Infinity отвергнуты |

## C. Инвентарь и контент

| ID | Сценарий / ожидаемый результат |
|---|---|
| C01 | 59 уникальных определений; 7 стартовых owned; ordinals/set names и rank names не смешаны |
| C02 | Старые aliases мигрируются, не создавая отдельные gauntlets/greaves/aura items |
| C03 | Все9 selectors имеют понятные подписи; none работает, initial outfit отдельно описан |
| C04 | Unowned/wrong-slot/unknown equip отвергнут, art_missing owned equip разрешён с объяснением |
| C05 | Два клиента с одним expected_revision: один success, второй409; никакой потерянной записи |
| C06 | Grant не auto-equip, preview не persistence/ownership, refresh сохраняет confirmed loadout |
| C07 | 3 ornament заменяют3 aura, не добавлены6 новых наград и не требуют full set |
| C08 | В9 positions нельзя положить unowned relic/дубликат, перестановка атомарна |
| C09 | 25 volumes/58 blueprints связаны или помечены unbound/blocked; никаких synthetic IDs в production |
| C10 | Holdout/решения/названия методов не утекают через reward DTO, поиск и MCP |

## D. Paper-doll

| ID | Сценарий / ожидаемый результат |
|---|---|
| D01 | Raw hashes сохранены, правильные Tier0/1 сопоставлены, rig anchors измерены |
| D02 | BASE/Tier3/sword ref alpha255 не выдан за прозрачный фон; белая ткань не удалена глобальным порогом |
| D03 | Сборка regions воспроизводит сегментированный BASE; wrap сохранён без дорисовки скрытой анатомии |
| D04 | 20 частей5 сетов по отдельности, 5 full sets, 10 mixed из visual_test_cases проверены |
| D05 | Legs hide применён только к допустимым regions: нет торчащей ноги/повязки, нет потери хвоста/рук |
| D06 | Снятие legs или failure картинки восстанавливает BASE+wrap без holes |
| D07 | Paint alpha не применяется дважды, max-union hide не переистончает AA край |
| D08 | Открытая кожа/голова/рога из BASE, нет второй кожи/ступни из бронепластины |
| D09 | High collar перекрывает нижнюю шею естественно; защищённое лицо остаётся pixel-stable |
| D10 | Меч: right hand слева зрителю, diagonal до правого низа перед обеими ногами |
| D11 | Neutral hand скрыта локально; back palm/sword/front fingers правильны, wrist неизменен |
| D12 | Sword null/missing grip возвращает neutral; отсутствующий слой не оставляет маску скрытия |
| D13 | Ornament позади головы, без силуэтного отверстия/лица в файле, independent none, без clip |
| D14 | Поздняя загрузка старого loadout не перезаписывает новый; manifest switch атомарен |
| D15 | Все3QC фона, scene widths240/360/480 и карточка160px; screenshot evidence реально существует |
| D16 | ARM05 missing не заменён rejected/старым золотым артом; gallery не имитирует independent equip |

## E. UX, производительность и перенос

| ID | Сценарий / ожидаемый результат |
|---|---|
| E01 | Светлая тема, актуальные tokens/fonts, нет зелёного/glass/glow redesign |
| E02 | Главная1280×800 содержит рабочую CTA/задачу до прокрутки; 4viewport проверены |
| E03 | Задача/теория сохраняют draft/attempt/позицию; длинные формулы не расширяют страницу |
| E04 | Keyboard-only маршрут, focus-visible, zoom200%, contrast и reduced motion реально проверены |
| E05 | Один polite reward message, нет pop-up каскада; missing art не съедает текстовые controls |
| E06 | Canvas имеет DOM-альтернативу описания/слотов; главный экран не eager-load всех raw PNG |
| E07 | Фактические runtime bytes/latency измерены; declared budgets не выданы за измерения |
| E08 | RPG off/outage оставляют весь учебный цикл; confirmed XP не заменяется нулём |
| E09 | Migration dry-run подтверждён, не складывает legacy и replay; aliases идемпотентны |
| E10 | Snapshot+cursor/live-tail backfill не теряет окно событий; replay silent по наградам |
| E11 | Backup/restore и rollback feature flags проверены; нет двух XP writers |
| E12 | Источники/license notices закреплены по реально установленным ресурсам, шрифты не hotlinked |

## Границы результата

**Code MVP** можно принять при missing final art, но нельзя принимать фиктивные награды, блокирующий save RPG-call, сломанную учебную работу или пустой backend за мокапом. **Visual MVP** требует реальные независимые части пяти существующих комплектов; pending parts — незавершённая визуальная работа. Sword/ornament и остальные цели подключаются по готовности, без принудительного ожидания всех45 изображений.

Нет обязанности перегенерировать принятый BASE. Нет утверждения о совместимости пяти источников до D04–D09. `not_run`/`BLOCKED_ART`/`BLOCKED_CONTENT` сохраняются в release report, а не превращаются в pass ради общего процента выполнения.
