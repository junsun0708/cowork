# ============================================================
# NanoClaw - Global Emission Factor Collector
# Docker Image: cowork-bot-emission-factor-collector
# ============================================================

# --- Stage 1: Builder ---
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Runtime ---
FROM python:3.11-slim

LABEL maintainer="thingspire <salvayh@thingspire.com>"
LABEL description="NanoClaw - Global Emission Factor Collection Agent with Slack Bot"
LABEL version="1.0.0"

# Java (tabula-py 의존성)
RUN apt-get update && \
    apt-get install -y --no-install-recommends default-jre-headless && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Python 패키지 복사
COPY --from=builder /install /usr/local

# 앱 사용자 생성
RUN useradd --system --shell /bin/false --home-dir /app nanoclaw

WORKDIR /app

# 소스 복사
COPY agents/ ./agents/
COPY config/ ./config/
COPY source_registry/ ./source_registry/
COPY parsing_profiles/ ./parsing_profiles/
COPY run.py ./

# 데이터 디렉토리 생성
RUN mkdir -p data logs output data/storage data/alerts && \
    chown -R nanoclaw:nanoclaw /app

# nanoclaw 사용자로 실행
USER nanoclaw

# 헬스체크
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "from agents.token_manager import TokenManager; t=TokenManager(); h=t.health_check(); exit(0 if h['healthy'] else 1)"

# 환경변수 기본값
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 볼륨 (DB, 로그 영속화)
VOLUME ["/app/data", "/app/logs"]

# Slack Bot 실행
CMD ["python", "-m", "agents.slack_bot"]
