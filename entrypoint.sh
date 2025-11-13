#!/bin/bash

# 스크립트 실행 중 오류가 발생하면 즉시 중단합니다.
set -e

# docker-compose.yml에서 환경 변수로 주입될 때까지 대기합니다.
# 이 변수들은 PostgreSQL 연결에 사용됩니다.
: "${POSTGRES_HOST?POSTGRES_HOST가 설정되지 않았습니다}"
: "${POSTGRES_PORT?POSTGRES_PORT가 설정되지 않았습니다}"
: "${POSTGRES_USER?POSTGRES_USER가 설정되지 않았습니다}"

echo "Waiting for postgres..."

# pg_isready를 사용하여 데이터베이스가 연결을 수락할 준비가 될 때까지 대기합니다.
# -h: 호스트, -p: 포트, -U: 사용자
while ! pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER"; do
  sleep 2
done

echo "PostgreSQL started"

# Alembic 마이그레이션을 최신 버전으로 업그레이드합니다.
echo "Running DB migrations..."
alembic upgrade head

# 스크립트의 마지막 인자(CMD)를 실행합니다.
# docker-compose.yml의 'command'로 전달된 uvicorn ... 명령이 실행됩니다.
exec "$@"
