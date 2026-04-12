# 사구팔구 멘토링 준비 세션 대화 기록 (2026-04-10)

> 이 문서는 멘토링 발표 직전에 진행된 Claude Code 세션의 대화 전문이다. 배포 아키텍처 의사결정, 데모 가이드, AWS 서울 리전 이전, Content Script vs Playwright 비교 등을 다룬다.

---

## Q1. 그간 한 일과 앞으로의 할 일 계획 세워보세요.

(플랜 모드로 진입하여 `C:\Users\bonjo\.claude\plans\smooth-finding-wave.md`에 회고 + 로드맵 작성)

**작성한 내용 요약**:
- Part 1 — 그간 한 일 (핵심 축 5가지: Agentic 아키텍처, 배포·운영 기반, 게시 아키텍처 대전환, 프론트엔드+자체 마켓, 품질 장치)
- Part 2 — 앞으로 할 일 (P0: 번개장터 신규 계정 검증, 서울 리전 전환, 데모 리허설 / P1: 발표 자료, 마켓 본 기능 / P2: pgvector, Supabase Storage, 당근마켓, Electron / P3: 리스크 관리)

---

## Q2. 이거 저장해두고. 우리 아키텍쳐 구조도 좀 그려주세요. 멘토가 한 눈에 보고 파악할 수 있게

플랜 파일 상단에 4개 다이어그램 섹션을 추가했습니다:

1. **전체 시스템 조감도** — 사용자 / 클라이언트 / AWS / 외부 / 플랫폼 5개 영역, 색상 구분 (활성=초록, 보류=회색, 외부=파랑)
2. **LangGraph 에이전틱 워크플로우** — 7 에이전트 + 3 Loop(Rewrite/Replan/Clarification), 에이전트 유형별 색상(ReAct/LLM+Fallback/Deterministic)
3. **게시 아키텍처 전환** — Before(계정정지) vs After(Content Script), 실패 지점과 해결 지점 시각화
4. **데이터 흐름 시퀀스 다이어그램** — 세션 생성부터 마켓 노출까지 전 과정

모든 다이어그램은 Mermaid 문법이라 GitHub/VSCode/Notion에서 바로 렌더됩니다.

---

## Q3. 이 플랜파일 경로 알려주세요

플랜 파일 경로는 다음과 같습니다:

`C:\Users\bonjo\.claude\plans\smooth-finding-wave.md`

---

## Q4. 사구팔구 프론트엔드, 백엔드 배포를 각각 어떻게 한 건가요?

## 사구팔구 배포 아키텍처

배포는 **단일 EC2 인스턴스에 Docker Compose로 4개 컨테이너를 올리는 방식**입니다. 프론트엔드·백엔드가 따로 호스팅되지 않고, 동일 서버에서 Caddy가 경로 기반으로 라우팅합니다.

### 전체 구조

```
[사용자] → [Caddy :80/:443 (HTTPS 자동)] → ┬─ /api/*, /health*, /uploads/* → backend:8000
                                            └─ 그 외 전부                     → frontend:80
```

### 백엔드 (FastAPI) 배포

**Dockerfile** (`Dockerfile:1`)
- `python:3.11-slim` 베이스
- `requirements.txt` 설치 + Playwright chromium `--with-deps`
- `app/`, `legacy_spikes/`, `migrations/` 복사
- `uvicorn app.main:app --host 0.0.0.0 --port 8000`

**2개 서비스로 분리** (M125)
- `backend` 컨테이너: API 전용 — `RUN_PUBLISH_WORKER=false`
- `worker` 컨테이너: 동일 이미지 재사용 — `RUN_PUBLISH_WORKER=true`, `MAX_CONCURRENT_BROWSERS=1`, 메모리 1536M 제한 (Playwright OOM 방지)
- 워커가 `publish_jobs` 테이블을 폴링해서 per-account lock으로 게시 처리

**볼륨 마운트**: `./sessions`, `./screenshots`, `./uploads` (호스트 영속)

**헬스체크**: `curl http://localhost:8000/health` (30초 간격)

### 프론트엔드 (React SPA) 배포

**멀티스테이지 Dockerfile** (`frontend/Dockerfile:1`)
- Stage 1 (`node:20-alpine`): `npm ci` → `npm run build` (Vite) → `dist/` 생성
- Stage 2 (`nginx:alpine`): `dist/`를 `/usr/share/nginx/html`로 복사, nginx 80 서빙

**nginx 역할** (`frontend/nginx.conf:1`)
- SPA fallback (`try_files $uri /index.html`) — 해시 라우팅 보정
- `/api/` → `backend:8000` 프록시 (CORS preflight 204 처리, `client_max_body_size 50M`)
- `/uploads/` → backend 프록시 (익스텐션 이미지 다운로드 경로, `^~` prefix로 regex보다 우선)
- 정적자산 1년 캐시 + gzip

### HTTPS 레이어 (Caddy) — M116

**`Caddyfile`** (한 블록 7줄)
```
{$DOMAIN_NAME:localhost} {
    reverse_proxy /api/*     backend:8000
    reverse_proxy /health*   backend:8000
    reverse_proxy /uploads/* backend:8000
    reverse_proxy            frontend:80
}
```
- `DOMAIN_NAME` 환경변수 기반, **Let's Encrypt 인증서 자동 발급/갱신**
- `caddy_data` named volume으로 인증서 영속 (재배포해도 재발급 없음)
- 미설정 시 `localhost` HTTP fallback

> 참고: `frontend/nginx.conf`의 `/api` 프록시는 레거시/로컬 개발용입니다. 프로덕션에서는 Caddy가 `/api/*`를 backend로 직접 보내기 때문에 nginx `/api` 블록을 거치지 않습니다. (frontend 컨테이너는 `ports: !reset []`로 외부 노출 제거, `expose: 80`만 유지 — Caddy만 접근)

### 배포 자동화 (GitHub Actions) — M68, M120

**트리거**: `main` 브랜치 push

**파이프라인** (`.github/workflows/ci.yml:1`)
1. `test` — unit → integration → full coverage (pytest)
2. `type-sync` — `scripts/generate_api_types.py --check` (OpenAPI↔TS 동기화)
3. `frontend-build` — `npm ci` + `npm test` (vitest) + `npm run build`
4. `docker-build` — backend/frontend 이미지 빌드 검증
5. `deploy` — `EC2_HOST` 설정 시만 SSH 접속 후 **Rolling restart**:
   ```
   git pull
   docker compose ... build backend frontend
   docker compose ... up --no-deps -d backend      # 먼저 교체
   wait for /health (최대 30초)
   docker compose ... up --no-deps -d frontend     # 그 다음 교체
   docker compose ... up --no-deps -d caddy        # 설정 변경 반영
   ```
6. 성공/실패 Discord 알림

### 배포 커맨드 요약

```bash
# 최초 세팅 (EC2)
bash scripts/setup_ec2.sh     # Docker, 스왑 1GB

# 프로덕션 기동
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 롤링 재시작 (CI가 수행하는 것과 동일)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --no-deps -d backend
```

### 요점 정리

| 레이어 | 기술 | 역할 |
|---|---|---|
| HTTPS/라우팅 | **Caddy** (`caddy:2-alpine`) | TLS 자동화 + 경로 분배 |
| 프론트 | **nginx + React 빌드물** | SPA 정적 서빙 (멀티스테이지) |
| API | **uvicorn + FastAPI** | 오케스트레이션 전용 |
| Worker | **동일 이미지 재사용** | Playwright 게시 (분리 프로세스, OOM 격리) |
| DB | Supabase (외부) | 컨테이너 밖 |
| S3 | 게시 증적만 (보조) | 컨테이너 밖 |

**핵심 설계 결정**:
- 프론트·백엔드가 같은 서버 같은 compose stack 안에 있음 → 단일 t3.small에서 운용 가능
- 워커를 분리해서 게시 트래픽이 API 응답성을 방해하지 않음
- Caddy 앞단이 HTTPS와 경로 분배를 모두 담당해서 nginx는 SPA 서빙에만 집중

---

## Q5. 이 문서 경로가 어떻게 되나요?

현재 답변은 문서 파일로 저장된 것이 아니라 대화 응답으로만 작성한 것입니다. 배포 구조 설명의 출처가 된 파일들은 다음과 같습니다:

| 파일 | 경로 |
|---|---|
| 백엔드 Dockerfile | `C:\Users\bonjo\Desktop\sagupalgu_integrated_base\Dockerfile` |
| 프론트엔드 Dockerfile | `C:\Users\bonjo\Desktop\sagupalgu_integrated_base\frontend\Dockerfile` |
| 프론트엔드 nginx 설정 | `C:\Users\bonjo\Desktop\sagupalgu_integrated_base\frontend\nginx.conf` |
| 기본 Docker Compose | `C:\Users\bonjo\Desktop\sagupalgu_integrated_base\docker-compose.yml` |
| 프로덕션 override | `C:\Users\bonjo\Desktop\sagupalgu_integrated_base\docker-compose.prod.yml` |
| Caddy 설정 | `C:\Users\bonjo\Desktop\sagupalgu_integrated_base\Caddyfile` |
| CI/CD 파이프라인 | `C:\Users\bonjo\Desktop\sagupalgu_integrated_base\.github\workflows\ci.yml` |
| EC2 초기 세팅 스크립트 | `C:\Users\bonjo\Desktop\sagupalgu_integrated_base\scripts\setup_ec2.sh` |
| 배포 가이드 문서 | `C:\Users\bonjo\Desktop\sagupalgu_integrated_base\docs\deployment.md` |

이 답변 내용을 별도 문서로 저장하길 원하시면 말씀해주세요.

---

## Q6. 플랜모드 해제했습니다. 이거 문서화하고 경로 알려주세요.

(`docs/deployment-architecture.md`로 저장)

---

## Q7. 제가 인스턴스 시작했거든요. 오늘 멘토링 때 시연 방법 스텝바이스텝으로 알려주세요. 참고로 퍼블릭 IPv4 주소 44.222.120.125 이겁니다.

(익스텐션 IP 갱신 후 데모 가이드 작성)

## 사구팔구 멘토링 시연 — 스텝바이스텝 가이드

**EC2 IP**: `44.222.120.125`
**서비스 URL**: `http://44.222.120.125`

---

### Phase 0 — 발표 30분 전 사전 준비

#### 0-1. EC2 SSH 접속 + 서비스 기동
```bash
# 로컬 PowerShell/Bash에서
ssh -i <키페어.pem> ubuntu@44.222.120.125

# EC2 안에서
cd ~/sagupalgu
git pull origin main          # 최신 코드 (익스텐션 IP 변경 포함)

# 컨테이너 상태 확인
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# 정지 상태면 기동
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 헬스 체크 (1~2분 대기 후)
curl http://localhost:8000/health
curl http://localhost:8000/health/ready | jq
```

**기대 결과**: `caddy`, `backend`, `worker`, `frontend` 4개 컨테이너 모두 `Up (healthy)`

#### 0-2. 외부에서 접속 확인
브라우저에서 `http://44.222.120.125` 접속 → 사구팔구 랜딩 페이지 정상 렌더링 확인.

> ⚠️ 보안그룹에서 80/443 포트가 열려 있어야 함. AWS 콘솔 → EC2 → 보안그룹 → 인바운드 규칙 확인.

#### 0-3. 익스텐션 재로드 (IP 갱신 반영)
1. Chrome에서 `chrome://extensions/` 접속
2. 우측 상단 "개발자 모드" 켜짐 확인
3. **사구팔구 플랫폼 연동** 카드의 **새로고침 버튼** 클릭 (방금 갱신한 IP 반영)
4. 익스텐션 아이콘 클릭 → "서버 URL (고급)" 입력란이 `http://44.222.120.125`로 표시되는지 확인

#### 0-4. 플랫폼 로그인 (쿠키 수집)
1. **별도 탭에서** `https://m.bunjang.co.kr` 로그인 (수동)
2. **별도 탭에서** `https://web.joongna.com` 로그인 (수동)
3. 사구팔구 웹앱(`http://44.222.120.125`)에서 우하단 **사이드바 → 플랫폼 연동** 섹션 확인
   - "Connect Token 발급" 클릭 → 토큰 복사
4. 익스텐션 팝업 열기
   - 번개장터/중고나라 각각 connect token 붙여넣기 → "연결" 버튼
   - "연결 완료" 메시지 확인

#### 0-5. 데모 상품 이미지 미리 준비
- 가장 안정적으로 성공하는 카테고리: **스마트폰 / 태블릿 / 노트북** (Vision AI 인식률 높음)
- 사진 2~3장, 깔끔한 배경, 1MB~5MB
- 데스크톱에 폴더로 정리 (드래그&드롭용)

---

### Phase 1 — 발표 시작 (오프닝 + 아키텍처 설명)

#### 1-1. 프로젝트 소개 (1분)
> "중고거래 자동 게시 플랫폼입니다. 이미지만 올리면 AI가 상품 분석 → 시세 산정 → 판매글 작성 → 자동 게시까지 처리합니다. LangGraph 기반 7 에이전트 / 10 툴 / 3 Agentic Loop 구조입니다."

#### 1-2. 아키텍처 다이어그램 보여주기 (2분)
- `C:\Users\bonjo\.claude\plans\smooth-finding-wave.md` 열기
- **[1] 전체 시스템 조감도** → "프론트/백/익스텐션이 어떻게 연결되는지"
- **[2] LangGraph 워크플로우** → "7 에이전트가 어떻게 협력하는지"
- **[3] Before→After** → "왜 서버 게시에서 익스텐션으로 전환했는지" (계정 정지 스토리 — 핵심 어필 포인트)

---

### Phase 2 — 라이브 데모 (8~10분)

#### 2-1. 웹앱 접속
브라우저: `http://44.222.120.125`

#### 2-2. 새 세션 시작
1. **랜딩 페이지 → "새 세션 시작"** 클릭
2. 사이드바에 새 세션 카드 생성됨 확인

#### 2-3. 이미지 업로드
1. 채팅 영역 **이미지 업로드 카드** 등장
2. **준비한 사진 2~3장 드래그&드롭** (또는 클릭 후 선택)
3. 업로드 진행률 표시 → 자동 업로드 완료

#### 2-4. AI 상품 식별 (자동 진행)
- 자동으로 Vision AI 호출 → 상품 후보 카드 등장
- **멘트**: "Vision AI(gpt-4.1-mini)가 사진을 분석해서 상품 후보를 3개까지 제시합니다. confidence가 낮으면 사용자에게 다시 물어봅니다."
- 적절한 후보 클릭 → "이 상품으로 확정"

#### 2-5. 추가 정보 입력 (Pre-listing Clarification)
- 상품 상태 / 사용기간 / 구성품 / 거래방법 4개 항목 질문 카드 등장
- **멘트**: "정보가 부족하면 LangGraph가 사용자 입력을 기다립니다. 이게 3개 Agentic Loop 중 Clarification Loop입니다."
- 간단히 입력 → "다음"

#### 2-6. 시세 분석 + 판매글 자동 생성 (자동 진행)
- 진행 상태 카드: "시세 분석 중 → 판매글 생성 중 → AI 비평 중..."
- **멘트**: "Agent 2(시세)가 ReAct로 번개장터·중고나라를 크롤링하고, RAG로 가격을 산정합니다. Agent 3(카피)가 판매글을 쓰고, Agent 6(Critic)이 70점 미만이면 재작성 루프를 돕니다."
- 약 30초~1분 후 **DraftCard** 등장
  - 제목, 설명, 가격, 태그
  - **AI 품질 평가 섹션** (Critic score, 피드백) — 멘토에게 어필 포인트
  - **에이전트 의사결정 시각화** (도구 호출 이력, 실행 전략, 의사결정 근거)

#### 2-7. 게시 준비
1. DraftCard에서 **플랫폼 선택**: 번개장터 + 중고나라
2. **"게시 준비"** 버튼 클릭
3. **PublishApprovalCard** 등장 → 최종 확인

#### 2-8. 자동 게시 (익스텐션 Content Script)
1. **"자동 게시"** 버튼 클릭
2. **멘트 (이게 핵심!)**:
   > "여기서부터가 우리 시스템의 차별점입니다. 서버에서 Playwright로 게시하면 미국 IP라서 계정이 정지됩니다. 그래서 크롬 익스텐션의 Content Script가 사용자 브라우저에서 직접 폼을 채웁니다. CDP Runtime.evaluate + React fiber onChange로 이미지 업로드까지 해결했어요."
3. 새 탭이 열리고 **번개장터 등록 페이지**가 자동으로 채워지는 모습 보여주기
4. 이어서 **중고나라 등록 페이지**도 자동 채움
5. 게시 완료 후 **PublishResultCard**에 두 플랫폼 게시글 URL 표시

#### 2-9. 자체 마켓 (M137, M143)
1. 사이드바 또는 URL: `http://44.222.120.125/#/market`
2. **마켓 페이지**: 방금 게시한 상품 + 기존 상품 카드 그리드
3. 상품 카드 클릭 → **상세 페이지**
   - 이미지 갤러리
   - **플랫폼 게시 링크 바로가기** (번개장터/중고나라로 직접 이동)
   - **검색 + 가격 필터** 시연
   - **구매 문의** 폼 작성 → Discord 웹훅 알림 도착 보여주기 (Discord 미리 띄워두기)

---

### Phase 3 — 백엔드 동작 시연 (선택, 1~2분)

EC2 SSH 터미널을 화면에 띄워두고:

```bash
# 워커 로그 실시간 (게시 처리 과정)
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f worker --tail 50

# 백엔드 로그
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend --tail 50
```

**멘트**: "JSON 구조화 로깅으로 request_id, session_id, 상태 전이, tool_calls가 전부 추적됩니다."

---

### Phase 4 — Q&A 대응 준비

#### 멘토가 물어볼 만한 질문 + 답변 포인트

| 질문 | 답변 |
|---|---|
| "왜 LangGraph인가? FastAPI만으로도 되지 않나?" | 7 에이전트 / 3 Loop를 코드로 직접 짜면 상태 머신이 폭발한다. LangGraph가 노드/엣지/체크포인트를 관리해서 비평→재작성, 계획→실행→재계획 루프가 깔끔하게 표현된다. |
| "Vision AI 비용은?" | gpt-4.1-mini 기준 이미지 1장당 약 $0.001. 게시 1건당 $0.005~0.01 수준. |
| "익스텐션 없이는 안 되는가?" | 서울 리전 EC2로 전환하면 서버 Playwright 복원 가능. 하지만 익스텐션은 사용자 IP/쿠키/핑거프린트 그대로 쓰기 때문에 탐지가 거의 불가능. 이중화가 베스트. |
| "테스트는?" | 723개 (unit 380 + integration 180 + E2E + FE 21). CI에서 매 PR마다 자동 실행. |
| "당근마켓은?" | Android 에뮬레이터 필요해서 보류. 발표 후 우선순위 재조정. |
| "법적 리스크는?" | 교육/연구 목적. 자체 마켓 본격화 시 통신판매업 신고 검토. |

#### 발표용 핵심 어필 포인트 3가지
1. **계정 정지 → Content Script 전환** 스토리 (실패에서 배운 것)
2. **CDP + React fiber** 이미지 업로드 난제 해결 (5번 시도 끝에)
3. **7 에이전트 + 3 Agentic Loop** Goal-driven 행동 변화 (같은 상품도 fast_sell/balanced/profit_max에 따라 가격·톤·비평 기준이 달라짐)

---

### Phase 5 — 트러블슈팅 (혹시 모를 상황)

| 증상 | 원인 | 즉시 대응 |
|---|---|---|
| 사이트 접속 안 됨 | 컨테이너 다운 / 보안그룹 미개방 | `docker compose ... ps` 확인, 80/443 인바운드 확인 |
| Vision 분석 실패 | OPENAI_API_KEY 만료 / 쿼터 | `.env` 확인, `docker compose logs backend \| grep -i error` |
| 이미지 업로드 후 무한 로딩 | uploads 볼륨 권한 | `docker compose exec backend ls -la /app/uploads` |
| 익스텐션이 서버 호출 실패 | IP 갱신 미반영 | `chrome://extensions/`에서 익스텐션 새로고침 |
| 익스텐션 게시 시 "쿠키 없음" | 플랫폼 로그인 만료 | 별도 탭에서 재로그인 → connect token 재발급 |
| 번개장터 자동 게시 멈춤 | DOM 변경 | "수동 첨부" fallback 안내, 폼은 자동 채워졌으니 "등록" 버튼만 누르면 됨 |
| 워커 OOM | 메모리 초과 | `MAX_CONCURRENT_BROWSERS=1` 확인, 워커 재시작 `docker compose restart worker` |

#### 비상 백업 시나리오
- 라이브 데모가 망가지면 **자체 마켓 페이지 (`/#/market`)**만 보여주기 → 이미 등록된 상품으로 검색/필터/구매문의 시연
- 그것도 안 되면 **로컬에서 미리 녹화한 영상** 재생 (사전에 한 번 녹화 권장)

---

## 변경된 파일 (이번 작업)

| 파일 | 변경 내용 |
|---|---|
| `sagupalgu-extension/background.js:9` | DEFAULT_SERVER_URL → `http://44.222.120.125` |
| `sagupalgu-extension/popup.js:5` | DEFAULT_SERVER_URL → `http://44.222.120.125` |
| `sagupalgu-extension/popup.html:105` | input value → `http://44.222.120.125` |

> 이 변경은 **로컬 익스텐션에 즉시 반영**되니 `chrome://extensions/`에서 새로고침만 누르면 됩니다. EC2 재배포는 필요 없습니다.

---

## Q8. 배포 왜 이렇게 했냐고 물어보면 뭐라고 대답하나요. 배포 이렇게 한 이유를 논리적으로 납득 가능하게 설명해주세요.

## 배포 설계 의사결정 — 멘토 질문 대비 답변 가이드

### 핵심 전제: 제약 조건부터 명시

답변할 때 **먼저 제약 조건을 깔고 시작**하면 모든 결정이 자연스럽게 정당화됩니다.

> "저희 프로젝트의 제약 조건은 세 가지였습니다. (1) 1인 개발자 운영 — DevOps 인력 없음, (2) 학생 신분 — AWS 크레딧 45만원 한정 예산, (3) 발표/시연 안정성 — 무중단 + 재현 가능성. 이 세 제약 안에서 '복잡도와 안정성의 균형점'을 찾는 게 목표였습니다."

이 한 문장이 깔리면 "왜 k8s 안 썼냐", "왜 멀티 AZ 안 했냐" 같은 질문에 자동으로 방어가 됩니다.

---

### 결정 1: 단일 EC2 + Docker Compose (vs ECS/EKS/k8s)

**왜 이걸 선택했나**
- **운영 인력 1명** — k8s/ECS는 학습 곡선 + 디버깅 비용이 1인 운영에 비현실적
- **트래픽 규모** — 발표/시연 + 베타 사용자 수십명 수준. 단일 t3.small로 충분히 커버
- **재현 가능성** — `docker compose up -d --build` 한 줄이면 어디서든 동일 환경 (로컬 = 스테이징 = 프로덕션 일치)
- **비용** — t3.small 1대 ≈ 월 $15. ECS Fargate는 작업당 시간 과금, 컨테이너 4개 상시 가동 시 $40~60. 크레딧 45만원으로 6개월+ 운영 보장

**왜 안 한 것**
- **k8s/EKS**: 컨트롤 플레인만 월 $73 (EKS 기준). 1명이서 운영할 만큼 가치 없음
- **ECS Fargate**: 비용 + 컨테이너 간 통신 복잡도. 단일 호스트에서 `service:port`로 끝나는 걸 ECS는 service discovery 설정 필요
- **Lambda + API Gateway**: Playwright 같은 무거운 런타임 부적합 (콜드스타트 + 250MB 패키지 한계)

**한계 인정**
- 단일 호스트라 **단일 장애점(SPOF)** 존재. 다음 단계는 ALB + 멀티 AZ.
- 트래픽이 일정 수준 넘으면 ECS로 전환할 예정.

> **멘토가 "확장성은?" 묻는다면**: "현재 단계에서 확장성을 미리 사는 건 over-engineering입니다. 단일 호스트 한계가 보이면 그때 ECS로 전환하는 게 합리적이라고 봤습니다. 컨테이너화는 이미 되어 있으니 마이그레이션 비용이 낮습니다."

---

### 결정 2: Caddy 리버스 프록시 (vs nginx, ALB)

**왜 Caddy인가**
- **TLS 자동화** — Let's Encrypt 인증서 자동 발급/갱신. nginx는 certbot + 크론 + 갱신 검증 따로 해야 함
- **설정 7줄** — Caddyfile이 nginx.conf 대비 압도적으로 간결. 프로덕션 설정 미스 가능성 최소화
- **운영 부담** — 인증서 만료로 서비스 다운되는 사고를 0%로 만들고 싶었음

**왜 안 한 것**
- **nginx + certbot**: 갱신 실패 시 알림 + 수동 개입 부담. 1인 운영에 부적합
- **ALB**: 월 $20 + 데이터 처리 비용. 단일 호스트에 ALB 붙이는 건 과투자
- **Cloudflare 앞단**: 도메인 NS 변경 + 무료 플랜 한계. 익스텐션이 직접 IP/도메인 호출하는 구조라 CDN 효과 적음

**한계 인정**
- Caddy 자체가 SPOF. 다중 인스턴스 시 Caddy를 사이드카로 쓰거나 ALB로 교체 필요.

---

### 결정 3: 프론트엔드 + 백엔드 동일 compose stack (vs CloudFront + S3)

**왜 같이 띄웠나**
- **단일 도메인 = CORS 문제 0** — 익스텐션이 cross-origin 호출 시 preflight 처리 복잡도 폭발
- **운영 단순성** — 배포 1번에 둘 다 갱신. 버전 불일치 가능성 제거
- **비용** — CloudFront + S3는 무료티어 풍부하지만, 환경 1개 추가 = 디버깅 표면 1개 추가
- **롤링 리스타트 가능** — 같은 호스트에 있어야 backend healthcheck 후 frontend 교체하는 순서 보장 가능

**왜 안 한 것**
- **CloudFront + S3**: CORS 설정 + 캐시 무효화 + 빌드 산출물 업로드 파이프라인 필요. **얻는 것**(전 세계 캐싱)이 **잃는 것**(복잡도) 대비 부족
- **Vercel/Netlify**: 백엔드 분리 호스팅 강제 → 다시 CORS 문제. 게다가 한국 사용자 대상이면 CDN 효과 미미
- **별도 EC2**: 비용 2배, 통신은 인터넷 경유 → 레이턴시 + 보안 그룹 + 요금

**한계 인정**
- 정적 자산 캐싱이 CDN보다 약함. nginx가 1년 immutable 캐시로 어느 정도 보완.
- 글로벌 사용자 확대 시 CloudFront 전면 전환 필요.

> **멘토가 "프론트는 왜 따로 안 뺐냐?" 묻는다면**: "분리 자체가 목적이 되면 안 된다고 봤습니다. 분리해서 얻는 이득(CDN, 독립 배포)보다, 분리해서 생기는 비용(CORS, 버전 불일치, 디버깅 표면 증가)이 현재 단계에서 더 큽니다."

---

### 결정 4: Worker 분리 (동일 이미지 재사용)

**왜 분리했나**
- **장애 격리** — Playwright가 OOM이나 무한 대기에 빠져도 API 응답성에 영향 없음
- **메모리 격리** — 워커만 1536M 메모리 제한 + `MAX_CONCURRENT_BROWSERS=1`로 OOM 방어. API는 영향 안 받음
- **수평 확장 준비** — 큐(`publish_jobs`) + per-account lock 구조라 워커만 여러 대로 늘릴 수 있음
- **graceful shutdown** — `lifespan` 전환 + active task drain으로 배포 중 게시 작업 안 끊김

**왜 동일 이미지인가**
- **일관성** — 코드 변경 시 한 번만 빌드. 환경 차이로 인한 "워커에서만 나는 버그" 가능성 제거
- **`RUN_PUBLISH_WORKER` 환경변수만 다름** — 부팅 시 워커 폴링 루프 시작 여부만 결정

**왜 안 한 것**
- **Celery + Redis**: 인프라 1개 더 추가. Postgres에 큐 만드는 게 충분 (PostgreSQL의 `SELECT FOR UPDATE SKIP LOCKED` 패턴)
- **별도 워커 이미지**: 빌드 2배 + 일관성 손해
- **API 안에 워커 스레드**: 메모리 격리 안 됨, OOM 시 API까지 죽음 (실제로 M125 이전에 겪었음)

> **멘토가 "왜 Celery 안 썼냐?" 묻는다면**: "외부 의존성을 추가하는 건 운영 부담입니다. Postgres는 이미 쓰고 있고, `publish_jobs` 테이블 + advisory lock으로 큐 + 워커 패턴이 충분히 구현됩니다. Redis 추가는 필요해질 때 하면 됩니다."

---

### 결정 5: Supabase (vs self-hosted PostgreSQL, RDS)

**왜 Supabase인가**
- **Auth + Storage + Postgres + pgvector + RLS** — 4가지 인프라가 한 서비스에 통합. 각각 직접 운영하면 4배 부담
- **무료티어** — 500MB DB + 1GB Storage + 50K MAU. 학생 프로젝트 규모에 충분
- **백업 자동화** — Point-in-time recovery 무료
- **RLS** — Postgres의 Row Level Security를 콘솔에서 정책 작성. 보안 경계가 DB 레벨에서 강제됨

**왜 안 한 것**
- **RDS**: t3.micro 기준 월 $15 + 스토리지 + 백업. 이미 EC2 비용 있는데 DB만 별도 호스팅하는 건 학생 예산에 부담
- **EC2 안에 Postgres 직접**: 백업/모니터링/장애 복구 전부 직접. 1인 운영 비현실적
- **DynamoDB**: pgvector 못 씀. RAG 못 함

**한계 인정**
- Supabase 의존도 높음. 서비스 중단 시 전체 다운.
- 무료티어 한계 도달 시 유료 전환($25/월) 필요.

---

### 결정 6: S3는 "보조" 스토리지 (vs 메인 스토리지)

**왜 S3를 보조로만 썼나**
- **메인은 Supabase Storage** — 이미지 업로드 경로는 단일화. S3는 **게시 증적 스크린샷 아카이빙**에만 사용
- **fire-and-forget** — 게시 직후 스크린샷 1장만 비동기 업로드. 실패해도 게시 흐름에 영향 없음
- **이중화 회피** — 두 스토리지에 같은 데이터를 저장하면 정합성 문제 발생

**왜 굳이 S3를 쓰나**
- **장기 보관 비용** — Supabase Storage 무료티어는 1GB. S3는 5GB 무료 + GB당 $0.023. 게시 이력 누적 시 S3가 압도적으로 저렴
- **운영 증적** — 분쟁/디버깅 시 게시 시점 화면이 필요. 비용 부담 없이 보관

---

### 결정 7: GitHub Actions Rolling Restart (vs Blue-Green, Canary)

**왜 Rolling Restart인가**
- **단일 호스트 + 컨테이너화** 환경에서 가장 단순한 무중단 패턴
- **순서 보장**: backend → health wait (최대 30초) → frontend → caddy. Caddy가 healthcheck로 backend 준비 대기
- **롤백 단순** — 실패 시 `git revert` + 재배포. 30초 안에 복구

**왜 안 한 것**
- **Blue-Green**: 단일 호스트에서는 의미 없음 (인스턴스 2배 비용)
- **Canary**: 트래픽 수 명 단위에서는 측정 자체가 불가능 (통계적 유의성 없음)
- **수동 배포**: 휴먼 에러 + 재현 불가

---

### 종합: "이 배포 설계의 일관된 철학"

발표용 한 마디로 압축하면:

> **"지금 단계에서 필요한 만큼만 복잡하게, 그 이상은 미루기."**

각 결정의 공통 패턴:
1. **외부 의존성 최소화** — Redis/Celery/k8s 같은 추가 인프라는 정말 필요할 때만
2. **운영 부담 최소화** — Caddy의 자동 TLS, Supabase 통합, GitHub Actions 자동화
3. **장애 격리는 확실히** — Worker 분리, 메모리 제한, graceful shutdown
4. **확장 경로는 열어둠** — 컨테이너화 / 큐 구조 / 환경변수 분리로 마이그레이션 비용 낮춤

---

### 멘토가 추가로 던질 만한 질문 + 답변

| 질문 | 답변 |
|---|---|
| "왜 Cloudflare 안 썼냐?" | DNS 변경 + 한국 사용자 대상이라 CDN 이득 적음. 익스텐션이 직접 호출하는 구조라 캐싱 효과가 미미함. |
| "Redis 캐시 없냐?" | 현재 트래픽에서 캐시 필요 지점 없음. Supabase Postgres 자체로 충분. 핫스팟 생기면 그때 도입. |
| "모니터링은?" | JSON 구조화 로깅 + Discord 알림 + /health/ready 3단계. 발표 후 Grafana Cloud 무료티어 도입 예정. |
| "DB 마이그레이션 관리는?" | `migrations/` 디렉터리에 SQL 파일 버전 관리. Alembic은 단일 개발자 환경에 과한 복잡도라 수동 SQL로 운영. |
| "보안은?" | JWT 인증 + 전 엔드포인트 소유권 검증 + DB 레벨 RLS + Rate Limit + 환경변수 암호화 (`SECRET_ENCRYPTION_KEY`). 전형적인 OWASP Top 10 대응. |
| "장애 났을 때 어떻게 알 수 있냐?" | Discord 웹훅으로 배포/게시 실패 알림. 발표 후 헬스체크 다운 알림 추가 예정. |
| "과한 거 아니냐?" | "복잡도는 수익에 비례해야 한다"는 원칙을 지켰습니다. 단일 호스트 + Compose는 학생 프로젝트 규모에서 최소 합리 수준이라고 봅니다. 이 이상 단순화하면 무중단 배포·장애 격리가 깨집니다. |

---

## Q9. 도커가 왜 4개나 필요해? 각각의 역할이 뭐야?

## Docker 컨테이너 4개 — 각각의 역할과 분리 이유

### 4개 컨테이너 한눈에

| # | 컨테이너 | 이미지 | 역할 한 줄 |
|---|---|---|---|
| 1 | **caddy** | `caddy:2-alpine` | HTTPS 종단 + 경로 라우팅 (현관문) |
| 2 | **frontend** | 자체 빌드 (nginx + React) | SPA 정적 파일 서빙 |
| 3 | **backend** | 자체 빌드 (FastAPI) | API 응답 + 오케스트레이션 |
| 4 | **worker** | backend와 동일 이미지 재사용 | Playwright 게시 처리 (분리 프로세스) |

---

### 1. caddy — 현관문 (HTTPS + 라우팅)

**역할**
- 외부에서 들어오는 80/443 포트 트래픽을 받음
- Let's Encrypt 인증서 자동 발급/갱신 (HTTPS)
- URL 경로를 보고 어디로 보낼지 결정:
  - `/api/*` → backend로
  - `/health*` → backend로
  - `/uploads/*` → backend로
  - 그 외 모두 → frontend로

**왜 따로 빼야 하나**
- HTTPS 처리는 **frontend나 backend의 책임이 아님**. 두 곳 모두에 TLS 인증서를 박으면 인증서 갱신을 두 번 해야 함
- 라우팅 로직을 한 곳에 모아야 디버깅이 쉬움 ("어디로 가는지" 확인할 곳이 1개)
- Caddy가 자동 갱신을 해주기 때문에 인증서 만료 사고가 0%

**이걸 안 빼면?**
- 옵션 A: backend가 직접 HTTPS 처리 → uvicorn에 TLS 설정 + certbot 따로 운영. 운영 부담 폭발
- 옵션 B: nginx 안에 합치기 → frontend 컨테이너가 무거워지고, 인증서 갱신 시 frontend 재시작 필요

---

### 2. frontend — SPA 정적 파일 서빙

**역할**
- React를 Vite로 빌드한 산출물(`dist/`)을 nginx로 서빙
- HTML, JS, CSS, 이미지 같은 **정적 파일**만 응답
- SPA fallback (`try_files $uri /index.html`) — 해시 라우팅(`#/market`) 보정
- 정적자산 1년 immutable 캐시 + gzip 압축

**왜 따로 빼야 하나**
- **언어/런타임이 완전히 다름** — frontend는 nginx(C 기반), backend는 Python. 한 컨테이너에 두 런타임을 넣으면 이미지 크기 폭발 + 빌드 시간 2배
- **빌드 사이클이 다름** — frontend는 `npm run build`, backend는 `pip install`. 별도 빌드 캐시 활용 가능
- **재시작 영향 없음** — 백엔드 코드만 바꿨을 때 frontend는 재시작 안 해도 됨 (롤링 리스타트 효율)
- **정적 파일 서빙은 nginx가 압도적으로 빠름** — Python uvicorn으로 정적 파일 서빙하면 비효율

**이걸 안 빼면?**
- 옵션 A: backend가 정적 파일도 서빙 → FastAPI `StaticFiles` 마운트. 가능하지만 nginx보다 10배 느림 + 캐시 헤더 직접 관리
- 옵션 B: S3 + CloudFront로 분리 → CORS 문제 + 별도 인프라 추가 (이미 다른 답변에서 설명한 이유로 거절)

---

### 3. backend — API + 오케스트레이션

**역할**
- FastAPI로 REST API 응답 (`uvicorn` 실행)
- 사용자 요청 받아서 처리:
  - 세션 생성/조회/업데이트
  - 이미지 업로드 받기
  - LangGraph 워크플로우 실행 (Vision AI → 가격 → 카피 → 비평)
  - SSE 스트리밍으로 실시간 상태 전송
  - DB(Supabase) 읽고 쓰기
- **게시는 직접 안 함** — `publish_jobs` 테이블에 작업만 등록하고 끝

**왜 worker와 분리하나**
- 핵심: **게시(Playwright)는 무겁고 위험함**
  - Chromium 브라우저 1개 = 메모리 500MB~1GB
  - 게시 1건당 30초~2분 걸림
  - DOM 변경/네트워크 이슈로 무한 대기 가능
  - OOM(메모리 초과) 가능성
- 만약 backend 안에서 게시를 처리하면:
  - 게시 중인 동안 **API 응답이 느려짐** (이벤트 루프 블로킹)
  - 게시 OOM 발생 시 **API까지 같이 죽음**
  - 게시 작업이 쌓이면 **헬스체크 실패** → Caddy가 트래픽을 못 보냄
  - 배포 시 게시 작업이 끊김

---

### 4. worker — Playwright 게시 처리 (분리 프로세스)

**역할**
- backend와 **완전히 동일한 이미지 사용** (코드, 의존성 모두 동일)
- 환경변수 `RUN_PUBLISH_WORKER=true`로 부팅 시 폴링 루프 시작
- `publish_jobs` 테이블을 폴링 → pending 작업 발견 → per-account lock 확보 → Playwright 실행
- 게시 결과를 DB에 기록 → backend가 SSE로 사용자에게 전달

**왜 동일 이미지인가**
- **코드 일관성** — 같은 도메인 로직을 두 컨테이너가 공유 (Service, Repository, Schema 등)
- **빌드 1번** — 두 이미지를 따로 만들면 빌드 시간 2배 + 버전 불일치 위험
- **환경변수만 다름** — `RUN_PUBLISH_WORKER` 플래그로 동일 이미지가 두 가지 모드로 동작

**왜 분리해야 하나 (장애 격리)**
- **메모리 격리** — worker만 1536M 제한 (`docker-compose.prod.yml:57`). OOM 발생해도 backend는 안 죽음
- **CPU 격리** — Playwright가 CPU 100% 잡아도 backend의 API 응답성 영향 없음
- **재시작 격리** — worker만 재시작해도 backend는 계속 동작. 게시 실패가 사용자 화면에 영향 없음
- **수평 확장 가능** — worker만 여러 대로 늘릴 수 있음 (큐 구조라서). backend는 1대로 충분

**실제로 겪은 사고 (M125 이전)**
- 워커를 backend에 합쳐뒀을 때, Playwright OOM 발생 → 백엔드 컨테이너 전체 죽음 → 사용자 화면이 흰색
- 이 사고로 워커 분리 결정

---

### 시각화: 트래픽 흐름

```
사용자 브라우저
    │ HTTPS
    ▼
┌─────────────────┐
│   1. caddy      │  ← 80/443 포트, TLS 종단
│  (현관문/라우터) │
└────┬────────────┘
     │
     ├─── /api/* ────────────────► ┌──────────────┐
     │                              │ 3. backend   │
     ├─── /health* ────────────────►│  (FastAPI)   │
     │                              └──────┬───────┘
     ├─── /uploads/* ──────────────►       │
     │                                     │ publish_jobs 테이블에 INSERT
     │                                     ▼
     │                              ┌──────────────┐
     │                              │ Supabase DB  │
     │                              └──────┬───────┘
     │                                     │
     │                                     │ 폴링 (SELECT pending)
     │                                     ▼
     │                              ┌──────────────┐
     │                              │ 4. worker    │
     │                              │ (Playwright) │
     │                              └──────────────┘
     │
     └─── 그 외 ──────────────────► ┌──────────────┐
                                    │ 2. frontend  │
                                    │   (nginx)    │
                                    └──────────────┘
```

---

### 멘토 질문 대비: "꼭 4개여야 해? 줄일 수 없나?"

**최소화 가능한 합치기 시나리오와 거절 이유**

| 합치기 시도 | 결과 | 거절 이유 |
|---|---|---|
| caddy + frontend 합치기 | nginx에 TLS + 정적 서빙 | TLS 자동화 잃음. certbot 별도 운영 부담 |
| frontend + backend 합치기 | FastAPI에 StaticFiles 마운트 | 정적 서빙 비효율 + 백엔드 재시작 시 프론트도 같이 다운 |
| backend + worker 합치기 | FastAPI 안에 BackgroundTasks | OOM 시 API 같이 죽음. **이미 한 번 사고 났음** |
| 전부 1개 컨테이너 | nginx + python + chromium 한 이미지 | 이미지 크기 GB 단위, 디버깅 지옥, 관심사 분리 0 |

**역으로 더 늘려야 할 케이스도 있나?**
- 트래픽 규모 커지면 worker를 여러 개로 (`docker compose up --scale worker=3`)
- DB가 외부 Supabase가 아니라면 postgres 컨테이너 추가
- 캐시 도입 시 redis 컨테이너 추가

**정리**
> "4개는 최소 합리 수준입니다. 각 컨테이너가 다음 책임을 가집니다 — caddy는 보안과 라우팅, frontend는 정적 서빙, backend는 API와 오케스트레이션, worker는 위험한 작업의 격리. 하나라도 합치면 단일 장애점이 늘어나거나 운영 부담이 폭발합니다."

---

### 한 줄로 외울 답변

> "4개를 책임 단위로 나눈 거예요. **caddy = 현관문(HTTPS), frontend = 정적 파일, backend = API 두뇌, worker = 위험한 게시 작업 격리.** 핵심은 worker 분리입니다. Playwright OOM이 API를 죽이는 사고를 겪고 나서 분리했어요."

---

## Q10. 프론트랑 캐디가 분리돼 있나요? 왜 그렇게 했나요?

좋은 질문입니다. 솔직하게 답할게요.

## 네, 분리되어 있습니다 — 그리고 이건 약간 redundant한 부분이 있습니다

### 현재 구조

```
[사용자]
    │
    ▼
┌─────────────────┐
│  caddy (외부)    │ ← 80/443, TLS 종단, 경로 라우팅
└────┬────────────┘
     │ /api/* → backend
     │ 그 외 → frontend
     ▼
┌─────────────────┐
│  frontend       │ ← nginx:alpine + React dist
│  (nginx)        │   SPA fallback, gzip, 캐시
└─────────────────┘
```

**즉, 웹서버가 두 개 있습니다 — Caddy와 nginx.** 이론적으로 Caddy가 React dist를 직접 서빙해도 되는데 왜 nginx를 한 번 더 거치는가?

---

### 솔직한 배경: 시간순으로 추가된 결과

1. **먼저 만들어진 것**: `frontend/Dockerfile` (M20)
   - 표준 React + nginx 멀티스테이지 빌드 패턴
   - Stage 1: `node:20-alpine`에서 `npm run build`
   - Stage 2: `nginx:alpine`에 `dist/` 복사 + `nginx.conf` 적용
   - 이때는 HTTPS가 없었음 (개발/초기 배포)

2. **나중에 추가된 것**: `Caddyfile` + `docker-compose.prod.yml` (M116)
   - HTTPS 자동화 + 도메인 연결이 필요해짐
   - **기존 frontend 컨테이너를 건드리지 않고** 그 앞에 Caddy를 놓음
   - 결과: Caddy → nginx 두 단계

**정직하게**: Caddy가 dist를 직접 서빙하도록 합치면 컨테이너 1개를 줄일 수 있습니다. 현재 구조는 "기존 패턴 유지 + 앞단 추가"의 자연스러운 진화 결과입니다.

---

### 그래도 분리를 유지한 이유 (사후 정당화 + 실제 이점)

#### 1. 빌드 산출물의 소유권 문제
- React 빌드(`npm run build`)는 Node.js 런타임이 필요
- Caddy 이미지(`caddy:2-alpine`)에는 Node.js가 없음
- Caddy가 dist를 직접 서빙하려면:
  - **옵션 A**: Caddy 이미지에 Node.js 추가 → 이미지 크기 폭발 + Caddy 공식 이미지 안 씀
  - **옵션 B**: 멀티스테이지 Dockerfile로 Caddy 이미지에 dist 복사 → Caddyfile + dist 빌드 컨텍스트가 한 Dockerfile에 섞임 (관심사 혼재)
  - **옵션 C**: frontend 컨테이너를 빌드 전용으로만 쓰고 dist를 볼륨으로 공유 → 빌드 타이밍 동기화 문제

→ **현재 구조**: frontend 컨테이너가 빌드 + 서빙을 함께 책임. Caddy는 순수 라우터 역할만.

#### 2. 책임 분리 (관심사의 분리)
- **Caddy**: 외부 트래픽, TLS, 도메인 라우팅 — "보안 + 네트워크"
- **frontend nginx**: SPA fallback, 정적 자산 캐싱, gzip — "정적 서빙"
- **backend**: 비즈니스 로직 — "애플리케이션"

각 컨테이너가 한 가지 책임만 가짐. 디버깅 시 "어디 문제인지" 명확.

#### 3. nginx의 검증된 정적 서빙 기능 활용
`frontend/nginx.conf`에 이미 잘 작성된 설정이 있음:
- `try_files $uri /index.html` — SPA 라우팅
- `expires 1y; immutable` — 빌드 해시 자산 캐싱
- `gzip on` + `gzip_types`
- `^~ /uploads/` regex 우선 처리

→ Caddy로 옮기려면 이걸 Caddyfile 문법으로 다시 써야 함. 검증 비용 발생.

#### 4. 로컬 개발 환경과의 일관성
- 로컬에서는 `docker-compose.yml`만 띄워서 frontend + backend로 개발
- Caddy는 `docker-compose.prod.yml`에서만 추가
- frontend가 독립적으로 80 포트로 동작해야 로컬 개발이 단순함

→ Caddy에 합치면 **로컬 개발 환경**에서도 Caddy를 띄워야 함. HTTPS 인증서 문제 + 개발 단순성 손해.

---

### 멘토가 "그러면 합쳐라"고 하면?

**정직한 답변**:
> "맞습니다. Caddy의 `file_server` 디렉티브로 정적 파일을 직접 서빙하면 컨테이너 1개를 줄일 수 있습니다. 다만 현재 구조의 이점은:
> 1. 멀티스테이지 빌드와 정적 서빙이 한 Dockerfile에 캡슐화되어 있고
> 2. 로컬 개발 환경에서 Caddy 없이도 frontend가 독립 동작하며
> 3. nginx.conf의 SPA fallback과 캐싱 설정이 이미 검증되어 있다는 점입니다.
>
> 합치는 리팩토링은 가능하지만, 얻는 이득(컨테이너 -1)이 잃는 비용(로컬 환경 변경 + Caddyfile 재작성 + 검증)보다 작다고 판단해서 미뤘습니다. 트래픽이 더 커지거나 메모리 압박이 생기면 합치는 게 합리적입니다."

---

### 합치는 리팩토링 시 모습 (참고)

```caddyfile
{$DOMAIN_NAME:localhost} {
    handle /api/* {
        reverse_proxy backend:8000
    }
    handle /health* {
        reverse_proxy backend:8000
    }
    handle /uploads/* {
        reverse_proxy backend:8000
    }
    handle {
        root * /srv
        try_files {path} /index.html
        file_server
        encode gzip
    }
}
```

이렇게 하면 frontend 컨테이너 제거 + Caddy 컨테이너에 dist 볼륨 마운트(또는 멀티스테이지 빌드)로 통합 가능. **트레이드오프**: 로컬 개발 환경 변경 + 빌드 파이프라인 재구성 필요.

---

### 한 줄 요약

> **분리되어 있습니다.** 시간순으로 frontend(nginx)가 먼저 만들어지고 그 앞에 Caddy(HTTPS)가 나중에 추가된 결과입니다. 합치는 게 가능하지만 (1) 빌드 산출물 소유권, (2) 로컬 개발 단순성, (3) 검증된 nginx 설정 재사용 측면에서 분리 유지가 현재 단계에서는 합리적입니다. 다만 정직하게 말하면, 트래픽이 커지거나 메모리 압박이 오면 합치는 게 맞습니다.

---

## Q11. 정확한 이유를 한줄로 설명해주세요. 하나로 합쳐도 된다는 것이지요?

**네, 합쳐도 됩니다.**

**한 줄 이유**: React 빌드(`npm run build`) 결과물인 `dist/`를 서빙할 책임자가 필요한데, 표준 React+nginx 멀티스테이지 빌드 패턴을 그대로 쓰다 보니 nginx 컨테이너가 생긴 거고, 나중에 HTTPS 자동화를 위해 그 앞에 Caddy를 덧붙여서 두 개가 된 것 — Caddy 하나로 `file_server` + `reverse_proxy`를 다 처리하면 컨테이너 1개로 합칠 수 있습니다.

---

## Q12. t3.small로 사용자 얼마나 감당 가능한지 말해줘요

## t3.small 수용량 분석

### 스펙 복기
- **CPU**: 2 vCPU (burstable, baseline 0.4 vCPU)
- **메모리**: 2 GB RAM + 1 GB 스왑 (`setup_ec2.sh`에서 설정)
- **네트워크**: 최대 5 Gbps (burst)
- **비용**: 약 월 $15

---

### 메모리 예산 (가장 빡빡한 자원)

| 컴포넌트 | 사용량 |
|---|---|
| OS + Docker daemon | ~250 MB |
| Caddy | ~30 MB |
| Frontend (nginx) | ~20 MB |
| Backend (FastAPI + LangGraph + 의존성) | ~400~500 MB |
| Worker (Playwright + Chromium 1개) | **최대 1,536 MB (제한)** |
| **합계** | **약 2.2~2.3 GB** |

> 2GB RAM을 살짝 초과하기 때문에 **1GB 스왑이 필수**. 그래서 `setup_ec2.sh`에 스왑 설정이 들어가 있고 `MAX_CONCURRENT_BROWSERS=1`로 강제.

---

### 사용자 수용량 (시나리오별)

#### 시나리오 A: 마켓 페이지 조회만 (정적 트래픽)
- `/market` 페이지, 상품 카드 그리드, Supabase 단순 SELECT
- **동시 접속 100~200명** 안정적
- **DAU 1,000~2,000명** 가능
- 병목 없음 (nginx가 정적 서빙, DB는 외부 Supabase가 처리)

#### 시나리오 B: 일반 사용자 (세션 생성 + 조회 + 마켓 조회)
- 이미지 업로드 X, AI 파이프라인 X
- **동시 활성 30~50명**
- **DAU 200~500명**
- 병목: backend 응답시간 (Python GIL)

#### 시나리오 C: AI 파이프라인 사용 (Vision + LLM + 시세)
- 이미지 업로드 → 분석 → 판매글 생성 (게시 제외)
- **동시 활성 5~10명** 안정
- **DAU 50~100명** 권장
- 병목: **LLM API 응답 대기 시간**이 대부분이라 서버 부하는 의외로 적음 (I/O 대기). 대신 burst credit 소진 주의

#### 시나리오 D: 게시까지 풀 코스 (Playwright)
- **동시 게시 작업 1개** (`MAX_CONCURRENT_BROWSERS=1` 강제)
- 게시 1건당 30초~2분
- **시간당 게시 처리량 30~60건**
- **DAU 30~50명** 안정 (1인당 평균 게시 1~2회 가정)
- 병목: **메모리 + Playwright 직렬 처리**

> 단, 현재 게시는 **익스텐션 Content Script가 사용자 브라우저에서** 처리하므로 worker는 거의 안 씀. **실제로는 시나리오 D보다 시나리오 C가 더 현실적인 병목**입니다.

---

### 종합 결론

| 사용자 유형 | 수용량 |
|---|---|
| **마켓 조회만** | DAU 1,000~2,000명 / 동시 100~200명 |
| **AI 파이프라인 사용** | DAU 50~100명 / 동시 5~10명 |
| **익스텐션 게시까지** | DAU 30~50명 / 동시 활성 5명 |
| **서버 게시(Playwright) 강제 시** | DAU 20~30명 / 동시 게시 1개 |

**한 줄 요약**: **t3.small은 베타 사용자 50~100명, 동시 활성 5~10명 규모의 데모/MVP 단계에 적합**합니다. 그 이상은 메모리 부족으로 worker OOM 또는 burst credit 고갈로 응답 지연이 발생합니다.

---

### 가장 먼저 터지는 병목 (예측)

1. **메모리** — 동시 게시 2개 시도 시 OOM (그래서 `MAX_CONCURRENT_BROWSERS=1`)
2. **CPU burst credit** — AI 파이프라인이 동시에 3~5건 돌면 baseline 0.4 vCPU 초과 → 30분 내 credit 고갈 → throttling
3. **Supabase 무료티어** — DB 500MB / Storage 1GB 한계 (서버 자원 아닌 외부)
4. **OpenAI API rate limit** — Tier 1 기준 분당 RPM 제한 (서버 자원 아님)

---

### 멘토가 "이걸로 충분하냐" 묻는다면

> "데모/MVP 단계에는 충분합니다. 발표/시연 + 베타 사용자 수십 명은 t3.small로 커버되고, 월 $15입니다. 동시 활성 10명 + DAU 100명까지가 안전 구간입니다. 그 이상이 되면 t3.medium(4GB)으로 수직 확장하거나, 워커만 별도 인스턴스로 분리해서 메모리 격리를 강화할 계획입니다. 트래픽이 보이기 전에 인프라를 키우는 건 over-provisioning이라고 봤습니다."

---

### 확장 경로

| 단계 | 변경 | 비용 | 수용량 |
|---|---|---|---|
| **현재** | t3.small 1대 | $15/월 | DAU 50~100 |
| **1차 확장** | t3.medium (4GB) | $30/월 | DAU 200~300 + `MAX_CONCURRENT_BROWSERS=2` |
| **2차 확장** | API 1대 + Worker 1대 분리 (둘 다 t3.small) | $30/월 | DAU 300~500 |
| **3차 확장** | ALB + API 2대 + Worker N대 | $80~150/월 | DAU 1,000+ |

컨테이너화 + 큐 구조 덕분에 **각 단계 마이그레이션 비용이 매우 낮음**.

---

## Q13. 콘텐츠 스크립트 방식이랑 플레이라이트 장단점 비교해주세요

## Content Script vs Playwright 비교

사구팔구는 두 방식을 다 구현해봤고, 현재 **Content Script 방식을 메인**으로 쓰고 있습니다. 각각의 트레이드오프를 정확히 이해하는 게 핵심입니다.

---

### 한눈에 보기

| 항목 | Playwright (서버) | Content Script (익스텐션) |
|---|---|---|
| **실행 위치** | 서버(EC2) | 사용자 브라우저 |
| **IP 주소** | 서버 IP (예: AWS 미국) | 사용자 IP (한국) |
| **쿠키/세션** | storage_state 파일로 주입 | 사용자가 이미 로그인된 상태 그대로 |
| **핑거프린트** | headless Chrome (탐지 가능) | 실제 사용자 브라우저 (탐지 불가) |
| **자동화 탐지** | **높음** (대부분 차단됨) | **거의 0** |
| **이미지 업로드** | 쉬움 (`page.setInputFiles()`) | **어려움** (CDP + React fiber 트릭 필요) |
| **동시 처리** | 서버 리소스 한계 (메모리 1.5GB/브라우저) | 사용자별 자체 처리 (이론상 무한) |
| **사용자 개입** | 없음 (완전 자동) | 익스텐션 설치 + 로그인 필요 |
| **DOM 변경 대응** | 서버 코드 수정 → 재배포 | 익스텐션 코드 수정 → 사용자 재설치/업데이트 |
| **디버깅** | 서버 로그 + 스크린샷 | 브라우저 콘솔 (사용자 환경) |
| **운영 비용** | 서버 메모리 1.5GB+ 점유 | 거의 0 |
| **법적/약관 리스크** | **높음** (서버에서 봇 운영) | **낮음** (사용자 본인이 게시) |

---

### Playwright (서버 자동화)

#### 장점

1. **사용자 마찰 0**
   - 사용자가 익스텐션 설치, 로그인, 권한 부여 같은 단계 없이 그냥 "게시" 버튼만 누르면 끝
   - 비개발자 친화적

2. **표준 API + 풍부한 생태계**
   - `page.click()`, `page.fill()`, `page.setInputFiles()` 등 직관적 API
   - 셀렉터 디버깅 도구, 비디오 녹화, trace viewer 등 디버깅 인프라 풍부
   - **이미지 업로드가 한 줄** (`page.setInputFiles('input[type=file]', 'photo.jpg')`)

3. **완전한 자동화**
   - 사용자가 컴퓨터를 끄고 자도 게시 진행
   - 백그라운드 큐 처리 가능 (`publish_jobs` 테이블)
   - 시간 예약 게시도 가능

4. **중앙화된 관리**
   - 코드 한 번 수정 → 재배포 → 모든 사용자에게 즉시 반영
   - 로그/모니터링/알림이 서버 한 곳에 집중

5. **재현 가능성**
   - 같은 입력 → 같은 결과 보장
   - 테스트 환경 구축 용이

#### 단점

1. **자동화 탐지에 매우 취약** ⚠️ **치명적**
   - headless Chrome의 `navigator.webdriver = true`
   - 마우스 움직임 패턴, 타이핑 속도가 부자연스러움
   - canvas fingerprint, WebGL fingerprint가 봇 패턴
   - **실제 사구팔구 사례**: 번개장터 계정 영구정지

2. **IP 차단**
   - AWS, GCP, Azure 같은 클라우드 IP 대역은 플랫폼이 봇 방지로 차단
   - **실제 사례**: 중고나라 CloudFront 403 (AWS 미국 IP 자체 차단)
   - 한국 IP가 아니면 "지역 불일치 → 계정 탈취 의심" 패턴

3. **무거운 리소스 점유**
   - Chromium 1개 = 메모리 500MB~1GB
   - t3.small(2GB)에서 동시 1개가 한계 (`MAX_CONCURRENT_BROWSERS=1`)
   - OOM 사고 발생 가능 (M125 이전 backend와 합쳐뒀을 때 실제 사고)

4. **세션 관리 복잡**
   - 쿠키를 `storage_state.json` 파일로 저장 → 만료 체크 → 갱신 → 동기화
   - 사용자 여러 명의 세션을 구분 저장 (`sessions/{user_id}/`)
   - 만료 시 사용자에게 다시 로그인 요청

5. **법적/약관 리스크**
   - 대부분 플랫폼 약관: "자동화된 수단으로 접근 금지"
   - 서버에서 봇 돌리는 건 명확한 위반
   - 법적 분쟁 시 방어 어려움

6. **DOM 변경에 매우 취약**
   - 플랫폼이 셀렉터 한 글자만 바꿔도 게시 실패
   - 서버 코드 수정 → 재배포 필요 (수십 분~수 시간)

---

### Content Script (크롬 익스텐션)

#### 장점

1. **자동화 탐지 거의 0** ⭐ **핵심 가치**
   - 사용자의 실제 브라우저에서 실행 → `navigator.webdriver = false`
   - 사용자의 실제 쿠키, IP, 핑거프린트 그대로 사용
   - 플랫폼 입장에서 "정상 사용자가 폼을 빠르게 채운 것"과 구분 불가
   - **결과**: 사구팔구가 번개장터 계정 정지 → Content Script 전환 후 0건 정지

2. **서버 자원 거의 0**
   - 서버는 게시 데이터(JSON)만 익스텐션에 전달하면 끝
   - Playwright Chromium 메모리 1.5GB가 통째로 사라짐
   - **t3.small 1대로 사용자 수십 배 더 수용 가능**

3. **사용자 IP/세션 그대로 사용**
   - 한국 사용자 → 한국 IP → 지역 불일치 0
   - 사용자가 이미 로그인된 상태 → 별도 쿠키 관리 불필요
   - 2단계 인증, 디바이스 등록 같은 보안 정책에 영향 없음

4. **법적 방어 가능**
   - "사용자 본인이 자신의 브라우저에서 폼을 채운 것" — 단순 입력 도우미
   - 약관 위반 주장이 어려움 (워드프로세서로 텍스트 작성하는 것과 본질적으로 같음)

5. **수평 확장 무한**
   - 사용자가 늘어도 서버 부담 0
   - 게시 부하가 사용자 수만큼 자연 분산

6. **빠른 시연 가능**
   - 새 탭이 열리고 폼이 자동으로 채워지는 모습이 **시각적으로 화려함**
   - 발표/데모 효과 극대화

#### 단점

1. **이미지 업로드가 매우 어려움** ⚠️ **개발 난이도 핵심**
   - 브라우저 보안: JavaScript로 `input[type=file]`에 프로그래밍 파일 주입 **금지**
   - 일반 방법(`new DataTransfer()`, `input.files = ...`)으로는 React onChange가 안 발동
   - **해결책**: CDP(Chrome DevTools Protocol) `Runtime.evaluate` + base64 → File 객체 + React fiber `__reactProps$` 직접 호출
   - **사구팔구 실제 경험**: 5번 시도 끝에 해결

2. **사용자 마찰 매우 큼**
   - 익스텐션 설치 (Chrome Web Store 심사 또는 개발자 모드)
   - 권한 부여 (`cookies`, `activeTab`, `scripting`, `debugger`)
   - 플랫폼 사이트에 미리 로그인 필요
   - 비개발자에게 진입 장벽

3. **사용자가 깨어 있어야 함**
   - 사용자 컴퓨터가 켜져 있어야만 게시 가능
   - 백그라운드/예약 게시 불가
   - 큐잉 전략에 한계

4. **디버깅 지옥**
   - 서버에서는 사용자 환경 로그를 못 봄
   - 사용자가 "게시 안 돼요" 말하면 → 사용자 화면 공유 받아서 콘솔 직접 봐야 함
   - 사용자별 환경 차이 (Chrome 버전, 다른 익스텐션 충돌, 광고 차단기)

5. **DOM 변경 대응이 번거로움**
   - 플랫폼이 DOM 바꾸면 → 익스텐션 코드 수정 → 사용자에게 업데이트 요청
   - Chrome Web Store 심사 시 며칠 걸릴 수 있음
   - 개발자 모드 설치는 사용자가 수동 갱신 필요

6. **권한이 강력해서 신뢰 이슈**
   - `debugger` 권한 = "이 익스텐션은 모든 페이지에 접근 가능"
   - Chrome이 사용자에게 경고 표시
   - 사용자가 보안 우려로 설치 거부 가능

7. **Manifest V3 제약**
   - background.js는 Service Worker (5분 후 종료)
   - 장기 실행 작업 불가
   - 메시지 패싱으로 모든 통신 처리 → 코드 복잡도 증가

8. **크로스 브라우저 미지원**
   - Chrome/Edge/Brave만 (Chromium 기반)
   - Firefox/Safari 사용자는 못 씀

---

### 사구팔구가 Content Script로 전환한 이유 (실제 의사결정)

#### 강제 요인 (선택지가 없었음)
1. **번개장터 계정 영구정지** — 미국 EC2 IP에서 게시 → 한국 로그인과 지역 불일치
2. **중고나라 CloudFront 403** — AWS IP 대역 자체 차단

→ **Playwright 방식은 기술적으로 작동 불가능한 상황**

#### 부수 효과 (이득)
- 서버 메모리 1.5GB 절약 → 같은 t3.small로 더 많은 사용자 수용
- 법적 리스크 감소
- 시연 시 시각 효과 극대화

#### 감수한 비용
- 이미지 업로드 5번 시도 끝에 해결 (CDP + React fiber)
- 사용자가 익스텐션 설치 + 로그인 필요
- 디버깅 어려움

---

### 어느 쪽을 언제 써야 하는가?

#### Playwright가 적합한 경우
- **봇 탐지가 약한 플랫폼** (예: 자체 admin, 내부 도구)
- **사용자 개입 없는 백그라운드 작업** (스크래핑, 모니터링)
- **시간 예약 게시** 필수
- **클라우드 IP를 차단하지 않는 플랫폼**
- **대량 자동화** (수천 건 동시)

#### Content Script가 적합한 경우
- **봇 탐지가 강한 플랫폼** (대형 커머스, SNS)
- **법적 회색지대** (약관상 자동화 금지)
- **사용자가 이미 로그인된 상태에서만 작동하면 충분한 경우**
- **시각적 시연 효과**가 중요한 경우
- **서버 비용 절감**이 중요한 경우

---

### 사구팔구의 결론: 하이브리드 전략 (이상)

```
[관리자 도구·스크래핑·시세 분석] → 서버 Playwright
[실제 게시(번개장터·중고나라)]   → 익스텐션 Content Script
[당근마켓(보류)]                  → Android 에뮬레이터 (또 다른 방식)
```

**즉, 한 가지 방식이 모든 걸 해결하지 않습니다.** 작업 특성에 따라 도구를 골라야 하고, 사구팔구는 시세 크롤링은 서버 Playwright로 (탐지 약함), 게시는 익스텐션으로 (탐지 강함) 분리한 하이브리드 구조입니다.

---

### 한 줄 요약

> **Playwright는 "쉽지만 탐지된다", Content Script는 "탐지 안 되지만 어렵다".** 봇 탐지가 강한 플랫폼에서는 사용자 브라우저를 빌려 쓰는 게 유일한 답이고, 그 대가로 이미지 업로드 같은 기술적 난제와 사용자 마찰을 감수해야 합니다.

---

## Q14. 제가 교육 기관에 빠른 답변 감사합니다! ... 이런 메일을 보내놨는데 지금 aws 들어가서 us-east-1에서 sagupalgu_seoul 인스턴스는 만들어놔야 하나요? 아님 저렇게 말하면 자기들이 알아서 인스턴스 생성해 놓나요?

(사용자가 교육기관에 보낸 메일 전문)

> 제가 교육 기관에 빠른 답변 감사합니다! 프로젝트 진행에 큰 도움이 되고 있습니다.
> 사용자 이름(AWS IAM 사용자 이름)은 upstage-sesac-09, 팀 이름은 sagupalgu_seoul로 부탁드립니다.
>
> 참고로 기존 us-east-1 인스턴스에서 국내 중고거래 플랫폼(번개장터)에 자동 게시를 시도했을 때,
> 미국 IP와 한국 로그인 세션 간 지역 불일치로 계정이 영구정지된 경험이 있습니다.
> 현재는 크롬 익스텐션 방식으로 우회하여 동작 중이지만, 서버와 사용자의 지역이 일치하는 것이 플랫폼 정책 위반 확률을 줄이는 데 훨씬 유리합니다.
>
> 그래서 서울 리전을 메인 서비스로 이전하려 합니다. 가능하다면 아래 사양으로 설정 부탁드립니다:
>
> - 인스턴스 타입: t3.small (또는 t3.micro 이상)
> - EBS 볼륨: 20GB
> - Security Group: SSH(22), HTTP(80), HTTPS(443)
>
> Docker 빌드(Python 패키지 + Playwright Chromium)에 최소 15GB가 필요하여 EBS 20GB를 요청드립니다.
> 기존 us-east-1 인스턴스는 이전 완료 후 정리하겠습니다.
>
> 번거롭게 해드려 죄송합니다.
> 정말 감사합니다!

## 결론부터: **지금 us-east-1에 만들지 마세요. 답변 기다리세요.**

### 왜 만들면 안 되나

1. **`sagupalgu_seoul`이라는 이름을 us-east-1에 만들면 모순** — 이름은 서울이지만 실제는 미국 리전. 멘토가 보면 혼란스럽고, 애초에 서울 이전을 요청한 목적(IP 일치)과 정반대
2. **보안그룹/IAM 정책이 다를 가능성** — 교육기관이 학생용으로 미리 만들어둔 보안그룹/서브넷/키페어가 us-east-1에만 있을 수 있음. 서울 리전은 전혀 다른 환경
3. **중복 인스턴스 비용** — 기존 us-east-1 인스턴스 + 새 인스턴스 두 개가 동시에 돌면 크레딧 두 배로 소모

---

### 교육기관(upstage-sesac)이 어떻게 처리할지 일반적인 패턴

한국의 AWS 교육 프로그램(SeSAC, 부트캠프 등)은 보통 다음 중 하나입니다:

#### 패턴 A (가장 흔함): 리전 권한 활성화
- 학생 IAM 사용자에 **us-east-1만 허용**된 정책이 걸려 있음
- 관리자가 **ap-northeast-2(서울) 권한을 추가**해줌
- 그 후 **학생이 직접 인스턴스 생성** (콘솔에서 리전 전환 → EC2 → 인스턴스 시작)
- 답장: *"서울 리전 권한 추가했습니다. 직접 생성하세요"*

#### 패턴 B: 관리자가 직접 생성
- 관리자가 인스턴스 + 키페어 + 보안그룹까지 만들어서 SSH 접속 정보를 학생에게 전달
- 답장: *"인스턴스 생성했습니다. 키페어와 IP 첨부합니다"*

#### 패턴 C: 별도 IAM 사용자/계정 발급
- 서울 리전 전용 IAM 사용자나 서브 계정을 새로 만들어서 발급
- 답장: *"새 사용자 정보 보냅니다"*

→ **어느 패턴이든 지금 당신이 us-east-1에 미리 만들어둘 필요가 없습니다.**

---

### 지금 해야 할 일

1. ✅ **답변 대기** — 평일 기준 보통 1~24시간 안에 회신
2. ✅ **기존 us-east-1 인스턴스는 그대로 두기** — 멘토링 발표는 오늘이라 했으니 시연에 필요. 답변 오면 그때 정리
3. ✅ **답변 오면 그에 맞게 행동**:
   - "권한 활성화했음" → 콘솔에서 **리전을 서울(ap-northeast-2)로 전환** 후 직접 생성
   - "만들어드림" → 받은 정보로 SSH 접속
4. ⏸️ **오늘 발표가 끝나기 전에는** 기존 us-east-1 인스턴스 삭제 금지

---

### 참고: 당신이 직접 만들게 될 경우 체크리스트

만약 패턴 A로 회신이 와서 직접 생성해야 한다면, 아래 순서대로:

```
1. AWS 콘솔 → 우측 상단 리전 → "아시아 태평양 (서울) ap-northeast-2"로 전환
2. EC2 → 키페어 생성 → "sagupalgu-seoul-key" (.pem 다운로드 + 안전 보관)
3. EC2 → 보안그룹 생성 → "sagupalgu-seoul-sg"
   - 인바운드: SSH 22 (내 IP), HTTP 80 (0.0.0.0/0), HTTPS 443 (0.0.0.0/0)
4. EC2 → 인스턴스 시작
   - 이름: sagupalgu_seoul
   - AMI: Ubuntu 22.04 LTS (ap-northeast-2 AMI)
   - 인스턴스 타입: t3.small
   - 키페어: 위에서 만든 것
   - 보안그룹: 위에서 만든 것
   - 스토리지: 20 GiB gp3
5. 시작 후 퍼블릭 IP 확인 → SSH 접속 → setup_ec2.sh 실행
6. git clone → docker compose 기동 → 익스텐션 IP 갱신
```

---

### 한 줄 요약

> **답변 기다리세요.** 교육기관 측에서 권한을 활성화해주거나 직접 만들어줍니다. 지금 us-east-1에 미리 만들면 이름과 실제가 어긋나고 의미 없는 비용만 발생합니다. **오늘 발표는 기존 us-east-1 인스턴스로 그대로 진행**하시고, 발표 끝난 뒤에 답변 받은 대로 전환하면 됩니다.

---

## Q15. 제가 지금 아시아태평양으로 전환해 인스턴스 생성 중인데 AMI ID(ami-084a56dceed3eb9bb)가 유효하지 않습니다. AMI가 더 이상 존재하지 않거나 다른 계정 또는 리전 전용일 수 있습니다. -> 이 메시지 뜨는 거면 아직 거기서 서울 추가 안 해준 건가요?

## 아니요, 그건 권한 문제가 아니라 **AMI ID는 리전마다 다르기 때문**입니다.

### 무슨 일이 벌어지고 있나

**AMI ID는 리전별로 완전히 다릅니다.** 같은 "Ubuntu 22.04 LTS"라도:
- us-east-1: `ami-084a56dceed3eb9bb` (예시)
- ap-northeast-2 (서울): `ami-0c9c942bd7bf113a2` (다른 ID)

당신이 입력한 `ami-084a56dceed3eb9bb`는 us-east-1 전용이고, 서울 리전에는 존재하지 않습니다. 그래서 "AMI가 더 이상 존재하지 않거나 다른 계정 또는 리전 전용일 수 있습니다"라는 에러가 나오는 겁니다.

→ **권한은 정상이고 (서울 리전 접근 자체는 됨), 단지 AMI ID를 잘못 가져온 것**입니다.

---

### 권한 문제였다면?

만약 서울 리전 권한이 없었다면:
- EC2 콘솔 자체에 진입조차 안 됨
- "리전 전환"하면 빨간 경고창
- "이 리전에서 작업할 권한이 없습니다" 같은 IAM 메시지
- 인스턴스 생성 화면에 도달조차 못 함

지금 당신은 **인스턴스 생성 화면까지 도달했고 AMI 검증 단계에서 막힌 것**이니, 권한은 있습니다.

---

### 해결 방법: AMI ID 직접 입력 말고 카탈로그에서 선택

1. EC2 → **인스턴스 시작 (Launch Instance)**
2. **이름**: `sagupalgu_seoul`
3. **애플리케이션 및 OS 이미지 (AMI)** 섹션에서:
   - **❌ 하지 말 것**: AMI ID 직접 붙여넣기
   - **✅ 할 것**: "빠른 시작" 탭에서 **Ubuntu** 클릭 → 드롭다운에서 **Ubuntu Server 22.04 LTS (HVM), SSD Volume Type** 선택
   - 그러면 서울 리전용 AMI ID가 **자동으로 채워집니다** (예: `ami-0c9c942bd7bf113a2` 같은 ID)
4. **아키텍처**: `64-bit (x86)` 확인 (ARM 아님 — t3.small은 x86)
5. **인스턴스 유형**: `t3.small`
6. **키 페어**: 새로 생성 (`sagupalgu-seoul-key`) → .pem 다운로드 → 안전 보관
7. **네트워크 설정**:
   - 보안 그룹 생성 → SSH 22, HTTP 80, HTTPS 443 허용
8. **스토리지**: 20 GiB gp3
9. **인스턴스 시작**

---

### 만약 카탈로그에 Ubuntu가 안 보이면

그건 진짜 권한 문제일 수 있습니다. 그때는:
1. 서울 리전 EC2 → AMI 카탈로그(좌측 메뉴 "AMI") 검색
2. **공개 이미지** 탭 → "Ubuntu 22.04" 검색 → 결과가 0개면 권한 없음
3. 결과가 나오면 **소유자가 `099720109477`(Canonical)**인 최신 ID 사용

---

### 한 줄 요약

> **권한은 있습니다.** AMI ID는 리전마다 다른데, us-east-1의 AMI ID를 서울에 입력해서 생긴 오류입니다. 인스턴스 시작 화면의 "빠른 시작" 탭에서 **Ubuntu 22.04 LTS를 직접 선택**하면 서울 리전 AMI ID가 자동으로 채워집니다.

---

## Q16. You are not authorized to perform this operation. User: arn:aws:iam::033407688855:user/upstage-sesac-09 is not authorized to perform: ec2:DescribeInstances with an explicit deny in an identity-based policy: arn:aws:iam::033407688855:policy/RestrictRegionVirginia -> 이거 뜨는데 아직 거기서 서울 안 열어 준 건가요/

## 네, **아직 서울 리전 권한이 없습니다.** 교육기관 답변을 기다려야 합니다.

### 에러 메시지 해석

```
not authorized to perform: ec2:DescribeInstances
with an explicit deny in an identity-based policy:
arn:aws:iam::033407688855:policy/RestrictRegionVirginia
```

핵심 단어 두 개:
- **explicit deny** (명시적 거부)
- **RestrictRegionVirginia** (정책 이름 — "버지니아 리전으로 제한")

→ **교육기관이 당신의 IAM 사용자에 "us-east-1(버지니아) 리전 외에는 거부"라는 정책을 명시적으로 걸어둔 상태**입니다. AWS IAM에서 explicit deny는 최우선 적용이라, 다른 권한이 있어도 무조건 차단됩니다.

### 무슨 의미인가

| 항목 | 상태 |
|---|---|
| AWS 계정 자체 | ✅ 살아있음 |
| IAM 사용자 | ✅ 정상 (`upstage-sesac-09`) |
| us-east-1 (버지니아) | ✅ 사용 가능 |
| ap-northeast-2 (서울) | ❌ **명시적 차단** |
| 다른 모든 리전 | ❌ 차단 |

→ 교육기관이 학생용 비용 통제를 위해 **us-east-1만 허용하는 정책을 일괄 적용**한 것입니다. 이건 매우 흔한 패턴입니다.

---

### 지금 해야 할 일

#### 1. 작업 중단 ⛔
서울 리전에서 더 이상 시도하지 마세요. AMI 검색, 인스턴스 생성, 보안그룹 생성 전부 차단됩니다.

#### 2. 리전 us-east-1로 되돌리기
AWS 콘솔 우측 상단 → **"미국 동부 (버지니아 북부) us-east-1"**로 전환. 안 그러면 콘솔이 계속 권한 에러로 도배됩니다.

#### 3. 답변 대기
교육기관이 다음 중 하나를 처리해야 합니다:
- `RestrictRegionVirginia` 정책에서 `ap-northeast-2`를 허용 리전에 추가
- 또는 새로운 정책으로 교체
- 또는 별도 IAM 사용자 발급

평일 기준 보통 1~24시간 내 회신.

#### 4. 오늘 발표는 us-east-1 인스턴스로 진행
멘토링이 오늘이라고 하셨으니, 기존 us-east-1 인스턴스(`44.222.120.125`)로 그대로 시연하면 됩니다. 서울 이전은 발표 후 작업.

---

### 답변 기다리는 동안 보낼 수 있는 추가 메일 (선택)

만약 답변이 너무 늦으면, 정책 이름을 명시해서 더 빠른 처리를 요청할 수 있습니다:

> 안녕하세요, 빠른 답변 감사합니다.
>
> 서울 리전 접근을 시도했더니 다음 IAM 정책에 의해 차단되었습니다:
>
> `arn:aws:iam::033407688855:policy/RestrictRegionVirginia`
>
> 해당 정책의 허용 리전 목록에 `ap-northeast-2`(서울)을 추가해주시면 직접 인스턴스를 생성할 수 있습니다. 번거롭게 해드려 죄송합니다.

이 메일을 보내면 관리자가 정책 파일을 바로 찾아서 수정할 수 있어 처리가 빨라집니다.

---

### 한 줄 요약

> **명시적 거부 정책에 의해 서울 리전이 차단된 상태**입니다. 권한은 교육기관이 풀어줘야 하고, 당신이 할 수 있는 게 없습니다. **us-east-1로 되돌리고, 오늘 발표는 기존 인스턴스로 진행**하세요. 답변은 보통 24시간 안에 옵니다.
