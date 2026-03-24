# 배포 가이드 — AWS EC2 + Docker Compose

## 구성 개요

```
인터넷
  │
  ▼
[EC2 인스턴스]
  ├── frontend (nginx :80)  ← React SPA + API 프록시
  └── backend  (uvicorn :8000, 내부 네트워크만)
```

nginx가 `/api/` 경로를 백엔드로 프록시하고, 나머지는 React SPA에서 처리한다.

---

## 1. EC2 인스턴스 준비

### 권장 스펙
- **AMI**: Amazon Linux 2023 (또는 Ubuntu 22.04 LTS)
- **Instance type**: t3.medium (2 vCPU / 4GB RAM) 이상
- **Storage**: 30GB gp3
- **Security Group**:
  - 인바운드: 22 (SSH), 80 (HTTP), 443 (HTTPS, 선택)
  - 아웃바운드: 전체 허용

### Docker 설치 (Amazon Linux 2023)

```bash
sudo dnf update -y
sudo dnf install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

# Docker Compose 플러그인
sudo dnf install -y docker-compose-plugin
```

---

## 2. 코드 배포

```bash
# 서버에서
git clone https://github.com/Chopper-Tony/sagupalgu.git
cd sagupalgu

# 환경 변수 설정
cp .env.example .env
nano .env   # 실제 키 값 입력
```

### `.env` 필수 항목

```dotenv
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SECRET_ENCRYPTION_KEY=32자이상의랜덤문자열
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
UPSTAGE_API_KEY=up-...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

---

## 3. 서비스 실행

```bash
# 빌드 + 실행 (백그라운드)
docker compose up -d --build

# 로그 확인
docker compose logs -f

# 상태 확인
docker compose ps
```

정상 실행 시:
- `http://<EC2-Public-IP>/` — 프론트엔드
- `http://<EC2-Public-IP>/health` — 백엔드 헬스체크

---

## 4. 업데이트 배포

```bash
git pull origin main
docker compose up -d --build
```

다운타임 최소화가 필요하면 `--no-deps` 플래그로 서비스별 재시작 가능:

```bash
docker compose up -d --build --no-deps backend
docker compose up -d --build --no-deps frontend
```

---

## 5. HTTPS 설정 (선택 — 도메인 보유 시)

Certbot(Let's Encrypt)으로 SSL 인증서 발급:

```bash
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

인증서 자동 갱신:
```bash
sudo crontab -e
# 추가: 0 0 * * * certbot renew --quiet
```

---

## 6. 모니터링

```bash
# 컨테이너 리소스 사용량
docker stats

# 백엔드 로그 실시간
docker compose logs -f backend

# 헬스체크 수동 실행
curl http://localhost/health
```

---

## 7. 트러블슈팅

| 증상 | 확인 사항 |
|---|---|
| 프론트엔드 접속 불가 | `docker compose ps` → frontend 컨테이너 Running 확인 |
| API 호출 실패 (502) | `docker compose logs backend` → 에러 확인 |
| 백엔드가 healthy 되지 않음 | `.env` 키 누락 여부 확인 |
| 게시 실패 (Playwright) | `docker compose exec backend playwright install chromium` |
