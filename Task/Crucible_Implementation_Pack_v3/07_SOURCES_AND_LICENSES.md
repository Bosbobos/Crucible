# 07. Источники, лицензии и технические основания

**Официальные страницы ниже открыты при подготовке редакции16.11.2026.** Ссылки нужны для источника/установки, не означают, что ресурс уже установлен в репозитории. Никакие font binaries и чужие художественные изображения в пакет не вложены. При реальной установке агент фиксирует конкретную версию/hash и применимые notices.

## S1. Onest — основной UI

- Официальный исходный проект: https://github.com/simpals/onest
- Каталог Google Fonts: https://github.com/google/fonts/tree/main/ofl/onest
- Metadata (включая cyrillic/latin): https://raw.githubusercontent.com/google/fonts/main/ofl/onest/METADATA.pb
- Лицензия SIL Open Font License1.1: https://raw.githubusercontent.com/google/fonts/main/ofl/onest/OFL.txt

Основной текст/задачи/UI, нужные начертания400/500/600/700. Обслуживать локально; сохранить фактический OFL/copyright notice установленной версии. Шрифтовые файлы пользователь получает через штатную установку агента из источника, не из этого архива. При невозможности получить — system-ui fallback и отмеченный блокер, не неизвестный font mirror.

## S2. Cormorant Garamond — крупные заголовки

- Проект: https://github.com/CatharsisFonts/Cormorant
- Каталог: https://github.com/google/fonts/tree/main/ofl/cormorantgaramond
- Metadata (cyrillic/latin): https://raw.githubusercontent.com/google/fonts/main/ofl/cormorantgaramond/METADATA.pb
- Лицензия SIL Open Font License1.1: https://raw.githubusercontent.com/google/fonts/main/ofl/cormorantgaramond/OFL.txt

Короткие H1/H2 и имена предметов, не мелкий UI/формулы. Проверить реальные кириллические строки и fallback, не считать наличие красивой латиницы достаточным. Старые Golos Text/Noto Serif из архива не второй обязательный комплект.

## S3. Lucide и собственные placeholders

- Официальный проект: https://lucide.dev/
- Лицензия: https://lucide.dev/license
- Репозиторий: https://github.com/lucide-icons/lucide

Основная лицензия ISC; перечисленные на странице производные Feather icons имеют MIT notice. Сохранять применимые уведомления реально используемой версии; не объявлять всё CC0. Выбирать существующие exports установленной версии, не придумывать названия функций/иконок.

Category placeholders, орденский знак, руны, SVG-инсигнии и CSS-полки допускаются собственные. Game-icons.net/Poly Haven из старого списка **не обязательны** и не были загружены в этот пакет. При их дополнительном использовании агент отдельно проверяет конкретный источник/лицензию и добавляет attribution; не наследовать неизвестные картинки из архива как автоматически разрешённые.

## S4. Контраст текста

W3C, WCAG2.2, Understanding Contrast Minimum: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html

Основание целей4.5:1 для обычного текста и3:1 для крупного с установленными критериями/исключениями. Приложение не объявляется соответствующим WCAG в целом только из-за выбора палитры; нужны проверки реальных состояний.

## S5. Значимые контролы и графика

W3C, Understanding Non-text Contrast: https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html

Контраст значимых частей UI/графики —3:1 с соседним цветом в рамках критерия. Декоративная рамка и функциональная граница поля различаются. Не округлять значение чуть ниже порога до формального pass.

## S6. Уменьшенное движение

MDN, prefers-reduced-motion: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion

Поддержка пользовательского запроса уменьшить несущественную анимацию. Не утверждать, что reduced-motion освобождает от остальных требований доступности.

## S7. Canvas-композиция

MDN, CanvasRenderingContext2D.globalCompositeOperation: https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/globalCompositeOperation

Основание применения source-over/destination-out к разным offscreen слоям. Выбор anatomical masks, pixelwise max-union, grip patches и render plan — **наша прикладная спецификация**, а не обещанная MDN автоматическая генерация одежды.

## S8. Границы сервисов

Microsoft Azure Architecture Center, Use domain analysis to model microservices: https://learn.microsoft.com/en-us/azure/architecture/microservices/model/domain-analysis

Подход к границам по бизнес-возможностям/bounded contexts и связности, не по горизонтальным техническим слоям. Конкретное решение «один character-service сейчас» выведено для Crucible и не приписывается Microsoft как универсальная рекомендация о числе сервисов.

## S9. Доставка сообщений

RabbitMQ, Consumer Acknowledgements and Publisher Confirms: https://www.rabbitmq.com/docs/confirms

Publisher confirm и consumer acknowledgement относятся к разным участкам доставки; это не общая транзакция БД приложения. Outbox/inbox, commit-before-ACK, semantic deduplication и correction ledger обязательны по нашей спецификации. На просмотренной странице описана актуальная ветка документации; агент обязан сопоставить клиент/broker API с **реальной установленной версией**, не обновлять брокер только ради ссылки.

## Собственные исходники и генерации

Семь PNG — материалы, переданные владельцем; происхождение по файлам/hash в `data/source_assets.json`. Дата/модель генерации и пользовательские условия использования не подтверждены самими PNG. Не объявлять их автоматически CC0, не переносить лицензии UI-иконок на персонажа. Для публикации зафиксировать подтверждённый provenance и права использования исходных референсов/output.

D&D/Diablo в обсуждении обозначают характер вдохновения, не разрешение копировать официальные изображения, конкретную экипировку или логотипы. Готовые промпты требуют самостоятельного дизайна. Не использовать имя живого художника как требование имитации.

## Source lock и уведомления при установке

Агент создаёт `assets/source-lock.json` в репозитории: resource ID, page URL, фактический полученный file URL, version/commit, дата, SHA-256, license, author, modifications, local path. В `THIRD_PARTY_NOTICES.md` указывает реально используемые ресурсы. Не встраивает hotlinks вместо локальных ассетов; не скачивает сомнительный mirror при проблеме официального источника.

Эта редакция обновляет справочник источников, но не заменяет проверку условий конкретной установленной версии и фактической сборки проекта.
