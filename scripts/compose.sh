# Общая функция не запускает daemon и не требует Python на хосте.
crucible_compose() {
    # Assessment выбирается явно; по умолчанию используется daily.
    if [ "${CRUCIBLE_ASSESSMENT:-0}" = 1 ]; then
        # Имя можно переопределить для независимого синтетического испытания.
        crucible_project=${CRUCIBLE_ASSESSMENT_PROJECT:-${COMPOSE_PROJECT_NAME:-crucible-assessment}}
        # Дополнительный overlay нужен, например, для изолированных тестовых подсетей.
        if [ -n "${CRUCIBLE_ASSESSMENT_OVERLAY:-}" ]; then
            # Все пути и пользовательские аргументы передаются без eval.
            docker compose -f compose.yaml -f compose.assessment.yaml -f "$CRUCIBLE_ASSESSMENT_OVERLAY" -p "$crucible_project" "$@"
        else # Выбираем альтернативную ветку того же условия.
            # Обычный assessment использует базовый файл и инфраструктурное расширение.
            docker compose -f compose.yaml -f compose.assessment.yaml -p "$crucible_project" "$@"
        fi # Завершаем выбор дополнительного overlay.
    else # Выбираем альтернативную ветку того же условия.
        # Daily сохраняет штатные COMPOSE_FILE и COMPOSE_PROJECT_NAME Docker CLI.
        docker compose "$@"
    fi # Завершаем выбор стенда.
} # Функция возвращает код завершения Docker Compose.
