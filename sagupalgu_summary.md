# 사구팔구(Sagupalgu) 프로젝트 정리

## 한 줄 요약

중고 물품 사진 한 장으로 상품 식별 → 시세 분석 → 판매글 자동 생성 → 번개장터/중고나라 자동 게시 → 마켓 거래(문의·응답·재등록)까지, LangGraph Agentic Workflow로 엔드투엔드 자동화한 중고거래 플랫폼.

---

## 에이전틱 워크플로우

### 구성 요소

- **7 에이전트** — 하이브리드 (ReAct + LLM+Fallback + Deterministic)
- **10 툴** — `app.tools.agentic_tools` 단일 facade
- **3 Agentic Loop** — Critic-Rewrite (max 2) / Replan (max 1) / Validation-Refinement (max 2)

### 그래프 플로우

```
START → Mission Planner (Agent 0)
      → Product Identity (Agent 1)
          ├─ needs_user_input → clarification → END
          └─ confirmed → Pre-listing Clarification
                ├─ 정보 부족 → END (사용자 대기)
                └─ 충분 → Market Intelligence (Agent 2, ReAct)
                       → Pricing Strategy
                       → Copywriting (Agent 3, ReAct)
                       → Listing Critic (Agent 6)
                            ├─ score ≥ 70 → Validation → Package Builder → END
                            ├─ rewrite (retry<2) → Copywriting   ← REWRITE LOOP
                            └─ replan (replan<1) → Mission Planner ← REPLAN LOOP
```

> 그래프 책임: 판매글 패키지 생성까지. 게시·복구·판매 후 최적화는 SessionService가 노드 함수 직접 호출.

### 7 에이전트

| # | 에이전트 | 유형 | 핵심 동작 |
|---|---------|------|----------|
| 0 | Mission Planner | LLM+Fallback | 세션 상태 해석 → 실행 계획 수립, replan 시 비평 반영 |
| 1 | 상품 식별 | Deterministic | Vision AI(OpenAI gpt-4.1-mini/Gemini 2.5 Flash) 호출 → confidence ≥ 0.6 자동 확정 |
| 2 | 시세·가격 전략 | ReAct | 크롤링·RAG 자율 선택, sample_count < 3이면 RAG 추가 호출 |
| 3 | 판매글 생성 | ReAct | rewrite_instruction 유무로 generate/rewrite 자율 선택, LLM 실패 시 템플릿 fallback |
| 4 | 검증·복구 | ReAct | 진단 → 패치 → Discord 알림 순서 자율 결정 |
| 5 | 판매 후 최적화 | Deterministic | 경과 일수별 가격 인하·재게시 제안 |
| 6 | Listing Critic | LLM+Fallback | 구매자 관점 비평, goal별 기준 (관용적/표준/엄격) |

### 10 툴

| 툴 | 에이전트 | 기능 |
|----|---------|------|
| `lc_market_crawl_tool` | 2 | 번개장터·중고나라 실시간 크롤링 |
| `lc_rag_price_tool` | 2 | pgvector→키워드→LLM 3단계 RAG |
| `lc_generate_listing_tool` | 3 | 판매글 LLM 생성 |
| `lc_rewrite_listing_tool` | 3 | 피드백 기반 재작성 |
| `lc_diagnose_publish_failure_tool` | 4 | 12종 에러 분류 진단 |
| `lc_auto_patch_tool` | 4 | LLM 자동 패치 |
| `lc_discord_alert_tool` | 4 | Discord 장애 알림 |
| `rewrite_listing_tool` | 3 | lc_ 래퍼 내부 구현 공유 |
| `diagnose_publish_failure_tool` | 4 | fallback용 |
| `price_optimization_tool` | 5 | 규칙 기반 가격 최적화 |

### Goal-driven 행동 변화

| | fast_sell | balanced | profit_max |
|---|----------|---------|-----------|
| 가격 배수 (high sample) | ×0.90 | ×0.97 | ×1.05 |
| 가격 배수 (low sample) | ×0.88 | ×0.95 | ×1.02 |
| 카피 톤 | 간결·긴급 | 실용·신뢰 | 프리미엄·가치 |
| Critic 기준 (price_threshold) | 1.4 | 1.3 | 1.5 |
| Critic 기준 (min_desc_len) | 30 | 50 | 80 |
| 네고 정책 | welcome, fast deal | small negotiation | firm price |
| 문의 응대 템플릿 | 긴급 유도 | 합리적 톤 | 프리미엄 톤 |

> 상세 상수: `app/domain/goal_strategy.py` 단일 원천.

---

## 상태 머신

### 세션 상태 (13개)

```
session_created
→ images_uploaded
→ awaiting_product_confirmation
→ product_confirmed
→ market_analyzing
→ draft_generated
→ awaiting_publish_approval
→ publishing
→ completed
  → awaiting_sale_status_update
    → optimization_suggested (terminal)
→ publishing_failed → awaiting_publish_approval (재시도)
→ failed (terminal)
```

- **전이 규칙**: `app/domain/session_status.py`의 `ALLOWED_TRANSITIONS` 기준
- **원자성**: `_update_or_raise(session_id, payload, expected_status=...)` — 불일치 시 409
- **next_action 해석**: `resolve_next_action()` 함수

### 판매 상태 (마켓 거래 루프)

- **상태**: `available` / `reserved` / `sold` / `unavailable`
- **전이 규칙** (`session_repository.py:SALE_STATUS_TRANSITIONS`):
  - `available` → reserved, sold
  - `reserved` → sold, available
  - `sold` → terminal (되돌릴 수 없음)
- **race condition 방어**: `eq("id").eq("user_id")` 조건부 업데이트 + `InvalidStateTransitionError` (409)

---

## 기술 스택

| 레이어 | 기술 |
|---|---|
| 백엔드 | FastAPI + Pydantic v2 (12,400줄) |
| 워크플로우 | LangGraph, `langchain.agents.create_agent` + bind_tools |
| Vision AI | OpenAI gpt-4.1-mini (기본) / Gemini 2.5 Flash |
| Listing LLM | OpenAI gpt-4.1-mini → Gemini → Solar (fallback 체인) + 규칙 기반 템플릿 |
| DB | Supabase (PostgreSQL + pgvector, 385건 시세 데이터) |
| 이미지 | Supabase Storage Public 버킷 `product-images` |
| 게시 | 크롬 익스텐션 Content Script (CDP 이미지 업로드) + 모바일 복사/직접 올리기 |
| 프론트엔드 | React 19 + TypeScript + Vite (7,080줄) |
| 알림 | Discord 웹훅 + Gmail SMTP (병렬 실행) |
| 배포 | Docker Compose + 서울 리전 EC2 (Elastic IP 43.201.188.57) + GitHub Actions CI/CD |

---

## 게시 아키텍처

### 왜 크롬 익스텐션인가

초기에는 서버 Playwright로 게시했으나, 번개장터/중고나라가 서버 IP를 봇으로 탐지해 계정 정지 위험. 사용자 브라우저에서 실행되는 크롬 익스텐션 Content Script 방식으로 전환.

### 핵심 구현

- **React 폼 입력**: `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set` 네이티브 setter + `input`/`change` 이벤트 dispatch로 React 상태 업데이트
- **이미지 업로드**: CDP(Chrome DevTools Protocol)로 file input 우회
- **카테고리 매핑**: Vision AI 카테고리 → 번개장터 3-depth 카테고리 매핑 테이블 (미매핑 시 "기타" fallback)
- **토큰 전달**: 익스텐션이 백엔드로 세션 쿠키를 StorageState 형식으로 전송 → DB 암호화 저장

### 모바일 분기

- 감지: `window.innerWidth <= 768`
- 데스크톱 → 익스텐션 자동 게시
- 모바일 → 판매글 전체 복사 버튼 + 플랫폼 `products/new` 직접 올리기 링크

### 게시 정책 단일 원천

`app/domain/publish_policy.py` — 타임아웃(180s), 재시도(MAX_PUBLISH_RETRIES=2, 지수 백오프 5×2^n), `FAILURE_TAXONOMY` 12종 에러 분류, `classify_error()` 메시지 기반 자동 분류.

---

## 마켓 + 셀러 코파일럿

### 마켓 (공개)
- `#/market` — 상품 목록 (검색·가격 필터·상태 필터·정렬·페이지네이션)
- `#/market/{id}` — 상품 상세 + **AI 상품 챗봇** (`POST /market/{id}/chat`)
  - 환각 방지: "상품 설명에 따르면" / "일반적으로 이 모델은" 분기
  - 추정 금지: 정품 여부·구성품·보증·배터리·하자 (5개)

### 셀러 대시보드 (`#/my-listings`, 인증)
- 내 상품 목록 + 판매 상태 변경
- **문의 관리**: `inquiries` 테이블 — DB 저장 + Discord 알림 + Gmail SMTP 알림 병렬
- **문의 응답 시 자동 상태 전이**: status → replied, is_read → true, last_reply_at → now
- **문의 코파일럿**: LLM 응답 초안 + goal별 fallback 템플릿 3종 (nego/condition/default)
- **재등록**: `POST /my-listings/{id}/relist` — 기존 세션 복제 + sale_status 초기화

---

## 저장소 구조

### sell_sessions 테이블

| 컬럼 | 내용 |
|---|---|
| `status` | 세션 전체 상태 (상태머신 13종) |
| `product_data` (JSONB) | 이미지 경로, Vision 후보, 확정 상품 정보 |
| `listing_data` (JSONB) | 시세, 가격 전략, 판매글, 플랫폼 패키지, sale_status |
| `workflow_meta` (JSONB) | checkpoint, tool_calls, 게시 결과, 진단 이력, critic trace |

### inquiries 테이블 (마켓 거래 루프)

| 컬럼 | 설명 |
|---|---|
| `id`, `listing_id` | 문의 ID, 상품(세션) FK |
| `buyer_name`, `buyer_contact`, `message` | 구매자 정보 + 문의 내용 |
| `reply`, `status` (open/replied), `is_read` | 응답 + 상태 |
| `created_at`, `last_reply_at` | 시각 |

---

## 시스템 아키텍처

### 계층별 책임

| 계층 | 파일 | 책임 |
|---|---|---|
| Router | `app/api/session_router.py`, `market_router.py`, `platform_router.py`, `admin_router.py` | HTTP 진입점, 응답 포맷 |
| Service | `session_service.py`, `seller_copilot_service.py`, `publish_orchestrator.py` | 상태 전이, 오케스트레이션 |
| Graph | `app/graph/seller_copilot_graph.py` + `nodes/` | 에이전트 판단·도구 선택 |
| Tools | `app/tools/agentic_tools.py` | 외부 호출 facade |
| Domain | `app/domain/` (session_status, goal_strategy, publish_policy, exceptions) | 단일 진실 원천 |
| Repository | `session_repository.py`, `inquiry_repository.py` | DB CRUD |
| Storage | `app/storage/` | Supabase Storage 클라이언트 |

### 의존성 주입

`app/dependencies.py`에서 `@lru_cache(maxsize=1)` 싱글턴 + FastAPI `Depends()`로 wiring. 테스트에서 `app.dependency_overrides`로 mock 주입.

### 예외 처리

`app/main.py` 글로벌 핸들러 단일 (`_DOMAIN_STATUS_MAP`):
- SessionNotFound→404, InvalidUserInput→400, InvalidStateTransition→409
- ListingGeneration/Rewrite→500, PublishExecution→502

### 인증

`app/core/auth.py` JWT 기반:
- local/dev: `X-Dev-User-Id` 헤더 bypass 허용
- prod: JWT 필수 + `X-Dev-User-Id` 거부 (403)
- 공개 엔드포인트: `get_optional_user` 완화 (마켓·챗봇·문의)

---

## 프론트엔드

- **해시 라우팅**: `#/` (셀러 코파일럿) / `#/market` / `#/market/{id}` / `#/my-listings`
- **13개 상태별 카드**: `sessionStatusUiMap.ts` SSOT로 상태 → CardType·ComposerMode 매핑
- **실시간**: SSE `EventSource` + 스마트 폴링 fallback (탭 비활성 시 폴링 간격 2.5s → 10s)
- **액션 훅** (CTO P1): `useSessionActions.ts` 단일 파일 — 10종 액션 집중 관리, App.tsx에 비즈니스 로직 금지
- **테마**: 라이트/다크 토글 + CSS 변수 기반 (`--btn-padding`, `--text-primary` 등)
- **모바일 반응형**: 사이드바 숨김, `+` 버튼 세션 자동 생성, 짧은 placeholder, 게시 분기

---

## 현재 상태

| 항목 | 상태 |
|---|---|
| 백엔드 E2E | ✅ 완료 (12,400줄) |
| 프론트엔드 UI | ✅ 완료 (7,080줄, React 19 + Vite) |
| LangGraph 조건 분기 + 3 Agentic Loop | ✅ 완료 |
| 번개장터 자동 게시 (Content Script) | ✅ 성공 확인 |
| 중고나라 자동 게시 (Content Script) | ✅ 성공 확인 |
| 모바일 게시 (복사 + 직접 올리기) | ✅ 완료 |
| pgvector RAG (385건 시세) | ✅ 활성화 |
| Supabase Storage | ✅ Public 버킷 `product-images` |
| AI 상품 챗봇 (구매자용) | ✅ 완료, 환각 방지 |
| 마켓 거래 루프 (문의·응답·재등록) | ✅ 완료 |
| 이메일 알림 (Gmail SMTP) | ✅ Discord와 병렬 |
| 라이트/다크 테마 토글 | ✅ 완료 |
| 서울 리전 배포 + Elastic IP 고정 | ✅ 43.201.188.57 |
| 테스트 | ✅ BE 596 unit / FE 60 |
| CI/CD (GitHub Actions + EC2 SSH 배포) | ✅ Rolling restart + Discord 알림 |
| JWT 인증 + dev bypass | ✅ 환경별 정책 |
| 프로덕션 로그인 UI | ⚠️ Supabase Auth 프론트 연결 개발 중 (현재 dev bypass + `get_optional_user` 운용) |
| 당근마켓 게시 | ❌ Android 에뮬레이터 필요 (보류) |
| 중고나라 크롤링 | ❌ CloudFlare 차단 (번개장터 데이터로 대체) |

---

## 배포 정보

| 항목 | 값 |
|---|---|
| 리전 | `ap-northeast-2` (서울) |
| Elastic IP | `43.201.188.57` (고정) |
| 인스턴스 | `t3.medium` (2 vCPU, 4 GB, 20 GB) |
| 컨테이너 | Caddy(HTTPS) + backend(FastAPI) + worker(Playwright) + frontend(nginx) |
| CI/CD | main push → test → type-sync → FE build → Docker build → SSH 배포 → Discord 알림 |

---

## 관련 문서

- `CLAUDE.md` — 프로젝트 개요 + 레이어 구조 + 핵심 규칙
- `docs/architecture.md` — 상세 아키텍처
- `docs/api-contract.md` — API 엔드포인트 명세
- `docs/deployment.md` / `deployment-architecture.md` — 배포 상세
- `docs/demo-guide-2026-04-10.md` — 데모 시나리오
- `.claude/rules/coding-rules.md` — 코딩 규칙
- `.claude/rules/architecture.md` — 에이전트·툴·그래프
- `.claude/rules/frontend.md` — 프론트엔드 규칙
