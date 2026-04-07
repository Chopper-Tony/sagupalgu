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
- **배포**: Docker Compose + Caddy HTTPS + GitHub Actions CI/CD
- **보조 스토리지**: S3 (게시 증적 스크린샷 아카이빙)

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

# 백엔드 테스트 (688개)
pip install -r requirements-dev.txt
python -m pytest tests/           # 전체
python -m pytest tests/ -m unit   # unit만 (0.5초)

# 프론트엔드 테스트 (21개)
cd frontend && npm test
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
- `tests/` — 688개 (unit ~380 + integration ~180 + E2E 3 + sync 5 + infra 6)
- `frontend/src/lib/__tests__/` — 프론트엔드 21개 (vitest + @testing-library/react)

## 핵심 코딩 규칙

상세 규칙: @.claude/rules/coding-rules.md

- **상태 머신**: `session_status.py` SSOT, `expected_status` 원자적 전이
- **툴 import**: `app.tools.agentic_tools` 단일 facade만 사용
- **예외**: `app/domain/exceptions.py`에 정의, `main.py` 글로벌 핸들러 단일
- **DI**: `app/dependencies.py` Depends()로만 주입, 라우터에서 직접 생성 금지
- **lazy import**: supabase·langgraph·langchain은 함수 내부에서만 import
- **Settings**: `config.py`의 `settings`는 `_SettingsProxy` lazy 프록시 — import 시점 초기화 없음
- **테스트**: LLM 응답 의존 assertion 금지, fallback 경로만 검증
- **legacy**: `legacy_spikes/` 수정 금지 → `app/publishers/`에서 패치
- **Agent trace**: tool_calls·critic_score 등 그래프→서비스→DB→UI 보존 필수
- **인증**: `app/core/auth.py` JWT 검증 + 전 엔드포인트(SSE 포함) 소유권 검증, DB 레벨 user_id 필터
- **Rate limit**: `app/middleware/rate_limit.py` in-memory sliding window, 경로 그룹별 bucket
- **Rewrite 정책**: rewrite_instruction 있으면 template 신규 생성 금지, 기존 listing 유지
- **게시 동시성**: `MAX_CONCURRENT_BROWSERS=2` 세마포어로 Playwright 동시 실행 제한

## 아키텍처 상세

상세: @.claude/rules/architecture.md

**Production Path**: SessionService/SellerCopilotService 하이브리드 오케스트레이션.
서비스가 상품 식별·시세 분석 선처리, LangGraph는 가격 전략→카피→비평→검증→패키징 담당.
게시·복구는 PublishOrchestrator, 판매 후 최적화는 SaleTracker가 담당.

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

- **M122**: 게시 링크 정합성 — publish_worker 결과 누적 저장(먼저 완료된 플랫폼 URL 소실 방지), 번개장터 리다이렉트 폴링 30초, 중고나라 completeSeq URL 파싱, 프론트 확정 메시지/스크롤/게시결과 카드 개선
- **M122~M124**: Job Queue 프로덕션 안정화 — Admin API 키 인증(`X-Admin-Key`), 워커 모니터링(`status()`), `/health/ready` 워커 상태, 큐 적체 Discord 알림, 게시 진행 SSE(`job_progress` → ProgressCard 플랫폼별 뱃지)
- **M125~M129**: 프로덕션 배포 준비 — Worker 프로세스 분리(`RUN_PUBLISH_WORKER`), FastAPI lifespan 전환(on_event deprecated 제거), Worker graceful shutdown(active task drain), Prod readiness gate 강화(admin/queue/JWT 검증), 전달물 위생(.env.example), requirements 완전 고정
- **Bugfix #114, #116**: Job Queue 워커 버그 6건 수정 — 테이블명/컬럼명 정합화(`sell_sessions`/`status`), `PublishResult` 속성명, `publish_results` 키 일치, legacy 대기시간 30초→3초, stale job 방지, enum `.value`, PublishResultCard 링크 복원, 스크롤 UX
- **M121**: Publish Job Queue 도입 — `publish_jobs` 테이블, 비동기 워커, per-account lock(DB 유니크 인덱스), admin 엔드포인트(재시도/강제 fail/플랫폼 중지), 단계별 타임아웃, structured logging, `PUBLISH_USE_QUEUE` 설정
- **M117~M120**: 프로덕션 안정성 Phase 1 — requirements 버전 고정, except 세분화, Caddy healthcheck
- **M117**: requirements.txt 버전 고정(`>=`→`==`) + `requirements-dev.txt` 분리(테스트 패키지)
- **M118**: except Exception 세분화 — auth/optimization 구체화 2건, 외부 경계 exc_info 로깅 강화 18건
- **M120**: Caddy healthcheck + Docker rolling restart + named volumes 영속성
- **M116**: AWS 인프라 최적화 — Caddy HTTPS 리버스 프록시(`docker-compose.prod.yml`), S3 보조 스토리지(게시 증적 스크린샷), EC2 스왑 설정, `deployment.md` 전면 재작성
- **M115**: 게시 안정성 개선 — 이벤트 루프 블로킹 해소(`asyncio.to_thread`), 번개장터 카테고리 3단계 보완 + 폼 입력 순서 수정, pgvector/Gemini 캐싱, LLM 타임아웃 30초
- **M114** (Phase B v7): Playwright 동시성 세마포어 + 워커 분리 로드맵 문서화

- **M100** (Phase A): Rewrite 강제 정책 — template fallback 완전 차단, 기존 listing 유지
- **M101** (Phase A): 소유권 검증 — 전 엔드포인트 get_current_user + user_id 검증, 403
- **M102** (Phase B): Rate Limit 키 재설계 — 경로 그룹별 독립 bucket
- **M103** (Phase B): Broad Exception 정리 — 핵심 노드 세분화, 57건→46건
- **M104** (Phase C): Prod 점검 스크립트 — CORS/debug/JWT/LLM/publisher 자동 검증
- **M105** (Phase C): Smoke Test 스크립트 — health + 세션 API 자동 검증
- **M106** (Phase D): Market 서비스 유닛 테스트 — QueryBuilder/RelevanceScorer/PriceAggregator 25개
- **M107** (Phase D): ListingService + ProductService 통합 테스트 22개
- **M108** (Phase D): 프론트엔드 테스트 인프라 — vitest + 21개 스모크 테스트
- **M110** (Phase A v7): SSE stream 소유권 검증 + rewrite 테스트 mock 강화
- **M111** (Phase A v7): SessionRepository DB 레벨 소유권 검증 (`get_by_id_and_user`)
- **M112** (Phase A v7): Rate Limit 경로 그룹별 bucket 적용 확인
- **M113** (Phase B v7): `copywriting_agent` 슬림화 — `_resolve_final_listing` 정책 함수 분리

## 마일스톤 이력

116+ 마일스톤 완료. 상세: @docs/milestones.md
