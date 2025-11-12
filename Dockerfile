# 1. 기본 이미지 (Python 3.10)
FROM python:3.11-slim

# 2. 작업 디렉터리 설정
WORKDIR /app

# 3. requirements.txt 먼저 복사 및 설치 (캐싱 활용)
COPY requirements.txt requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-cache-dir -r requirements.txt

# 4. DB 연결 확인을 위한 postgresql-client 설치
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# 5. 프로젝트 코드 전체 복사
COPY . .

# 6. entrypoint 스크립트에 실행 권한 부여 및 ENTRYPOINT 설정
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]

# docker-compose.yml의 command가 ENTRYPOINT의 인자로 전달됩니다.