# 에이전트 · 툴 · 그래프 아키텍처 (5 + 2 + 4)

> PR1~4 리팩터 결과. 명목상 7 에이전트 → 실제 selection을 수행하는 5 에이전트 + 2 단일툴 + 4 결정론으로 재분류.
> PR4 에서 `product_identity_node` 가 결정론 노드 → Tool Agent (ReAct) 로 승격되며 4+2+5 → 5+2+4 로 변동.
> 정책 단일 원천: `app/domain/critic_policy.py`.

## 5 에이전트 (selection 수행)

| 분류 | 노드 | 결정 책임 |
|---|---|---|
| **Strategy Agent** | `mission_planner_node` | 4 정책 필드 결정: plan_mode / market_depth / critic_policy / clarification_policy. POLICY_COMBO_RULES 위반 정규화. replan 시 strict 강화 |
| **Tool Agent (ReAct)** | `product_identity_node` | **PR4-2 승격**. lc_image_reanalyze_tool / lc_rag_product_catalog_tool / lc_ask_user_clarification_tool 자율 선택. confidence·정보 보강. `enable_product_identity_agent=False` 또는 LLM 실패 시 PR4-cleanup 의 deterministic 로직 100% 보존 (5단계 fallback chain) |
| **Tool Agent (ReAct)** | `market_intelligence_node` | lc_market_crawl_tool + lc_rag_price_tool 자율 선택. market_depth='crawl_only'면 RAG 제외 |
| **Routing Agent** | `listing_critic_node` | LLM이 score + repair_action(7값) + failure_mode + rewrite_plan 결정. critic_policy로 엄격도 동적 |
| **Tool Agent (ReAct)** | `recovery_node` | lc_diagnose / lc_auto_patch / lc_discord_alert 자율 선택 |

## 2 단일 툴 노드 (LLM 호출하나 selection 없음)

| 노드 | 동작 | 비고 |
|---|---|---|
| `copywriting_node` | critic이 정해준 rewrite_plan(target/instruction)을 실행. rewrite_plan 없으면 신규 generate. ListingService → rule-based → template fallback 체인 (결정론 안전망) | "Single Tool Node with deterministic fallback chain" |
| `clarification_node` | state로 모드 자동 분기 (product 식별 대기 / pre_listing 질문 생성). clarification_policy로 적극성 조절 | PR3 통합 (구 `pre_listing_clarification_node` + `product_agent.clarification_node`) |

## 4 결정론 노드 (LLM 없음)

| 노드 (PR1 알리아스) | 동작 |
|---|---|
| `pricing_strategy_node` (= `pricing_rule_node`) | goal_strategy 모듈 기반 규칙 산정 |
| `validation_node` (= `validation_rules_node`) | 필수 필드·길이·가격 검사 + **자동 보강 흡수** (description 짧음 / price 0원) + repair_action_hint |
| `post_sale_optimization_node` (= `post_sale_policy_node`) | sale_status 기반 price_optimization_tool 결정론적 호출 |
| `package_builder_node` | canonical → 플랫폼별 패키지 (번개장터 수수료 3.5% 보전 등) |

> `product_identity_node` 는 PR4-2 에서 Tool Agent 로 승격. 5 결정론 → 4 결정론.

## 13 툴

| 툴 | 에이전트 | 기능 |
|----|---------|------|
| `lc_image_reanalyze_tool` | 1 (Product Identity) | **PR4-2 신규**. focus(ocr/spec/category_hint) 다른 prompt 로 Vision 재분석. 한 세션 최대 2회 + SHA256 1h TTL 캐시 |
| `lc_rag_product_catalog_tool` | 1 (Product Identity) | **PR4-2 신규**. PR4-1 hybrid_search_catalog (sessions sold + price_history) 호출. cold_start flag 포함 |
| `lc_ask_user_clarification_tool` | 1 (Product Identity) | **PR4-2 신규**. 사용자 식별 질문 발행. 한 세션 최대 1회 |
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

## 그래프 플로우 (PR3 이후)

```
START → planner (Strategy: 4 정책) → product_identity
  ├─ needs_user_input → clarification → END
  └─ confirmed → pre_listing_clarification
       ├─ needs_more_info → END (사용자 대기)
       └─ enough_info → [route_after_planner: market_depth 분기]
              ├─ skip 가드 통과 → pricing_strategy ← SKIP PATH
              └─ 그 외 → market_intelligence (ReAct, Tool Agent)
                          → pricing_strategy → copywriting (Single Tool Node)
                          → listing_critic (Routing Agent: repair_action 결정)
                              ├─ pass               → validation → package → END
                              ├─ rewrite_*          → copywriting   ← REWRITE LOOP
                              ├─ reprice            → pricing_strategy ← REPRICE LOOP
                              ├─ clarify            → clarification → END
                              └─ replan             → planner       ← REPLAN LOOP
```

## repair_action 라우팅 (PR2)

| repair_action | 다음 노드 | 의미 |
|---|---|---|
| `pass` | validation_node | 품질 충분 |
| `rewrite_title` / `rewrite_description` / `rewrite_full` | copywriting_node | 부분/전체 재작성 |
| `reprice` | pricing_strategy_node | 가격만 재산정 |
| `clarify` | clarification_node | 사용자 추가 정보 요청 |
| `replan` | mission_planner_node | plan 수정 (MAX_PLAN_REVISIONS=2 가드) |

## 정책 매트릭스 (PR3 planner 산출)

| | shallow | balanced | deep |
|---|---|---|---|
| 의미 | 빠른 경로, 정보 풍부 | 기본 | 정보 부족 / replan |
| critic_policy 허용 (POLICY_COMBO_RULES) | minimal, normal | minimal, normal, strict | normal, strict |
| 권장 market_depth | skip / crawl_only | crawl_plus_rag | crawl_plus_rag |
| 권장 clarification_policy | ask_late | ask_early | ask_early |

## Skip 가드 (PR3 _skip_allowed)

market_depth='skip'은 아래 조건 중 1개 이상 충족 시만 실제 적용. 미충족 시 silent crawl_only fallback + `skip_rejected_reason` 기록.

1. `state.user_product_input.price` 존재
2. `state.market_context` 잔존 (replan 케이스)
3. `plan_mode == "shallow"` AND `confirmed_product.category in LOW_RISK_SKIP_CATEGORIES`

## Failure Mode Taxonomy (PR2)

- **System** (안전망 발동, 운영 알람 후보): `critic_parse_error`, `replan_limit_reached`, `max_critic_retries_reached`, `missing_listing`
- **Critic Decision** (정상 동작): `title_weak`, `description_weak`, `price_off`, `info_missing`, `untrusted_seller`, `general_quality`

## 노드 이름 일관성 원칙 (PR4-cleanup)

리팩터 시리즈에서 alias/deprecated stub를 모두 제거한 뒤 정착된 단일 이름 체계.
이 원칙이 흔들리면 라우팅이 KeyError로 깨지거나, 분류와 export가 어긋나 디버깅이 어려워진다.

1. **`routing.py` 반환 문자열은 graph builder의 `add_node` 정식 이름과 1:1 매칭**한다.
   legacy 이름은 더 이상 허용하지 않는다. 단 한 가지 예외 — `route_after_product_identity`
   가 `pre_listing_clarification_node`를 반환하는 경로는 graph builder dict가 통합
   `clarification_node`로 매핑한다 (last legacy seam).
   - **TODO(post-PR5)**: 이 마지막 seam도 제거해 routing이 직접 `clarification_node`를 반환하게.
2. **`nodes/__init__.py` `__all__` 분류**는 본 문서의 분류표와 동일하게 유지한다
   (Strategy / Tool / Routing / Single Tool / Deterministic / Side-effect).
   새 노드 추가 시 본 문서·`__all__`·`CLAUDE.md` 세 곳을 같은 PR에서 갱신.
3. **Deprecated alias 부활 금지**: PR1 알리아스(`product_identity_node` 등)와
   deprecated stub(`refinement_node`, `pre_listing_clarification_node`,
   `product_agent.clarification_node`)은 PR4-cleanup에서 제거됨. 호환성 위해
   `# REMOVED: use <new_name>` 주석은 각 모듈 끝에 남아있다 — 이것이 실수로
   다시 alias로 변환되지 않게.

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

## Product Identity 카탈로그 sync flow (PR4-1·4-2·4-3)

```
[sell_sessions: status=completed AND sale_status=sold]
        │  (cron 일 1회 또는 수동 trigger)
        ▼
[scripts/cron/sync_catalog.py]
        │
        ▼
[app/services/catalog_sync_service.py
  · cursor 읽기 (catalog_sync_cursor)
  · 신규/갱신된 sold session 만 batch 추출
  · 정규화 (브랜드 alias, 모델, 카테고리)
  · OpenAI text-embedding-3-small 임베딩
  · price_history INSERT (source_type='sell_session')
  · cursor write]
        │
        ▼
[Supabase price_history (pgvector)] ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
                                                              │
[product_identity_agent ReAct]                                 │
        │                                                      │
        ▼ (LLM 자율 호출)                                        │
[lc_rag_product_catalog_tool]                                  │
        │                                                      │
        ▼                                                      │
[app/db/product_catalog_store.hybrid_search_catalog]            │
  · vector RPC (vector_search_catalog_hybrid) ─────────────────┘
  · 실패 시 keyword RPC (keyword_search_catalog_hybrid)
  · 그래도 실패 시 Python ILIKE fallback (CTO PR4-1 #2)
  · cold_start 판정 (hits<3 OR top_conf<0.5)
        │
        ▼
[ToolMessage(cold_start=bool, matches=[...])]
        │
        ▼
[product_agent._extract_catalog_cold_start → state.product_identity_catalog_cold_start]
        │
        ▼
[app/middleware/metrics.emit_product_identity_run]
        · cold_start_rate / fallback_rate 누적
        · compute_alert_status: cold_start>20% OR fallback>10% (표본>=20) → alert
```

> Feature flag 2개로 단계적 rollout: `ENABLE_CATALOG_HYBRID` (PR4-1) → `ENABLE_PRODUCT_IDENTITY_AGENT` (PR4-2). 둘 다 default=False (opt-in).

## Product Identity 운영 runbook (PR4-3)

### Threshold 튜닝 (CTO PR4-3 #2)

`COLD_START_ALERT_THRESHOLD=0.20` / `FALLBACK_ALERT_THRESHOLD=0.10` 은 **임시 static 값**이다.
실제 분포 모르는 상태에서 도입한 reasonable default — 운영 진입 후 baseline 으로 재조정.

절차:
1. **Day 0~3**: `ENABLE_CATALOG_HYBRID=true` + `ENABLE_PRODUCT_IDENTITY_AGENT=true` 활성화 후 표본 ≥ 100 누적까지 alert 무시
2. **Day 4**: `compute_diagnostic_breakdown()` snapshot 으로 baseline 측정
   - cold_start_rate baseline → 그 +50% 를 신규 threshold (예: baseline 12% → 18%)
   - fallback_rate baseline → 그 +100% 를 신규 threshold (fallback 은 더 민감하게)
3. **Day 7~**: trend 기반 alert 추가 — 전일 대비 cold_start +5%p OR fallback +3%p 급증 시 알림 (baseline 절대치보다 변화량이 더 의미)

코드 변경 위치: `app/middleware/metrics.py` 의 `COLD_START_ALERT_THRESHOLD` / `FALLBACK_ALERT_THRESHOLD` 상수.
trend 비교는 별도 store (Redis 또는 SQL) 도입 시 추가.

### Rollout / Rollback 기준 (CTO PR4-3 #5)

**Rollout (off → on)**
- PR4-1 (`ENABLE_CATALOG_HYBRID`):
  - 전제: migration 005 dev/prod 적용 완료 + `scripts/cron/sync_catalog.py --dry-run` 정상
  - on 후 24h 표본 ≥ 30 + RPC 에러율 < 5%
- PR4-2 (`ENABLE_PRODUCT_IDENTITY_AGENT`):
  - 전제: PR4-1 7일 안정 (cold_start_rate baseline 확정)
  - on 후 48h 표본 ≥ 50 + fallback_rate < 15% + agent vs deterministic delta 평균 ≥ -0.05 (quality regression 방지)

**Rollback (on → off)**
즉시 `.env` 토글 + `docker compose restart`. 기준:
- fallback_rate > 25% (1h window)
- cold_start_rate > 40% (1h window) — 카탈로그 데이터 또는 RPC 자체 문제
- agent vs deterministic delta 평균 < -0.15 — quality 명백히 하락
- LLM 비용 일일 예산 1.5배 초과

**Diagnostic 우선순위** (compute_diagnostic_breakdown 의 failure_modes 분포로 판정)
- `react_exception` 우세 → LLM provider 장애 의심 → fallback chain 점검
- `parse_error` 우세 → system_prompt 응답 형식 drift → prompt 재정렬
- `react_total_budget_exceeded` 우세 → 무한 루프 케이스 발생 → max_iterations / tool budget 재검토
- `clarify_forced_by_heuristic` 우세 → vision 품질 하락 → identify_product fallback 점검
