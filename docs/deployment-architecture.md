# 사구팔구 배포 아키텍처

배포는 **단일 EC2 인스턴스에 Docker Compose로 4개 컨테이너를 올리는 방식**이다. 프론트엔드·백엔드가 따로 호스팅되지 않고, 동일 서버에서 Caddy가 경로 기반으로 라우팅한다.

## 전체 구조

```
[사용자] → [Caddy :80/:443 (HTTPS 자동)] → ┬─ /api/*, /health*, /uploads/* → backend:8000
                                            └─ 그 외 전부                     → frontend:80
```

### 컨테이너 구성

| 컨테이너 | 이미지 | 역할 | 노출 포트 |
|---|---|---|---|
| `caddy` | `caddy:2-alpine` | HTTPS 종단 + 경로 라우팅 | 80, 443 |
| `backend` | 자체 빌드 (Python 3.11) | FastAPI 오케스트레이션 | 8000 (내부) |
| `worker` | `backend`와 동일 이미지 재사용 | Playwright 게시 전담 | 8001 (내부) |
| `frontend` | 자체 빌드 (nginx:alpine) | React SPA 정적 서빙 | 80 (내부) |

> **핵심**: 프론트·백엔드가 같은 서버 같은 compose stack 안에 있어 단일 t3.small에서 운용 가능하다. 워커를 분리해서 게시 트래픽이 API 응답성을 방해하지 않는다.

---

## 백엔드 (FastAPI) 배포

### Dockerfile — `Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

COPY app/ ./app/
COPY legacy_spikes/ ./legacy_spikes/
COPY migrations/ ./migrations/

RUN mkdir -p sessions screenshots
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**포인트**
- Playwright chromium을 `--with-deps`로 설치 (시스템 라이브러리 자동 포함)
- `legacy_spikes/`를 이미지에 포함 (게시 어댑터에서 재사용)
- `sessions`, `screenshots`, `uploads` 디렉터리는 호스트 볼륨으로 마운트되어 영속

### 2개 서비스로 분리 (M125)

`docker-compose.prod.yml`에서 동일 이미지를 두 번 띄운다:

```yaml
backend:
  environment:
    - RUN_PUBLISH_WORKER=false  # API 전용 — 워커 미시작

worker:
  build: .
  command: uvicorn app.main:app --host 0.0.0.0 --port 8001
  environment:
    - RUN_PUBLISH_WORKER=true
    - PUBLISH_USE_QUEUE=true
    - MAX_CONCURRENT_BROWSERS=1   # t3.small 2GB 기준 안전값
  deploy:
    resources:
      limits:
        memory: 1536M             # Playwright OOM 방지
```

**역할 분리**
- `backend` 컨테이너: REST API + SSE 응답 전담
- `worker` 컨테이너: `publish_jobs` 테이블 폴링 → per-account lock 확보 → Playwright 게시 실행

### 헬스체크 — `docker-compose.yml`

```yaml
backend:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

Caddy와 frontend가 `depends_on: backend: service_healthy`로 헬스체크 통과를 기다린다.

---

## 프론트엔드 (React SPA) 배포

### 멀티스테이지 Dockerfile — `frontend/Dockerfile`

```dockerfile
# Stage 1: 빌드
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: 서빙
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**포인트**
- 빌드 단계에서만 Node.js 사용 → 런타임 이미지는 nginx:alpine만 포함 (이미지 크기 최소화)
- Vite가 생성한 `dist/`만 nginx 문서 루트로 복사

### nginx 역할 — `frontend/nginx.conf`

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # React SPA — 404를 index.html로 fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # /api/ — 프록시 + CORS preflight
    location /api/ {
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'Content-Type, Authorization, X-Admin-Key';
            return 204;
        }
        proxy_pass http://backend:8000;
        proxy_read_timeout 120s;
        client_max_body_size 50M;
    }

    # 업로드 이미지 (익스텐션 다운로드용) — ^~ 로 regex보다 우선
    location ^~ /uploads/ {
        proxy_pass http://backend:8000/uploads/;
    }

    # 정적 자산 1년 캐시
    location ~* \.(?:js|css|woff2?|png|jpg|svg|ico)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    gzip on;
}
```

**참고**: `frontend/nginx.conf`의 `/api` 프록시는 레거시/로컬 개발용이다. 프로덕션에서는 Caddy가 `/api/*`를 backend로 직접 보내기 때문에 nginx의 `/api` 블록을 거치지 않는다. frontend 컨테이너는 `ports: !reset []`로 외부 노출이 제거되고 `expose: 80`만 남아 Caddy만 접근한다.

---

## HTTPS 레이어 (Caddy) — M116

### Caddyfile

```caddy
{$DOMAIN_NAME:localhost} {
    reverse_proxy /api/*     backend:8000
    reverse_proxy /health*   backend:8000
    reverse_proxy /uploads/* backend:8000
    reverse_proxy            frontend:80
}
```

**포인트**
- `DOMAIN_NAME` 환경변수로 도메인 주입 — 미설정 시 `localhost` HTTP fallback
- **Let's Encrypt 인증서 자동 발급/갱신** — 별도 certbot 불필요
- `caddy_data` named volume으로 인증서 영속 (재배포해도 재발급 없음)
- 우선순위: `/api/*`, `/health*`, `/uploads/*`는 backend로, 나머지는 frontend로

### 볼륨

```yaml
caddy:
  volumes:
    - ./Caddyfile:/etc/caddy/Caddyfile:ro
    - caddy_data:/data        # TLS 인증서 영속
    - caddy_config:/config
```

---

## 배포 자동화 (GitHub Actions) — M68, M120

### 파이프라인 — `.github/workflows/ci.yml`

트리거: `main` 브랜치 push

```
1. test          — pytest unit → integration → full + coverage
2. type-sync     — OpenAPI↔TypeScript 동기화 검증
3. frontend-build— npm ci + npm test (vitest) + npm run build
4. docker-build  — backend/frontend 이미지 빌드 검증
5. deploy        — EC2_HOST secret 설정 시만 SSH 접속 후 rolling restart
```

### Rolling Restart 스크립트 (deploy job)

```bash
cd ~/sagupalgu
git pull origin main

# 이미지 빌드
docker compose -f docker-compose.yml -f docker-compose.prod.yml build backend frontend

# 1) backend 먼저 교체 (Caddy가 계속 서빙)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --no-deps -d backend

# 2) health 대기 (최대 30초)
for i in $(seq 1 30); do
  if docker compose exec -T backend curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "Backend healthy after ${i}s"
    break
  fi
  sleep 1
done

# 3) frontend 교체
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --no-deps -d frontend

# 4) Caddy 설정 반영
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --no-deps -d caddy
```

### 알림

성공/실패 모두 Discord 웹훅으로 커밋 메시지와 함께 전송.

---

## 배포 커맨드 요약

```bash
# 최초 세팅 (EC2)
bash scripts/setup_ec2.sh     # Docker 설치, 1GB 스왑 설정

# 프로덕션 기동 (수동)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 롤링 재시작 (CI가 수행하는 것과 동일)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --no-deps -d backend

# 로그 확인
docker compose logs -f backend
docker compose logs -f worker

# 상태 확인
docker compose ps
curl https://<domain>/health/ready | jq
```

---

## 요점 정리

| 레이어 | 기술 | 책임 |
|---|---|---|
| HTTPS/라우팅 | **Caddy** (`caddy:2-alpine`) | TLS 자동화 + 경로 분배 |
| 프론트 | **nginx + Vite 빌드물** | SPA 정적 서빙 (멀티스테이지) |
| API | **uvicorn + FastAPI** | 오케스트레이션 전용 (`RUN_PUBLISH_WORKER=false`) |
| Worker | **동일 이미지 재사용** | Playwright 게시 (`RUN_PUBLISH_WORKER=true`, 메모리 1536M 제한) |
| DB | **Supabase** (외부) | 컨테이너 밖 — PostgreSQL + pgvector |
| 보조 스토리지 | **S3** | 게시 증적 스크린샷만 (fire-and-forget) |

### 핵심 설계 결정

1. **Monorepo + 단일 compose stack**: 프론트·백엔드·워커가 같은 서버에서 돌아서 단일 t3.small로 운용 가능
2. **워커 프로세스 분리**: 게시 부하가 API 응답성을 방해하지 않음 (M125)
3. **Caddy 앞단**: HTTPS 종단과 경로 분배를 Caddy가 모두 담당 → nginx는 SPA 서빙에만 집중
4. **동일 이미지 재사용**: backend와 worker가 같은 Dockerfile로 빌드되어 환경변수만 다름 → 일관성 확보
5. **Rolling restart**: backend → health wait → frontend → caddy 순서로 무중단 배포

---

## 관련 파일 경로

| 목적 | 경로 |
|---|---|
| 백엔드 Dockerfile | `Dockerfile` |
| 프론트엔드 Dockerfile | `frontend/Dockerfile` |
| 프론트엔드 nginx 설정 | `frontend/nginx.conf` |
| 기본 Docker Compose | `docker-compose.yml` |
| 프로덕션 override | `docker-compose.prod.yml` |
| Caddy 설정 | `Caddyfile` |
| CI/CD 파이프라인 | `.github/workflows/ci.yml` |
| EC2 초기 세팅 스크립트 | `scripts/setup_ec2.sh` |
| 배포 상세 가이드 | `docs/deployment.md` |
