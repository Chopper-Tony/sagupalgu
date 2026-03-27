# CLAUDE.md

## 프로젝트 개요

중고거래(번개장터, 중고나라) 자동 게시 플랫폼.
이미지 → AI 분석 → 가격 산정 → 카피라이팅 → 게시 → 복구의 파이프라인을
LangGraph Agentic Workflow로 구현. 7 에이전트 / 10 툴 / 3 Agentic Loop.

> 당근마켓은 Android 에뮬레이터 기반, 현재 실험적 지원.

## 기술 스택

- **백엔드**: FastAPI + Pydantic v2
- **워크플로우**: LangGraph 1.1.3 (`app/graph/`)
- **에이전틱**: `langchain.agents.create_agent` + bind_tools
- **Vision AI**: OpenAI gpt-4.1-mini (기본) / Gemini 2.5 Flash (설정 전환)
- **Listing LLM**: OpenAI gpt-4.1-mini → Gemini → Solar (fallback 체인)
- **DB**: Supabase (PostgreSQL + pgvector)
- **크롤러/게시**: Playwright (웹 자동화)
- **프론트엔드**: React 18 + TypeScript + Vite
- **배포**: Docker Compose + GitHub Actions CI/CD

## 주요 명령어

```bash
# 의존성 설치
pip install -r requirements.txt
pip install langchain-google-genai langchain-openai
python -m playwright install chromium

# FastAPI 서버
uvicorn app.main:app --reload

# 프론트엔드 (별도 터미널)
cd frontend && npm install && npm run dev

# Docker 풀스택
docker compose up --build

# 테스트 (508개)
python -m pytest tests/           # 전체
python -m pytest tests/ -m unit   # unit만 (0.5초)
```

## 레이어 구조

- `app/domain/` — 상태 머신(SessionStatus SSOT), 스키마, 예외, Goal 전략, 게시 정책
- `app/graph/` — LangGraph StateGraph, 노드, 라우팅 (lazy import)
  - `nodes/` — 7개 에이전트 노드 모듈
- `app/tools/` — 10개 툴 (`agentic_tools.py` 단일 facade)
- `app/services/` — 비즈니스 로직 (세션, 리스팅, 게시, 복구, 최적화)
- `app/publishers/` — 플랫폼별 게시 adapter (Playwright)
- `app/vision/` — Vision AI provider (OpenAI, Gemini)
- `app/db/` — Supabase 클라이언트 + pgvector
- `app/core/` — 설정, 로깅, 유틸리티
- `app/api/` — FastAPI 라우터
- `app/dependencies.py` — DI 체인 (lru_cache 싱글턴)
- `frontend/` — React SPA (13개 상태 카드, SSE 실시간)
- `legacy_spikes/` — **읽기 전용**, 직접 수정 금지
- `tests/` — 508개 (unit ~300 + integration ~120 + E2E 3 + sync 5)

## 핵심 코딩 규칙

상세 규칙: @.claude/rules/coding-rules.md

- **상태 머신**: `session_status.py` SSOT, `expected_status` 원자적 전이
- **툴 import**: `app.tools.agentic_tools` 단일 facade만 사용
- **예외**: `app/domain/exceptions.py`에 정의, `main.py` 글로벌 핸들러 단일
- **DI**: `app/dependencies.py` Depends()로만 주입, 라우터에서 직접 생성 금지
- **lazy import**: supabase·langgraph·langchain은 함수 내부에서만 import
- **테스트**: LLM 응답 의존 assertion 금지, fallback 경로만 검증
- **legacy**: `legacy_spikes/` 수정 금지 → `app/publishers/`에서 패치
- **Agent trace**: tool_calls·critic_score 등 그래프→서비스→DB→UI 보존 필수

## 아키텍처 상세

상세: @.claude/rules/architecture.md

**Production Path**: SessionService/SellerCopilotService 하이브리드 오케스트레이션.
서비스가 상품 식별·시세 분석 선처리, LangGraph는 가격 전략→카피→비평→검증→패키징 담당.
게시·복구·최적화는 SessionService가 노드 함수 직접 호출.

## 프론트엔드

상세: @.claude/rules/frontend.md

- ChatGPT 스타일 대화형 UI, 다크 테마
- 13개 상태별 카드 컴포넌트
- SSE 실시간 + 폴링 fallback
- 웹 UI 플랫폼 로그인 (Playwright 브라우저 → 쿠키 저장)

## 현재 미완성 항목

- pgvector 활성화: `migrations/001_pgvector_setup.sql` 실행 후 `python scripts/setup_pgvector.py --seed`
- 당근마켓 게시 본격 구현 (Android 에뮬레이터)
- Supabase Storage Public 버킷 생성 (코드는 완료)

## 최근 변경 (이번 세션)

- **M77**: rewrite 회귀 봉합 — ReAct 실패 시 fallback rewrite 재시도 + 회귀 방지 테스트
- **M78**: Vision 프롬프트 품질 검증 15개 테스트 + 수동 실테스트 스크립트
- **M81**: 게시 성공률 안정화 — 카테고리 실패 예외, 타임아웃 180초, 에러 3종 추가, 세션 만료 감지
- **M82**: 데모 리허설 스크립트 (`scripts/manual/demo_rehearsal.py`) + golden session 백업
- **M83**: Agent Decision Visualization — DraftCard에 도구 호출 이력·실행 전략·의사결정 근거 시각화
- Vision AI 프롬프트 개선 — 30종 카테고리 예시, 오인식 방지 지시, 한국어 대응
- 번개장터 수수료: +10,000원 고정 → ×1.035 (실 수수료율 3.5%)
- 게시 후 대기: 30초 → 5초
- DraftCard AI 품질 평가: 표(table) 형식으로 개선
- 게시 완료 카드 중복 표시 버그 수정
- CLAUDE.md: 공식 가이드 기반 재구성 (1300줄 → 100줄, `.claude/rules/` 분할)

## 마일스톤 이력

82+ 마일스톤 완료. 상세: @docs/milestones.md
