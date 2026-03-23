# 사구팔구(Sagupalgu) 프로젝트 정리

## 한 줄 요약

중고 물품 사진 한 장으로 시세 분석 → 판매글 자동 생성 → 번개장터/중고나라 동시 게시까지 LangGraph 기반 워크플로우로 완전 자동화

---

## 에이전틱 워크플로우

### 실제로 에이전틱한 부분

**Agent 2 — 도구 선택 자율성**

- `market_crawl_tool` 호출 후 sample_count < 3이면 `rag_price_tool` 추가 호출
- 표본이 충분하면 RAG 스킵
- 결과를 보고 다음 도구를 자율적으로 선택

**Agent 4 — 결과 기반 재시도**

- validation 실패 → `refinement_node`에서 자동 수정 → 재검증
- 최대 2회 반복 후 강제 통과
- 실패를 감지하고 스스로 고쳐서 재시도

### 전체 실행 흐름

```
사용자 (사진 업로드 / 상품 정보 입력)
        ↓
[Agent 1] 상품 식별
  confidence ≥ 0.6 → 자동 확정
  confidence < 0.6 → 사용자 입력 요청 → 대기
        ↓
[Agent 2] 시세 수집
  market_crawl_tool 호출
  sample_count < 3 → rag_price_tool 추가 호출 (자율 판단)
        ↓
[Agent 2] 가격 전략 수립
  시세 중앙값 × 97% → 추천 가격
        ↓
[Agent 3] 판매글 생성
  rewrite_instruction 있음 → rewrite_listing_tool
  없음 → LLM 생성 → 실패 시 템플릿 fallback
        ↓
[Agent 4] 검증
  통과 → package_builder
  실패 → refinement_node → 재검증 (최대 2회, 자율 반복)
        ↓
패키지 빌더
  번개장터: 가격 +10,000원
  중고나라: 가격 그대로
        ↓
게시 실행 (Playwright)
  성공 → completed
  실패 → [Agent 4] recovery_node
            diagnose_publish_failure_tool → 원인 분석
            discord_alert_tool → 알림 발송
            자동 복구 가능 → 재시도 (최대 2회)
            불가 → publishing_failed
        ↓
[Agent 5] 판매 후 최적화
  sold → 종료
  unsold → price_optimization_tool → 가격 재제안
```

### 상태머신 전이

```
session_created
→ images_uploaded
→ awaiting_product_confirmation
→ product_confirmed
→ draft_generated
→ awaiting_publish_approval
→ publishing
→ completed / publishing_failed
→ awaiting_sale_status_update
→ optimization_suggested
```

---

## 각 에이전트 역할과 툴

### Agent 1 — 상품 식별 에이전트

**역할:** 사진을 보고 어떤 상품인지 판단. 확신이 없으면 사용자에게 직접 입력 요청

| 판단 조건 | 결과 |
| --- | --- |
| 사용자가 직접 입력 | 바로 확정 |
| Vision AI confidence ≥ 0.6 | 자동 확정 |
| confidence < 0.6 또는 unknown | 사용자 입력 요청 |

**툴:** 없음 (Vision API는 내부 capability로 직접 호출)

---

### Agent 2 — 시세·가격 전략 에이전트

**역할:** 번개장터/중고나라에서 시세를 수집하고 판매 가격 전략을 수립

| 판단 조건 | 행동 |
| --- | --- |
| 항상 | market_crawl_tool 먼저 호출 |
| sample_count < 3 | rag_price_tool 추가 호출 |
| sample_count ≥ 3 | RAG 스킵 |

| 툴 | 설명 |
| --- | --- |
| `market_crawl_tool` | 번개장터/중고나라 실시간 크롤링 |
| `rag_price_tool` | 과거 거래 데이터 기반 가격 참고값 조회 |

---

### Agent 3 — 판매글 생성 에이전트

**역할:** 시세와 상품 정보를 바탕으로 판매글 초안 생성. 사용자 피드백 시 재작성

| 판단 조건 | 행동 |
| --- | --- |
| rewrite_instruction 있음 | rewrite_listing_tool 호출 |
| 없음 | LLM으로 신규 생성 |
| LLM 실패 | 템플릿 기반 fallback |

| 툴 | 설명 |
| --- | --- |
| `rewrite_listing_tool` | 사용자 피드백 반영해서 판매글 재작성 |

---

### Agent 4 — 검증·복구 에이전트

**역할:** 판매글 품질 검사 + 게시 실패 시 원인 진단 및 복구

**검증 로직**

| 조건 | 행동 |
| --- | --- |
| 제목 5자 미만 / 설명 20자 미만 / 가격 0 | 자동 수정 후 재검증 |
| 재시도 2회 초과 | 강제 통과 |

**복구 로직**

| 실패 원인 | 자동 복구 |
| --- | --- |
| 네트워크 오류 | 가능 (재시도) |
| 로그인 만료 | 불가 (수동 처리) |
| 콘텐츠 정책 위반 | 불가 (수동 처리) |

| 툴 | 설명 |
| --- | --- |
| `diagnose_publish_failure_tool` | 실패 원인 분석 |
| `discord_alert_tool` | Discord 웹훅으로 장애 알림 발송 |

---

### Agent 5 — 판매 후 최적화 에이전트

**역할:** 판매 여부 확인 후 미판매 시 가격 재전략 제안

| 조건 | 행동 |
| --- | --- |
| sold | 종료 |
| unsold + 7일 | -5% 인하 제안 (urgency: medium) |
| unsold + 14일 이상 | -10% 인하 제안 (urgency: high) |

| 툴 | 설명 |
| --- | --- |
| `price_optimization_tool` | 미판매 기간 기반 가격 인하 전략 계산 |

---

## 저장소 구조

### 핵심 원칙

> AI 중간 산출물은 `sell_sessions` JSONB에 저장
> 운영 추적 데이터는 별도 테이블에서 관리

### sell_sessions 테이블

| 컬럼 | 내용 |
| --- | --- |
| `status` | 세션 전체 상태 (상태머신) |
| `product_data_jsonb` | 이미지 경로, Vision 후보, 확정 상품 정보 |
| `listing_data_jsonb` | 시세, 가격 전략, 판매글 초안, 플랫폼 패키지, 최적화 제안 |
| `workflow_meta_jsonb` | checkpoint, tool_calls, 게시 결과, 진단 결과, 재작성 이력 |

### product_data_jsonb

```json
{
  "image_paths": ["..."],
  "analysis_source": "vision | user_input",
  "candidates": [...],
  "confirmed_product": {
    "brand": "애플",
    "model": "아이폰 15 Pro",
    "confidence": 0.92,
    "source": "vision"
  },
  "needs_user_input": false
}
```

### listing_data_jsonb

```json
{
  "market_context": {
    "median_price": 830000,
    "price_band": [600000, 1150000],
    "sample_count": 25,
    "crawler_sources": ["번개장터", "중고나라"]
  },
  "strategy": {
    "goal": "fast_sell",
    "recommended_price": 805000
  },
  "canonical_listing": {
    "title": "애플 아이폰 15 Pro 급처합니다",
    "description": "...",
    "price": 805000,
    "tags": ["애플", "아이폰15Pro", "스마트폰"]
  },
  "platform_packages": {
    "bunjang": {"price": 815000},
    "joongna": {"price": 805000}
  }
}
```

### workflow_meta_jsonb

```json
{
  "checkpoint": "C_complete",
  "tool_calls": [
    {"tool_name": "market_crawl_tool", "success": true},
    {"tool_name": "diagnose_publish_failure_tool", "success": true}
  ],
  "publish_results": {
    "bunjang": {"success": true, "external_url": "https://m.bunjang.co.kr/products/..."},
    "joongna": {"success": true}
  },
  "rewrite_history": [...],
  "publish_diagnostics": [...]
}
```

### 파일 스토리지 구조

```
original-images/      ← 원본 업로드 이미지
processed-images/     ← 전처리/리사이즈 이미지
crawler-snapshots/    ← 크롤링 결과 스냅샷
publish-artifacts/    ← 게시 payload
publish-evidence/     ← 게시 성공/실패 스크린샷
```

---

## 시스템 아키텍처

### 전체 구조

```
[Frontend - Next.js]              ← 미구현
        ↓
[FastAPI API Layer]                ← app/main.py
        ↓
[Session Router]                   ← app/api/session_router.py
  status / checkpoint / next_action 중심 응답
        ↓
[SessionService]                   ← app/services/session_service.py
  실제 서비스 진입점 / 상태 전이 관리
        ↓
[SellerCopilotService]             ← app/services/seller_copilot_service.py
  LangGraph 실행 래퍼
        ↓
[LangGraph Runner]                 ← app/graph/seller_copilot_runner.py
  graph.invoke() 실행
        ↓
[LangGraph Workflow Nodes]         ← app/graph/seller_copilot_nodes.py
  5개 에이전트 / 6개 도구 자율 선택
        ↓
[Supabase DB]                      ← sell_sessions JSONB
        ↓
[External Services]
  Vision AI (Gemini / OpenAI)
  시세 크롤러 (aiohttp)
  Playwright Publisher
  Discord Webhook
```

### 계층별 책임 분리

| 계층 | 파일 | 책임 |
| --- | --- | --- |
| Router | `session_router.py` | HTTP 진입점, 응답 포맷 |
| Service | `session_service.py` | 상태 전이, 비즈니스 로직 |
| Copilot | `seller_copilot_service.py` | LangGraph 입력 구성 |
| Graph | `seller_copilot_nodes.py` | 에이전트 판단·도구 선택 |
| Tools | `agentic_tools.py` | 실제 외부 호출 |
| Infra | `session_repository.py` | DB CRUD |

### 런타임 실행 흐름

```
1. 사용자 API 호출
2. SessionService → 현재 status 검사
3. 허용된 상태면 SellerCopilotService 호출
4. LangGraph graph.invoke() 실행
5. 각 노드(에이전트)가 도구 선택·호출
6. 결과를 sell_sessions JSONB에 저장
7. tool_calls 이력 포함해서 UI 친화 구조로 반환
8. 프론트가 status / next_action 기준으로 화면 갱신
```

### 핵심 API

| 엔드포인트 | 설명 |
| --- | --- |
| `POST /sessions` | 세션 생성 |
| `POST /sessions/{id}/images` | 이미지 업로드 |
| `POST /sessions/{id}/analyze` | Vision AI 상품 분석 |
| `POST /sessions/{id}/confirm-product` | 상품 확정 |
| `POST /sessions/{id}/provide-product-info` | 수동 상품 정보 입력 |
| `POST /sessions/{id}/generate-listing` | 판매글 생성 (LangGraph 실행) |
| `POST /sessions/{id}/rewrite-listing` | 판매글 재작성 |
| `POST /sessions/{id}/prepare-publish` | 게시 준비 |
| `POST /sessions/{id}/publish` | 실제 게시 (Playwright) |
| `POST /sessions/{id}/sale-status` | 판매 상태 입력 → 최적화 트리거 |

---

## 현재 상태 요약

| 항목 | 상태 |
| --- | --- |
| 백엔드 E2E | ✅ 완료 |
| LangGraph 조건 분기 | ✅ 완료 |
| 번개장터 게시 | ✅ 실제 성공 확인 |
| 중고나라 게시 | ✅ 실제 성공 확인 |
| 테스트 코드 | ✅ 33개 통과 |
| 프론트 UI | ❌ 미구현 |
| RAG 실제 구현 | ❌ 더미 상태 |
| 사용자 인증 | ❌ temp-user-id 하드코딩 |

## 남은 것

- 프론트 UI 구축 (Next.js)
- `app/agents/` 죽은 코드 정리
- RAG 실제 벡터 DB 연결
- user_id 실제 인증 연동
- LLM 기반 진짜 도구 선택 고도화 (현재는 규칙 기반)
