# CLAUDE.md

## 프로젝트 개요
중고거래(번개장터, 중고나라) 자동 게시 플랫폼.
이미지 → AI 분석 → 가격 산정 → 카피라이팅 → 게시 → 복구의 파이프라인을
LangGraph Agentic Workflow로 구현.

> 당근마켓은 Android 에뮬레이터 기반으로 현재 미구현 상태. 웹 기반 두 플랫폼 우선 완성.

## 기술 스택
- **백엔드**: FastAPI + Pydantic v2
- **워크플로우**: LangGraph 1.1.3 (`app/graph/`)
- **에이전틱**: `langchain.agents.create_agent` + LangChain bind_tools (langchain-google-genai, langchain-openai)
- **Vision AI**: OpenAI gpt-4.1-mini (기본) / Gemini 2.5 Flash (설정 전환, graceful fallback)
- **Listing LLM**: OpenAI gpt-4.1-mini (기본) → Gemini → Solar (LISTING_LLM_PROVIDER 설정 존중, fallback 체인)
- **DB**: Supabase (PostgreSQL + pgvector) — `migrations/001_pgvector_setup.sql` 적용 후 활성화
- **크롤러/게시**: Playwright (웹 자동화), uiautomator2 (Android — 미구현)

## 에이전트 구조 (7 에이전트 / 10 툴)

### Agent 0: Mission Planner ★ NEW
- 노드: `mission_planner_node`
- 동작: 세션 상태 해석 → 실행 계획 생성 (goal·steps·focus·rationale·missing_information). Critic이 replan 요청 시 비평 피드백을 반영해 계획 수정. LLM 실패 시 룰 기반 fallback

### Agent 1: 상품 식별 에이전트 (deterministic)
- 노드: `product_identity_node`, `clarification_node`
- 툴: 없음 (Vision AI 직접 호출, 룰 기반 분기)
- 동작: user_product_input → 바로 확정 / candidates → confidence 체크 / 없으면 사용자 입력 요청

### Agent 2: 시세·가격 전략 에이전트 ★ ReAct
- 노드: `market_intelligence_node`, `pricing_strategy_node`
- 툴: `lc_market_crawl_tool`, `lc_rag_price_tool`
- 동작: `create_react_agent`로 LLM이 툴을 자율 선택. sample_count < 3이면 LLM이 rag_price_tool 추가 호출 결정

### Agent 3: 판매글 생성 에이전트 ★ ReAct
- 노드: `copywriting_node`, `refinement_node`
- 툴: `lc_generate_listing_tool`, `lc_rewrite_listing_tool`
- 동작: `create_react_agent`로 LLM이 상황 판단. rewrite_instruction 있으면 rewrite, 없으면 generate 자율 선택. Critic 피드백 기반 재작성 루프 지원

### Agent 4: 검증·복구 에이전트 ★ ReAct
- 노드: `validation_node`, `recovery_node`
- 툴: `lc_diagnose_publish_failure_tool`, `lc_auto_patch_tool`, `lc_discord_alert_tool`
- 동작: `create_react_agent`로 LLM이 진단 → 패치 → Discord 알림 순서 자율 결정. auto_recoverable이면 재시도

### Agent 5: 판매 후 최적화 에이전트 (deterministic)
- 노드: `post_sale_optimization_node`
- 툴: `price_optimization_tool` (내부 계산 기반)
- 동작: sale_status == "unsold" 시 트리거. 경과 일수에 따라 가격 인하 제안

### Agent 6: Listing Critic 에이전트 ★ NEW
- 노드: `listing_critic_node`
- 동작: LLM 기반 판매글 품질 비평 (구매자 관점). 점수/문제 유형/수정 지시를 생성. score < 70이면 copywriting에 rewrite 지시 후 재생성 루프. 최대 2회 retry 후 강제 통과. LLM 실패 시 룰 기반 fallback

## 그래프 플로우 (M38 이후 — Planner + Critic + Replan 루프)

```
START
  → mission_planner_node (Agent 0)  ★ 목표 해석·계획 생성
  → product_identity_node
      ├─ needs_user_input → clarification_node → END
      └─ confirmed → pre_listing_clarification_node  ★ 정보 부족 감지
             ├─ needs_more_info → END (사용자 답변 대기)
             └─ enough_info → market_intelligence_node (ReAct)
                    → pricing_strategy_node
                    → copywriting_node (ReAct)
                    → listing_critic_node (Agent 6)
                        ├─ pass (score ≥ 70) → validation_node
                        │     ├─ failed → refinement_node → validation_node
                        │     └─ passed → package_builder_node → END
                        ├─ rewrite (retry < 2) → copywriting_node  ★ REWRITE LOOP
                        └─ replan (rewrite 한도 초과) → mission_planner_node  ★ REPLAN LOOP
```

> 그래프 책임: 판매글 패키지 생성까지.
> 게시(publish), 복구(recovery), 판매 후 최적화(post_sale)는 SessionService가 노드 함수를 직접 호출.
> `graph.invoke(_start_node=...)` 패턴 폐기 — 이중 오케스트레이션 문제 해소.

## 툴 목록 (10개)

| # | 툴 이름 | 에이전트 | LangChain @tool | 구현 상태 |
|---|---|---|---|---|
| 1 | `lc_market_crawl_tool` | Agent 2 | ✅ | ✅ 실동작 |
| 2 | `lc_rag_price_tool` | Agent 2 | ✅ | ✅ pgvector → 키워드 → LLM 생성 3단계 RAG |
| 3 | `lc_generate_listing_tool` | Agent 3 | ✅ | ✅ 신규 판매글 LLM 생성 |
| 4 | `lc_rewrite_listing_tool` | Agent 3 | ✅ | ✅ 피드백 기반 재작성 |
| 5 | `lc_diagnose_publish_failure_tool` | Agent 4 | ✅ | ✅ 규칙 기반 진단 |
| 6 | `lc_auto_patch_tool` | Agent 4 | ✅ | ✅ LLM 기반 패치 생성 |
| 7 | `lc_discord_alert_tool` | Agent 4 | ✅ | ✅ 실동작 |
| 8 | `rewrite_listing_tool` | Agent 3 | — | ✅ lc_ 래퍼의 내부 구현 공유 |
| 9 | `diagnose_publish_failure_tool` | Agent 4 | — | ✅ fallback용 |
| 10 | `price_optimization_tool` | Agent 5 | — | ✅ 규칙 기반 |

## 레이어 구조

- `app/domain/session_status.py` — SessionStatus SSOT, ALLOWED_TRANSITIONS, resolve_next_action, is_terminal_status
- `app/graph/` — LangGraph StateGraph, 노드, 상태, 러너
  - `routing.py` — 순수 라우팅 함수 (langgraph 의존성 0, unit 테스트 가능)
  - `seller_copilot_graph.py` — StateGraph 빌드·컴파일 (langgraph lazy import + `_LazyGraphProxy` lazy 빌드)
  - `seller_copilot_runner.py` — LangGraph 실행 진입점 (`_get_graph()` lazy 로드, 초기 state 조립)
- `app/tools/` — 에이전트별 툴 모듈
  - `agentic_tools.py` — **public facade** (외부 코드의 단일 import 진입점, patch 경로 고정)
  - `market_tools.py` — Agent 2 (lc_market_crawl_tool, lc_rag_price_tool, _impl 분리)
  - `listing_tools.py` — Agent 3 (lc_generate_listing_tool, lc_rewrite_listing_tool, _impl 분리)
  - `recovery_tools.py` — Agent 4 (lc_diagnose/auto_patch/discord_alert, _impl 분리)
  - `optimization_tools.py` — Agent 5 (price_optimization_tool)
  - `_common.py` — 공통 헬퍼 (make_tool_call, extract_json)
- `app/graph/nodes/` — 에이전트별 노드 모듈 (seller_copilot_nodes.py는 re-export shim)
  - `helpers.py` — _run_async, _build_react_llm, 공통 state 헬퍼 (`_safe_int`은 `app/core/utils.py`로 이동)
  - `product_agent.py` — Agent 1
  - `market_agent.py` — Agent 2
  - `copywriting_agent.py` — Agent 3
  - `validation_agent.py` — Agent 4 검증
  - `recovery_agent.py` — Agent 4 복구
  - `packaging_agent.py` — 패키지 빌더 + 게시
  - `optimization_agent.py` — Agent 5
  - `planner_agent.py` — Agent 0 Mission Planner (LLM 계획 생성 + 룰 기반 fallback)
  - `critic_agent.py` — Agent 6 Listing Critic (LLM 품질 비평 + 룰 기반 fallback)
  - `clarification_listing_agent.py` — Pre-listing Clarification (판매글 전 정보 부족 감지·질문 생성)
- `app/db/client.py` — Supabase 클라이언트 싱글턴 (`get_supabase()`, lazy import — 미설치 환경 호환)
- `app/db/pgvector_store.py` — pgvector 임베딩 생성·검색·삽입 (OpenAI embedding)
- `migrations/001_pgvector_setup.sql` — pgvector 확장, price_history 테이블, RPC 함수
- `scripts/setup_pgvector.py` — 테이블 확인 + 크롤 데이터 시딩 자동화
- `scripts/manual/` — 수동 실행 스크립트 (pytest 수집 대상 아님)
- `app/publishers/` — 플랫폼 게시 adapter (Playwright 기반)
  - `bunjang_publisher.py`: `PatchedBunjangPublisher` (floating footer 클릭 버그 수정)
  - `joongna_publisher.py`: legacy adapter
- `app/domain/` — 도메인 규칙 단일 진실 원천
  - `session_status.py`: SessionStatus, ALLOWED_TRANSITIONS, `assert_allowed_transition()` → InvalidStateTransitionError, `resolve_next_action()`
  - `product_rules.py`: `normalize_text`, `needs_user_input`, `build_confirmed_product_*` — 상품 도메인 규칙
  - `exceptions.py`: 도메인 예외 5개 + **예외 매핑 정책** (SessionNotFoundError→404, InvalidStateTransitionError→409, ListingGenerationError/ListingRewriteError→500, PublishExecutionError→502, ValueError→400)
  - `schemas.py`: `CanonicalListingSchema` Pydantic 모델 — LLM 출력 직후 shape 강제, `from_llm_result()`·`from_rewrite_result()` classmethod
  - `goal_strategy.py`: Goal 기반 전략 상수 및 순수 함수 (`get_pricing_multiplier`·`get_copywriting_tone`·`get_negotiation_policy`·`get_critic_criteria`) — mission_goal(fast_sell/balanced/profit_max)별 행동 변화 SSOT
  - `node_contracts.py`: 노드별 output contract 정의 (`NODE_OUTPUT_CONTRACTS`·`check_contract()`) — 각 노드가 state에 남겨야 하는 키 계약
  - `publish_policy.py`: 게시 신뢰성 정책 (`FAILURE_TAXONOMY` 8개 에러 분류·`classify_error()` 에러 정규화·`get_retry_delay()` 지수 백오프·`PUBLISH_TIMEOUT_SECONDS` 타임아웃)
- `app/services/` — 비즈니스 로직
  - `session_service.py`: 세션 오케스트레이터. `_ensure_transition()`·`_persist_and_respond()` 내부 헬퍼. 데이터 조작은 3개 순수 함수 모듈에 위임
  - `session_product.py`: product_data 순수 함수 집합 (`attach_image_paths`, `apply_analysis_result`, `confirm_from_candidate`, `confirm_from_user_input`) — SessionService에서 분리
  - `session_ui.py`: `build_session_ui_response()` — DB 레코드 → UI 응답 평탄화 (SessionService에서 분리)
  - `session_meta.py`: workflow_meta 순수 함수 집합 (`set_analysis_checkpoint`, `set_product_confirmed`, `normalize_listing_meta`, `append_rewrite_entry`, `set_publish_prepared`, `set_publish_complete`, `set_publish_diagnostics`, `set_sale_status`, `append_tool_calls`) — SessionService에서 분리
  - `listing_service.py`: `build_canonical_listing()`(최초 생성) + `rewrite_listing()`(피드백 재작성). LLM 호출은 `listing_llm.py`에 위임
  - `listing_llm.py`: OpenAI/Gemini/Solar HTTP 호출 어댑터 + fallback dispatch(`generate_copy`) + 규칙 기반 폴백(`build_template_copy`) — ListingService에서 분리
  - `listing_prompt.py`: `build_copy_prompt()`·`extract_json_object()`·`build_tool_calls_context()`·`build_rewrite_context()`·`build_pricing_strategy()` 순수 함수 (ListingService에서 분리, 단독 테스트 가능)
  - `publish_service.py`: `build_platform_packages(canonical, platforms)` — 플랫폼별 가격 차등 패키지 빌드
  - `recovery_service.py`: Agent 4 복구 노드 호출 격리 — SessionService의 graph 직접 import 제거
  - `optimization_service.py`: Agent 5 최적화 노드 호출 격리
  - `seller_copilot_service.py`: LangGraph 브릿지. 전체 async
  - `product_service.py`: 상품 식별 서비스
- `app/dependencies.py` — FastAPI DI 체인: `get_session_repository`·`get_session_service` 등 6개 `lru_cache` 싱글턴. 테스트에서 `app.dependency_overrides`로 mock 주입 가능
- `app/core/utils.py` — 공통 유틸리티: `safe_int()` (레이어 무관 순수 함수, 중복 정의 제거)
- `app/core/logging.py` — JSON 구조화 로깅: `JsonFormatter`(log→JSON 한 줄)·`configure_logging()`·contextvars `request_id` 자동 포함
- `app/middleware/request_id.py` — `RequestIdMiddleware`: X-Request-ID 헤더 전파·UUID4 자동 발급·응답 헤더 포함
- `app/storage/storage_client.py` — Supabase Storage 클라이언트: `upload_image()`·`get_public_url()`. lazy import + `lru_cache` 싱글턴
- `app/crawlers/` — MarketCrawler legacy wrapper
- `legacy_spikes/` — **읽기 전용** 참고용, 직접 수정 금지
- `frontend/` — React + Vite + TypeScript SPA
  - `src/types/` — `session.ts`(SessionStatus·SessionResponse 등), `ui.ts`(CardType·ComposerMode·TimelineItem·TimelineItemInput)
  - `src/lib/sessionStatusUiMap.ts` — 13개 상태 → CardType·ComposerMode·polling SSOT
  - `src/lib/api.ts` — axios 클라이언트, 전체 API 래퍼
  - `src/hooks/useSession.ts` — 스마트 폴링 (2500ms 활성/10000ms 비활성)
  - `src/components/layout/` — AppShell, SessionSidebar
  - `src/components/chat/` — ChatWindow(타임라인 렌더링), ChatComposer(4가지 모드)
  - `src/components/cards/` — ImageUploadCard, ProductConfirmationCard, DraftCard, PublishApprovalCard, PublishResultCard, SaleStatusCard, OptimizationSuggestionCard, ProgressCard, ErrorCard (13개 상태 전부 커버)
  - `Dockerfile` — node:20-alpine 멀티스테이지 빌드 + nginx:alpine 서빙
  - `nginx.conf` — SPA routing + `/api/` 백엔드 프록시 + 정적자산 캐시
- `tests/api/` — API 통합 테스트 (conftest 공유 픽스처 + 4파일 분할: basic·product·listing·publish)
- `docs/deployment.md` — AWS EC2 배포 가이드 (Docker 설치·환경변수·실행·HTTPS·모니터링)
- `docs/architecture.md` — 아키텍처 문서 (Mermaid 그래프·Deterministic vs Agentic 구분·에이전틱 근거·레이어 구조·3 Agentic Loop)

## 코딩 규칙

### 상태 머신
- SessionStatus 정의는 반드시 `app/domain/session_status.py` 단 한 곳에서만 — 다른 파일은 import만
- 상태 전이 유효성은 `ALLOWED_TRANSITIONS` 기준
- next_action 해석은 `resolve_next_action()` 함수 사용
- **상태 전이 원자성**: 주요 전이 메서드는 `_update_or_raise(session_id, payload, expected_status=current_status)` 패턴 사용. DB 업데이트 시 `expected_status` 불일치면 `InvalidStateTransitionError`(409) 발생 — TOCTOU race condition 방어

### Agent Trace 보존
- `_build_workflow_payload()`는 반드시 `tool_calls`·`decision_rationale`·`plan`·`critic_score`·`critic_feedback`를 workflow_meta에 병합
- `session_ui.py`의 `agent_trace` 섹션에서 이 필드들이 프론트엔드에 노출됨
- 에이전트가 뭘 했는지 추적하는 약속이 그래프→서비스→DB→UI까지 끊기지 않아야 함

### 에이전트 노드
- 반드시 `state: SellerCopilotState` 인자를 받는 동기 함수로 구현
- async 도구 호출은 `_run_async(lambda: coro())` 헬퍼 경유 (lambda 패턴 — RuntimeWarning 방지)
- ReAct 에이전트는 `langchain.agents.create_agent(llm, tools, system_prompt=...)` 패턴 사용

### 툴
- 외부 import 진입점은 반드시 `app.tools.agentic_tools` — 노드·서비스·테스트 모두 여기서만 import (하위 모듈 직접 import 금지)
- LangChain `@tool` 데코레이터 붙은 버전(`lc_` prefix)만 ReAct 에이전트에 bind
- 내부 구현은 `_impl` 함수로 분리해 직접 호출과 lc_ 래퍼가 공유
- 모든 툴은 `make_tool_call()` 형식으로 결과 반환 (state 기록 용이) — `app/tools/_common.py`
- `langchain_core` conditional import — 미설치 환경에서도 `_impl` 함수 정상 동작
- `HumanMessage` 등 langchain_core 의존 import는 try 블록 안에 배치 — 미설치 시 except 폴백 보장

### 예외 처리
- 도메인 예외는 `app/domain/exceptions.py` 단 한 곳에서 정의
- 매핑 정책: SessionNotFoundError→404, InvalidUserInputError→400, InvalidStateTransitionError→409, SessionUpdateError→500, ListingGenerationError/ListingRewriteError→500, PublishExecutionError→502
- 적용 위치: `main.py` 글로벌 핸들러 단일 (`_DOMAIN_STATUS_MAP` 데이터 주도, `SagupalguError` 통합 + `ValueError` 핸들러)
- 라우터는 예외를 잡지 않음 — 순수 서비스 호출 + 응답 변환만 담당

### 의존성 주입 (DI)
- 서비스 인스턴스는 `app/dependencies.py`의 `Depends()` 함수를 통해서만 라우터에 주입
- 라우터에서 직접 `SessionService()` / `SessionRepository()` 생성 금지
- SessionService 생성자는 5개 의존성 모두 required (Optional 기본값 없음, 인라인 fallback 금지)
- 테스트 격리: `app.dependency_overrides[get_session_service] = lambda: mock_svc` 패턴 사용

### 외부 의존성 import
- supabase, langgraph, langchain 등 무거운 런타임 의존성은 반드시 **lazy import** (함수 내부에서 import)
- 모듈 최상단 eager import 금지 — clean env(미설치 환경)에서 pytest 수집이 통과해야 함
- TYPE_CHECKING 블록은 타입 힌트 용도로만 사용

### 테스트
- **unit**: 순수 함수 직접 호출, mock 불필요, CI 필수 통과
- **integration**: 노드 함수 호출하되 **외부 LLM은 반드시 mock** (`_build_react_llm` → `None`). CI 안정성 확보
- **e2e**: 실제 LLM 호출, CI 필수 아님 (별도 환경)
- LLM 응답에 의존하는 assertion 금지 — 룰 기반 fallback 경로만 검증

### 게시 (publishers)
- `legacy_spikes/` 직접 수정 금지 → `app/publishers/`에서 서브클래스로 패치
- 당근은 Android 에뮬레이터 기반, 현재 미구현
- 게시/복구/판매후최적화는 SessionService에서 노드 함수 직접 호출 (graph.invoke 우회 금지)

## 현재 미완성 항목 (TODO)
- pgvector 활성화: Supabase SQL Editor에서 `migrations/001_pgvector_setup.sql` 실행 후 `python scripts/setup_pgvector.py --seed`
- 당근마켓 게시 구현 (Android 에뮬레이터)
- Supabase Storage 버킷 연결 (이미지 업로드) — ✅ M25에서 `storage_client.py` 구현 완료, 대시보드에서 Public 버킷 생성만 필요

## 주요 명령어

```bash
# 의존성 설치
pip install -r requirements.txt
pip install langchain-google-genai langchain-openai
python -m playwright install chromium

# 세션 갱신 (번개장터/중고나라 로그인 — 수동 필요)
python scripts/manual/run_seller_copilot_graph.py

# pgvector 활성화 (최초 1회 — SQL 마이그레이션 후 실행)
python scripts/setup_pgvector.py --check    # 연결 확인
python scripts/setup_pgvector.py --seed     # 가격 데이터 시딩

# 전체 워크플로우 수동 테스트
python scripts/manual/run_seller_copilot_graph.py

# FastAPI 서버 실행
uvicorn app.main:app --reload

# 프론트엔드 개발 서버 실행 (별도 터미널)
cd frontend && npm run dev

# 풀스택 Docker Compose 실행 (프론트 80포트 + 백엔드 내부)
docker compose up --build

# 백그라운드 실행
docker compose up -d --build

# 로그 확인
docker compose logs -f

# 테스트 전체 (486개)
python -m pytest tests/

# unit 테스트만 (langchain 불필요, 0.56s)
python -m pytest tests/ -m unit

# integration 테스트만
python -m pytest tests/ -m integration
```

## 리팩토링 마일스톤 이력 (CTO 코드리뷰 대응)

| 마일스톤 | 상태 | 주요 변경 |
|---|---|---|
| M1: 위생·테스트 기반 | ✅ 완료 | pytest.ini 고정, 33/33 테스트 green, 수동 스크립트 `scripts/manual/` 격리, screenshots git 제거 |
| M2: 프로덕션 경로 단일화 | ✅ 완료 | `app/domain/session_status.py` SSOT 생성, _resolve_next_action 중복 제거, 그래프에서 publish/recovery/post_sale 노드 제거, graph.invoke(_start_node) 깨진 패턴 제거 |
| M3: God File 분해 | ✅ 완료 | `tools/` → `_common/market/listing/recovery/optimization_tools.py` 5개 모듈, `graph/nodes/` 패키지 → `helpers/product/market/copywriting/validation/recovery/packaging/optimization_agent.py` 8개 모듈, 원본 파일은 re-export shim으로 전환 |
| M4: API 계약 정리 | ✅ 완료 | `ProductInfo/ListingInfo/PublishInfo` 중첩 스키마, `ErrorResponse` 통일, `RewriteListingRequest/SaleStatusRequest` 추가, `_build_session_ui_response` 데드 코드 제거, `_api_error` 헬퍼 적용 |
| M5: 버그 수정·안정화 | ✅ 완료 | `rewrite_instruction` 미연결 버그 수정, `nest_asyncio`/`asyncio.run` 제거(async 전환), `_normalize_text` 중복 제거, 테스트 mock 경로 6곳 정상화(33/33 green), `SessionService` 분해(`build_session_ui_response` 모듈 함수 분리, `PublishService.build_platform_packages` 신설) |
| M6: 아키텍처 정리 | ✅ 완료 | `app/domain/product_rules.py` 신설(도메인 규칙 분리), `assert_allowed_transition()` 상태 전이 강제화, `RecoveryService`/`OptimizationService` 신설(graph 레이어 경계 정리), `requirements.txt` 누락 의존성 추가 |
| M7: 실행 안정화·테스트 회복 | ✅ 완료 | SellerCopilotRunner 단순화(325줄→68줄) ✅, PublishService.execute_publish 분리 ✅, SessionService publish 루프 위임 ✅, create_react_agent → langchain.agents.create_agent 교체 ✅, _run_async lambda 패턴 도입(RuntimeWarning 제거) ✅, requirements.txt cp949 버그·langchain 누락 수정 ✅, 테스트 33/33 경고 0개 ✅ |
| M8: 코드 품질 강화 (DI·테스트 계층·API 계약) | ✅ 완료 | SessionService 생성자 DI 도입(5개 서비스 주입 가능) ✅, create_session 더블콜 제거·get_session UI응답 통일 ✅, 테스트 계층 분리(unit/integration 마커, test_session_status.py 41개·test_domain.py 35개 신규) ✅, 112/112 테스트 통과·unit 단독 0.11초 ✅ |
| M9: 구조 정리 (데드코드·라우팅 분리·테스트 분할) | ✅ 완료 | app/graph/routing.py 신설(langgraph 의존성 0, unit 라우팅 테스트 8개) ✅, seller_copilot_graph.py에서 중복 라우터 제거·routing.py import ✅, test_agentic_workflow.py → 4파일 분리(product_market/copywriting_validation/recovery_optimization/graph_routing) ✅, conftest.py 공유 픽스처 ✅, 데드코드 legacy_spikes/dead_code/로 이동(app/agents/ 5파일·nodes.py·graph.py) ✅, app/tools/__init__.py 명시적 export ✅, 114/114 테스트 통과 ✅ |
| M10: import 경계·tool facade 확정 | ✅ 완료 | app/tools/__init__.py 비움(auto-import 제거) ✅, agentic_tools.py public facade 확정(독스트링·contract 명시) ✅, market/listing/recovery_tools.py conditional langchain_core import(미설치 환경 _impl 정상 동작) ✅, SessionService _ensure_transition·_append_tool_calls 헬퍼 추가(8개 메서드 중복 제거) ✅, test_graph_routing.py edge case 5개 추가(총 13개) ✅, 118/118 테스트 통과·unit 0.12s ✅ |
| M11: facade 일관성·rewrite 경로 정리 | ✅ 완료 | 노드 4개(market/copywriting/recovery/optimization) import → agentic_tools facade 통일(전수 완료) ✅, ListingService.rewrite_listing() 공식 메서드 신설(최초 생성과 재작성 유스케이스 분리) ✅, listing_tools._rewrite_listing_impl monkey patch 제거(svc.rewrite_listing() 직접 호출) ✅, 118/118 테스트 통과 ✅ |
| M12: facade 봉인·도메인 예외·HTTP 매핑 | ✅ 완료 | agentic_tools.py에서 _impl re-export 3개 제거(facade 계약 봉인) ✅, app/domain/exceptions.py 도메인 예외 5개 신설(SessionNotFoundError→404, InvalidStateTransitionError→409, ListingGenerationError/ListingRewriteError→500, PublishExecutionError→502) ✅, assert_allowed_transition → InvalidStateTransitionError 발생 ✅, SessionService._get_or_raise → SessionNotFoundError ✅, main.py 글로벌 exception_handler 5개 ✅, tests/test_agentic_tools_contract.py contract 테스트(공개 심볼 18개·_impl 노출 금지 3개) ✅, 137/137 테스트 통과 ✅ |
| M13: API 매핑 마감·LangChain 경계 정리·헬퍼 이름 정리 | ✅ 완료 | session_router.py _domain_error 헬퍼 추가(SagupalguError→HTTP 코드 명시, SessionNotFoundError→404·InvalidStateTransitionError→409·PublishExecutionError→502) ✅, market/copywriting/recovery_agent HumanMessage import를 try 블록 안으로 이동(langchain_core 미설치 시 fallback 정상 동작) ✅, _make_tool_call→make_tool_call·_extract_json→extract_json 공개형 이름 전환(5개 모듈) ✅, exceptions.py 예외 매핑 정책 주석(전 프로젝트 단일 기준) ✅, 137/137 테스트 통과 ✅ |
| M14: 테스트 안정화·asyncio 경고 제거 | ✅ 완료 | helpers.py asyncio.get_event_loop() → asyncio.get_running_loop() 패턴 교체(Python 3.10+ DeprecationWarning 제거) ✅, test_nodes_copywriting_validation.py sys.modules patch 추가(create_agent 미존재 환경에서 ReAct 경로 보장) ✅, 137/137 테스트 통과 ✅ |
| M15: 배포 기반 확립 | ✅ 완료 | pytest.ini pythonpath 추가(CI 단독 실행 보장) ✅, .env.example 생성(민감정보 분리) ✅, .dockerignore 추가 ✅, Dockerfile(python:3.11-slim + playwright chromium) ✅, docker-compose.yml(backend + healthcheck) ✅, GitHub Actions ci.yml(pytest + docker build) ✅, docs/api-contract.md 초안(상태→카드→API 매핑 테이블) ✅, GitHub Secrets 7개 등록(SUPABASE/OPENAI/GEMINI/UPSTAGE/DISCORD) ✅, 137/137 테스트 통과 ✅ |
| M16: 프론트엔드 기반 세팅 | ✅ 완료 | React+Vite+TypeScript 세팅 ✅, 타입 계약(session.ts·ui.ts·TimelineItemInput) ✅, sessionStatusUiMap.ts(상태→카드·ComposerMode·폴링) ✅, api.ts(axios) ✅, useSession hook(스마트 폴링) ✅, AppShell·SessionSidebar ✅, ChatWindow(타임라인) ✅, ChatComposer(모드 분기) ✅, ProgressCard·ErrorCard 공용 ✅, 빌드 통과 ✅ |
| M17: 핵심 카드 구현 | ✅ 완료 | ProductConfirmationCard(후보 최대 3개·confidence bar·직접 입력) ✅, ImageUploadCard(drag&drop+click) ✅, DraftCard(listing 표시·플랫폼 선택·승인/재작성) ✅, PublishApprovalCard(게시 확인·수정 버튼) ✅, PublishResultCard(플랫폼별 성공/실패·링크·판매상태 업데이트) ✅, ChatWindow 실제 카드 컴포넌트 렌더링 연결 ✅, App.tsx handleAction 전체 switch(upload_images/confirm_product/prepare_publish/rewrite/publish/edit_draft/update_sale_status/retry_publish/restart) ✅, 빌드 통과(TypeScript 에러 0) ✅ |
| M18: 서비스 절개·shape 강제·카드 완성 | ✅ 완료 | app/domain/schemas.py CanonicalListingSchema 신설(Pydantic shape 강제·LLM 출력 직후 validate) ✅, app/services/listing_prompt.py PromptBuilder 분리(build_copy_prompt·extract_json_object 순수 함수) ✅, app/services/session_ui.py SessionResponseAssembler 분리(build_session_ui_response 이동) ✅, listing_service.py → CanonicalListingSchema.from_llm_result/from_rewrite_result 사용 ✅, session_service.py → session_ui.py import ✅, SaleStatusCard(팔렸어요/안팔렸어요) ✅, OptimizationSuggestionCard(가격 제안·이유·새로 시작) ✅, App.tsx mark_sold/mark_unsold 액션 추가 ✅, 137/137 테스트 통과·빌드 에러 0 ✅ |
| M19: FastAPI DI 완성 | ✅ 완료 | app/dependencies.py 신설(lru_cache 싱글턴 + Depends 체인 6개 서비스) ✅, session_router.py 전역 인스턴스 제거 → Depends(get_session_service) 전환(11개 엔드포인트) ✅, SessionRepository import 라우터에서 제거 ✅, app.dependency_overrides로 mock 주입 가능(테스트 격리 준비) ✅, 137/137 테스트 통과 ✅ |
| M20: Docker 풀스택 통합·AWS 배포 준비 | ✅ 완료 | frontend/Dockerfile 신설(node:20-alpine 멀티스테이지 빌드 + nginx:alpine 서빙) ✅, frontend/nginx.conf(SPA routing + /api/ 백엔드 프록시 + 정적자산 캐시) ✅, docker-compose.yml backend+frontend 풀스택 구성(healthcheck depends_on) ✅, frontend/.dockerignore 추가 ✅, ci.yml frontend-build 잡 추가(node:20 캐시·npm ci·npm run build) + docker-build가 두 이미지 빌드 ✅, docs/deployment.md AWS EC2 배포 가이드(Docker 설치·환경변수·실행·HTTPS·모니터링·트러블슈팅) ✅, 137/137 테스트 통과·빌드 에러 0 ✅ |
| M21: LLMAdapter·StateCoordinator 분리·gitignore 보완 | ✅ 완료 | app/services/listing_llm.py 신설(OpenAI/Gemini/Solar HTTP 호출 어댑터·fallback dispatch·규칙 기반 폴백, listing_service에서 300줄 분리) ✅, app/services/session_meta.py 신설(workflow_meta 순수 함수 9개, session_service 인라인 meta 조작 제거) ✅, listing_service.py → generate_copy() 단순 호출(LLM 세부사항 완전 분리) ✅, session_service.py → _append_tool_calls 인스턴스 메서드 제거·datetime import 제거 ✅, .gitignore frontend/node_modules·frontend/dist 명시 추가 ✅, 137/137 테스트 통과 ✅ |
| M22: 신설 모듈 unit 테스트 확충 | ✅ 완료 | test_session_meta.py(9개 순수 함수 27개 케이스) ✅, test_listing_llm.py(build_template_copy·3 provider·fallback dispatch 21개 케이스, mock httpx) ✅, 137→185 테스트 통과·unit 단독 0.56s ✅ |
| M23: API 엔드포인트 통합 테스트 | ✅ 완료 | test_session_api.py 신설(TestClient + dependency_overrides mock 주입) ✅, 엔드포인트 11개 전부 커버(정상·422·도메인 예외→HTTP 매핑 36개 케이스) ✅, SessionNotFoundError→404·InvalidStateTransitionError→409·ListingGenerationError→500·PublishExecutionError→502 전수 검증 ✅, 185→221 테스트 통과 ✅ |
| M24: 관찰 가능성(Observability) 기반 구축 | ✅ 완료 | app/core/logging.py 신설(JsonFormatter·configure_logging·contextvars request_id 자동 포함) ✅, app/middleware/request_id.py 신설(X-Request-ID 전파·UUID4 자동 발급·응답 헤더 포함) ✅, main.py 미들웨어 등록·/health 상세화(environment·checks 필드) ✅, test_observability.py(19개: JsonFormatter·contextvars·미들웨어·헬스체크) ✅, 221→240 테스트 통과 ✅ |
| M25: Supabase storage 클라이언트 | ✅ 완료 | app/storage/storage_client.py 쌍(upload_image·get_public_url, lazy import + lru_cache 싱글턴) ✅, config.py storage_bucket_name 필드 추가 ✅, test_storage_client.py 7개 추가 ✅ |
| M26: 보안·운영 강화(CORS) | ✅ 완료 | UploadImagesRequest field validator(HTTP(S) URL 검증·빈값·whitespace strip) ✅, PreparePublishRequest @field_validator(VALID_PLATFORMS·frozenset 검증) ✅, SaleStatusRequest Literal 타입 강화 ✅, test_security.py 22개 추가 ✅ |
| M27: DI required 전환·Router 정리 | ✅ 완료 | SessionService DI required 전환 ✅, session_router.py _handle() 공통 래퍼 신설(try-except 중복 제거) ✅ |
| M28: 예외 핸들링 일원화 | ✅ 완료 | main.py 글로벌 핸들러 통합(5개 개별→SagupalguError 1개 + ValueError 핸들러, _DOMAIN_STATUS_MAP 데이터 주도) ✅, session_router.py try-except 완전 제거(순수 서비스 호출만) ✅, _api_error/_domain_error 헬퍼·ErrorResponse import·예외 import 전부 제거 ✅, exceptions.py 매핑 적용 위치 주석 단일화 ✅, 269/269 테스트 통과 ✅ |
| M29: 데드코드·중복 제거 + 테스트 파일 분할 | ✅ 완료 | app/core/utils.py 신설(safe_int 단일 정의) ✅, helpers.py·session_service.py 중복 _safe_int 제거→utils.py import ✅, seller_copilot_service.py 미사용 alias(_normalize_text·_needs_user_input)·normalize_text import 제거 ✅, test_session_api.py(401줄) → tests/api/ 4파일 분할(basic·product·listing·publish + conftest) ✅, 269/269 테스트 통과 ✅ |
| M30: 테스트 환경 격리 + 출력 계약 봉합 | ✅ 완료 | app/db/client.py supabase eager import → lazy import 전환(clean env에서 pytest 수집 통과) ✅, build_template_copy 출력 계약 위반 수정(price·images·strategy·product 키 누락 → CanonicalListingSchema 계약 준수) ✅, test_output_contract.py 신설(25개: from_llm_result·from_rewrite_result·fallback·template·price coercion·tags 정규화 6경로 전수 검증) ✅, 269→294 테스트 통과 ✅ |
| M31: SessionService 절개 | ✅ 완료 | app/services/session_product.py 신설(product_data 순수 함수 4개: attach_image_paths·apply_analysis_result·confirm_from_candidate·confirm_from_user_input) ✅, SessionService 상품 로직 인라인→순수 함수 위임(349줄→300줄) ✅, _persist_and_respond 헬퍼 신설(반복 업데이트+응답 패턴 통합) ✅, test_session_product.py 17개 unit 테스트 ✅, 286/286 테스트 통과 ✅ |
| M32: ListingService 절개 | ✅ 완료 | listing_prompt.py에 build_tool_calls_context·build_rewrite_context·build_pricing_strategy 순수 함수 3개 추가(95줄→137줄) ✅, listing_service.py 인라인 context 빌드·pricing 로직 제거(125줄→93줄, -26%) ✅, test_listing_prompt_ext.py 13개 unit 테스트 ✅, 294→307 테스트 통과 ✅ |
| M33: 상태 전이 계약 + UI 응답 shape 검증 | ✅ 완료 | test_status_contract.py 신설(14개: ALLOWED_TRANSITIONS 완전성·전이 대상 유효성·self-loop 검증·터미널 상태·resolve_next_action 전수·happy path 체인·UI 응답 shape×13상태·섹션 존재 검증) ✅, 324→338 테스트 통과 ✅ |
| M34: langgraph import 격리 | ✅ 완료 | seller_copilot_graph.py eager import → build 내부 lazy import 전환 ✅, _LazyGraphProxy + _get_compiled_graph로 lazy 빌드 구조 전환 ✅, seller_copilot_runner.py _get_graph() lazy 호출로 변경 ✅, clean env(langgraph 미설치) pytest 수집 통과 ✅, 324/324 테스트 통과 ✅ |
| M35: rewrite 출력 계약 봉합 + datetime 경고 제거 | ✅ 완료 | copywriting_agent.py _normalize_listing() 신설(ReAct 결과→CanonicalListingSchema 검증, 필수 키 보장 fallback) ✅, session_meta.py datetime.utcnow()→datetime.now(timezone.utc) 전환(DeprecationWarning 제거) ✅, 338/338 테스트 통과·경고 0개 ✅ |
| M36: CTO2 지적 대응 — 노드 분리·예외 세분화·운영성 보강 | ✅ 완료 | copywriting_node 3함수 분리(_run_copywriting_agent·_extract_listing_payload·_build_prompts + 기존 _normalize_listing·_fallback_generate) ✅, InvalidUserInputError·SessionUpdateError 도메인 예외 신설(ValueError 6곳→도메인 예외 전환) ✅, repository.update() expected_status 조건부 업데이트(race condition 방어) ✅, /health/live·/health/ready 분리(readiness probe 보강) ✅, 338→340 테스트 통과 ✅ |
| M37: Listing Critic + Rewrite 루프 | ✅ 완료 | Agent 6 listing_critic_node 신설(LLM 품질 비평 + 룰 기반 fallback, score/issues/rewrite_instructions 출력) ✅, SellerCopilotState에 critic 필드 5개 추가(critic_score·critic_feedback·critic_rewrite_instructions·critic_retry_count·max_critic_retries) ✅, route_after_critic 라우터(pass→validation / rewrite→copywriting, max retry 방어) ✅, 그래프에 copywriting→critic→(pass:validation / rewrite:copywriting) 루프 연결 ✅, test_critic_agent.py 15개(룰 기반 6·라우팅 5·통합 4) ✅, 340→355 테스트 통과 ✅ |
| M38: Mission Planner + Replan 루프 | ✅ 완료 | Agent 0 mission_planner_node 신설(LLM 계획 생성 + 룰 기반 fallback, goal·plan·rationale·missing_information 출력) ✅, SellerCopilotState에 planner 필드 6개 추가(mission_goal·plan·plan_revision_count·max_replans·decision_rationale·missing_information) ✅, route_after_critic에 replan 분기 추가(rewrite 한도 초과→planner 재호출) ✅, 그래프 진입점 START→mission_planner→product_identity 변경 ✅, test_planner_agent.py 13개(룰 기반 7·replan 라우팅 3·통합 3) ✅, 기존 340개 + 신규 29개 테스트 통과 ✅ |
| M39: Pre-listing Clarification | ✅ 완료 | pre_listing_clarification_node 신설(상품 상태·사용기간·구성품·거래방법 4항목 정보 부족 감지, LLM 질문 생성 + 룰 기반 fallback) ✅, SellerCopilotState에 3필드 추가(pre_listing_questions·pre_listing_answers·pre_listing_done) ✅, route_after_pre_listing_clarification 라우터(부족→END 사용자 대기 / 충분→market) ✅, 그래프에 product_identity→pre_listing_clarification→market 경로 추가 ✅, test_pre_listing_clarification.py 14개(탐지 5·질문 생성 2·라우팅 3·통합 4) ✅, 기존 340개 테스트 통과 ✅ |
| M40: Goal 기반 행동 변화 | ✅ 완료 | app/domain/goal_strategy.py 신설(PRICING_MULTIPLIER·COPYWRITING_TONE·NEGOTIATION_POLICY·CRITIC_CRITERIA 4개 맵 + 순수 함수 4개) ✅, market_agent.py 하드코딩 goal="fast_sell" 3곳 제거→state["mission_goal"] 참조·goal별 가격 배수(0.88~1.05) ✅, copywriting_agent.py _build_prompts에 goal별 톤 지시 삽입 ✅, critic_agent.py _rule_based_critique goal별 평가 기준(설명 길이·가격 임계·신뢰 감점) ✅, listing_prompt.py build_pricing_strategy goal 파라미터 추가 ✅, schemas.py·listing_llm.py 기본값 balanced 전환 ✅, test_goal_strategy.py 27개 unit ✅, 369→412 테스트 통과 ✅ |
| M41: 노드별 state contract 테스트 | ✅ 완료 | app/domain/node_contracts.py 신설(NODE_OUTPUT_CONTRACTS 9노드·check_contract() 검증 함수) ✅, test_node_contracts.py 17개(check_contract 유틸 5·노드별 contract 11·커버리지 1) ✅, 412→429 테스트 통과 ✅ |
| M42: 아키텍처 문서화 | ✅ 완료 | docs/architecture.md 신설(Mermaid 그래프 다이어그램·Deterministic vs Agentic 구분표·"왜 에이전틱인지" 6가지 근거·레이어 구조·3가지 Agentic Loop 상세·Goal-driven 행동 변화 테이블) ✅ |
| M43: E2E 경로 봉합 | ✅ 완료 | session_router.py multipart/form-data 파일 업로드 엔드포인트 전환 ✅, session_ui.py 응답 평탄화(image_urls·product_candidates·canonical_listing·platform_results 등 최상위 필드) ✅, schemas/session.py 평탄화 필드 추가 ✅, api.ts FormData+rewriteListing+platform_targets 계약 수정 ✅, App.tsx useEffect 이동+API 호출 수정 ✅, health/ready provider-aware 판정 ✅, MarketService print()→logger ✅, E2E 응답 shape 테스트 3개 ✅, 429→431 테스트 통과 ✅ |
| M44: Publish Reliability 강화 | ✅ 완료 | app/domain/publish_policy.py 신설(FAILURE_TAXONOMY 8개 에러 분류·classify_error() 메시지 기반 추론·get_retry_delay() 지수 백오프·PUBLISH_TIMEOUT_SECONDS) ✅, publish_service.py asyncio.wait_for 타임아웃·에러 정규화 분류·auto_recoverable 판정·구조화 로깅 ✅, test_publish_policy.py 23개 unit ✅, 431→454 테스트 통과 ✅ |
| M45: RAG stub 제거 | ✅ 완료 | rag_price_retrieval.py(3줄 TODO stub) 삭제 ✅, 실제 RAG 구현은 market_tools.py에 이미 완전 구현(pgvector 벡터 검색→키워드 검색→LLM 추정 3단계) ✅, import 전수 검증(참조 0건) ✅ |
| M46: E2E 통합 테스트 | ✅ 완료 | test_e2e_happy_path.py 신설(전체 세션 라이프사이클 8단계 API 체인·상태 전이 순서 검증·모든 단계 프론트 필드 shape 검증) ✅, 454→457 테스트 통과 ✅ |
| M47: 프론트엔드 타입 자동 동기화 | ✅ 완료 | scripts/generate_api_types.py 신설(OpenAPI→TypeScript 타입 생성·--check CI 모드) ✅, frontend/src/types/api-generated.ts 자동 생성(SessionStatusGenerated 13상태·SessionResponseGenerated 16필드) ✅, test_api_type_sync.py 5개(상태 집합 일치·필드 존재·파일 존재 검증) ✅, 457→462 테스트 통과 ✅ |
| M48: README 발표용 재작성 | ✅ 완료 | README.md 전면 재작성(프로젝트 소개·아키텍처 다이어그램·Goal-driven 테이블·기술 스택·빠른 시작·테스트 구조·API 엔드포인트·프로젝트 구조·환경 변수) ✅ |
| M49: CI 파이프라인 보강 | ✅ 완료 | ci.yml에 type-sync 잡 추가(generate_api_types.py --check) ✅, 테스트를 unit→integration→full 3단계 분리 ✅, docker-build가 type-sync 의존 추가 ✅ |
| M50: 프론트엔드 이미지 표시 | ✅ 완료 | DraftCard에 이미지 갤러리 추가(listing.images 렌더링·100px 썸네일·가로 스크롤) ✅, ImageUploadCard에 업로드 프리뷰 추가(File→ObjectURL·80px 썸네일) ✅, 빌드 에러 0 ✅ |
| M51: create_app() 팩토리 패턴 | ✅ 완료 | main.py를 create_app() 함수로 래핑(import 시점 결합 해소·테스트 환경 분리·부트 안정화) ✅, 462 테스트 통과 ✅ |
| M52: legacy_spikes 의존 정리 | ✅ 완료 | app/publishers/_legacy_compat.py 신설(legacy_spikes import 단일 진입점·try/except 안전 import) ✅, app/ 내 7곳 legacy_spikes 직접 import → _legacy_compat 경유로 전환 ✅, 462 테스트 통과 ✅ |
| M53: SessionService 정리 | ✅ 완료 | publish_session에서 _handle_publish_failure 헬퍼 추출(recovery 로직 분리) ✅, SessionService는 이미 도메인 서비스에 위임하는 얇은 오케스트레이터 구조이므로 추가 분리보다 현재 구조 유지 ✅, 462 테스트 통과 ✅ |
| P2-1: 당근 자동 게시 통합 | ✅ 완료 | VALID_PLATFORMS에 daangn 추가 ✅, DaangnPublisher dependency 체크+에러분류+로깅 ✅, config DAANGN_DEVICE_ID ✅, DraftCard 플랫폼 한글→영문 매핑 ✅, 463 테스트 통과 ✅ |
| P2-2: 게시 실패 Discord 알림 | ✅ 완료 | DISCORD_ALERT_THRESHOLD=3 ✅, _handle_publish_failure에서 누적 실패 추적→3회 이상 Discord 자동 발송 ✅, 465 테스트 통과 ✅ |
| E2E 버그 수정 | ✅ 완료 | ProgressCard 스택 버그 수정(새 카드 시 이전 progress 제거) ✅, LLM fallback 순서를 LISTING_LLM_PROVIDER 설정 존중 ✅, Gemini Vision mock→실구현(Google AI API) ✅, 프론트 auto-analyze+auto-generateListing ✅, baseURL /api/v1 ✅, timeout 120초 ✅, 에러 메시지 사용자 친화적 변환 ✅, 백엔드 로그 노이즈 제거(hpack/httpcore WARNING) ✅, orphan builders 삭제 ✅, readiness 정교화(meta 분리) ✅, daangn_crawler EXPERIMENTAL 명시 ✅, 465→466 테스트 통과 ✅ |
| E2E 실테스트 + 긴급 수정 | ✅ 완료 | LangGraph _run_async Windows 이벤트루프 문제 발견→fallback 직접 LLM 호출 구현(generate_copy→build_template_copy 2단 fallback) ✅, fallback 가격 0원→strategy.recommended_price 보정 ✅, DraftCard null-safe 렌더링(price·tags·title) ✅, ProductConfirmationCard placeholder 한글화(애플/아이폰 15 프로/스마트폰) ✅, debug_session.py 디버그 스크립트 신설 ✅, **E2E 게시 준비까지 완전 성공**(세션생성→이미지→분석→확정→시세크롤링21개→판매글생성→가격698400원→게시준비→게시시도) ✅ |
| M54: _run_async Windows 근본 수정 | ✅ 완료 | _run_async를 전용 이벤트루프 스레드 패턴으로 교체(ThreadPoolExecutor+asyncio.run→asyncio.run_coroutine_threadsafe+전용 데몬 스레드) ✅, Windows SelectorEventLoop 강제(ProactorEventLoop 불안정성 제거) ✅, _get_dedicated_loop double-check locking 싱글턴 ✅, 120초 타임아웃 ✅, test_run_async.py 8개(기본동작·싱글턴·running loop·concurrent) ✅, 466→474 테스트 통과 ✅ |
| M55: 프론트엔드 한글화 + ErrorCard 개선 | ✅ 완료 | sessionStatusUiMap.ts에 platformLabel() 유틸 추가(bunjang→번개장터·joongna→중고나라·daangn→당근마켓) ✅, PublishApprovalCard·PublishResultCard 플랫폼 한글 표시 ✅, ChatWindow PublishApprovalCard platforms를 selected_platforms 우선 사용 ✅, App.tsx friendlyError 강화(422·502·404·기술 메시지 필터링 추가) ✅, 빌드 에러 0·474 테스트 통과 ✅ |
| M56: tool_calls trace 봉합 | ✅ 완료 | `_build_workflow_payload()`에 `tool_calls`·`decision_rationale`·`plan`·`critic_score`·`critic_feedback` 보존 추가(CTO3 P0 agent trace 소실 방지) ✅, `session_ui.py` agent_trace에 확장 필드 포함 ✅, test_trace_and_atomicity.py 6개 unit 테스트 ✅, 474→486 테스트 통과 ✅ |
| M57: 상태 전이 원자성 확보 | ✅ 완료 | `_update_or_raise()`에 `expected_status` 파라미터 추가(CTO3 P0 TOCTOU 방어) ✅, 불일치 시 `InvalidStateTransitionError`(409) 발생 ✅, `_persist_and_respond()`에 `expected_status` 전달 ✅, 7개 주요 전이 메서드(attach_images·analyze·confirm·provide·generate·prepare·publish)에 적용 ✅, test_trace_and_atomicity.py 6개 unit 테스트 ✅, 486 테스트 통과 ✅ |
| M58: 사이드바 세션 상태 보정 | ✅ 완료 | App.tsx `sessionIds: string[]` → `sessions: { id, lastKnownStatus }[]` 전환(CTO1 P0) ✅, `statusLabel()` 한글 매핑 유틸 추가(13개 상태 커버) ✅, 활성 세션 상태 변경 시 사이드바 자동 동기화 useEffect ✅, 빌드 에러 0 ✅ |
| M59: README/문서 정합화 | ✅ 완료 | 테스트 수 486개 반영 ✅, LLM/Vision 기본값 openai로 정합(CTO2 P0 문서-코드 불일치 해소) ✅, README·architecture.md에 production path 한 줄 선언 추가(하이브리드 오케스트레이션 명시) ✅, CLAUDE.md 기술 스택 정합화 ✅ |

## CTO 코드리뷰 점수 이력

| 시점 | 점수 | 주요 변경 |
|---|---|---|
| 초기 | 72/100 | 기본 파이프라인, 이중 오케스트레이션, God File |
| M1~M4 완료 | 80/100 | 상태 머신 SSOT, God File 분해, API 계약 정리 |
| M5 완료 | 85/100 | rewrite 버그 수정, asyncio 제거, SessionService 분해, 테스트 신뢰성 확보 |
| M6 완료 | 84/100 | 도메인 규칙 분리, 상태 전이 강제화, graph 레이어 경계 정리. Runner magic/asyncio 잔재·SessionService 무게·테스트 20개 실패가 감점 요인 |
| M7~M8 완료 | 79/100 | Runner 단순화, asyncio 제거, DI 도입, 테스트 계층 분리. tools import 구조·patch contract 불안정·데드코드 잔존이 감점 요인 |
| M9~M10 완료 | 84→90 예상 | routing.py 분리, 데드코드 제거, tools __init__ 경량화, conditional import, SessionService 헬퍼 정리 |
| M11~M12 완료 | 92/100 | facade 봉인, monkey patch 제거, 도메인 예외 계층, contract 테스트. 라우터 매핑·LangChain 경계가 남은 감점 요인 |
| M13 완료 | 93/100 | API 예외 매핑 마감, HumanMessage import 경계 정리, 헬퍼 공개형 이름 전환, 예외 정책 문서화. test KeyError·asyncio 경고·SessionService ValueError가 남은 감점 요인 |
| M14 완료 | 96 예상 | asyncio.get_running_loop() 교체(경고 제거), 테스트 ReAct 경로 sys.modules patch 안정화 |
| M15~M20 완료 | 91/100 (실제) | 배포 기반·프론트엔드·Docker·DI 완성. 배포 인프라 강화 but SessionService 무게·테스트 확충 미비 |
| M21~M24 완료 | 97 예상 | LLM/Meta 분리, 테스트 185→240, API 통합 테스트 36개, 관찰 가능성 기반 |
| M25~M29 완료 | 89→90/100 (실제) | 1차 89점(supabase import·SessionService 비대·ListingService 혼재·출력 계약 미비), 2차 90점(supabase 해결 but langgraph import 실패 잔존) |
| M30~M34 완료 | 90/100 (CTO2 실제) | supabase+langgraph lazy import, 출력 계약 봉합, SessionService·ListingService 절개. CTO2 84점 (rewrite 깨짐·legacy 의존·예외 남용 지적) → M35~M36으로 대응 후 CTO1 재평가 90점 |
| M35~M39 완료 | 95 예상 | rewrite 계약 봉합, 예외 세분화(InvalidUserInputError·SessionUpdateError), health/live·ready 분리, **Critic+Planner+Clarification 3개 에이전트 추가** (7에이전트 체제), rewrite·replan·clarification 3개 agentic loop 완성, 테스트 369개 |
| M40~M42 완료 | 97 예상 | **Goal-driven 행동 변화** (같은 상품도 goal별 가격·톤·비평 기준 차별화), 노드별 output contract 테스트(9노드 계약 고정), 아키텍처 문서(Mermaid·에이전틱 근거), 테스트 429개 |
| M43~M45 완료 | 90+ 예상 | CTO P0 전수 대응(API 계약 4건·React·health·로깅), 파일 업로드 E2E 봉합, **Publish Reliability**(타임아웃·에러 분류·지수 백오프), RAG stub 제거(이미 완전 구현 확인), 테스트 454개 |
| M55 완료 (CTO 리뷰) | CTO1: 91 / CTO2: 85 / CTO3: 84 | 공통: 스파게티 아님·구조 보임·과제 목표 부합. CTO1: 제품 마감·사이드바 상태. CTO2: 문서-코드 불일치·production path 선언. CTO3: tool_calls trace 소실·TOCTOU·업로드 validation |
| M56~M59 완료 | 93+ 예상 | CTO 3명 P0 전수 대응: agent trace 봉합·상태 전이 원자성·사이드바 보정·문서 정합화, 테스트 486개 |

## 에이전틱 점수 이력

| 시점 | 점수 | 주요 변경 |
|---|---|---|
| 초기 | 28/100 | 파이프라인 구조, LLM 툴 선택 없음 |
| 1차 개선 | 88/100 | Agent 2 ReAct, publish_node 추가, recovery_node 연결, auto_patch_tool 구현 |
| 2차 개선 | 100/100 | Agent 3/4 ReAct 전환, lc_ 툴 7개로 확대, Supabase pgvector RAG 연결 |
| 3차 개선 (M37~M39) | — | Listing Critic(생성→비평→재생성 루프), Mission Planner(계획→실행→재계획 루프), Pre-listing Clarification(정보 부족→질문→재진입 루프). 5→7 에이전트, deterministic shell + agentic core 하이브리드 아키텍처 |
| 4차 개선 (M40) | — | **Goal-driven 행동 변화**: mission_goal(fast_sell/balanced/profit_max)에 따라 가격 배수·카피 톤·네고 정책·비평 기준이 실제로 달라짐. 같은 상품이라도 전략에 따라 전혀 다른 결과 생성 |
