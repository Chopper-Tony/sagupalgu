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
- **DB**: Supabase (PostgreSQL + Storage) — 테이블 미생성
- **크롤러/게시**: Playwright (웹 자동화), uiautomator2 (Android — 미구현)

## 에이전트 구조 (5 에이전트 / 7 툴)

### Agent 1: 상품 식별 에이전트
- 노드: `product_identity_node`, `clarification_node`
- 툴: 없음 (Vision AI 직접 호출, 룰 기반 분기)
- 동작: user_product_input → 바로 확정 / candidates → confidence 체크 / 없으면 사용자 입력 요청

### Agent 2: 시세·가격 전략 에이전트 ★ ReAct 구현
- 노드: `market_intelligence_node`, `pricing_strategy_node`
- 툴: `lc_market_crawl_tool`, `lc_rag_price_tool`
- 동작: `create_react_agent`로 LLM이 툴을 자율 선택. sample_count < 3이면 LLM이 rag_price_tool 추가 호출 결정

### Agent 3: 판매글 생성 에이전트
- 노드: `copywriting_node`, `refinement_node`
- 툴: `rewrite_listing_tool`
- 동작: rewrite_instruction 있으면 rewrite_tool, 없으면 ListingService LLM 생성. tool_calls 기록을 프롬프트에 포함

### Agent 4: 검증·복구 에이전트
- 노드: `validation_node`, `recovery_node`
- 툴: `diagnose_publish_failure_tool`, `auto_patch_tool`, `discord_alert_tool`
- 동작: 게시 실패 시 진단 → 자동 패치 생성 → Discord 알림. 자동복구 가능하면 publish 재시도

### Agent 5: 판매 후 최적화 에이전트
- 노드: `post_sale_optimization_node`
- 툴: `price_optimization_tool` (내부 계산 기반)
- 동작: sale_status == "unsold" 시 트리거. 경과 일수에 따라 가격 인하 제안

## 그래프 플로우 (단일 통합 그래프)

```
START
  → product_identity_node
      ├─ needs_user_input → clarification_node → END
      └─ confirmed → market_intelligence_node (ReAct)
           → pricing_strategy_node
           → copywriting_node
           → validation_node
               ├─ failed (retry < 2) → refinement_node → validation_node
               └─ passed → package_builder_node
                    → publish_node
                        ├─ 성공 → END (status: published, checkpoint: D_complete)
                        └─ 실패 → recovery_node (Agent 4)
                             ├─ auto_recoverable → publish_node (재시도, 최대 2회)
                             └─ 불가 → END (status: publishing_failed)
```

> `build_graph()` / `build_post_confirmation_graph()` 이중 구조 폐기.
> publish_node가 graph 내부에 포함되어 단일 실행으로 게시까지 완료.

## 툴 목록 (7개)

| # | 툴 이름 | 에이전트 | LangChain @tool | 구현 상태 |
|---|---|---|---|---|
| 1 | `lc_market_crawl_tool` | Agent 2 | ✅ | ✅ 실동작 |
| 2 | `lc_rag_price_tool` | Agent 2 | ✅ | ✅ LLM 기반 RAG (Supabase pgvector 미연결) |
| 3 | `rewrite_listing_tool` | Agent 3 | — | ✅ 실동작 |
| 4 | `diagnose_publish_failure_tool` | Agent 4 | — | ✅ 규칙 기반 |
| 5 | `auto_patch_tool` | Agent 4 | — | ✅ LLM 기반 패치 생성 |
| 6 | `discord_alert_tool` | Agent 4 | — | ✅ 실동작 |
| 7 | `price_optimization_tool` | Agent 5 | — | ✅ 규칙 기반 |

## 레이어 구조

- `app/graph/` — LangGraph StateGraph, 노드, 상태, 러너
- `app/tools/agentic_tools.py` — 7개 툴 정의 (LangChain @tool 포함)
- `app/publishers/` — 플랫폼 게시 adapter (Playwright 기반)
  - `bunjang_publisher.py`: `PatchedBunjangPublisher` (floating footer 클릭 버그 수정)
  - `joongna_publisher.py`: legacy adapter
- `app/services/` — 비즈니스 로직 (ListingService, PublishService 등)
- `app/crawlers/` — MarketCrawler legacy wrapper
- `legacy_spikes/` — **읽기 전용** 참고용, 직접 수정 금지

## 코딩 규칙

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

## 현재 미완성 항목 (TODO)
- Supabase 테이블/버킷 미생성 (pgvector 포함)
- Agent 3 copywriting_node → LLM bind_tools 전환 (현재 Python if-else)
- Agent 4 recovery_node → LLM 자율 판단 전환 (현재 순서 고정)
- Supabase pgvector 실제 데이터 적재 및 연결
- 당근마켓 게시 구현 (Android 에뮬레이터)
- 에이전틱 점수: 현재 88/100 → 목표 100/100

## 주요 명령어

```bash
# 의존성 설치
pip install -r requirements.txt
pip install langchain-google-genai langchain-openai
python -m playwright install chromium

# 세션 갱신 (번개장터/중고나라 로그인 — 수동 필요)
python scripts/manual_spikes/save_sessions.py   # 3 선택 → 두 플랫폼 동시

# 전체 워크플로우 테스트 (AI 파이프라인 + 실제 게시까지)
python -m scripts.test_seller_copilot_graph

# FastAPI 서버 실행
uvicorn app.main:app --reload
```

## 에이전틱 점수 이력

| 시점 | 점수 | 주요 변경 |
|---|---|---|
| 초기 | 28/100 | 파이프라인 구조, LLM 툴 선택 없음 |
| 1차 개선 | 88/100 | Agent 2 ReAct, publish_node 추가, recovery_node 연결, auto_patch_tool 구현 |
| 목표 | 100/100 | Agent 3/4 LLM bind_tools, Supabase pgvector 연결 |
