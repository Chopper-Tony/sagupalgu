# CLAUDE.md

## 프로젝트 개요

중고거래(번개장터, 중고나라) 자동 게시 + 자체 마켓 플랫폼.
이미지 → AI 분석 → 가격 산정 → 카피라이팅 → 게시 → 복구의 파이프라인을
LangGraph Agentic Workflow로 구현. 7 에이전트 / 10 툴 / 3 Agentic Loop.

게시는 크롬 익스텐션 Content Script 방식 (서버 Playwright → 계정 정지로 전환).
자체 마켓(`#/market`, `#/my-listings`)에서 판매 상태 관리 + 문의 응답 + 셀러 코파일럿 제공.

## 기술 스택

- **백엔드**: FastAPI + Pydantic v2
- **워크플로우**: LangGraph (`app/graph/`), `langchain.agents.create_agent` + bind_tools
- **Vision AI**: OpenAI gpt-4.1-mini (기본) / Gemini 2.5 Flash
- **Listing LLM**: OpenAI gpt-4.1-mini → Gemini → Solar (fallback 체인)
- **DB**: Supabase (PostgreSQL + pgvector)
- **게시**: 크롬 익스텐션 Content Script (CDP 이미지 업로드)
- **프론트엔드**: React 18 + TypeScript + Vite
- **배포**: Docker Compose (4 컨테이너) + Caddy HTTPS + GitHub Actions CI/CD

## 주요 명령어

```bash
pip install -r requirements.txt && python -m playwright install chromium
uvicorn app.main:app --reload
cd frontend && npm install && npm run dev

# 테스트
pip install -r requirements-dev.txt
python -m pytest tests/ -m unit     # unit (~525개, 5초)
cd frontend && npm test             # FE 21개 (vitest)

# Docker
docker compose up --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build  # prod
```

## 레이어 구조

- `app/domain/` — 상태 머신(SessionStatus SSOT), 스키마, 예외, Goal 전략, 게시 정책
- `app/graph/nodes/` — 7개 에이전트 노드 (lazy import)
- `app/tools/` — 10개 툴 (`agentic_tools.py` 단일 facade)
- `app/services/` — 세션, 리스팅, 게시, 복구, 최적화, 셀러 코파일럿, 판매 추적
- `app/publishers/` — 플랫폼별 게시 adapter
- `app/api/` — `session_router.py` (세션), `market_router.py` (마켓 + 판매자 대시보드)
- `app/repositories/` — `session_repository.py`, `inquiry_repository.py`
- `app/dependencies.py` — DI 체인 (lru_cache 싱글턴)
- `frontend/src/pages/` — MarketPage, MarketDetailPage, MyListingsPage
- `sagupalgu-extension/` — 크롬 익스텐션 (Manifest V3, Content Script)
- `legacy_spikes/` — **읽기 전용**, 직접 수정 금지

## 핵심 코딩 규칙

상세: @.claude/rules/coding-rules.md

- **상태 머신**: `session_status.py` SSOT, `expected_status` 원자적 전이
- **툴 import**: `app.tools.agentic_tools` 단일 facade만 사용
- **예외**: `app/domain/exceptions.py`에 정의, `main.py` 글로벌 핸들러 단일 (`_DOMAIN_STATUS_MAP`)
- **DI**: `app/dependencies.py` Depends()로만 주입, 라우터에서 직접 생성 금지
- **lazy import**: supabase·langgraph·langchain은 함수 내부에서만 import
- **Settings**: `config.py`의 `settings`는 `_SettingsProxy` lazy 프록시
- **테스트**: LLM 응답 의존 assertion 금지, fallback 경로만 검증
- **legacy**: `legacy_spikes/` 수정 금지 → `app/publishers/`에서 패치
- **인증**: `app/core/auth.py` JWT, dev 환경 `X-Dev-User-Id` bypass, prod에서는 차단 (403)
- **게시 동시성**: `MAX_CONCURRENT_BROWSERS=2` 세마포어

## 아키텍처

상세: @.claude/rules/architecture.md

- **Production Path**: SessionService + SellerCopilotService 하이브리드 오케스트레이션
- **게시**: PublishOrchestrator → 크롬 익스텐션 Content Script (서버 Playwright 아님)
- **판매 추적**: SaleTracker → OptimizationService
- **마켓**: market_router.py — 공개 목록/상세/검색 + 판매자 대시보드/문의 관리/재등록/코파일럿

## 프론트엔드

상세: @.claude/rules/frontend.md

- ChatGPT 스타일 대화형 UI, 다크 테마, 13개 상태별 카드
- SSE 실시간 + 폴링 fallback
- 해시 라우팅: `#/` (셀러 코파일럿), `#/market` (마켓), `#/market/{id}` (상세), `#/my-listings` (대시보드)
- `api.ts`: dev 환경 `X-Dev-User-Id` 자동 주입 interceptor

## 마켓 + 셀러 코파일럿

- **판매 상태**: available / reserved / sold — 전이 규칙 + race condition 방어 (`WHERE sale_status IN ...`)
- **문의**: `inquiries` 테이블 (`004_inquiries.sql`) — DB 저장 + Discord 알림 병행
  - 응답 시 자동 상태 전이: status→replied, is_read→true, last_reply_at→now
  - inquiry 조회 시 listing 컨텍스트 포함 (title, price, thumbnail)
- **재등록**: `POST /my-listings/{id}/relist` — 기존 세션 복제, sale_status 초기화, relisted_from 기록
- **문의 코파일럿**: `POST .../suggest-reply` — LLM 응답 초안 + goal별 fallback 템플릿 3종
- **카테고리 필터**: `confirmed_product.category` 기반

## 미완성 항목

- pgvector 활성화: `migrations/001_pgvector_setup.sql` 실행 후 `python scripts/setup_pgvector.py --seed`
- 당근마켓 게시 (Android 에뮬레이터 필요, 보류)
- Supabase Storage Public 버킷 생성 (코드는 완료)
- 프로덕션 로그인 UI (Supabase Auth 프론트 연결 — dev bypass로 개발 중)
