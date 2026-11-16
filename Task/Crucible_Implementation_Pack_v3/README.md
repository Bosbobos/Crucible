# Crucible Implementation Pack v3

Начать с [00_START_HERE.md](00_START_HERE.md). Полное поручение агенту: [06_AGENT_EXECUTION.md](06_AGENT_EXECUTION.md). Одиночные промпты: [08_ART_PROMPTS_ALL.md](08_ART_PROMPTS_ALL.md).

Пакет содержит актуализированные MD, точные определения прогрессии, целевые контракты, CSS-токены, входные PNG и проверки согласованности. Репозиторий приложения не модифицирован; готовые paper-doll слои не заявлены.

Проверки из корня пакета:

```bash
python tools/validate_pack.py
python -m unittest discover -s tests -v
python tools/simulate_progression.py
```

Основные программы используют стандартную библиотеку Python; для теста DST нужна IANA timezone database. Дополнительный `python tools/validate_pack.py --full-schema` использует установленный `jsonschema` и проверяет схемы формально. Проверки здесь относятся к спецификации и референсной арифметике; integration/E2E/визуальный QA приложения запускает кодовый агент в реальном репозитории.
