# 사구팔구 (Sagupalgu) — AI 중고거래 자동 게시 플랫폼

> 사진 한 장으로 상품 분석부터 판매글 작성, 게시까지 자동화하는 LangGraph Agentic Workflow 플랫폼

[![Tests](https://img.shields.io/badge/tests-462%20passed-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11-blue)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)]()
[![React](https://img.shields.io/badge/React-18-61DAFB)]()

---

## 핵심 기능

- **이미지 → 상품 식별**: Vision AI로 사진에서 브랜드·모델·카테고리 자동 인식
- **시세 분석**: 번개장터·중고나라 크롤링 + pgvector RAG 검색으로 실시간 가격 산정
- **Goal-driven 전략**: 빠른 판매 / 균형 / 수익 극대화 목표에 따라 가격·문구·평가 기준이 달라짐
- **AI 카피라이팅**: LLM이 매력적인 판매글 자동 생성 + Critic 자기 비평 루프
- **멀티 플랫폼 게시**: 번개장터·중고나라 동시 게시 (Playwright 웹 자동화)
- **장애 진단**: 게시 실패 시 에러 분류(8종) → 자동 복구 가능 여부 판정 → 재시도

---

## 아키텍처

### 7 에이전트 · 10 툴 · 3 Agentic Loop

```
START
  → Mission Planner (목표 해석·계획 수립)
  → Product Identity (상품 식별)
  → Pre-listing Clarification (정보 부족 감지·질문)
  → Market Intelligence (ReAct: 크롤링 + RAG)
  → Pricing Strategy (Goal-driven 가격 배수)
  → Copywriting (ReAct: 판매글 생성/재작성)
  → Listing Critic (품질 비평)
       ├─ pass → Validation → Package → END
       ├─ rewrite → Copywriting (재생성 루프, 최대 2회)
       └─ replan → Mission Planner (전략 재수립)
```

### Deterministic + Agentic 하이브리드

| 유형 | 에이전트 | 특징 |
|---|---|---|
| **ReAct Agentic** | Market Intelligence, Copywriting, Validation/Recovery | LLM이 툴을 자율 선택 |
| **LLM + Fallback** | Mission Planner, Listing Critic, Pre-listing Clarification | LLM 비평 + 룰 기반 안전망 |
| **Deterministic** | Product Identity, Pricing Strategy, Post-sale Optimization | 룰 기반, 예측 가능 |

### Goal-driven 행동 변화

같은 상품이라도 판매 목표에 따라 결과가 달라집니다:

| | fast_sell | balanced | profit_max |
|---|---|---|---|
| 가격 | 시세 ×0.90 | 시세 ×0.97 | 시세 ×1.05 |
| 톤 | 간결·긴급 | 실용·신뢰 | 프리미엄·가치 |
| 비평 | 관용적 | 표준 | 엄격 |

> 상세 아키텍처 문서: [docs/architecture.md](docs/architecture.md)

---

## 기술 스택

| 레이어 | 기술 |
|---|---|
| **백엔드** | FastAPI + Pydantic v2 |
| **워크플로우** | LangGraph 1.1 (StateGraph) |
| **에이전틱** | LangChain create_agent + bind_tools |
| **LLM** | Gemini 2.5 Flash (primary) → OpenAI → Solar (fallback) |
| **Vision** | OpenAI (실동작) · Gemini (mock — 향후 연동 예정) |
| **DB** | Supabase (PostgreSQL + pgvector) |
| **크롤러** | Playwright (웹 자동화) |
| **프론트엔드** | React 18 + TypeScript + Vite |
| **배포** | Docker Compose (backend + frontend nginx) |

---

## 빠른 시작

### Docker (권장)

```bash
# 1. 환경 변수 설정
cp .env.example .env
# .env 파일에 API 키 입력 (OPENAI_API_KEY, GEMINI_API_KEY, SUPABASE_URL 등)

# 2. 실행
docker compose up --build

# 프론트엔드: http://localhost
# 백엔드 API: http://localhost:8000
# API 문서: http://localhost:8000/docs
```

### 로컬 개발

```bash
# 백엔드
pip install -r requirements.txt
python -m playwright install chromium
uvicorn app.main:app --reload

# 프론트엔드 (별도 터미널)
cd frontend && npm install && npm run dev
```

---

## 테스트

```bash
# 전체 테스트 (462개)
python -m pytest tests/

# unit 테스트만 (0.5초)
python -m pytest tests/ -m unit

# integration 테스트만
python -m pytest tests/ -m integration

# E2E happy path
python -m pytest tests/api/test_e2e_happy_path.py -v
```

### 테스트 구조

| 카테고리 | 테스트 수 | 내용 |
|---|---|---|
| **Unit** | ~300 | 순수 함수, 도메인 로직, goal 전략, 에러 분류 |
| **Integration** | ~120 | 노드 실행, API 엔드포인트, contract 검증 |
| **E2E** | 3 | 전체 세션 라이프사이클 8단계 체인 |
| **Sync** | 5 | 백엔드-프론트엔드 타입 drift 감지 |

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/v1/sessions` | 세션 생성 |
| POST | `/api/v1/sessions/{id}/images` | 이미지 업로드 (multipart) |
| POST | `/api/v1/sessions/{id}/analyze` | 상품 분석 |
| POST | `/api/v1/sessions/{id}/provide-product-info` | 상품 정보 입력 |
| POST | `/api/v1/sessions/{id}/generate-listing` | 판매글 생성 |
| POST | `/api/v1/sessions/{id}/rewrite-listing` | 판매글 재작성 |
| POST | `/api/v1/sessions/{id}/prepare-publish` | 게시 준비 |
| POST | `/api/v1/sessions/{id}/publish` | 게시 실행 |
| POST | `/api/v1/sessions/{id}/sale-status` | 판매 상태 업데이트 |
| GET | `/health/ready` | 헬스체크 (provider-aware) |

---

## 프로젝트 구조

```
app/
├── api/            # FastAPI 라우터
├── domain/         # 상태 머신, 스키마, 예외, goal 전략, 게시 정책
├── graph/          # LangGraph StateGraph, 노드, 라우팅
│   └── nodes/      # 7개 에이전트 노드 모듈
├── tools/          # 10개 에이전틱 툴 (agentic_tools facade)
├── services/       # 비즈니스 로직 (세션, 리스팅, 게시, 복구)
├── publishers/     # 플랫폼별 게시 어댑터
├── db/             # Supabase + pgvector 클라이언트
└── core/           # 설정, 로깅, 유틸리티
frontend/
├── src/components/ # React 카드 컴포넌트 (13개 상태 커버)
├── src/hooks/      # 스마트 폴링 (useSession)
├── src/lib/        # API 클라이언트, 상태 매핑
└── src/types/      # TypeScript 타입 (자동 동기화)
tests/              # 462개 테스트 (unit + integration + E2E)
docs/               # 아키텍처 문서, 배포 가이드
```

---

## 환경 변수

`.env.example` 참조. 주요 변수:

| 변수 | 필수 | 설명 |
|---|---|---|
| `SUPABASE_URL` | O | Supabase 프로젝트 URL |
| `SUPABASE_SERVICE_ROLE_KEY` | O | Supabase 서비스 키 |
| `OPENAI_API_KEY` | △ | OpenAI API 키 (LLM fallback + 임베딩) |
| `GEMINI_API_KEY` | △ | Gemini API 키 (primary LLM) |
| `BUNJANG_USERNAME` / `PASSWORD` | △ | 번개장터 계정 (게시 시) |
| `JOONGNA_USERNAME` / `PASSWORD` | △ | 중고나라 계정 (게시 시) |

> △ = LLM provider 중 하나 이상 필요, 게시 시 해당 플랫폼 계정 필요

---

## 라이선스

이 프로젝트는 학술 목적으로 개발되었습니다.
