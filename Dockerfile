FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (Playwright chromium용)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright chromium 설치
RUN playwright install chromium --with-deps

# 소스 복사
COPY app/ ./app/
COPY legacy_spikes/ ./legacy_spikes/
COPY migrations/ ./migrations/

# 세션/스크린샷 디렉터리
RUN mkdir -p sessions screenshots uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
