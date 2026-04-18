# 배포 가이드 — AWS EC2 (서울 리전) + Docker Compose

## 현재 배포 상태 (2026-04-18)

| 항목 | 값 |
|------|-----|
| 리전 | ap-northeast-2 (서울) |
| Elastic IP | 43.201.188.57 (고정) |
| 인스턴스 | t3.medium (2vCPU, 4GB RAM, 20GB EBS) |
| AMI | Amazon Linux 2023 |
| SSH | `ssh -i sagupalgu-seoul-key.pem ec2-user@43.201.188.57` |
| Docker Compose | `docker-compose up --build -d` |

> 이전 us-east-1 인스턴스는 정리 완료. Elastic IP로 재시작해도 IP 변경 없음.

## 아키텍처

```
사용자 → (HTTP :80) → Caddy → ├── /api/*     → backend(:8000)
                              ├── /health*   → backend(:8000)
                              ├── /uploads/* → backend(:8000)
                              └── /          → frontend(:80, nginx)

backend (단일):        FastAPI + LangGraph + 크롤링 (RUN_PUBLISH_WORKER=false)
프론트:                  React 19 + Vite SPA, Supabase Auth 로그인
게시:                   크롬 익스텐션 Content Script (사용자 브라우저)
DB/Auth/Storage:        Supabase (외부)
증적 스크린샷:           S3 보조 (선택)
```

**설계 원칙**: AWS는 컴퓨트(EC2)만 사용. DB/Auth/Storage는 Supabase 유지. 번개장터·중고나라 게시는 크롬 익스텐션이 전담 — 서버 Playwright 없음. IP 기반 운영이라 Caddy `auto_https off` + `:80` 바인딩 (도메인 연결 시 HTTPS 활성화 블록 주석 해제).

---

## 1. EC2 인스턴스 준비

### 권장 사양

| 항목 | 기본 | 발표/알파 주간 |
|------|------|--------------|
| Instance type | t3.medium (2vCPU, 4GB) | — |
| AMI | Amazon Linux 2023 | — |
| Storage | 20GB gp3 | |
| Security Group | SSH(22), HTTP(80), HTTPS(443) | |

> **주의**: 공인 IPv4는 시간당 $0.005 과금됩니다 (무료 아님).
> ALB는 단일 인스턴스에 과합하므로 사용하지 않습니다.

### 초기 설정

```bash
# 자동 설정 스크립트 (Docker + swap + 필수 패키지)
bash scripts/setup_ec2.sh
```

---

## 2. 환경 변수 설정

```bash
cp .env.example .env
nano .env   # 실제 키 값 입력
```

### 필수 항목

```dotenv
# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SECRET_ENCRYPTION_KEY=<Fernet 키>

# LLM
OPENAI_API_KEY=sk-...

# 게시 계정
BUNJANG_USERNAME=<번개장터 계정>
BUNJANG_PASSWORD=<번개장터 비밀번호>
JOONGNA_USERNAME=<중고나라 계정>
JOONGNA_PASSWORD=<중고나라 비밀번호>

# 운영
ADMIN_API_KEY=<운영자 API 키>
DOMAIN_NAME=sagupalgu.example.com
ENVIRONMENT=prod
PUBLISH_USE_QUEUE=false   # 익스텐션 직접 게시 — 서버 큐 미사용
```

---

## 3. 서비스 실행

```bash
# 프로덕션 모드 (Caddy HTTPS + 단일 backend)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 상태 확인
docker compose ps

# 헬스체크
curl https://<도메인>/health
curl https://<도메인>/health/ready
```

---

## 4. 배포 (GitHub Actions 자동 — 기본 경로)

**2026-04-18부터 main push → 자동 롤링 재시작 활성**. 수동 SSH 는 fallback/비상용으로만 사용.

### 필수 GitHub Secrets

Settings → Secrets and variables → Actions 에 등록:

| Secret | 용도 |
|---|---|
| `EC2_HOST` | `43.201.188.57` |
| `EC2_USER` | `ec2-user` |
| `EC2_SSH_KEY` | pem 파일 전체 내용 (BEGIN~END 포함) |
| `VITE_SUPABASE_URL` | Supabase project URL (클라이언트 번들에 인라인) |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon key (클라이언트 번들에 인라인) |
| `SUPABASE_URL`·`SUPABASE_SERVICE_ROLE_KEY`·`SECRET_ENCRYPTION_KEY` | 백엔드 테스트·type-sync 용 |
| `OPENAI_API_KEY`·`GEMINI_API_KEY`·`UPSTAGE_API_KEY`·`DISCORD_WEBHOOK_URL` | 통합 테스트·알림용 |

### 자동 배포 플로우 (`.github/workflows/ci.yml`)

1. test · type-sync · frontend-build · docker-build 전부 green
2. deploy job: appleboy/ssh-action 으로 EC2 SSH
3. 원격 스크립트 실행:
   - `docker compose` (v2) / `docker-compose` (v1 legacy) 런타임 감지
   - `frontend/.env` 를 CI Secret 기반 heredoc 으로 재작성 (fallback: 루트 `.env` 추출)
   - `VISION_PROVIDER=openai` 잔존 시 `gemini` 로 치환 (idempotent)
   - backend 이미지 rebuild + `--force-recreate` 로 교체
   - `/health` 최대 30s 대기
   - frontend `--no-cache` 빌드 + `--force-recreate`
   - Caddy `--force-recreate` (Caddyfile 볼륨 마운트 재로드)
4. Discord 웹훅 배포 완료 알림

### 수동 배포 (fallback)

자동 배포 불가(CI 장애 등) 시에만:
```bash
ssh -i sagupalgu-seoul-key.pem ec2-user@43.201.188.57
cd ~/sagupalgu && git pull origin main
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build backend frontend
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up --no-deps -d --force-recreate backend frontend caddy
```

---

## 5. 배포 전 체크리스트

```bash
# 자동 검증
python scripts/check_prod_readiness.py

# 배포 후 검증
python scripts/smoke_test.py --base-url https://<도메인>
```

필수 체크:
- [ ] GitHub Secrets 8종 등록 (EC2_* + VITE_SUPABASE_* + 백엔드 공통)
- [ ] `ADMIN_API_KEY` 설정됨
- [ ] EC2 `.env` 에 `RUN_PUBLISH_WORKER=false` + `PUBLISH_USE_QUEUE=false`
- [ ] Supabase 대시보드 Site URL / Redirect URLs 에 `http://43.201.188.57` 등록
- [ ] Supabase → Providers → Google 활성 (Client ID/Secret 입력)
- [ ] Google Cloud Console OAuth Redirect URI 에 `https://<ref>.supabase.co/auth/v1/callback`
- [ ] 크롬 익스텐션 `host_permissions` 이 운영 도메인과 일치 (현재 `43.201.188.57`)
- [ ] smoke test 성공

---

## 6. 스케일 한계

| 지표 | 현재 한계 | Scale 기준 |
|------|----------|-----------|
| 동시 게시 | 익스텐션 분산 처리 (사용자 브라우저별 1건) | 서버 측 병목 없음 |
| 동시 활성 사용자 | ~15~25명 | API 응답 > 3초 |
| 메모리 | 4GB (t3.medium) | backend OOM 발생 시 |

Scale 대응: `_connect_tokens` Supabase 이전 후 uvicorn `--workers 2` 증설 → t3.large 업그레이드 순.

---

## 7. 장애 대응

| 상황 | 대응 |
|------|------|
| API 죽음 | `docker compose restart backend` → health 확인 |
| Caddy TLS 실패 | `docker compose logs caddy` → DNS·도메인 확인 |
| Supabase 장애 | 서비스 degraded (fallback 없음) |
| 익스텐션 게시 실패율 증가 | 번개장터·중고나라 DOM 변경 의심 → Content Script 업데이트 후 웹스토어 재배포 |
| OOM | `restart: unless-stopped`로 자동 재시작 |

---

## 8. 로그/모니터링

```bash
# 실시간 로그
docker compose logs -f backend
docker compose logs -f caddy

# 리소스 사용량
docker stats

# 추적 포인트
# - sell_sessions.status (13개 상태 전이)
# - session_transition 로그 (from → to)
# - 익스텐션 게시 결과 콜백 (/api/v1/sessions/{id}/extension-publish-result)
```

중요 지표:
- 세션 완주율: completed / (completed + failed)
- 평균 LLM 처리 시간 (Vision + listing 생성)
- 익스텐션 게시 성공률 (콜백 기반)

---

## 9. 수업 종료 후 운영 전략

| 옵션 | 월 비용 | 비고 |
|------|--------|------|
| t3.micro 다운그레이드 | ~15,000원 | 1GB RAM, Playwright는 로컬/스케줄 실행 분리 |
| Oracle Cloud 무료 | 0원 | ARM 4 OCPU/24GB, 가입 어려움 |
| 서비스 축소 | 0원 | 게시 기능 off, API+프론트만 무료 PaaS |

---

## 10. 비용 참고

| 항목 | 월 비용 |
|------|--------|
| EC2 t3.medium (서울) | ~50,000원 |
| EBS 20GB gp3 | ~2,500원 |
| 공인 IPv4 | ~5,400원 |
| 데이터 전송 | ~0원 (월 100GB 무료) |
| S3 보조 | ~200원 |
| **합계** | **~58,000원** |
