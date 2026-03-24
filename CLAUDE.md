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
- **Vision AI**: OpenAI / Gemini (graceful fallback)
- **Listing LLM**: Gemini 2.5 Flash (primary) → OpenAI → Solar (fallback 체인)
- **DB**: Supabase (PostgreSQL + pgvector) — `migrations/001_pgvector_setup.sql` 적용 후 활성화
- **크롤러/게시**: Playwright (웹 자동화), uiautomator2 (Android — 미구현)

## 에이전트 구조 (5 에이전트 / 10 툴)

### Agent 1: 상품 식별 에이전트
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
- 동작: `create_react_agent`로 LLM이 상황 판단. rewrite_instruction 있으면 rewrite, 없으면 generate 자율 선택

### Agent 4: 검증·복구 에이전트 ★ ReAct
- 노드: `validation_node`, `recovery_node`
- 툴: `lc_diagnose_publish_failure_tool`, `lc_auto_patch_tool`, `lc_discord_alert_tool`
- 동작: `create_react_agent`로 LLM이 진단 → 패치 → Discord 알림 순서 자율 결정. auto_recoverable이면 재시도

### Agent 5: 판매 후 최적화 에이전트
- 노드: `post_sale_optimization_node`
- 툴: `price_optimization_tool` (내부 계산 기반)
- 동작: sale_status == "unsold" 시 트리거. 경과 일수에 따라 가격 인하 제안

## 그래프 플로우 (M2 이후 — 게시/복구는 그래프 외부)

```
START
  → product_identity_node
      ├─ needs_user_input → clarification_node → END
      └─ confirmed → market_intelligence_node (ReAct)
           → pricing_strategy_node
           → copywriting_node (ReAct)
           → validation_node
               ├─ failed (retry < 2) → refinement_node → validation_node
               └─ passed → package_builder_node → END
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
  - `seller_copilot_graph.py` — StateGraph 빌드·컴파일 (routing.py import)
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

## 코딩 규칙

### 상태 머신
- SessionStatus 정의는 반드시 `app/domain/session_status.py` 단 한 곳에서만 — 다른 파일은 import만
- 상태 전이 유효성은 `ALLOWED_TRANSITIONS` 기준
- next_action 해석은 `resolve_next_action()` 함수 사용

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
- 매핑 정책: SessionNotFoundError→404, InvalidStateTransitionError→409, ListingGenerationError/ListingRewriteError→500, PublishExecutionError→502, ValueError→400
- 적용 위치: `main.py` 글로벌 핸들러 단일 (`_DOMAIN_STATUS_MAP` 데이터 주도, `SagupalguError` 통합 + `ValueError` 핸들러)
- 라우터는 예외를 잡지 않음 — 순수 서비스 호출 + 응답 변환만 담당

### 의존성 주입 (DI)
- 서비스 인스턴스는 `app/dependencies.py`의 `Depends()` 함수를 통해서만 라우터에 주입
- 라우터에서 직접 `SessionService()` / `SessionRepository()` 생성 금지
- SessionService 생성자는 5개 의존성 모두 required (Optional 기본값 없음, 인라인 fallback 금지)
- 테스트 격리: `app.dependency_overrides[get_session_service] = lambda: mock_svc` 패턴 사용

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

# 테스트 전체 (324개)
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
| M33: 상태 전이 계약 + UI 응답 shape 검증 | ✅ 완료 | test_status_contract.py 신설(14개: ALLOWED_TRANSITIONS 완전성·전이 대상 유효성·self-loop 검증·터미널 상태·resolve_next_action 전수·happy path 체인·UI 응답 shape×13상태·섹션 존재 검증) ✅, 307→321 테스트 통과 ✅ |
| M34: langgraph import 격리 | ✅ 완료 | seller_copilot_graph.py eager import → build 내부 lazy import 전환 ✅, _LazyGraphProxy + _get_compiled_graph로 lazy 빌드 구조 전환 ✅, seller_copilot_runner.py _get_graph() lazy 호출로 변경 ✅, clean env(langgraph 미설치) pytest 수집 통과 ✅, 324/324 테스트 통과 ✅ |

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
| M25~M29 완료 | 89/100 (실제) | Storage 클라이언트, 입력 검증 강화, DI required, 예외 핸들링 일원화, 중복 제거. supabase import·SessionService 비대·ListingService 혼재·출력 계약 미비가 감점 요인 |
| M30~M32 완료 | 95 예상 | supabase lazy import, 출력 계약 25개 회귀 테스트, SessionService 절개(session_product.py), ListingService 절개(listing_prompt.py 확장), 테스트 324개 |

## 에이전틱 점수 이력

| 시점 | 점수 | 주요 변경 |
|---|---|---|
| 초기 | 28/100 | 파이프라인 구조, LLM 툴 선택 없음 |
| 1차 개선 | 88/100 | Agent 2 ReAct, publish_node 추가, recovery_node 연결, auto_patch_tool 구현 |
| 2차 개선 | 100/100 | Agent 3/4 ReAct 전환, lc_ 툴 7개로 확대, Supabase pgvector RAG 연결 |
