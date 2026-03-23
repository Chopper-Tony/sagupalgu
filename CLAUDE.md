# CLAUDE.md

## 프로젝트 개요
중고거래(번개장터, 중고나라) 자동 게시 플랫폼.
이미지 → AI 분석 → 가격 산정 → 카피라이팅 → 게시 → 복구의 파이프라인을
LangGraph Agentic Workflow로 구현.

> 당근마켓은 Android 에뮬레이터 기반으로 현재 미구현 상태. 웹 기반 두 플랫폼 우선 완성.

## 기술 스택
- **백엔드**: FastAPI + Pydantic v2
- **워크플로우**: LangGraph 1.1.3 (`app/graph/`)
- **에이전틱**: `create_react_agent` + LangChain bind_tools (langchain-google-genai, langchain-openai)
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
- `app/tools/` — 에이전트별 툴 모듈 (agentic_tools.py는 re-export shim)
  - `market_tools.py` — Agent 2 (lc_market_crawl_tool, lc_rag_price_tool)
  - `listing_tools.py` — Agent 3 (lc_generate_listing_tool, lc_rewrite_listing_tool)
  - `recovery_tools.py` — Agent 4 (lc_diagnose/auto_patch/discord_alert)
  - `optimization_tools.py` — Agent 5 (price_optimization_tool)
  - `_common.py` — 공통 헬퍼 (_make_tool_call, _extract_json)
- `app/graph/nodes/` — 에이전트별 노드 모듈 (seller_copilot_nodes.py는 re-export shim)
  - `helpers.py` — _run_async, _build_react_llm, 공통 state 헬퍼
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
  - `session_status.py`: SessionStatus, ALLOWED_TRANSITIONS, `assert_allowed_transition()`, `resolve_next_action()`
  - `product_rules.py`: `normalize_text`, `needs_user_input`, `build_confirmed_product_*` — 상품 도메인 규칙
- `app/services/` — 비즈니스 로직
  - `session_service.py`: 세션 오케스트레이터. `build_session_ui_response()` 모듈 함수로 UI 응답 조립 분리
  - `publish_service.py`: `build_platform_packages(canonical, platforms)` — 플랫폼별 가격 차등 패키지 빌드
  - `recovery_service.py`: Agent 4 복구 노드 호출 격리 — SessionService의 graph 직접 import 제거
  - `optimization_service.py`: Agent 5 최적화 노드 호출 격리
  - `seller_copilot_service.py`: LangGraph 브릿지. 전체 async
  - `listing_service.py`, `product_service.py`: 개별 도메인 서비스
- `app/crawlers/` — MarketCrawler legacy wrapper
- `legacy_spikes/` — **읽기 전용** 참고용, 직접 수정 금지

## 코딩 규칙

### 상태 머신
- SessionStatus 정의는 반드시 `app/domain/session_status.py` 단 한 곳에서만 — 다른 파일은 import만
- 상태 전이 유효성은 `ALLOWED_TRANSITIONS` 기준
- next_action 해석은 `resolve_next_action()` 함수 사용

### 에이전트 노드
- 반드시 `state: SellerCopilotState` 인자를 받는 동기 함수로 구현
- async 도구 호출은 `_run_async()` 헬퍼 경유
- ReAct 에이전트는 `create_react_agent(llm, tools)` 패턴 사용

### 툴
- LangChain `@tool` 데코레이터 붙은 버전(`lc_` prefix)만 `create_react_agent`에 bind
- 내부 구현은 `_impl` 함수로 분리해 직접 호출과 lc_ 래퍼가 공유
- 모든 툴은 `_make_tool_call()` 형식으로 결과 반환 (state 기록 용이)

### 게시 (publishers)
- `legacy_spikes/` 직접 수정 금지 → `app/publishers/`에서 서브클래스로 패치
- 당근은 Android 에뮬레이터 기반, 현재 미구현
- 게시/복구/판매후최적화는 SessionService에서 노드 함수 직접 호출 (graph.invoke 우회 금지)

## 현재 미완성 항목 (TODO)
- pgvector 활성화: Supabase SQL Editor에서 `migrations/001_pgvector_setup.sql` 실행 후 `python scripts/setup_pgvector.py --seed`
- 당근마켓 게시 구현 (Android 에뮬레이터)
- Supabase Storage 버킷 연결 (이미지 업로드)

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

# 테스트 (33개)
python -m pytest tests/
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
| M7: 실행 안정화·테스트 회복 | 진행 예정 | SellerCopilotRunner asyncio.run 제거·단순화, SessionService publish 분리, 테스트 green 회복(파일 분해 + patch 경로 정상화) |
| M8: 배포 준비 | 대기 | Dockerfile, CI(GitHub Actions), 환경변수 정리 — M7 완료 후 진행 |

## CTO 코드리뷰 점수 이력

| 시점 | 점수 | 주요 변경 |
|---|---|---|
| 초기 | 72/100 | 기본 파이프라인, 이중 오케스트레이션, God File |
| M1~M4 완료 | 80/100 | 상태 머신 SSOT, God File 분해, API 계약 정리 |
| M5 완료 | 85/100 | rewrite 버그 수정, asyncio 제거, SessionService 분해, 테스트 신뢰성 확보 |
| M6 완료 | 84/100 | 도메인 규칙 분리, 상태 전이 강제화, graph 레이어 경계 정리. Runner magic/asyncio 잔재·SessionService 무게·테스트 20개 실패가 감점 요인 |

## 에이전틱 점수 이력

| 시점 | 점수 | 주요 변경 |
|---|---|---|
| 초기 | 28/100 | 파이프라인 구조, LLM 툴 선택 없음 |
| 1차 개선 | 88/100 | Agent 2 ReAct, publish_node 추가, recovery_node 연결, auto_patch_tool 구현 |
| 2차 개선 | 100/100 | Agent 3/4 ReAct 전환, lc_ 툴 7개로 확대, Supabase pgvector RAG 연결 |
