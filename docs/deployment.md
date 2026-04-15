# 배포 가이드 — AWS EC2 (서울 리전) + Docker Compose

## 현재 배포 상태 (2026-04-15)

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
사용자 → (HTTPS) → Caddy(:443)
                      ├── /api/*     → backend(:8000)
                      ├── /health*   → backend(:8000)
                      ├── /uploads/* → backend(:8000)
                      └── /          → frontend(:80)

backend (API 전용):     RUN_PUBLISH_WORKER=false
worker  (게시 전용):     RUN_PUBLISH_WORKER=true + Playwright
DB/Auth/Storage:        Supabase (외부)
증적 스크린샷:           S3 보조 (선택)
```

**설계 원칙**: AWS는 컴퓨트(EC2)만 사용. DB/Auth/Storage는 Supabase 유지.

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
PUBLISH_USE_QUEUE=true
```

---

## 3. 서비스 실행

```bash
# 프로덕션 모드 (Caddy HTTPS + API/Worker 분리)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 상태 확인
docker compose ps

# 헬스체크
curl https://<도메인>/health
curl https://<도메인>/health/ready
```

---

## 4. 배포 (CI/CD 자동 또는 수동)

### 자동 배포 (GitHub Actions)
main branch push 시 자동 실행. `EC2_HOST` GitHub Secret 필요.

### 수동 배포 (Rolling Restart)
```bash
cd ~/sagupalgu && git pull origin main

# 1. 백엔드 먼저
docker compose -f docker-compose.yml -f docker-compose.prod.yml build backend
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --no-deps -d backend

# 2. 헬스체크 대기
for i in $(seq 1 30); do
  curl -sf http://localhost:8000/health && break
  sleep 1
done

# 3. 프론트엔드 + Caddy
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --no-deps -d frontend caddy
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
- [ ] `ADMIN_API_KEY` 설정됨
- [ ] `RUN_PUBLISH_WORKER` backend=false / worker=true
- [ ] `MAX_CONCURRENT_BROWSERS=1` (초기 안전값)
- [ ] docker memory limit 적용 (worker 1536M)
- [ ] smoke test 성공

---

## 6. 스케일 한계

| 지표 | 현재 한계 | Scale 기준 |
|------|----------|-----------|
| 동시 게시 | 1건 (MAX_CONCURRENT_BROWSERS=1) | queue 대기 > 5건 |
| 동시 사용자 | ~5~10명 | API 응답 > 3초 |
| 메모리 | 2GB (t3.small) | worker OOM 발생 시 |

Scale 대응: worker 별도 EC2 분리 또는 t3.medium 업그레이드.

---

## 7. 장애 대응

| 상황 | 대응 |
|------|------|
| API 죽음 | `docker compose restart backend` → health 확인 |
| Worker stuck | `docker compose restart worker` + admin `/release-stuck` |
| Supabase 장애 | 서비스 degraded (fallback 없음) |
| Playwright 실패율 증가 | admin API로 플랫폼 pause |
| OOM | `restart: unless-stopped`로 자동 재시작 |

---

## 8. 로그/모니터링

```bash
# 실시간 로그
docker compose logs -f backend
docker compose logs -f worker

# 리소스 사용량
docker stats

# 추적 포인트
# - publish_jobs.status (pending/running/completed/failed)
# - session_transition 로그 (from → to)
# - publish_job_success duration_ms
```

중요 지표:
- 게시 성공률: completed / (completed + failed)
- 평균 게시 시간: publish_job_success duration_ms
- retry 비율: retry_scheduled / total

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
| EC2 t3.small (서울) | ~25,000원 |
| EBS 20GB gp3 | ~2,500원 |
| 공인 IPv4 | ~5,400원 |
| 데이터 전송 | ~0원 (월 100GB 무료) |
| S3 보조 | ~200원 |
| **합계** | **~34,000원** |
