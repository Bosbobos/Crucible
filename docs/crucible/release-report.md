# Crucible v3 — отчёт реализации и приёмки

Дата: **16 ноября 2026**, ветка `codex/crucible-v3`, ruleset `crucible-v1`,
catalog `3.0.0:9c3b39c6fec5a719`, art manifest `af8ca469de88241c4cab`.
Рабочий адрес: **http://127.0.0.1:28080** (Compose project `paladin`).
Соседний исходный проект `crucible` на :18080 не модернизировался.

## Результат и границы

**Code MVP:** character-service, отдельная БД/роль/миграции, транзакционные
inbox/ledger/outbox, корректировки, 60 уровней, V/E/R/K/M, права на 59 определений,
инвентарь, 9 слотов, примерка, коллекция и preferences реализованы. Учебный цикл
работает при остановленном RPG. Основной профиль содержит **0 попыток / 0 XP**;
синтетическая история в него не добавлялась. Полная приёмка всех исторических
сценариев не заявляется: C02/E10 требуют найденных legacy записей и отдельно
подтверждённого cutover. Автоматический backfill непустой истории не реализован.

**Visual MVP:** BASE и **20 независимых частей ARM-00…04** приняты по paint/mask/rig
SHA; пять комплектов смешиваются. Начальный образ — четыре части ARM-00, остальные
слоты пусты; семь стартовых предметов owned. SWD-03 снят с production rendering
после failed QA гарды/хвата, его право и выбор сохраняются независимо от арта.

**Full art catalogue:** не готов. Приняты база и пять существующих бронекомплектов;
39 остальных художественных целей не приняты, включая доработку меча. Новые PNG
генерирует владелец по одному; генератор при модернизации не запускался.

Все **25 томов / 58 чертежей** честно `unbound / BLOCKED_CONTENT`. Исходный банк
содержит 57 задач и 4 заметки, но не проверенные curated families и необходимые
рубрики. Обработка evidence и публикация привязок реализованы; production-печати
не выданы на основании tags/номеров навыков. Реестр: [content-gaps](content-gaps.md).
Контрольные условия и решения при авторинге не открывались.

**Готовность P/D не заявляется.** Firewall, SQL isolation и restore проверены;
failover пяти кластеров и подключение MCP в реальном desktop-host не проверялись.
Реальный MCP SDK stdio-client проверен отдельно и не заменяет MCP-host.

## Изменённые границы

- Content публикует immutable campaign bindings и metadata; обычный каталог/MCP
  не раскрывает holdout. Проверяются unit kind, принадлежность тому, equivalence,
  реальные опубликованные ID и семейства, состав K/M и disjoint training families.
- Practice хранит canonical самооценку/quality/freshness, собственные ответы и
  outbox; владелец исправляет оценку с reason/revision. Агент только предлагает.
  Неизвестные freshness/обязательства повторения остаются неизвестными.
- Learning сохраняет свои review obligations и отправляет их в readonly
  projection practice; синхронного вызова scheduler/RPG из save нет.
- Character владеет XP/entitlements/ever-owned/recheck/loadout/preferences;
  полный пересчёт компенсирует ошибку отрицательной ledger delta. Другие DB ему
  недоступны. Четыре независимых source streams не образуют дыр в main cursor.
- Reports включает owner snapshot character; при его отказе отмечает отсутствие
  снимка явно. Character events инвалидируют экспорт, учебная часть сохраняется.

OpenAPI и JSON Schemas: `packages/contracts/schemas/`; обзор SQL:
`migrations/character/schema.sql`. Runtime применяет только numbered migrations.

## Фактические проверки

Python 3.11 из conda **IAD**, зависимости `.deps/`; PostgreSQL 17, React 19.3.1,
Vite 8.3.8, Playwright 1.65.0 / Chromium 158.0.8127.18. Образы базовых runtime
закреплены digest в Dockerfiles. Локальный тестовый PostgreSQL — отдельная
`character_test`, все прикладные API-тесты — отдельный `crucible-character-test`.

| Проверка | Результат | Команда / свидетельство |
|---|---|---|
| Baseline до изменения | passed, 29 passed / 8 skipped | `docs/crucible/audit.md`, закрытый G0 backup |
| Полный Python-набор | **passed, 73 passed, 0 skipped**, 20.71s | команда ниже |
| TypeScript / production build | passed | `docker compose build`, `npm --prefix apps/web run build` |
| Браузерный набор | **passed, 9 passed**, 33.1s | `apps/web/e2e`, команда ниже |
| Настоящий renderer | passed, 35 cases, 3 backgrounds, 240/360/480 | `scripts/check_paper_doll.mjs`, `lab/renderer-report.json` |
| SQL isolation | passed, 5 own / 20 foreign denied | `scripts/check_sql_isolation.py`, `.private/evidence/sql-isolation.json` |
| Firewall fault / restore policy | passed, 58 checks, 6 namespaces | `.private/evidence/firewall-test-20261116T001258Z.json` |
| Outage / duplicate / correction | passed | `.private/evidence/crucible-v3/event-flow.json` |
| Unknown schema / DLQ | passed, следующий факт принят | `crucible-v3/poison.json` |
| Producer ACL | passed, cross-owner publish ACCESS_REFUSED | `crucible-v3/producer-acl.json` |
| Feature flags rollback | passed, read/write 503, practice save 200, backlog recovered | `crucible-v3/rollback.json` |
| UI theme rollback build | passed | `VITE_CRUCIBLE_UI=0 npm --prefix apps/web run build`, закрытая сборка `ui-rollback-build/` |
| Импорт dry-run основного профиля | passed, 0 attempts, cursor0, 0 writes | `crucible-v3/import-preview.json` |
| Согласованный backup / restore 5 DB | passed | `.private/evidence/backup.json`, `restore.json`, `crucible-v3/restore-character.json` |
| Итоговый main doctor | passed, content/practice/learning/character HTTP200 | `scripts/doctor`, firewall check 6 namespaces |
| Git whitespace | passed | `git diff --check` |

Полный Python-прогон (все fault tests направлены только на отдельный проект):

```sh
COMPOSE_FILE=compose.yaml:.private/crucible-v3-test/compose.override.yaml \
COMPOSE_PROJECT_NAME=crucible-character-test \
CRUCIBLE_INTEGRATION=1 CRUCIBLE_RESILIENCE=1 \
CRUCIBLE_TEST_CONFIG_DIR=.secrets/character-test \
CRUCIBLE_TEST_PASSWORD_FILE=.secrets/character-test/owner-password \
CRUCIBLE_TEST_BASE_URL=http://127.0.0.1:28083 \
CRUCIBLE_CHARACTER_TEST_DSN=postgresql://postgres@127.0.0.1:55436/character_test \
CRUCIBLE_LOCAL_PYTHON=1 scripts/python -m pytest -q
```

Браузерный прогон из `apps/web`:

```sh
CRUCIBLE_TEST_ORIGIN=http://127.0.0.1:28083 \
CRUCIBLE_TEST_SECRETS=../../.secrets/character-test \
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/crucible-playwright npx playwright test
```

`scripts/character_test_stack.py up` воспроизводит изолированный прикладной стенд;
PostgreSQL для DB-тестов создаётся отдельно, допускается только имя `*_test`. На новой машине (если контейнер ещё не существует):

```sh
docker run -d --name crucible-character-test-db \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=character_test \
  -p 127.0.0.1:55436:5432 \
  postgres:17@sha256:846a7ddaa67a4b354ae1d21087b683901aa6113a4ed626d3787cfbf6c85e3e07
```

Это disposable тестовая БД без личных данных; Python fixture очищает только её.

Секреты, traces, backup и evidence остаются в `.secrets/` и `.private/`, в Git
не включаются. Исходные незакоммиченные изменения сохранены, reset/clean не было.

### Проверенный reward flow

Реальная synthetic B попытка `2e467e13-cad5-493f-b87a-cbc74450b0c4` сохранилась
при остановленном character. Correlation `3be2edb8-4914-48a6-9462-6803b4cc1665`:
после восстановления **+80**, второй event ID того же факта **+0**, подтверждённая
владельцем коррекция **−24**. Ledger совпал со summary (160 → 136 на этом шаге).
Полный trace с original/duplicate IDs лежит в `event-flow.json`. Восстановленный
позднейший согласованный snapshot имеет **176 XP** в ledger и summary после
replay сохранённого outbox; это отдельный момент synthetic истории.

### Измерения, а не целевые бюджеты

`scripts/check_character_ui_metrics.mjs`: локальный Docker Desktop + Chromium,
один synthetic profile, холодный browser cache. Последний замер: **954527 bytes**
ресурсов Today (без navigation HTML), **393569 bytes** ресурсов `/character/`; первый видимый
инвентарь нагрудников после Today — **1133546 cumulative transfer bytes** в том
же браузере. Это не изолированная холодная загрузка всего каталога и не load test.
Summary: 20 запросов, p50 **17.0ms**, p95 **38.4ms**, max **39.8ms**; величины зависят
от локальной нагрузки. Полные resource timings — `crucible-v3/ui-metrics.json`.

Paint layer max **118313 bytes**, BASE **163884 bytes**. Canvas 35 cases: median
**67.1ms**, max **133.4ms**, без постоянного animation-frame loop. Raw PNG на главной
не запрашиваются; immutable hash URLs кешируются, manifest проверяется заново.
JS bundle около 1.25MB до gzip, предупреждение Vite о >500KB остаётся (было и в
baseline); proxy теперь сжимает JS/CSS/JSON/SVG. Стартовый декоративный бюджет
1.5MB соблюдён в этом замере. Контраст четырёх новых token pairs 5.17–14.15:1;
reduced-motion даёт transition duration 0s. Это не полная сертификация WCAG.

## Матрица пунктов 11_ACCEPTANCE_AND_TESTS

`passed` относится к указанной проверке. Отсутствие production content/art
помечено отдельно; synthetic test не превращает его в опубликованный материал.

| ID | Статус | Проверка / ограничение |
|---|---|---|
| A01 | passed | audit.md; baseline 29/8; G0 backup |
| A02 | passed | SQL isolation: 5 own / 20 denied |
| A03 | passed | event-flow.json: practice save при остановленном RPG |
| A04 | passed | resilience + retained outbox replay + duplicate flow |
| A05 | passed | test_store: rollback до commit, redelivery после commit |
| A06 | passed | poison.json; DLQ + следующий факт |
| A07 | passed | ready, graceful recreate, outbox age, source cursors, inbox dispositions, correlation logs |
| A08 | passed | один character owner; Canvas в браузере; runtime LLM нет |
| A09 | passed | producer-acl.json; auth/scopes; grant-xp endpoint отсутствует |
| A10 | passed | чужой profile 403; opaque operation pending; own evidence checks |
| B01 | passed | все 60 boundaries; cap33276; next_cost null |
| B02 | passed | A/B/C40/80/120, B+ без отдельного тарифа |
| B03 | passed | 68/72/28, Fraction, одно floor |
| B04 | passed | reviewed без note/skipped0; cosmetic write не начисляет XP |
| B05 | passed | 28→56→80, deltas28/28/24 |
| B06 | passed | новый event ID/command retry/redelivery не удваивает |
| B07 | passed | revision3→2 + contiguous main cursor |
| B08 | passed | hash/revision conflict с rollback |
| B09 | passed | реальная компенсация −24 + pure max group |
| B10 | passed | 168h exact; due и obligation обязательны |
| B11 | passed | raw quality≥.8 отдельно; repeat factor.3 |
| B12 | passed | четвёртый repeat не платит |
| B13 | passed | primary gain исключает repeat |
| B14 | passed | permutations/replay + исходные timestamps |
| B15 | passed | reader84+V40; diagnostic route без unread XP |
| B16 | passed | разные verified families + cold independent |
| B17 | passed | новое третье семейство, first E evidence168h |
| B18 | passed | K: E5/R3, weights, C.5; correction prerequisites |
| B19 | passed | 3 M, зарегистрированный состав/дисциплины/disjoint families |
| B20 | passed | единственный volume binding; V использует evidence без повторной оплаты primary |
| B21 | passed | fresh independent C, один fixed sigil ID; no grant XP |
| B22 | passed | pure K compensation + DB ever-owned/recheck |
| B23 | passed | entitlement difference + ever-owned unique key |
| B24 | passed | definitions grants_xp0, auto_grant true / auto_equip false |
| B25 | passed | cap + chronology2000, UI Хроники |
| B26 | passed | IANA/DST source rhythm test + profile stream |
| B27 | passed | closed schema + invalid weights/parts/NaN/Infinity |
| C01 | passed | 59 definitions / 7 starting owned |
| C02 | not_run | legacy записей не найдено; alias map валидируется, actual migration не выполнялась |
| C03 | passed | 9 labelled radios + none, начальные 4 части описаны |
| C04 | passed | DB/API wrong-slot/unowned/unknown422; missing sword equip200 |
| C05 | passed | two threads: 200/409; no lost update |
| C06 | passed | browser preview+refresh; DB no auto-equip |
| C07 | passed | 3 ornament, 59 total, independent slot |
| C08 | passed | owned fixture: duplicate422, atomic swap; unowned422 |
| C09 | passed | 25/58 unbound; отдельный реестр BLOCKED_CONTENT |
| C10 | passed | safe trial DTO без profiles; private/internal404; MCP без solutions |
| D01 | passed | 7 SHA verified, rig measured, Tier1→ARM00 |
| D02 | passed | alpha preparation + white cloth/enamel QA |
| D03 | passed | 11 segments reconstruct exact BASE |
| D04 | passed | 35 cases renderer-report + 3 contact sheets |
| D05 | passed | allowed-region clamp + max-union; tail/head/hand stable |
| D06 | passed | failed paint возвращает complete BASE |
| D07 | passed | one body alpha, separate paint/hide; no AA multiply twice |
| D08 | passed | BASE skin/head; per-part protected regions |
| D09 | passed | collar visual QC + opaque head pixels stable |
| D10 | failed | кандидат SWD03: гарда не принята; production BLOCKED_ART |
| D11 | failed | универсальный grip не принят; production neutral сохранён |
| D12 | passed | missing grip dependency → complete neutral BASE, renderer test |
| D13 | passed | synthetic ornament behind head passed; реальных ORN sources нет (BLOCKED_ART) |
| D14 | passed | stale generation ignored, full frame commit после decode |
| D15 | passed | 3 BG × 240/360/480 + item160 screenshot |
| D16 | passed | ARM05 missing; labelled full-source gallery |
| E01 | passed | White Atlas tokens, system-ui/Georgia deviation; no gradient redesign |
| E02 | passed | 1920/1280/768/390 + CTA in viewport1280×800 |
| E03 | passed | draft/theory return, chapters, 60-term formula no overflow |
| E04 | passed | keyboard.json, CSS zoom200%, 4 contrast pairs, reduced motion; не WCAG certificate |
| E05 | passed | один polite channel, bounded poll; textual controls при missing art |
| E06 | passed | canvas aria label + slot DOM; raw PNG не запрашиваются |
| E07 | passed | ui-metrics.json + renderer timings; scope замеров описан |
| E08 | passed | outage keeps confirmed XP; draft save; flags rollback |
| E09 | passed | main dry-run0 attempts/0 writes; legacy writer отсутствует |
| E10 | not_run | непустой historical backfill/cutover не разрешён и не запускался |
| E11 | passed | 5 DB restore + ledger=summary176; feature flags recovered; no dual writer |
| E12 | passed | Assets/source-lock.json + 165 local package license records + notices; no font hotlinks |

## Арт и следующий вход от владельца

Подробная приёмка и **один конкретный repair request для SWD-03 с локальным хватом**:
[art-qa](art-qa.md). Перегенерация BASE или пяти комплектов не требуется.
Не принятые цели:

ARM-05, SWD-00, SWD-01, SWD-02, SWD-03, SWD-04, SWD-05, SHD-00, SHD-01, SHD-02, SHD-03, SHD-04, SHD-05, CLK-00, CLK-01, CLK-02, CLK-03, CLK-04, CLK-05, REL-01, REL-02, REL-03, REL-04, REL-05, REL-06, REL-07, REL-08, REL-09, ENV-SILK, ENV-ARCHIVE, HALL-LA, HALL-CA, HALL-PR, HALL-DS, HALL-OD, HALL-CONCLAVE, ORN-01, ORN-02, ORN-03.

Точные пути, provenance и SHA ресурсов — `Assets/source-lock.json`;
[THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md). Внешняя лицензия входных PNG
не выдумана, публикация приложения наружу не выполнялась.

## Экраны и закрытые свидетельства

Все пути ниже относительно корня checkout; они реально созданы в `.private/`.

| Что показано | Файл |
|---|---|
| Главная основного профиля 1280×800, настоящие 0 XP | `.private/evidence/crucible-v3/main/today-1280.png` |
| Начальный герой основного профиля | `.private/evidence/crucible-v3/main/character-initial.png` |
| Задача с длинной формулой, увеличение200% | `.private/evidence/crucible-v3/ui/long-formula-200percent.png` |
| Теория и черновик рядом / возврат | `.private/evidence/screenshots/theory-with-draft.png`, `workflow.spec.ts` |
| Закрытый предмет и примерка без записи | `.private/evidence/crucible-v3/ui/locked-preview.png` |
| Mixed outfit из настоящих частей | `.private/evidence/crucible-v3/lab/mixed-01.png` |
| 160px карточка | `.private/evidence/crucible-v3/ui/item-160.png` |
| Мобильная главная/задача/теория | `crucible-v3/ui/today-390.png`, `screenshots/mobile-workspace.png`, `screenshots/mobile-theory.png` внутри evidence |
| 35 сочетаний на трёх фонах | `.private/evidence/crucible-v3/art/contact-*.jpg` |
| Fault/duplicate/correction/rollback | `.private/evidence/crucible-v3/{event-flow,poison,rollback}.json` |

Исходное рабочее дерево и независимые исходные DB snapshots сохранены в
`.private/backups/crucible-v3-g0/` (эти 4 исходных dump не являются общим
согласованным snapshot). Проверенный согласованный пятибазовый backup:
`.private/backups/20261116T001324Z.cruciblebackup`; ключ отдельно в `.secrets/`.
Восстановление выполнено в **новый** `crucible-restore-v3-20261116`, port28084,
с проверкой checksums/табличных counts и replay retained outbox.

Off-device copy, автоматическое расписание backup, HA failover и настоящий
MCP-host остаются **not_run / не настроены**. Старые исторические отчёты других
топологий не объявляются новыми passes этой пятисервисной конфигурации.

После QA синтетический прикладной стенд, стенд restore и disposable PostgreSQL остановлены; volumes и evidence сохранены. Основной `paladin` на :28080 продолжает работать.
