.PHONY: setup up publish dev-setup test integration resilience e2e assessment backup restore doctor firewall-test sql-check
# Restore по умолчанию публикует новый web только на отдельном loopback-порту.
PORT ?= 18082
setup:
	scripts/deploy setup
up:
	scripts/deploy
publish:
	scripts/deploy publish
dev-setup:
	conda run --no-capture-output -n IAD python -m pip install --target .deps -r requirements.lock
test:
	scripts/test unit
integration:
	scripts/test integration
resilience:
	CRUCIBLE_DEMO=1 scripts/test resilience
e2e:
	scripts/test e2e
assessment:
	scripts/assessment up
backup:
	CRUCIBLE_DEMO=1 scripts/operator scripts/backup.py
restore:
	scripts/restore "$(BACKUP)" --project "$(PROJECT)" --port "$(PORT)"
sql-check:
	scripts/operator scripts/check_sql_isolation.py
doctor:
	scripts/doctor
firewall-test:
	CRUCIBLE_DEMO=1 scripts/firewall test
