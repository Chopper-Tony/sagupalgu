# 사구팔구 — 발표 자료

## 1. 프로젝트 소개 (1분)

**사구팔구**: 사진 한 장으로 중고거래 판매글 작성부터 게시까지 자동화하는 AI 플랫폼

**해결하는 문제**: 중고거래 판매자가 겪는 3대 고충
- 적정 가격을 모르겠다 → AI 시세 분석
- 판매글 쓰기 귀찮다 → AI 카피라이팅
- 여러 플랫폼에 올리기 번거롭다 → 멀티 플랫폼 동시 게시

**핵심 차별점**: 단순 파이프라인이 아닌 **LangGraph Agentic Workflow**
- LLM이 도구를 자율 선택 (ReAct 패턴)
- 자기 비평 → 재생성 루프
- 실패 시 전략 자체를 재수립

---

## 2. 아키텍처 (2분)

### 7 에이전트 · 10 툴 · 3 Agentic Loop

```
이미지 업로드
  ↓
Agent 0: Mission Planner ─── 목표 해석, 전략 수립
  ↓
Agent 1: Product Identity ── Vision AI로 상품 식별
  ↓
Pre-listing Clarification ── 부족한 정보 감지 → 사용자 질문
  ↓
Agent 2: Market Intelligence ── ReAct: 크롤링 + RAG 시세 분석
  ↓
Pricing Strategy ──────────── Goal별 가격 배수 적용
  ↓
Agent 3: Copywriting ──────── ReAct: 판매글 생성/재작성
  ↓
Agent 6: Listing Critic ───── LLM 품질 비평
  │
  ├─ score ≥ 70 → Agent 4: Validation → Package → 게시 준비
  ├─ score < 70 → Copywriting 재생성 (Rewrite Loop, 최대 2회)
  └─ rewrite 한도 초과 → Planner 재계획 (Replan Loop)
```

### Deterministic + Agentic 하이브리드

| 유형 | 에이전트 | 핵심 |
|---|---|---|
| **ReAct Agentic** | Market, Copywriting, Recovery | LLM이 툴을 **스스로 선택** |
| **LLM + Fallback** | Planner, Critic, Clarification | LLM 판단 + 룰 기반 안전망 |
| **Deterministic** | Product, Pricing, Post-sale | 예측 가능한 룰 기반 |

---

## 3. 에이전틱 핵심 포인트 (3분) — 발표의 핵심

### 3.1 자율적 도구 선택 (ReAct)

Agent 3 (Copywriting) 예시:
```
시스템: "당신은 판매글 작성 에이전트입니다. 도구: [generate_listing, rewrite_listing]"
LLM 판단: "rewrite_instruction이 있으므로 rewrite_listing을 호출하겠습니다"
→ lc_rewrite_listing_tool 호출 (LLM이 스스로 결정)
```

**실제 E2E 로그:**
```
agent3:react_agent:invoking LLM with tools=[generate_listing, rewrite_listing]
agent3:llm_selected_tool:lc_generate_listing_tool    ← 1차: LLM이 generate 선택
agent6:critic:rewrite score=65 retry=1/2              ← Critic: 65점, 재작성 지시
agent3:llm_selected_tool:lc_rewrite_listing_tool      ← 2차: LLM이 rewrite 선택
agent6:critic:pass score=90                            ← Critic: 90점, 통과
```

### 3.2 자기 비평 루프 (Critic Loop)

```
1차 생성: "애플 아이폰 15 Pro 스마트폰 판매합니다" → score=65 (부족)
  ↓ Critic 피드백: "제목에 용량/색상 키워드 추가, 가격 근거 설명"
2차 재작성: "애플 아이폰 15 Pro 256GB 실버 상태 최상" → score=90 (통과)
```

### 3.3 Goal-driven 행동 변화

같은 아이폰 15 Pro라도 **판매 목표에 따라 결과가 완전히 달라짐**:

| | fast_sell | balanced | profit_max |
|---|---|---|---|
| **가격** | 765,000원 (시세×0.90) | 824,000원 (시세×0.97) | 892,500원 (시세×1.05) |
| **톤** | "급처합니다" | "상태 양호, 협상 가능" | "프리미엄 컨디션" |
| **비평 기준** | 관용적 | 표준 | 엄격 |

### 3.4 Graceful Degradation

모든 LLM 노드에 룰 기반 fallback → LLM 장애에도 파이프라인 완주

```
ReAct 에이전트 실패 → 직접 도구 호출 → ListingService → 템플릿 생성
```

---

## 4. 기술 스택 (30초)

| 레이어 | 기술 |
|---|---|
| 백엔드 | FastAPI + Pydantic v2 |
| 워크플로우 | LangGraph 1.1 (StateGraph) |
| 에이전틱 | LangChain create_agent + bind_tools |
| LLM | Gemini 2.5 Flash → OpenAI → Solar (3단 fallback) |
| Vision | OpenAI GPT-4 Vision |
| DB | Supabase (PostgreSQL + pgvector) |
| 크롤러/게시 | Playwright (웹 자동화) |
| 프론트엔드 | React 18 + TypeScript + Vite |
| 배포 | Docker Compose |
| CI | GitHub Actions (unit → integration → full) |

---

## 5. E2E 데모 시나리오 (3분)

### 데모 준비
```bash
# 터미널 1: 백엔드
uvicorn app.main:app --reload

# 터미널 2: 프론트엔드
cd frontend && npm run dev
```

### 데모 흐름

**Step 1: 세션 생성** (새 세션 버튼 클릭)

**Step 2: 이미지 업로드** (상품 사진 드래그&드롭)
- Vision AI가 자동 분석
- "Panasonic Lumix DMC-TZ70 (신뢰도 90%)" 같은 후보 표시

**Step 3: 상품 확정** (직접 입력 또는 후보 선택)
- "Apple iPhone 15 Pro" 입력 → 확정

**Step 4: 판매글 자동 생성** (10~30초 소요)
- 시세 크롤링 (번개장터·중고나라 21개 매물)
- Goal-driven 가격 산정 (824,000원)
- ReAct 에이전트가 판매글 생성
- Critic이 65점 → 재작성 지시 → 90점 통과

**Step 5: 게시 플랫폼 선택** (번개장터 ✓ 중고나라 ✓)
- "게시 준비" 클릭

**Step 6: 게시** (Playwright가 자동으로 글 작성)
- 번개장터: 834,000원 (수수료 반영)
- 중고나라: 824,000원

### 데모 포인트 (강조할 것)
1. **ReAct 도구 선택**: "LLM이 generate를 선택했다가, Critic 피드백 후 rewrite를 선택"
2. **Critic 루프**: "65점 → 재작성 → 90점으로 품질 향상"
3. **실제 게시**: "Playwright가 브라우저에서 실제로 글을 작성하는 모습"

---

## 6. 대안 데모: CLI 스크립트 (서버 없이)

프론트엔드 없이 빠르게 보여줄 때:

```bash
# LangGraph 전체 파이프라인 실행
$env:PYTHONPATH = "C:\Users\bonjo\Desktop\sagupalgu_integrated_base"
python scripts/manual/run_seller_copilot_graph.py
```

**출력 포인트:**
- `debug_logs`에서 각 에이전트 실행 순서
- `tool_calls`에서 LLM이 선택한 도구 목록
- `critic_score` 변화 (65 → 90)
- `canonical_listing` 최종 판매글

---

## 7. 정량적 성과 (30초)

| 항목 | 수치 |
|---|---|
| 에이전트 | 7개 (3 ReAct + 3 LLM+Fallback + 1 Deterministic) |
| 툴 | 10개 (LangChain @tool 7개 + 내부 3개) |
| Agentic Loop | 3개 (Rewrite + Replan + Recovery) |
| 테스트 | 474개 통과 (unit + integration + E2E) |
| 마일스톤 | 55개 완료 |
| 코드 | 백엔드 ~5000줄, 프론트 ~2000줄, 테스트 ~3000줄 |
| 실제 게시 | 번개장터 ✅, 중고나라 ✅ (Playwright 자동화) |

---

## 8. 한계와 향후 계획 (30초)

| 항목 | 현재 | 향후 |
|---|---|---|
| 당근마켓 | 코드 완성, 에뮬레이터 보안 제약으로 미테스트 | 실기기 연결 시 즉시 가능 |
| pgvector RAG | SQL 마이그레이션 미적용 | Supabase 대시보드에서 1회 실행 |
| Pre-listing 질문 | 그래프 내 동작, API 연결 미완 | 프론트 질문/답변 UI 연결 |
| 동시 게시 | 순차 실행 | asyncio.gather로 병렬화 가능 |

---

## 9. Q&A 예상 질문

**Q: 왜 LangGraph를 선택했나?**
> StateGraph 기반 상태 머신으로 복잡한 분기(Critic 루프, Replan)를 선언적으로 표현 가능. 단순 체인과 달리 조건부 라우팅과 루프를 자연스럽게 지원.

**Q: ReAct와 단순 함수 호출의 차이는?**
> 함수 호출은 "어떤 도구를 쓸지" 개발자가 결정. ReAct는 LLM이 상황을 보고 자율 결정. 예: 시세 데이터가 부족하면 LLM이 RAG 추가 검색을 스스로 결정.

**Q: Critic이 왜 필요한가?**
> LLM 생성 결과의 품질이 일정하지 않음. Critic이 구매자 관점에서 평가하고 구체적 수정 지시를 내려 품질을 65점→90점으로 향상. 사람이 검수하는 것과 같은 역할.

**Q: fallback이 있으면 에이전틱이 아닌 것 아닌가?**
> fallback은 프로덕션 안정성을 위한 안전망. 정상 경로에서는 LLM이 자율 판단. 실제 E2E에서 ReAct가 도구를 선택하고 Critic이 비평하는 것이 확인됨. Graceful Degradation은 에이전틱과 상충하지 않음.

**Q: 실제 게시가 되나?**
> 번개장터와 중고나라에 실제 게시 성공 확인. Playwright로 브라우저를 자동화하여 로그인→글작성→등록→URL 검증까지 완료.
