# CLAUDE.md

## 프로젝트 개요

중고거래(번개장터, 중고나라) 자동 게시 + 자체 마켓 플랫폼.
이미지 → AI 분석 → 가격 산정 → 카피라이팅 → 게시 → 복구의 파이프라인을
LangGraph Agentic Workflow로 구현. 7 에이전트 / 10 툴 / 3 Agentic Loop.

게시는 크롬 익스텐션 Content Script 방식 (서버 Playwright → 계정 정지로 전환).
자체 마켓(`#/market`, `#/my-listings`)에서 판매 상태 관리 + 문의 응답 + 셀러 코파일럿 제공.
마켓 상세 페이지에서 구매자용 AI 상품 챗봇 제공.

## 기술 스택

- **백엔드**: FastAPI + Pydantic v2 (12,400줄)
- **워크플로우**: LangGraph (`app/graph/`), `langchain.agents.create_agent` + bind_tools
- **Vision AI**: Gemini 2.5 Flash (기본) → OpenAI gpt-4.1-mini (fallback)
- **Listing LLM**: OpenAI gpt-4.1-mini → Gemini → Solar (fallback 체인)
- **DB**: Supabase (PostgreSQL + pgvector, 385건 시세 데이터)
- **이미지**: Supabase Storage (Public 버킷 `product-images`)
- **게시**: 크롬 익스텐션 Content Script (CDP 이미지 업로드) + 모바일 복사/직접 올리기
- **프론트엔드**: React 19 + TypeScript + Vite (7,080줄)
- **알림**: Discord 웹훅 + Gmail SMTP (구매 문의 이메일 알림)
- **배포**: Docker Compose + 서울 리전 EC2 (Elastic IP 43.201.188.57) + GitHub Actions CI/CD

## 주요 명령어

```bash
pip install -r requirements.txt && python -m playwright install chromium
uvicorn app.main:app --reload
cd frontend && npm install && npm run dev

# 테스트
pip install -r requirements-dev.txt
python -m pytest tests/ -m unit     # unit (596개, 14초)
cd frontend && npm test             # FE 60개 (vitest)

# Docker
docker compose up --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build  # prod

# EC2 서울 배포
ssh -i sagupalgu-seoul-key.pem ec2-user@43.201.188.57
cd ~/sagupalgu && git pull && docker-compose up --build -d
```

## 레이어 구조

- `app/domain/` — 상태 머신(SessionStatus SSOT), 스키마, 예외, Goal 전략, 게시 정책(`publish_policy.py`)
- `app/graph/nodes/` — 7개 에이전트 노드 (lazy import)
- `app/tools/` — 10개 툴 (`agentic_tools.py` 단일 facade)
- `app/services/` — 세션, 리스팅, 게시 오케스트레이터, 복구, 최적화, 셀러 코파일럿, 판매 추적
- `app/publishers/` — 플랫폼별 게시 adapter
- `app/api/` — `session_router.py` (세션), `market_router.py` (마켓 + 대시보드 + AI 챗봇)
- `app/repositories/` — `session_repository.py`, `inquiry_repository.py`
- `app/storage/` — Supabase Storage 클라이언트
- `app/dependencies.py` — DI 체인 (lru_cache 싱글턴)
- `frontend/src/pages/` — MarketPage, MarketDetailPage, MyListingsPage
- `frontend/src/hooks/` — useSession, useWishlist, useRecentlyViewed, useSessionActions
- `frontend/src/components/` — ThemeToggle, 13개 상태별 카드, ChatWindow, ChatComposer
- `sagupalgu-extension/` — 크롬 익스텐션 (Manifest V3, Content Script, 토큰 자동 발급)
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
- **인증**: `app/core/auth.py` JWT, dev 환경 `X-Dev-User-Id` bypass, prod `get_optional_user` 완화
- **이미지 저장**: Supabase Storage (`USE_CLOUD_STORAGE=true`) + 로컬 fallback
- **게시 정책**: `app/domain/publish_policy.py` 단일 원천 (타임아웃·재시도·에러 분류·플랫폼 capability)
- **게시 동시성**: `MAX_CONCURRENT_BROWSERS=2` 세마포어
- **프론트 액션**: `useSessionActions.ts` 훅에서 관리 (App.tsx에 직접 로직 금지)

## 아키텍처

상세: @.claude/rules/architecture.md

- **Production Path**: SessionService + SellerCopilotService 하이브리드 오케스트레이션
- **게시**: PublishOrchestrator → 크롬 익스텐션 Content Script (서버 Playwright 아님)
- **판매 추적**: SaleTracker → OptimizationService
- **마켓**: market_router.py — 공개 목록/상세/검색 + AI 챗봇 + 판매자 대시보드/문의 관리/재등록/코파일럿
- **알림**: 구매 문의 시 Discord 웹훅 + Gmail SMTP 동시 알림

## 프론트엔드

상세: @.claude/rules/frontend.md

- ChatGPT 스타일 대화형 UI, 라이트/다크 테마 토글, 13개 상태별 카드
- SSE 실시간 + 폴링 fallback
- 해시 라우팅: `#/` (셀러 코파일럿), `#/market` (마켓), `#/market/{id}` (상세), `#/my-listings` (대시보드)
- `api.ts`: dev 환경 `X-Dev-User-Id` 자동 주입 interceptor
- 모바일 반응형: 사이드바 숨김, + 버튼으로 세션 자동 생성 + 업로드, 짧은 placeholder
- 디바이스 분기: 데스크톱 = 자동 게시, 모바일 = 판매글 복사 + 직접 올리기
- CSS 변수 기반 테마 시스템 (`--btn-padding` 등 공통 토큰)

## 마켓 + 셀러 코파일럿

- **판매 상태**: available / reserved / sold — 전이 규칙 + race condition 방어 (InvalidStateTransitionError 예외)
- **문의**: `inquiries` 테이블 — DB 저장 + Discord 알림 + 이메일 알림 병행
  - 응답 시 자동 상태 전이: status→replied, is_read→true, last_reply_at→now
- **재등록**: `POST /my-listings/{id}/relist` — 기존 세션 복제, sale_status 초기화
- **문의 코파일럿**: `POST .../suggest-reply` — LLM 응답 초안 + goal별 fallback 템플릿 3종
- **AI 상품 챗봇**: `POST /market/{id}/chat` — 상품 정보(판매글+Vision AI+시세) 기반 구매자 질문 답변
  - 환각 방지: 확인된 정보 vs 일반 지식 구분, 추정 금지 항목 5개, fallback 사유 구분

## 미완성 항목

- 당근마켓 게시 (Android 에뮬레이터 필요, 보류)
- 프로덕션 로그인 UI (Supabase Auth 프론트 연결 — dev bypass + get_optional_user로 개발 중)
- 중고나라 크롤링 (CloudFlare 봇 탐지로 서버 크롤링 차단 — 번개장터 데이터로 시세 산정)

## 완료된 항목 (최근)

- 서울 리전 이전: Elastic IP 43.201.188.57 (고정, 재시작해도 안 바뀜)
- AI 상품 챗봇: 마켓 상세 페이지에서 구매자 질문 AI 답변
- 이메일 알림: 구매 문의 시 Gmail SMTP 알림 추가
- pgvector 활성화: 385건 시세 데이터 시딩 완료
- Supabase Storage: Public 버킷 `product-images` 활성화
- 번개장터 자동 게시: Content Script + React 이벤트 체인 방식
- 중고나라 자동 게시: Content Script 방식
- 모바일 반응형: + 버튼 업로드 + 판매글 복사 + 직접 올리기
- 라이트/다크 테마 토글
- CTO P1 반영: publish 정책 단일화 + App.tsx 액션 훅 분리
- 프론트엔드 테스트 60개 (useWishlist, useRecentlyViewed, hashRouting, 타입 계약 등)

## EC2 서울 리전 배포 정보

- **Elastic IP**: 43.201.188.57 (고정 — 재시작해도 안 바뀜)
- **SSH**: `ssh -i sagupalgu-seoul-key.pem ec2-user@43.201.188.57`
- **키 파일**: `C:\Users\bonjo\Downloads\sagupalgu_seoul_key\sagupalgu-seoul-key.pem`
- **인스턴스**: t3.medium (2vCPU, 4GB RAM, 20GB EBS)
- **리전**: ap-northeast-2 (서울)
- **Docker Compose**: `docker-compose up --build -d`
