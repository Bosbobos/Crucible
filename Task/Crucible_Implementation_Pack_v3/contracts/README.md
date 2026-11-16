# Целевые контракты

JSON Schema Draft2020-12 описывает envelope, четыре вида snapshots и atomic loadout command. Это **целевые DTO**, ещё не установленные API. Примеры имеют `synthetic-*` IDs и предназначены только для тестов; они не заполняют campaign-bindings.

Схема проверяет форму; предметная валидация дополнительно проверяет unique part IDs, порядок timestamps, correct_count≤total_count, exact K/M composition/weights, допустимые content mappings, ownership, producer trust и revisions. `format` uuid/date-time проверять включённым format checker, не считать его автоматически обязательным во всех библиотеках.

При реальном внедрении агент генерирует/проверяет DTO в языке проекта и добавляет consumer-driven/integration tests. Синтетический B-пример даёт68XP и **не E**: у второго пункта есть помощь.

`tools/validate_pack.py` проверяет структурную согласованность пакета и примеров, но не является универсальным JSON Schema engine. Полная schema validation выполняется средствами стека агента; при подготовке пакета она отдельно проверена установленным validator, результат в `qa/PACK_VALIDATION.md`.
