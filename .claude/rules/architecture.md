# 에이전트 · 툴 · 그래프 아키텍처

## 7 에이전트

| # | 에이전트 | 유형 | 노드 | 핵심 동작 |
|---|---------|------|------|----------|
| 0 | Mission Planner | LLM+Fallback | `mission_planner_node` | 세션 상태 해석 → 실행 계획 생성. replan 시 비평 피드백 반영 |
| 1 | 상품 식별 | Deterministic | `product_identity_node`, `clarification_node` | Vision AI 호출 → confidence 체크 → 사용자 확정/입력 |
| 2 | 시세·가격 전략 | ReAct | `market_intelligence_node`, `pricing_strategy_node` | LLM이 크롤링·RAG 툴 자율 선택. sample_count < 3이면 RAG 추가 |
| 3 | 판매글 생성 | ReAct | `copywriting_node`, `refinement_node` | rewrite_instruction 유무로 generate/rewrite 자율 선택 |
| 4 | 검증·복구 | ReAct | `validation_node`, `recovery_node` | 진단→패치→Discord 알림 순서 자율 결정 |
| 5 | 판매 후 최적화 | Deterministic | `post_sale_optimization_node` | 경과 일수별 가격 인하·재게시 제안 |
| 6 | Listing Critic | LLM+Fallback | `listing_critic_node` | 구매자 관점 비평. score < 70 → rewrite 루프 (최대 2회) |

## 10 툴

| 툴 | 에이전트 | 기능 |
|----|---------|------|
| `lc_market_crawl_tool` | 2 | 번개장터·중고나라 실시간 크롤링 |
| `lc_rag_price_tool` | 2 | pgvector→키워드→LLM 3단계 RAG |
| `lc_generate_listing_tool` | 3 | 판매글 LLM 생성 |
| `lc_rewrite_listing_tool` | 3 | 피드백 기반 재작성 |
| `lc_diagnose_publish_failure_tool` | 4 | 12종 에러 분류 진단 (publish_policy.FAILURE_TAXONOMY) |
| `lc_auto_patch_tool` | 4 | LLM 자동 패치 |
| `lc_discord_alert_tool` | 4 | Discord 장애 알림 |
| `rewrite_listing_tool` | 3 | lc_ 래퍼 내부 구현 공유 |
| `diagnose_publish_failure_tool` | 4 | fallback용 |
| `price_optimization_tool` | 5 | 규칙 기반 가격 최적화 |

## 그래프 플로우

```
START → mission_planner → product_identity
  ├─ needs_user_input → clarification → END
  └─ confirmed → pre_listing_clarification
       ├─ needs_more_info → END (사용자 대기)
       └─ enough_info → market_intelligence (ReAct)
              → pricing_strategy → copywriting (ReAct)
              → listing_critic
                  ├─ pass (≥70) → validation → package → END
                  ├─ rewrite (retry<2) → copywriting ← REWRITE LOOP
                  └─ replan → mission_planner ← REPLAN LOOP
```

> 그래프 책임: 판매글 패키지 생성까지.
> 게시·복구·판매후최적화는 SessionService가 노드 함수 직접 호출.

## Goal-driven 행동 변화

| | fast_sell | balanced | profit_max |
|---|----------|---------|-----------|
| 가격 배수 (high sample) | ×0.90 | ×0.97 | ×1.05 |
| 가격 배수 (low sample) | ×0.88 | ×0.95 | ×1.02 |
| 카피 톤 | 간결·긴급 | 실용·신뢰 | 프리미엄·가치 |
| 비평 기준 (price_threshold) | 1.4 | 1.3 | 1.5 |
| 비평 기준 (min_desc_len) | 30 | 50 | 80 |
| 비평 기준 (trust_penalty) | 5 | 10 | 15 |
| 네고 정책 | welcome, fast deal | small negotiation | firm price |
| 문의 응대 템플릿 | 긴급 유도 | 합리적 톤 | 프리미엄 톤 |

> 상세 상수: `app/domain/goal_strategy.py` 단일 원천 — PRICING_MULTIPLIER, COPYWRITING_TONE, CRITIC_CRITERIA, NEGOTIATION_POLICY, INQUIRY_REPLY_TEMPLATES 5개 딕셔너리.

## 마켓 거래 루프 (판매글 생성 이후)

판매글 생성 → 마켓 목록 노출 → 구매자 문의 → 판매자 응답 → 판매 상태 전이 → 재등록(옵션).

### 컴포넌트
- **마켓 목록/상세**: `market_router.py` 공개 엔드포인트 (검색·가격필터·정렬·페이지네이션)
- **AI 상품 챗봇**: `POST /market/{id}/chat` — 구매자용, 상품 정보(판매글+Vision AI+시세) 기반 답변 + 환각 방지 가드레일
- **문의 제출**: `POST /market/{id}/inquiry` — DB 저장 + Discord + Gmail SMTP 병렬 알림
- **판매자 대시보드**: `GET /my-listings` + 인증 (문의 관리, 상태 변경, 재등록, 코파일럿)
- **문의 코파일럿**: `POST /my-listings/{id}/inquiries/{inquiry_id}/suggest-reply` — LLM 초안 + goal별 fallback 템플릿 3종 (nego/condition/default)
- **재등록**: `POST /my-listings/{id}/relist` — 기존 세션 복제 + sale_status 초기화

### 판매 상태 머신
- **상태**: `available` / `reserved` / `sold` (3종)
- **전이 규칙** (`session_repository.py:SALE_STATUS_TRANSITIONS`):
  - `available` → reserved, sold
  - `reserved` → sold, available
  - `sold` → [] (terminal, 되돌릴 수 없음)
- **race condition 방어**: `eq("id", session_id).eq("user_id", user_id)` 조건부 업데이트 + `InvalidStateTransitionError` (409)

## 판매 후 최적화 (Agent 5)

- 입력: 경과 일수 + 판매 상태 + 문의 수
- 출력: `price_drop` / `rewrite` / `platform_add` 제안
- 트리거: `SaleTracker`가 completed → awaiting_sale_status_update → optimization_suggested 전이 관리
