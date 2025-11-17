"""
FastAPI 애플리케이션의 API 계층을 구성하는 패키지입니다.

이 패키지는 다음과 같은 모듈들을 포함합니다:
- `endpoints`: 각 기능별 API 라우터(Router)를 정의합니다.
- `schemas`: Pydantic 모델을 사용하여 API 요청/응답 데이터의 형식을 정의합니다.
- `dependencies`: FastAPI의 의존성 주입(Dependency Injection)을 위한 함수들을 정의합니다.
- `main.py`: FastAPI 앱 인스턴스를 생성하고, 미들웨어와 라우터를 설정하는 메인 진입점입니다.
"""
