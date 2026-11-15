#!/bin/bash
set -eu
export PGDATA=/var/lib/postgresql/data
if [ "$(id -u)" = 0 ]; then
  mkdir -p "$PGDATA"
  chown postgres:postgres "$PGDATA"
  chmod 700 "$PGDATA"
  exec gosu postgres bash "$0"
fi
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  export PGPASSWORD="$(cat /run/secrets/replication_password)"
  pg_basebackup -d "host=${PRIMARY_HOST:?} port=5432 user=replicator application_name=crucible_standby" -D "$PGDATA" -R -X stream --checkpoint=fast
fi
cp /etc/crucible-pg-hba.conf "$PGDATA/pg_hba.conf"
exec postgres -D "$PGDATA" -c hot_standby=on
