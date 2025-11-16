# Repository Guidelines

## Project Structure & Module Organization
핵심 애플리케이션 코드는 `src/`에 있으며, `api/`는 FastAPI 엔드포인트와 라우터, `core/`는 설정·로깅·보안 유틸, `components/`는 RAG 관련 컴포넌트, `worker/`는 Celery 진입점(`celery_app.py`)과 태스크를 담습니다. 데이터베이스 마이그레이션은 `alembic/`과 `alembic.ini`에서 관리하고, 테스트는 동일한 모듈 구조를 `tests/` 아래에 반영합니다. 샘플 문서나 임시 아티팩트는 `data/`에 두되, 배포 전 비우세요. 루트에는 `docker-compose.yml`, `run_indexing.py`, `.env.example` 등이 있으니 새 자격 증명을 추가할 때마다 예제 파일을 복사해 `.env`를 갱신하세요.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` — 깨끗한 가상환경 구성.
- `uvicorn src.api.main:app --reload` — FastAPI 서버를 로컬에서 핫 리로드로 실행.
- `celery -A src.worker.celery_app:celery_app worker -l info` — 비동기 채팅·인덱싱 태스크를 담당하는 Celery 워커 기동.
- `docker-compose up --build api worker db redis` — API, 워커, Postgres(pgvector), Redis를 포함한 전체 스택 부팅.
- `alembic upgrade head` / `alembic revision --autogenerate -m "add documents table"` — 마이그레이션 적용·생성.
- `pytest -q` 또는 `pytest tests/api/test_chat.py -k happy_path` — 전체/부분 테스트 실행.

## Coding Style & Naming Conventions
Python 3.11을 기준으로 모든 공개 함수에 타입 힌트를 추가하고, 구조화된 페이로드는 가급적 Pydantic 모델로 정의합니다. `black`(88자 폭)을 통해 포매팅하고, import는 표준/서드파티/로컬 순으로 정렬합니다. 모듈·함수·Celery 태스크는 `snake_case`, 클래스는 `PascalCase`, 설정·환경 변수는 `SCREAMING_SNAKE_CASE`를 사용하며, 로그 메시지는 간결한 영어로 남깁니다.

## Testing Guidelines
`conftest.py`가 `src/`를 경로에 추가하므로, 새 테스트는 해당 모듈의 미러 위치(예: `src/worker/tasks.py` ↔ `tests/worker/test_tasks.py`)에 배치합니다. 벡터 스토어 어댑터, 설정 로더, 스키마 유효성 등은 빠른 단위 테스트로 검증하고, 서비스 간 상호작용은 `fastapi.testclient.TestClient`나 Celery eager 모드를 활용한 통합 테스트를 추가하세요. 마이그레이션·인덱싱·설정 폴백을 수정했다면 회귀 테스트를 동반하거나 PR 본문에 수동 검증 절차를 명시합니다.

## Commit & Pull Request Guidelines
커밋 제목은 명령형·72자 이내(`Add throttling to chat endpoint`)로 작성하고, 필요 시 본문에 동기·영향·후속 조치를 불릿으로 정리합니다. 이슈는 `Refs #123` 또는 `Fixes #123` 형식으로 연결하세요. PR은 변경 요약, 스키마/환경/스크립트 수정 여부, 사용자 영향 스냅샷(스크린샷·CLI 로그)과 함께 제출하며, `pytest`·`alembic upgrade head` 실행 결과를 명시합니다. 영향 범위별 리뷰어를 태그하고, 무관한 리팩터링과 기능 변경을 한 PR에 혼합하지 마세요.

## Configuration & Security Notes
`src/core/config.py`는 `config.yml`, 환경 변수, `.env`를 통합해 `DATABASE_URL`, `CELERY_BROKER_URL` 등 계산 필드를 제공합니다. 민감 정보는 `.env`나 비밀 관리자에만 보관하고, `config.yml`에는 기본값이나 비민감 설정만 커밋하세요. 로컬 개발 시 Postgres·Redis 포트를 `docker-compose.yml`과 맞추고, 키가 노출되면 즉시 폐기 후 새 키로 교체합니다.
