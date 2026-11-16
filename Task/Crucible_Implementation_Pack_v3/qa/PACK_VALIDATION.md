# Проверка пакета — 16.11.2026

Это результаты **проверки подготовленного пакета**, не проверка репозитория Crucible и не приёмка графических слоёв.

## Выполнено

| Проверка | Результат | Evidence |
|---|---|---|
| Целостность JSON, ID, references, локальных Markdown-ссылок | passed | `pack_validation.json` |
| Все 60 точных XP-порогов; 59 item/cosmetic IDs; 6 ranks | passed | `pack_validation.json` |
| 25 volumes и 58 trial blueprints, без фиктивных content bindings | passed | `pack_validation.json` |
| 45 художественных целей; 6 выполненных источников; 39 новых/извлекаемых целей | passed | `pack_validation.json` |
| Все 39 художественных одиночных промптов + 1 условный технический; совпадение общего индекса | passed | `pack_validation.json` |
| SHA-256 семи исходных PNG, canvas 1024×1536 | passed | `pack_validation.json`, `data/source_assets.json` |
| Шесть JSON Schema Draft2020-12 и два полного примера с format checking | passed | `pack_validation.json` |
| 28 референсных unit tests арифметики/округления/порогов/времени/корректировок | passed | `unit_tests.txt` |
| Три иллюстративных сценария; baseline29 520XP / level56 | passed | `simulation.json` |
| Отсутствие font binaries в пакете | passed | `pack_validation.json` |

Команды:

```bash
python tools/validate_pack.py --full-schema
python -m unittest discover -s tests -v
python tools/simulate_progression.py
```

Для `--full-schema` использован установленный `jsonschema` с `referencing`; они не включены в архив. Обычный `validate_pack.py` использует стандартную библиотеку и отдельно отмечает formal schema validation как not_run. Unit-тест DST использует IANA timezone database, имеющуюся в среде проверки.

## Намеренно не заявлено выполненным

- Аудит/запуск/изменение реального репозитория: **not_run**, код не предоставлен.
- Production service implementation, migrations, broker fault tests, authorization и E2E: **not_run**, поручены агенту.
- Полный исполняемый evaluator V/E/R/K/M: **не реализован в этом пакете**, здесь definitions/specification.
- Реальные привязки математических задач/томов/holdout: **unbound**, IDs не придуманы.
- Удаление фоновой подложки, segmentation, measured anchors и slot extraction: **not_run**.
- QA 20 бронеслоёв/10 mixed outfits/меча/орнаментов: **not_run**, настоящих derived layers нет.
- Генерация ARM-05 и недостающего арта: **не выполнялась**, приложены одиночные промпты.

Исходные изображения сохранены без изменения; alpha metadata проверена отдельно при подготовке реестра. Сходство поз на референсах не выдано за доказательство pixel registration.
