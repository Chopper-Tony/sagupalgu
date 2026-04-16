# 코딩 규칙

## 상태 머신
- `SessionStatus`는 `app/domain/session_status.py` 단 한 곳에서 정의 — 다른 파일은 import만
- 전이 유효성: `ALLOWED_TRANSITIONS` 기준 (13개 상태)
- next_action: `resolve_next_action()` 함수 사용
- **원자성**: `_update_or_raise(session_id, payload, expected_status=...)` — 불일치 시 409
- **판매 상태 전이**: `session_repository.py`의 `SALE_STATUS_TRANSITIONS` — available ↔ reserved → sold (sold는 되돌릴 수 없음)

## Agent Trace 보존
- `_build_workflow_payload()`는 `tool_calls`·`decision_rationale`·`plan`·`critic_score`·`critic_feedback`를 workflow_meta에 병합
- 그래프→서비스→DB→UI까지 trace가 끊기면 안 됨

## 에이전트 노드
- `state: SellerCopilotState` 동기 함수로 구현
- async 호출: `_run_async(lambda: coro())` 헬퍼 (graph 노드 내부만, service layer 확산 금지)
- ReAct: `langchain.agents.create_agent(llm, tools, system_prompt=...)` 패턴

## 툴
- 외부 import 진입점: `app.tools.agentic_tools` 단일 facade (하위 모듈 직접 import 금지)
- `lc_` prefix = LangChain `@tool` 버전 (ReAct bind용)
- 내부 구현 `_impl` 분리 → 직접 호출과 lc_ 래퍼 공유
- 결과: `make_tool_call()` 형식 반환
- `langchain_core` conditional import — 미설치 환경 호환

## 예외 처리
- 도메인 예외: `app/domain/exceptions.py` 단 한 곳
- 매핑: SessionNotFound→404, InvalidUserInput→400, InvalidStateTransition→409, ListingGeneration/Rewrite→500, PublishExecution→502
- 적용: `main.py` 글로벌 핸들러 단일 (`_DOMAIN_STATUS_MAP`)
- 라우터는 예외를 잡지 않음

## 의존성 주입
- `app/dependencies.py`의 `Depends()`로만 라우터에 주입
- 라우터에서 직접 `SessionService()` 생성 금지
- SessionService 생성자 5개 의존성 모두 required (session_repository, product_service, publish_orchestrator, copilot_service, sale_tracker)
- `@lru_cache(maxsize=1)` 싱글턴 — 의존성 트리로 wiring
- 테스트: `app.dependency_overrides[get_session_service] = lambda: mock_svc`

## 외부 의존성 import
- supabase, langgraph, langchain: 반드시 **lazy import** (함수 내부)
- 모듈 최상단 eager import 금지 — clean env pytest 수집 통과 필수
- `TYPE_CHECKING` 블록은 타입 힌트 전용

## 테스트
- **unit**: 순수 함수, mock 불필요, CI 필수 (596개, 14초)
- **integration**: 노드 호출, 외부 LLM 반드시 mock
- **e2e**: 실제 LLM, CI 필수 아님
- LLM 응답 의존 assertion 금지 — fallback 경로만 검증
- 프론트엔드 테스트: vitest 60개 (hooks, lib, 타입 계약)
- FE/BE 타입 동기화: `scripts/generate_api_types.py --check` CI 필수

## 게시 정책 (단일 원천)
- **`app/domain/publish_policy.py`** — 타임아웃·재시도·에러 분류·플랫폼 capability 단일 원천
  - `EXTENSION_ONLY_PLATFORMS`: frozenset({"joongna", "bunjang"}) — 서버 Playwright 불가
  - `PUBLISH_TIMEOUT_SECONDS=180`, `MAX_CONCURRENT_BROWSERS=2`
  - `MAX_PUBLISH_RETRIES=2`, `RETRY_BASE_DELAY_SECONDS=5.0` (지수 백오프)
  - `FAILURE_TAXONOMY`: 12종 에러 분류 (timeout, login_expired, content_policy, image_upload_failed 등)
  - `classify_error(error_code, error_message)` — 에러 코드/메시지 기반 자동 분류
- **`legacy_spikes/` 직접 수정 금지** → `app/publishers/`에서 패치
- 게시/복구/최적화: SessionService에서 노드 함수 직접 호출
- 번개장터 가격: 수수료 3.5% 보전 (`base_price × 1.035`)

## 프론트엔드 액션 규칙
- **`frontend/src/hooks/useSessionActions.ts`** 단일 파일에서 모든 세션 액션 관리 (CTO P1 반영)
- App.tsx에 비즈니스 로직 직접 작성 금지 — `createActionHandler(ctx)` 훅만 사용
- 12 case / 11 unique 액션: upload_images, confirm_product, prepare_publish, rewrite, publish, direct_edit, edit_draft, update_sale_status (mark_sold와 fall-through), mark_sold, mark_unsold, retry_publish, restart
- 액션별 상태 전이·카드 push·에러 처리 모두 훅 내부에서 처리
- 에러 변환: `friendlyError()` 헬퍼가 HTTP 상태 코드(409/422/429/500/502/404/timeout/network)를 한국어 메시지로 매핑
- 새 액션 추가 시 `useSessionActions.ts`에만 추가 + `ActionContext` 타입 업데이트

## 인증
- `app/core/auth.py` JWT 기반 + 환경별 정책
- dev/local: `X-Dev-User-Id` 헤더 bypass 허용 (로그인 UI 없이 개발)
- prod: `get_optional_user` 완화 모드 + `X-Dev-User-Id` 거부 (403)

## 이미지 저장
- Supabase Storage Public 버킷 `product-images` (USE_CLOUD_STORAGE=true)
- 로컬 fallback 지원 (개발 환경)

## 알림
- 구매 문의 수신 시 Discord 웹훅 + Gmail SMTP 이메일 **병렬 실행**
- 각 채널 독립 실패 처리 (try-except) — 하나 실패해도 저장은 성공
- 환경변수: `DISCORD_WEBHOOK_URL`, `SMTP_EMAIL`, `SMTP_APP_PASSWORD`
