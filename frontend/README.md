# Sentinel Frontend

## 개발 서버 실행

1. 의존성 설치
   ```bash
   cd frontend
   npm install
   ```
2. 개발 서버
   ```bash
   npm run dev
   ```
   기본 포트는 `5173`이며, `.env`에 `VITE_API_BASE_URL`을 지정하지 않으면 `http://localhost:8000`으로 백엔드에 연결합니다.

## 주요 폴더

- `src/components`: 레이아웃, 채팅, 컨텍스트 패널 UI 컴포넌트
- `src/hooks`: 문서/채팅 스트림과 같은 데이터 훅
- `src/styles.css`: 간단한 다크 테마 스타일

## 환경 변수

`.env` 혹은 `.env.local`
```
VITE_API_BASE_URL=http://localhost:8000
```
