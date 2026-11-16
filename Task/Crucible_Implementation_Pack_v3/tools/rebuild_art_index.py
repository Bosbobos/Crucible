"""Rebuild the readable prompt index from individual authoritative prompt files."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def main() -> None:
    index = json.loads((ROOT / "data/prompt_index.json").read_text(encoding="utf-8"))
    header = """# 08. ART_PROMPTS_ALL — одиночные запросы Crucible v3

**16.11.2026. Один запрос → один результат. Батчи отменены.** Этот файл собран из `art_prompts/*.md`; редактировать первичные файлы, затем запускать `python tools/rebuild_art_index.py`.

## Уже выполнено — НЕ генерировать заново

| Статус | ID | Реальный исходник |
|---|---|---|
| [x] Дизайн создан | BASE-00 | references/BASE-00.png (вход Base.png) |
| [x] Дизайн создан | ARM-00 | references/ARM-00.png (вход Tier_1.png) |
| [x] Дизайн создан | ARM-01 | references/ARM-01.png (вход Tier_0.png) |
| [x] Дизайн создан | ARM-02 | references/ARM-02.png |
| [x] Дизайн создан | ARM-03 | references/ARM-03.png |
| [x] Дизайн создан | ARM-04 | references/ARM-04.png |

Это отметки завершённой генерации **источников**, не готовых paper-doll слоёв. Маски/альфа/rig/слоты готовит агент. Старые запросы этих источников остаются только в archive и не исполняются.

**SWD-03:** есть пример на персонаже `references/SWORD-POSE-REF.png`. Сначала извлечение меча и общего хвата агентом; одиночный запрос ниже используется, когда отдельный слой нельзя получить без дорисовки закрытых участков. Не заказывать ещё один целый белый комплект с мечом.

**ARM-05:** гипотеза следующей генерации, не утверждённый финал. **HAND-R-GRIP-01:** условный технический слой, не новый предмет награды.

## Как пользоваться

Открыть один файл/раздел, приложить перечисленные изображения из `references/`, скопировать только текст между `PROMPT_START` и `PROMPT_END`. Все художественные и технические требования уже внутри. Не посылать весь справочник генератору. Новый результат передать агенту с целевым ID; он проверит/подготовит слой и заменит placeholder без изменения XP/ownership.

Рекомендуемая первая очередь: подготовка текущих пяти сетов → SWD-03/хват → ORN-01 → ARM-05. Затем остальные мечи/орнаменты и ENV; щиты/мантии/реликвии/залы позже. Пока изображения создаются, кодовая работа продолжается с честными заглушками.

## Указатель оставшихся запросов

"""
    rows = ["| ID | Название | Очередь | Статус |", "|---|---|---|---|"]
    chunks = []
    for entry in index["prompts"]:
        rows.append(f"| [{entry['asset_id']}]({entry['file']}) | {entry['title']} | {entry['priority']} | {entry['status']} |")
        chunks.append((ROOT / entry["file"]).read_text(encoding="utf-8"))
    output = header + "\n".join(rows) + "\n\n---\n\n" + "\n\n---\n\n".join(chunks)
    (ROOT / "08_ART_PROMPTS_ALL.md").write_text(output, encoding="utf-8")
if __name__ == "__main__":
    main()
