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
| `lc_diagnose_publish_failure_tool` | 4 | 8종 에러 분류 진단 |
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
| 가격 배수 | ×0.90 | ×0.97 | ×1.05 |
| 카피 톤 | 간결·긴급 | 실용·신뢰 | 프리미엄·가치 |
| 비평 기준 | 관용적 (1회) | 표준 (2회) | 엄격 (3회) |
