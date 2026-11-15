#!/bin/bash
set -eu
export RABBITMQ_ERLANG_COOKIE="$(cat /run/secrets/erlang_cookie)"
exec docker-entrypoint.sh rabbitmq-server
