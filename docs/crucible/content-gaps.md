# Недостающий контент

Исходный каталог содержит 57 карточек и четыре заметки. Импорт сохранил исходные
семейства как непроверенные; это не доказательство независимых curated families.
25 целевых томов и 58 чертежей пакета — definitions, не опубликованные испытания.
Совпадение кода навыка с номером тома не является подтверждённой привязкой.

Все 25 V/E/R и восемь K/M требуют content-owner campaign publication:
конкретные immutable IDs, reward equivalence, проверенные family IDs, версии рубрик,
четыре раздела/ядро/лаборатория/final-check/diagnostic на том. Сейчас binding unbound,
UI должен показывать `BLOCKED_CONTENT`. Два числовых клона не считаются двумя семействами.
Контрольные варианты не открывать для заполнения этой таблицы.

Обычный primary XP допустим по явно подтверждённой самооценке и metadata принятой
попытки; неизвестные freshness/review obligation не становятся true. Отдельный
чертёж не публикуется как пройденный. Новых «официальных вариантов» не создаётся.

## Реестр привязок

| Том | Название | V / E / R |
|---|---|---|
| LA-01 | Системы и пространства | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| LA-02 | Ортогональность и проекции | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| LA-03 | Спектр и функции от матриц | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| LA-04 | Квадратичные формы | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| LA-05 | SVD и структурные приёмы | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| CA-01 | Пределы и локальные модели | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| CA-02 | Производная, выпуклость и оценки | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| CA-03 | Интегралы и параметры | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| CA-04 | Ряды и сходимость | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| CA-05 | Многомерный анализ | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| PR-01 | Условие и пространство исходов | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| PR-02 | Распределения и ожидание события | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| PR-03 | Ожидание, индикаторы и зависимость | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| PR-04 | Совместные законы и преобразования | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| PR-05 | Предельные оценки и статистика | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| DS-01 | Подсчёт и модели выбора | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| DS-02 | Рекурсии и производящие функции | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| DS-03 | Графы и инварианты | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| DS-04 | Динамическое программирование | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| DS-05 | Алгоритмическое доказательство | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| OD-01 | Первый порядок: основные модели | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| OD-02 | Линейные уравнения и замены | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| OD-03 | Постоянные коэффициенты | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| OD-04 | Неоднородность и резонанс | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |
| OD-05 | Системы и качественное поведение | BLOCKED_CONTENT / BLOCKED_CONTENT / BLOCKED_CONTENT |

Чертежи (все `unbound`, публикация условий отсутствует):

E: E-LA-01, E-LA-02, E-LA-03, E-LA-04, E-LA-05, E-CA-01, E-CA-02, E-CA-03, E-CA-04, E-CA-05, E-PR-01, E-PR-02, E-PR-03, E-PR-04, E-PR-05, E-DS-01, E-DS-02, E-DS-03, E-DS-04, E-DS-05, E-OD-01, E-OD-02, E-OD-03, E-OD-04, E-OD-05.

R: R-LA-01, R-LA-02, R-LA-03, R-LA-04, R-LA-05, R-CA-01, R-CA-02, R-CA-03, R-CA-04, R-CA-05, R-PR-01, R-PR-02, R-PR-03, R-PR-04, R-PR-05, R-DS-01, R-DS-02, R-DS-03, R-DS-04, R-DS-05, R-OD-01, R-OD-02, R-OD-03, R-OD-04, R-OD-05.

K: K-LA, K-CA, K-PR, K-DS, K-OD.

M: M-01, M-02, M-03.

Для M также требуется полный проверенный список семейств тренировочного банка. Публикация отвергается, пока хотя бы одно семейство не проверено, и если контрольные family пересекаются с тренировочными. Для каждого unit фиксируются вид, том и immutable content version; чужой вид или повторная привязка отвергаются.
