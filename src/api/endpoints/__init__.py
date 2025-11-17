"""
애플리케이션의 각 기능별 API 엔드포인트(라우터)를 정의하는 모듈들을 포함하는 패키지입니다.

각 파일은 특정 도메인(예: 'auth', 'chat')과 관련된 API 경로들을 그룹화하여
FastAPI의 `APIRouter`로 정의합니다. 이렇게 모듈화된 라우터들은 `api/main.py`에서
메인 FastAPI 앱에 포함(include)됩니다.

이러한 구조는 코드의 관심사를 분리(Separation of Concerns)하여 유지보수성을 높입니다.
"""
