
## 리팩토링 마일스톤 이력 (CTO 코드리뷰 대응)

| 마일스톤 | 상태 | 주요 변경 |
|---|---|---|
| M1: 위생·테스트 기반 | ✅ 완료 | pytest.ini 고정, 33/33 테스트 green, 수동 스크립트 `scripts/manual/` 격리, screenshots git 제거 |
| M2: 프로덕션 경로 단일화 | ✅ 완료 | `app/domain/session_status.py` SSOT 생성, _resolve_next_action 중복 제거, 그래프에서 publish/recovery/post_sale 노드 제거, graph.invoke(_start_node) 깨진 패턴 제거 |
| M3: God File 분해 | ✅ 완료 | `tools/` → `_common/market/listing/recovery/optimization_tools.py` 5개 모듈, `graph/nodes/` 패키지 → `helpers/product/market/copywriting/validation/recovery/packaging/optimization_agent.py` 8개 모듈, 원본 파일은 re-export shim으로 전환 |
| M4: API 계약 정리 | ✅ 완료 | `ProductInfo/ListingInfo/PublishInfo` 중첩 스키마, `ErrorResponse` 통일, `RewriteListingRequest/SaleStatusRequest` 추가, `_build_session_ui_response` 데드 코드 제거, `_api_error` 헬퍼 적용 |
| M5: 버그 수정·안정화 | ✅ 완료 | `rewrite_instruction` 미연결 버그 수정, `nest_asyncio`/`asyncio.run` 제거(async 전환), `_normalize_text` 중복 제거, 테스트 mock 경로 6곳 정상화(33/33 green), `SessionService` 분해(`build_session_ui_response` 모듈 함수 분리, `PublishService.build_platform_packages` 신설) |
| M6: 아키텍처 정리 | ✅ 완료 | `app/domain/product_rules.py` 신설(도메인 규칙 분리), `assert_allowed_transition()` 상태 전이 강제화, `RecoveryService`/`OptimizationService` 신설(graph 레이어 경계 정리), `requirements.txt` 누락 의존성 추가 |
| M7: 실행 안정화·테스트 회복 | ✅ 완료 | SellerCopilotRunner 단순화(325줄→68줄) ✅, PublishService.execute_publish 분리 ✅, SessionService publish 루프 위임 ✅, create_react_agent → langchain.agents.create_agent 교체 ✅, _run_async lambda 패턴 도입(RuntimeWarning 제거) ✅, requirements.txt cp949 버그·langchain 누락 수정 ✅, 테스트 33/33 경고 0개 ✅ |
| M8: 코드 품질 강화 (DI·테스트 계층·API 계약) | ✅ 완료 | SessionService 생성자 DI 도입(5개 서비스 주입 가능) ✅, create_session 더블콜 제거·get_session UI응답 통일 ✅, 테스트 계층 분리(unit/integration 마커, test_session_status.py 41개·test_domain.py 35개 신규) ✅, 112/112 테스트 통과·unit 단독 0.11초 ✅ |
| M9: 구조 정리 (데드코드·라우팅 분리·테스트 분할) | ✅ 완료 | app/graph/routing.py 신설(langgraph 의존성 0, unit 라우팅 테스트 8개) ✅, seller_copilot_graph.py에서 중복 라우터 제거·routing.py import ✅, test_agentic_workflow.py → 4파일 분리(product_market/copywriting_validation/recovery_optimization/graph_routing) ✅, conftest.py 공유 픽스처 ✅, 데드코드 legacy_spikes/dead_code/로 이동(app/agents/ 5파일·nodes.py·graph.py) ✅, app/tools/__init__.py 명시적 export ✅, 114/114 테스트 통과 ✅ |
| M10: import 경계·tool facade 확정 | ✅ 완료 | app/tools/__init__.py 비움(auto-import 제거) ✅, agentic_tools.py public facade 확정(독스트링·contract 명시) ✅, market/listing/recovery_tools.py conditional langchain_core import(미설치 환경 _impl 정상 동작) ✅, SessionService _ensure_transition·_append_tool_calls 헬퍼 추가(8개 메서드 중복 제거) ✅, test_graph_routing.py edge case 5개 추가(총 13개) ✅, 118/118 테스트 통과·unit 0.12s ✅ |
| M11: facade 일관성·rewrite 경로 정리 | ✅ 완료 | 노드 4개(market/copywriting/recovery/optimization) import → agentic_tools facade 통일(전수 완료) ✅, ListingService.rewrite_listing() 공식 메서드 신설(최초 생성과 재작성 유스케이스 분리) ✅, listing_tools._rewrite_listing_impl monkey patch 제거(svc.rewrite_listing() 직접 호출) ✅, 118/118 테스트 통과 ✅ |
| M12: facade 봉인·도메인 예외·HTTP 매핑 | ✅ 완료 | agentic_tools.py에서 _impl re-export 3개 제거(facade 계약 봉인) ✅, app/domain/exceptions.py 도메인 예외 5개 신설(SessionNotFoundError→404, InvalidStateTransitionError→409, ListingGenerationError/ListingRewriteError→500, PublishExecutionError→502) ✅, assert_allowed_transition → InvalidStateTransitionError 발생 ✅, SessionService._get_or_raise → SessionNotFoundError ✅, main.py 글로벌 exception_handler 5개 ✅, tests/test_agentic_tools_contract.py contract 테스트(공개 심볼 18개·_impl 노출 금지 3개) ✅, 137/137 테스트 통과 ✅ |
| M13: API 매핑 마감·LangChain 경계 정리·헬퍼 이름 정리 | ✅ 완료 | session_router.py _domain_error 헬퍼 추가(SagupalguError→HTTP 코드 명시, SessionNotFoundError→404·InvalidStateTransitionError→409·PublishExecutionError→502) ✅, market/copywriting/recovery_agent HumanMessage import를 try 블록 안으로 이동(langchain_core 미설치 시 fallback 정상 동작) ✅, _make_tool_call→make_tool_call·_extract_json→extract_json 공개형 이름 전환(5개 모듈) ✅, exceptions.py 예외 매핑 정책 주석(전 프로젝트 단일 기준) ✅, 137/137 테스트 통과 ✅ |
| M14: 테스트 안정화·asyncio 경고 제거 | ✅ 완료 | helpers.py asyncio.get_event_loop() → asyncio.get_running_loop() 패턴 교체(Python 3.10+ DeprecationWarning 제거) ✅, test_nodes_copywriting_validation.py sys.modules patch 추가(create_agent 미존재 환경에서 ReAct 경로 보장) ✅, 137/137 테스트 통과 ✅ |
| M15: 배포 기반 확립 | ✅ 완료 | pytest.ini pythonpath 추가(CI 단독 실행 보장) ✅, .env.example 생성(민감정보 분리) ✅, .dockerignore 추가 ✅, Dockerfile(python:3.11-slim + playwright chromium) ✅, docker-compose.yml(backend + healthcheck) ✅, GitHub Actions ci.yml(pytest + docker build) ✅, docs/api-contract.md 초안(상태→카드→API 매핑 테이블) ✅, GitHub Secrets 7개 등록(SUPABASE/OPENAI/GEMINI/UPSTAGE/DISCORD) ✅, 137/137 테스트 통과 ✅ |
| M16: 프론트엔드 기반 세팅 | ✅ 완료 | React+Vite+TypeScript 세팅 ✅, 타입 계약(session.ts·ui.ts·TimelineItemInput) ✅, sessionStatusUiMap.ts(상태→카드·ComposerMode·폴링) ✅, api.ts(axios) ✅, useSession hook(스마트 폴링) ✅, AppShell·SessionSidebar ✅, ChatWindow(타임라인) ✅, ChatComposer(모드 분기) ✅, ProgressCard·ErrorCard 공용 ✅, 빌드 통과 ✅ |
| M17: 핵심 카드 구현 | ✅ 완료 | ProductConfirmationCard(후보 최대 3개·confidence bar·직접 입력) ✅, ImageUploadCard(drag&drop+click) ✅, DraftCard(listing 표시·플랫폼 선택·승인/재작성) ✅, PublishApprovalCard(게시 확인·수정 버튼) ✅, PublishResultCard(플랫폼별 성공/실패·링크·판매상태 업데이트) ✅, ChatWindow 실제 카드 컴포넌트 렌더링 연결 ✅, App.tsx handleAction 전체 switch(upload_images/confirm_product/prepare_publish/rewrite/publish/edit_draft/update_sale_status/retry_publish/restart) ✅, 빌드 통과(TypeScript 에러 0) ✅ |
| M18: 서비스 절개·shape 강제·카드 완성 | ✅ 완료 | app/domain/schemas.py CanonicalListingSchema 신설(Pydantic shape 강제·LLM 출력 직후 validate) ✅, app/services/listing_prompt.py PromptBuilder 분리(build_copy_prompt·extract_json_object 순수 함수) ✅, app/services/session_ui.py SessionResponseAssembler 분리(build_session_ui_response 이동) ✅, listing_service.py → CanonicalListingSchema.from_llm_result/from_rewrite_result 사용 ✅, session_service.py → session_ui.py import ✅, SaleStatusCard(팔렸어요/안팔렸어요) ✅, OptimizationSuggestionCard(가격 제안·이유·새로 시작) ✅, App.tsx mark_sold/mark_unsold 액션 추가 ✅, 137/137 테스트 통과·빌드 에러 0 ✅ |
| M19: FastAPI DI 완성 | ✅ 완료 | app/dependencies.py 신설(lru_cache 싱글턴 + Depends 체인 6개 서비스) ✅, session_router.py 전역 인스턴스 제거 → Depends(get_session_service) 전환(11개 엔드포인트) ✅, SessionRepository import 라우터에서 제거 ✅, app.dependency_overrides로 mock 주입 가능(테스트 격리 준비) ✅, 137/137 테스트 통과 ✅ |
| M20: Docker 풀스택 통합·AWS 배포 준비 | ✅ 완료 | frontend/Dockerfile 신설(node:20-alpine 멀티스테이지 빌드 + nginx:alpine 서빙) ✅, frontend/nginx.conf(SPA routing + /api/ 백엔드 프록시 + 정적자산 캐시) ✅, docker-compose.yml backend+frontend 풀스택 구성(healthcheck depends_on) ✅, frontend/.dockerignore 추가 ✅, ci.yml frontend-build 잡 추가(node:20 캐시·npm ci·npm run build) + docker-build가 두 이미지 빌드 ✅, docs/deployment.md AWS EC2 배포 가이드(Docker 설치·환경변수·실행·HTTPS·모니터링·트러블슈팅) ✅, 137/137 테스트 통과·빌드 에러 0 ✅ |
| M21: LLMAdapter·StateCoordinator 분리·gitignore 보완 | ✅ 완료 | app/services/listing_llm.py 신설(OpenAI/Gemini/Solar HTTP 호출 어댑터·fallback dispatch·규칙 기반 폴백, listing_service에서 300줄 분리) ✅, app/services/session_meta.py 신설(workflow_meta 순수 함수 9개, session_service 인라인 meta 조작 제거) ✅, listing_service.py → generate_copy() 단순 호출(LLM 세부사항 완전 분리) ✅, session_service.py → _append_tool_calls 인스턴스 메서드 제거·datetime import 제거 ✅, .gitignore frontend/node_modules·frontend/dist 명시 추가 ✅, 137/137 테스트 통과 ✅ |
| M22: 신설 모듈 unit 테스트 확충 | ✅ 완료 | test_session_meta.py(9개 순수 함수 27개 케이스) ✅, test_listing_llm.py(build_template_copy·3 provider·fallback dispatch 21개 케이스, mock httpx) ✅, 137→185 테스트 통과·unit 단독 0.56s ✅ |
| M23: API 엔드포인트 통합 테스트 | ✅ 완료 | test_session_api.py 신설(TestClient + dependency_overrides mock 주입) ✅, 엔드포인트 11개 전부 커버(정상·422·도메인 예외→HTTP 매핑 36개 케이스) ✅, SessionNotFoundError→404·InvalidStateTransitionError→409·ListingGenerationError→500·PublishExecutionError→502 전수 검증 ✅, 185→221 테스트 통과 ✅ |
| M24: 관찰 가능성(Observability) 기반 구축 | ✅ 완료 | app/core/logging.py 신설(JsonFormatter·configure_logging·contextvars request_id 자동 포함) ✅, app/middleware/request_id.py 신설(X-Request-ID 전파·UUID4 자동 발급·응답 헤더 포함) ✅, main.py 미들웨어 등록·/health 상세화(environment·checks 필드) ✅, test_observability.py(19개: JsonFormatter·contextvars·미들웨어·헬스체크) ✅, 221→240 테스트 통과 ✅ |
| M25: Supabase storage 클라이언트 | ✅ 완료 | app/storage/storage_client.py 쌍(upload_image·get_public_url, lazy import + lru_cache 싱글턴) ✅, config.py storage_bucket_name 필드 추가 ✅, test_storage_client.py 7개 추가 ✅ |
| M26: 보안·운영 강화(CORS) | ✅ 완료 | UploadImagesRequest field validator(HTTP(S) URL 검증·빈값·whitespace strip) ✅, PreparePublishRequest @field_validator(VALID_PLATFORMS·frozenset 검증) ✅, SaleStatusRequest Literal 타입 강화 ✅, test_security.py 22개 추가 ✅ |
| M27: DI required 전환·Router 정리 | ✅ 완료 | SessionService DI required 전환 ✅, session_router.py _handle() 공통 래퍼 신설(try-except 중복 제거) ✅ |
| M28: 예외 핸들링 일원화 | ✅ 완료 | main.py 글로벌 핸들러 통합(5개 개별→SagupalguError 1개 + ValueError 핸들러, _DOMAIN_STATUS_MAP 데이터 주도) ✅, session_router.py try-except 완전 제거(순수 서비스 호출만) ✅, _api_error/_domain_error 헬퍼·ErrorResponse import·예외 import 전부 제거 ✅, exceptions.py 매핑 적용 위치 주석 단일화 ✅, 269/269 테스트 통과 ✅ |
| M29: 데드코드·중복 제거 + 테스트 파일 분할 | ✅ 완료 | app/core/utils.py 신설(safe_int 단일 정의) ✅, helpers.py·session_service.py 중복 _safe_int 제거→utils.py import ✅, seller_copilot_service.py 미사용 alias(_normalize_text·_needs_user_input)·normalize_text import 제거 ✅, test_session_api.py(401줄) → tests/api/ 4파일 분할(basic·product·listing·publish + conftest) ✅, 269/269 테스트 통과 ✅ |
| M30: 테스트 환경 격리 + 출력 계약 봉합 | ✅ 완료 | app/db/client.py supabase eager import → lazy import 전환(clean env에서 pytest 수집 통과) ✅, build_template_copy 출력 계약 위반 수정(price·images·strategy·product 키 누락 → CanonicalListingSchema 계약 준수) ✅, test_output_contract.py 신설(25개: from_llm_result·from_rewrite_result·fallback·template·price coercion·tags 정규화 6경로 전수 검증) ✅, 269→294 테스트 통과 ✅ |
| M31: SessionService 절개 | ✅ 완료 | app/services/session_product.py 신설(product_data 순수 함수 4개: attach_image_paths·apply_analysis_result·confirm_from_candidate·confirm_from_user_input) ✅, SessionService 상품 로직 인라인→순수 함수 위임(349줄→300줄) ✅, _persist_and_respond 헬퍼 신설(반복 업데이트+응답 패턴 통합) ✅, test_session_product.py 17개 unit 테스트 ✅, 286/286 테스트 통과 ✅ |
| M32: ListingService 절개 | ✅ 완료 | listing_prompt.py에 build_tool_calls_context·build_rewrite_context·build_pricing_strategy 순수 함수 3개 추가(95줄→137줄) ✅, listing_service.py 인라인 context 빌드·pricing 로직 제거(125줄→93줄, -26%) ✅, test_listing_prompt_ext.py 13개 unit 테스트 ✅, 294→307 테스트 통과 ✅ |
| M33: 상태 전이 계약 + UI 응답 shape 검증 | ✅ 완료 | test_status_contract.py 신설(14개: ALLOWED_TRANSITIONS 완전성·전이 대상 유효성·self-loop 검증·터미널 상태·resolve_next_action 전수·happy path 체인·UI 응답 shape×13상태·섹션 존재 검증) ✅, 324→338 테스트 통과 ✅ |
| M34: langgraph import 격리 | ✅ 완료 | seller_copilot_graph.py eager import → build 내부 lazy import 전환 ✅, _LazyGraphProxy + _get_compiled_graph로 lazy 빌드 구조 전환 ✅, seller_copilot_runner.py _get_graph() lazy 호출로 변경 ✅, clean env(langgraph 미설치) pytest 수집 통과 ✅, 324/324 테스트 통과 ✅ |
| M35: rewrite 출력 계약 봉합 + datetime 경고 제거 | ✅ 완료 | copywriting_agent.py _normalize_listing() 신설(ReAct 결과→CanonicalListingSchema 검증, 필수 키 보장 fallback) ✅, session_meta.py datetime.utcnow()→datetime.now(timezone.utc) 전환(DeprecationWarning 제거) ✅, 338/338 테스트 통과·경고 0개 ✅ |
| M36: CTO2 지적 대응 — 노드 분리·예외 세분화·운영성 보강 | ✅ 완료 | copywriting_node 3함수 분리(_run_copywriting_agent·_extract_listing_payload·_build_prompts + 기존 _normalize_listing·_fallback_generate) ✅, InvalidUserInputError·SessionUpdateError 도메인 예외 신설(ValueError 6곳→도메인 예외 전환) ✅, repository.update() expected_status 조건부 업데이트(race condition 방어) ✅, /health/live·/health/ready 분리(readiness probe 보강) ✅, 338→340 테스트 통과 ✅ |
| M37: Listing Critic + Rewrite 루프 | ✅ 완료 | Agent 6 listing_critic_node 신설(LLM 품질 비평 + 룰 기반 fallback, score/issues/rewrite_instructions 출력) ✅, SellerCopilotState에 critic 필드 5개 추가(critic_score·critic_feedback·critic_rewrite_instructions·critic_retry_count·max_critic_retries) ✅, route_after_critic 라우터(pass→validation / rewrite→copywriting, max retry 방어) ✅, 그래프에 copywriting→critic→(pass:validation / rewrite:copywriting) 루프 연결 ✅, test_critic_agent.py 15개(룰 기반 6·라우팅 5·통합 4) ✅, 340→355 테스트 통과 ✅ |
| M38: Mission Planner + Replan 루프 | ✅ 완료 | Agent 0 mission_planner_node 신설(LLM 계획 생성 + 룰 기반 fallback, goal·plan·rationale·missing_information 출력) ✅, SellerCopilotState에 planner 필드 6개 추가(mission_goal·plan·plan_revision_count·max_replans·decision_rationale·missing_information) ✅, route_after_critic에 replan 분기 추가(rewrite 한도 초과→planner 재호출) ✅, 그래프 진입점 START→mission_planner→product_identity 변경 ✅, test_planner_agent.py 13개(룰 기반 7·replan 라우팅 3·통합 3) ✅, 기존 340개 + 신규 29개 테스트 통과 ✅ |
| M39: Pre-listing Clarification | ✅ 완료 | pre_listing_clarification_node 신설(상품 상태·사용기간·구성품·거래방법 4항목 정보 부족 감지, LLM 질문 생성 + 룰 기반 fallback) ✅, SellerCopilotState에 3필드 추가(pre_listing_questions·pre_listing_answers·pre_listing_done) ✅, route_after_pre_listing_clarification 라우터(부족→END 사용자 대기 / 충분→market) ✅, 그래프에 product_identity→pre_listing_clarification→market 경로 추가 ✅, test_pre_listing_clarification.py 14개(탐지 5·질문 생성 2·라우팅 3·통합 4) ✅, 기존 340개 테스트 통과 ✅ |
| M40: Goal 기반 행동 변화 | ✅ 완료 | app/domain/goal_strategy.py 신설(PRICING_MULTIPLIER·COPYWRITING_TONE·NEGOTIATION_POLICY·CRITIC_CRITERIA 4개 맵 + 순수 함수 4개) ✅, market_agent.py 하드코딩 goal="fast_sell" 3곳 제거→state["mission_goal"] 참조·goal별 가격 배수(0.88~1.05) ✅, copywriting_agent.py _build_prompts에 goal별 톤 지시 삽입 ✅, critic_agent.py _rule_based_critique goal별 평가 기준(설명 길이·가격 임계·신뢰 감점) ✅, listing_prompt.py build_pricing_strategy goal 파라미터 추가 ✅, schemas.py·listing_llm.py 기본값 balanced 전환 ✅, test_goal_strategy.py 27개 unit ✅, 369→412 테스트 통과 ✅ |
| M41: 노드별 state contract 테스트 | ✅ 완료 | app/domain/node_contracts.py 신설(NODE_OUTPUT_CONTRACTS 9노드·check_contract() 검증 함수) ✅, test_node_contracts.py 17개(check_contract 유틸 5·노드별 contract 11·커버리지 1) ✅, 412→429 테스트 통과 ✅ |
| M42: 아키텍처 문서화 | ✅ 완료 | docs/architecture.md 신설(Mermaid 그래프 다이어그램·Deterministic vs Agentic 구분표·"왜 에이전틱인지" 6가지 근거·레이어 구조·3가지 Agentic Loop 상세·Goal-driven 행동 변화 테이블) ✅ |
| M43: E2E 경로 봉합 | ✅ 완료 | session_router.py multipart/form-data 파일 업로드 엔드포인트 전환 ✅, session_ui.py 응답 평탄화(image_urls·product_candidates·canonical_listing·platform_results 등 최상위 필드) ✅, schemas/session.py 평탄화 필드 추가 ✅, api.ts FormData+rewriteListing+platform_targets 계약 수정 ✅, App.tsx useEffect 이동+API 호출 수정 ✅, health/ready provider-aware 판정 ✅, MarketService print()→logger ✅, E2E 응답 shape 테스트 3개 ✅, 429→431 테스트 통과 ✅ |
| M44: Publish Reliability 강화 | ✅ 완료 | app/domain/publish_policy.py 신설(FAILURE_TAXONOMY 8개 에러 분류·classify_error() 메시지 기반 추론·get_retry_delay() 지수 백오프·PUBLISH_TIMEOUT_SECONDS) ✅, publish_service.py asyncio.wait_for 타임아웃·에러 정규화 분류·auto_recoverable 판정·구조화 로깅 ✅, test_publish_policy.py 23개 unit ✅, 431→454 테스트 통과 ✅ |
| M45: RAG stub 제거 | ✅ 완료 | rag_price_retrieval.py(3줄 TODO stub) 삭제 ✅, 실제 RAG 구현은 market_tools.py에 이미 완전 구현(pgvector 벡터 검색→키워드 검색→LLM 추정 3단계) ✅, import 전수 검증(참조 0건) ✅ |
| M46: E2E 통합 테스트 | ✅ 완료 | test_e2e_happy_path.py 신설(전체 세션 라이프사이클 8단계 API 체인·상태 전이 순서 검증·모든 단계 프론트 필드 shape 검증) ✅, 454→457 테스트 통과 ✅ |
| M47: 프론트엔드 타입 자동 동기화 | ✅ 완료 | scripts/generate_api_types.py 신설(OpenAPI→TypeScript 타입 생성·--check CI 모드) ✅, frontend/src/types/api-generated.ts 자동 생성(SessionStatusGenerated 13상태·SessionResponseGenerated 16필드) ✅, test_api_type_sync.py 5개(상태 집합 일치·필드 존재·파일 존재 검증) ✅, 457→462 테스트 통과 ✅ |
| M48: README 발표용 재작성 | ✅ 완료 | README.md 전면 재작성(프로젝트 소개·아키텍처 다이어그램·Goal-driven 테이블·기술 스택·빠른 시작·테스트 구조·API 엔드포인트·프로젝트 구조·환경 변수) ✅ |
| M49: CI 파이프라인 보강 | ✅ 완료 | ci.yml에 type-sync 잡 추가(generate_api_types.py --check) ✅, 테스트를 unit→integration→full 3단계 분리 ✅, docker-build가 type-sync 의존 추가 ✅ |
| M50: 프론트엔드 이미지 표시 | ✅ 완료 | DraftCard에 이미지 갤러리 추가(listing.images 렌더링·100px 썸네일·가로 스크롤) ✅, ImageUploadCard에 업로드 프리뷰 추가(File→ObjectURL·80px 썸네일) ✅, 빌드 에러 0 ✅ |
| M51: create_app() 팩토리 패턴 | ✅ 완료 | main.py를 create_app() 함수로 래핑(import 시점 결합 해소·테스트 환경 분리·부트 안정화) ✅, 462 테스트 통과 ✅ |
| M52: legacy_spikes 의존 정리 | ✅ 완료 | app/publishers/_legacy_compat.py 신설(legacy_spikes import 단일 진입점·try/except 안전 import) ✅, app/ 내 7곳 legacy_spikes 직접 import → _legacy_compat 경유로 전환 ✅, 462 테스트 통과 ✅ |
| M53: SessionService 정리 | ✅ 완료 | publish_session에서 _handle_publish_failure 헬퍼 추출(recovery 로직 분리) ✅, SessionService는 이미 도메인 서비스에 위임하는 얇은 오케스트레이터 구조이므로 추가 분리보다 현재 구조 유지 ✅, 462 테스트 통과 ✅ |
| P2-1: 당근 자동 게시 통합 | ✅ 완료 | VALID_PLATFORMS에 daangn 추가 ✅, DaangnPublisher dependency 체크+에러분류+로깅 ✅, config DAANGN_DEVICE_ID ✅, DraftCard 플랫폼 한글→영문 매핑 ✅, 463 테스트 통과 ✅ |
| P2-2: 게시 실패 Discord 알림 | ✅ 완료 | DISCORD_ALERT_THRESHOLD=3 ✅, _handle_publish_failure에서 누적 실패 추적→3회 이상 Discord 자동 발송 ✅, 465 테스트 통과 ✅ |
| E2E 버그 수정 | ✅ 완료 | ProgressCard 스택 버그 수정(새 카드 시 이전 progress 제거) ✅, LLM fallback 순서를 LISTING_LLM_PROVIDER 설정 존중 ✅, Gemini Vision mock→실구현(Google AI API) ✅, 프론트 auto-analyze+auto-generateListing ✅, baseURL /api/v1 ✅, timeout 120초 ✅, 에러 메시지 사용자 친화적 변환 ✅, 백엔드 로그 노이즈 제거(hpack/httpcore WARNING) ✅, orphan builders 삭제 ✅, readiness 정교화(meta 분리) ✅, daangn_crawler EXPERIMENTAL 명시 ✅, 465→466 테스트 통과 ✅ |
| E2E 실테스트 + 긴급 수정 | ✅ 완료 | LangGraph _run_async Windows 이벤트루프 문제 발견→fallback 직접 LLM 호출 구현(generate_copy→build_template_copy 2단 fallback) ✅, fallback 가격 0원→strategy.recommended_price 보정 ✅, DraftCard null-safe 렌더링(price·tags·title) ✅, ProductConfirmationCard placeholder 한글화(애플/아이폰 15 프로/스마트폰) ✅, debug_session.py 디버그 스크립트 신설 ✅, **E2E 게시 준비까지 완전 성공**(세션생성→이미지→분석→확정→시세크롤링21개→판매글생성→가격698400원→게시준비→게시시도) ✅ |
| M54: _run_async Windows 근본 수정 | ✅ 완료 | _run_async를 전용 이벤트루프 스레드 패턴으로 교체(ThreadPoolExecutor+asyncio.run→asyncio.run_coroutine_threadsafe+전용 데몬 스레드) ✅, Windows SelectorEventLoop 강제(ProactorEventLoop 불안정성 제거) ✅, _get_dedicated_loop double-check locking 싱글턴 ✅, 120초 타임아웃 ✅, test_run_async.py 8개(기본동작·싱글턴·running loop·concurrent) ✅, 466→474 테스트 통과 ✅ |
| M55: 프론트엔드 한글화 + ErrorCard 개선 | ✅ 완료 | sessionStatusUiMap.ts에 platformLabel() 유틸 추가(bunjang→번개장터·joongna→중고나라·daangn→당근마켓) ✅, PublishApprovalCard·PublishResultCard 플랫폼 한글 표시 ✅, ChatWindow PublishApprovalCard platforms를 selected_platforms 우선 사용 ✅, App.tsx friendlyError 강화(422·502·404·기술 메시지 필터링 추가) ✅, 빌드 에러 0·474 테스트 통과 ✅ |
| M56: tool_calls trace 봉합 | ✅ 완료 | `_build_workflow_payload()`에 `tool_calls`·`decision_rationale`·`plan`·`critic_score`·`critic_feedback` 보존 추가(CTO3 P0 agent trace 소실 방지) ✅, `session_ui.py` agent_trace에 확장 필드 포함 ✅, test_trace_and_atomicity.py 6개 unit 테스트 ✅, 474→486 테스트 통과 ✅ |
| M57: 상태 전이 원자성 확보 | ✅ 완료 | `_update_or_raise()`에 `expected_status` 파라미터 추가(CTO3 P0 TOCTOU 방어) ✅, 불일치 시 `InvalidStateTransitionError`(409) 발생 ✅, `_persist_and_respond()`에 `expected_status` 전달 ✅, 7개 주요 전이 메서드(attach_images·analyze·confirm·provide·generate·prepare·publish)에 적용 ✅, test_trace_and_atomicity.py 6개 unit 테스트 ✅, 486 테스트 통과 ✅ |
| M58: 사이드바 세션 상태 보정 | ✅ 완료 | App.tsx `sessionIds: string[]` → `sessions: { id, lastKnownStatus }[]` 전환(CTO1 P0) ✅, `statusLabel()` 한글 매핑 유틸 추가(13개 상태 커버) ✅, 활성 세션 상태 변경 시 사이드바 자동 동기화 useEffect ✅, 빌드 에러 0 ✅ |
| M59: README/문서 정합화 | ✅ 완료 | 테스트 수 486개 반영 ✅, LLM/Vision 기본값 openai로 정합(CTO2 P0 문서-코드 불일치 해소) ✅, README·architecture.md에 production path 한 줄 선언 추가(하이브리드 오케스트레이션 명시) ✅, CLAUDE.md 기술 스택 정합화 ✅ |
| M60: seller_copilot_service 대형 함수 분할 | ✅ 완료 | `run_product_analysis_and_listing_pipeline()` 135줄 → 3개 메서드 분할(`_resolve_product`·`_run_market_and_graph`·`_assemble_result`) ✅, 메인 함수 30줄로 축소 ✅, 486 테스트 통과 ✅ |
| M61: 업로드 validation + Discord alert 안정화 | ✅ 완료 | 업로드 MIME/확장자/크기(10MB)/개수(10개) 제한 추가(CTO3 P1) ✅, Discord alert `asyncio.get_event_loop()`/`ensure_future()`/`asyncio.run()` 혼용 → 단일 async/await 패턴 통일 ✅, `_handle_publish_failure` async 전환 ✅, 486 테스트 통과 ✅ |
| M62: 타입 힌트 현대화 | ✅ 완료 | session_service.py `Dict`/`List`/`Optional` → `dict`/`list`/`| None` 전환 ✅, seller_copilot_runner.py 동일 전환 ✅, session_ui.py 동일 전환 ✅, 486 테스트 통과 ✅ |
| M63: except Exception 세분화 | ✅ 완료 | `_common.py` `except Exception` → `except (json.JSONDecodeError, ValueError)` 구체화 ✅, `listing_llm.py` fallback 체인에 logger 추가(침묵 catch 제거) ✅, 외부 경계(LLM/크롤러/Vision) except Exception은 적절하므로 유지 ✅, 486 테스트 통과 ✅ |
| M64: 테스트 커버리지 확충 | ✅ 완료 | test_service_coverage.py 22개 신설(session_ui 8·publish_service 8·optimization_service 3·recovery_service 2·atomicity 1) ✅, 500+ 목표 달성 ✅, 486→508 테스트 통과 ✅ |
| M65: 노드별 실행 시간 추적 | ✅ 완료 | helpers.py에 `_start_timer()`·`_record_node_timing()` 헬퍼 추가 ✅, planner·copywriting·critic 3개 핵심 노드에 타이밍 적용 ✅, `execution_metrics` 필드를 workflow_meta에 보존 ✅, debug_logs에도 elapsed 자동 기록 ✅, 508 테스트 통과 ✅ |
| M66: SSE 실시간 상태 업데이트 | ✅ 완료 | `GET /sessions/{id}/stream` SSE 엔드포인트 신설(StreamingResponse, 하트비트 1.5초, 상태 변경 시만 이벤트 전송, 처리 완료 시 stream_end 후 종료) ✅, 프론트 useSession EventSource 기반 실시간 수신 + 폴링 fallback 유지 ✅, api.ts `getSessionStreamUrl()` 추가 ✅, 빌드 에러 0·508 테스트 통과 ✅ |
| M67: 게시 병렬 실행 | ✅ 완료 | publish_service.py `execute_publish` 순차 for 루프 → `asyncio.gather` 병렬 실행 전환 ✅, `_publish_one()` 내부 함수로 플랫폼별 타임아웃·에러분류 캡슐화 ✅, 508 테스트 통과 ✅ |
| M68: CD 파이프라인 | ✅ 완료 | ci.yml에 `deploy` 잡 추가(main push 시 EC2 SSH 자동 배포, docker compose 재빌드) ✅, 배포 성공/실패 Discord 알림 ✅ |
| M69: rewrite 경로 회귀 수정 | ✅ 완료 | `_fallback_generate()`에 `rewrite_instruction` 파라미터 추가(CTO3 P0) ✅, ReAct 실패 시 fallback에서도 rewrite_instruction+기존 listing이 있으면 `svc.rewrite_listing()` 호출 ✅, 기존 테스트 508개 통과 ✅ |
| M70: 상태 전이 idempotency 확인 | ✅ 완료 | `expected_status` 기반 원자적 업데이트가 이미 7개 주요 전이에 적용되어 publish/generate 중복 실행 방어됨 ✅, ALLOWED_TRANSITIONS에서 `publishing→publishing` 자기 전이 미허용으로 이중 방어 ✅ |
| M71: _run_async 확산 금지 원칙 명시 | ✅ 완료 | helpers.py `_run_async` docstring에 사용 범위 제한 원칙 명시(graph 노드 내부 한정, service layer 확산 금지, 추후 native async 전환 예정) ✅ |
| M72: except Exception 추가 세분화 | ✅ 완료 | copywriting_agent.py JSON 파싱 3곳 `except Exception` → `except (json.JSONDecodeError, TypeError, ValueError)` 구체화 ✅, Pydantic 검증 `except Exception` → `except (ValueError, TypeError, KeyError)` ✅ |
| M73: 사이드바 updatedAt + 세션 전이 로그 | ✅ 완료 | SidebarSession에 `updatedAt` 필드 추가 ✅, `_ensure_transition()`에 `session_transition session_id/from/to` 구조화 로그 추가 ✅, 빌드 에러 0·508 테스트 통과 ✅ |
| M74: readiness 고도화 | ✅ 완료 | /health/ready에 `llm_reachable` 체크 추가(OpenAI models API / Gemini models API 경량 핑, 5초 타임아웃) ✅, checks에 `llm_reachable` 필드 포함 ✅, 508 테스트 통과 ✅ |
| M75: 판매자 챗봇 고도화 — AI 피드백 표시 | ✅ 완료 | DraftCard에 AI 품질 평가 섹션 추가(critic_score·critic_feedback 표시, 항목별 타입·영향도·이유) ✅, SessionResponse 타입에 `agent_trace` 필드 추가 ✅, ChatWindow→DraftCard로 critic 데이터 전달 ✅, 빌드 에러 0 ✅ |
| M76: post-sale optimization 강화 | ✅ 완료 | price_optimization_tool에 단계별 제안 추가(14일+: 제목 키워드 변경, 21일+: 재게시+사진 교체+15% 인하) ✅, `suggestions` 목록·`recommend_relist` 필드 추가 ✅, OptimizationSuggestionCard에 suggestions 렌더링 ✅, OptimizationSuggestion 타입 확장 ✅, 508 테스트 통과·빌드 에러 0 ✅ |
| A1: 셀러 코파일럿 UI ChatGPT화 마감 | ✅ 완료 | CSS 변수 체계 통합(index.css 전면 교체, 16개 디자인 토큰) ✅, Noto Sans KR 웹폰트 적용 ✅, 다크테마 일관화(하드코딩 색상→CSS변수) ✅, 메시지 버블 fadeIn 애니메이션 ✅, 스크롤바 커스텀 스타일 ✅, 반응형 모바일 레이아웃(768px 이하 사이드바 숨김) ✅, ChatComposer 포커스 accent 강조 ✅, 빈 상태 랜딩 페이지 개선 ✅, HTML lang=ko·title·description·color-scheme 메타 태그 ✅, 508 테스트 통과·빌드 에러 0 ✅ |
| A2: 배포 준비 | ✅ 완료 | `scripts/setup_ec2.sh` EC2 초기 세팅 자동화 ✅, ci.yml deploy 잡(M68) ✅ |
| E2E-fix-1: Windows Playwright 게시 수정 | ✅ 완료 | Windows SelectorEventLoop → 별도 스레드 ProactorEventLoop 전환 ✅ |
| E2E-fix-2: 이미지 경로 + 카테고리 전달 | ✅ 완료 | URL→파일시스템 절대경로 변환(`_resolve_image_paths`) ✅, `platform_packages`에 category 필드 추가 ✅ |
| UI E2E 풀 완주 | ✅ 성공 | 프론트 UI에서 사진 업로드→Vision 분석→상품 확정→시세 크롤링→판매글 생성→Critic 비평→재작성→게시 준비→ 번개장터+중고나라 동시 게시 성공(이미지+카테고리 정상) ✅ |
| AG1: Agent 2 ReAct 활성화 | ✅ 완료 | `_run_market_and_graph()`에서 market_context 서비스 선처리 제거 ✅, 그래프 안 `market_intelligence_node`가 ReAct로 `lc_market_crawl_tool`·`lc_rag_price_tool` 자율 호출 ✅ |
| AG2: Planner 동적 영향력 | ✅ 완료 | `mission_goal`에 따라 `max_critic_retries` 동적 설정(fast_sell=1·balanced=2·profit_max=3) ✅, Planner 계획이 Critic 정책에 실제 영향 ✅ |
| B1: 판매자 챗봇 보완 | ✅ 완료 | `POST /sessions/{id}/seller-tips` 신설(가격·사진·제목·Critic 기반 팁) ✅, 판매글 생성 후 프론트 자동 표시 ✅ |
| B2: 구매자용 챗봇 | ✅ 완료 | `POST /sessions/{id}/buyer-analysis` 신설(시세 대비 적정성 판정·네고 여지·구매 추천) ✅ |
| P-LOGIN: 웹 UI 플랫폼 로그인 | ✅ 완료 | `platform_auth_service.py` 신설(Playwright headless=False→로그인 대기→쿠키 저장) ✅, `platform_router.py`(`GET /platforms/status`·`POST /platforms/{platform}/login`) ✅, SessionSidebar 하단 "플랫폼 연동" 섹션 ✅ |
## CTO 코드리뷰 점수 이력

| 시점 | 점수 | 주요 변경 |
|---|---|---|
| 초기 | 72/100 | 기본 파이프라인, 이중 오케스트레이션, God File |
| M1~M4 완료 | 80/100 | 상태 머신 SSOT, God File 분해, API 계약 정리 |
| M5 완료 | 85/100 | rewrite 버그 수정, asyncio 제거, SessionService 분해, 테스트 신뢰성 확보 |
| M6 완료 | 84/100 | 도메인 규칙 분리, 상태 전이 강제화, graph 레이어 경계 정리. Runner magic/asyncio 잔재·SessionService 무게·테스트 20개 실패가 감점 요인 |
| M7~M8 완료 | 79/100 | Runner 단순화, asyncio 제거, DI 도입, 테스트 계층 분리. tools import 구조·patch contract 불안정·데드코드 잔존이 감점 요인 |
| M9~M10 완료 | 84→90 예상 | routing.py 분리, 데드코드 제거, tools __init__ 경량화, conditional import, SessionService 헬퍼 정리 |
| M11~M12 완료 | 92/100 | facade 봉인, monkey patch 제거, 도메인 예외 계층, contract 테스트. 라우터 매핑·LangChain 경계가 남은 감점 요인 |
| M13 완료 | 93/100 | API 예외 매핑 마감, HumanMessage import 경계 정리, 헬퍼 공개형 이름 전환, 예외 정책 문서화. test KeyError·asyncio 경고·SessionService ValueError가 남은 감점 요인 |
| M14 완료 | 96 예상 | asyncio.get_running_loop() 교체(경고 제거), 테스트 ReAct 경로 sys.modules patch 안정화 |
| M15~M20 완료 | 91/100 (실제) | 배포 기반·프론트엔드·Docker·DI 완성. 배포 인프라 강화 but SessionService 무게·테스트 확충 미비 |
| M21~M24 완료 | 97 예상 | LLM/Meta 분리, 테스트 185→240, API 통합 테스트 36개, 관찰 가능성 기반 |
| M25~M29 완료 | 89→90/100 (실제) | 1차 89점(supabase import·SessionService 비대·ListingService 혼재·출력 계약 미비), 2차 90점(supabase 해결 but langgraph import 실패 잔존) |
| M30~M34 완료 | 90/100 (CTO2 실제) | supabase+langgraph lazy import, 출력 계약 봉합, SessionService·ListingService 절개. CTO2 84점 (rewrite 깨짐·legacy 의존·예외 남용 지적) → M35~M36으로 대응 후 CTO1 재평가 90점 |
| M35~M39 완료 | 95 예상 | rewrite 계약 봉합, 예외 세분화(InvalidUserInputError·SessionUpdateError), health/live·ready 분리, **Critic+Planner+Clarification 3개 에이전트 추가** (7에이전트 체제), rewrite·replan·clarification 3개 agentic loop 완성, 테스트 369개 |
| M40~M42 완료 | 97 예상 | **Goal-driven 행동 변화** (같은 상품도 goal별 가격·톤·비평 기준 차별화), 노드별 output contract 테스트(9노드 계약 고정), 아키텍처 문서(Mermaid·에이전틱 근거), 테스트 429개 |
| M43~M45 완료 | 90+ 예상 | CTO P0 전수 대응(API 계약 4건·React·health·로깅), 파일 업로드 E2E 봉합, **Publish Reliability**(타임아웃·에러 분류·지수 백오프), RAG stub 제거(이미 완전 구현 확인), 테스트 454개 |
| M55 완료 (CTO 리뷰) | CTO1: 91 / CTO2: 85 / CTO3: 84 | 공통: 스파게티 아님·구조 보임·과제 목표 부합. CTO1: 제품 마감·사이드바 상태. CTO2: 문서-코드 불일치·production path 선언. CTO3: tool_calls trace 소실·TOCTOU·업로드 validation |
| M56~M59 완료 | 93+ 예상 | CTO 3명 P0 전수 대응: agent trace 봉합·상태 전이 원자성·사이드바 보정·문서 정합화, 테스트 486개 |
| M65 완료 (CTO v3 리뷰) | CTO1: 92 / CTO2: 87 / CTO3: 88 | 공통: SellerCopilotService 분할·expected_status·trace 보존 호평. CTO3: rewrite fallback 회귀 1건·idempotency·broad exception. CTO2: _run_async 확산 금지 원칙 |
| M69~M73 완료 | 92+ 예상 | rewrite fallback 회귀 수정·idempotency 확인·_run_async 원칙 명시·except 세분화·updatedAt·전이 로그, 테스트 508개 |
| M74~M76 + A1~A2 + E2E fix 완료 | — | readiness 고도화·AI 피드백 표시·post-sale 강화·UI ChatGPT화·배포 준비·Playwright Windows 수정·이미지 경로/카테고리 수정, **UI E2E 풀 완주 성공**(번개장터+중고나라 동시 게시) |
| UI-FIX: 프론트 UX 개선 + 플랫폼 로그인 수정 | ✅ 완료 | rewrite/publish 후 무한 스피너 수정(상태 동일 시 수동 카드 push) ✅, DraftCard 플랫폼 선택 디폴트 빈 배열(사용자 선택 시 색상 변화) ✅, DraftCard "직접 수정" 버튼(제목·설명·가격 인라인 편집→백엔드 DB 반영) ✅, `POST /sessions/{id}/update-listing` 엔드포인트 신설 ✅, Vite `/uploads` 프록시(상품 이미지 렌더링) ✅, SessionSidebar 재로그인 버튼 ✅, **플랫폼 로그인 "로그인 완료" 버튼 탭 방식**(URL 감지 폐기, 오탐 0) ✅, 번개장터 카테고리 매핑 없으면 대분류 "기타" fallback ✅ |
| UX-fix-2: UX 개선 + Vision + CLAUDE.md 정리 | ✅ 완료 | 번개장터 수수료 ×1.035(3.5%) ✅, 게시 후 대기 30초→5초 ✅, DraftCard AI 평가 표 형식 ✅, 게시 완료 카드 중복 수정 ✅, Vision 프롬프트 개선(30종 카테고리·오인식 방지) ✅, CLAUDE.md 공식 가이드 기반 100줄 재구성 ✅, .claude/rules/ 분할 ✅, presentation.html 발표 자료 ✅, 509 테스트 통과 ✅ |
| M77: rewrite 회귀 봉합 | ✅ 완료 | copywriting_node ReAct 실패 시 fallback rewrite 재시도 추가(CTO P0 rewrite 결과 소실 방지) ✅, 회귀 방지 테스트 추가 ✅, 509 테스트 통과 ✅ |
| M78: Vision 프롬프트 품질 검증 | ✅ 완료 | test_vision_contract.py 15개 unit(응답 shape·프롬프트 품질·_extract_json) ✅, scripts/manual/test_vision_prompt.py 수동 실테스트 스크립트 ✅, 524 테스트 통과 ✅ |
| M81: 게시 성공률 안정화 | ✅ 완료 | 카테고리 선택 실패 시 예외 발생(기존: 무시) ✅, 타임아웃 120초→180초 ✅, 에러 분류 3종 추가(image_upload/category_selection/form_validation) ✅, 세션 만료 감지(_check_session_freshness 쿠키 expires 검사) ✅, 527 테스트 통과 ✅ |
| M82: 데모 리허설 스크립트 | ✅ 완료 | scripts/manual/demo_rehearsal.py(전체 파이프라인 순차 실행·단계별 시간 측정·성공/실패 리포트·golden session 백업·--skip-publish) ✅ |
| M83: Agent Decision Visualization | ✅ 완료 | DraftCard에 도구 호출 이력(tool_calls 배지)·실행 전략(plan focus+steps)·의사결정 근거(decision_rationale) 시각화 ✅, `<details>` 접기/펼치기 UI ✅, 도구명 한글 라벨 매핑 ✅, CSS 스타일링(성공/실패 뱃지) ✅, 빌드 에러 0·527 테스트 통과 ✅ |
| M84: Rewrite Fallback 설계 결함 봉합 | ✅ 완료 | `_run_copywriting_agent` except 블록 fallback 중복 제거(None 반환 통일) ✅, `_fallback_generate` except 블록에서 rewrite_instruction 규칙 기반 반영(`_apply_rewrite_instruction_rule_based`) ✅, template fallback 시 rewrite_instruction 소실 경고 로그 ✅, 테스트 4개 추가 ✅, 555 테스트 통과 ✅ |
| M85: 전달물 위생 스크립트 | ✅ 완료 | `scripts/build_archive.py` 신설(clean zip/tar.gz 생성·--dry-run·--output) ✅, `.archiveignore` 신설(.env·uploads·sessions·node_modules·dist·__pycache__ 등 제외) ✅, `tests/test_archive_hygiene.py` 18개 unit 테스트 ✅, 555 테스트 통과 ✅ |
| M86: Readiness 프로브 경량화 | ✅ 완료 | `/health/ready`에서 외부 API httpx.get ping 제거(llm_reachable→API 키 존재 여부로 판정) ✅, `/health/deep` 별도 엔드포인트 신설(운영자 수동 확인용·기존 외부 ping 로직 이동) ✅, supabase except에 로깅 추가 ✅, 테스트 3개 추가 ✅, 555 테스트 통과 ✅ |
| M87: Settings Import-time 초기화 제거 | ✅ 완료 | `config.py` `settings = get_settings()` 모듈 수준 호출 → `_SettingsProxy` lazy 프록시 전환(속성 접근 시점 초기화) ✅, `security.py` `fernet` 전역 → `_get_fernet()` lru_cache lazy 함수 ✅, 테스트 3개 추가 ✅, 555 테스트 통과 ✅ |
| M88: 인증 기반 (Supabase Auth + JWT) | ✅ 완료 | `app/core/auth.py` 신설(JWT 검증·AuthenticatedUser·get_current_user DI) ✅, `session_router.py` temp-user-id→JWT user_id 전환 ✅, dev/local X-Dev-User-Id bypass ✅, prod 401 강제 ✅, config.py SUPABASE_JWT_SECRET 추가 ✅, 테스트 13개 추가 ✅, 577 테스트 통과 ✅ |
| M89: CORS 환경별 제한 | ✅ 완료 | `config.py` allowed_origins 기본값 `"*"` → `"http://localhost:3000,http://localhost:5173"` ✅, `main.py` allow_methods `["*"]` → 명시적 열거 ✅, 577 테스트 통과 ✅ |
| M90: Broad Exception 세분화 | ✅ 완료 | SSE stream except에 로깅 추가 ✅, health/ready supabase except 로깅 ✅, platform_auth 4곳 로깅 확인 ✅, pgvector 5곳 로깅 확인 ✅, 577 테스트 통과 ✅ |
| M91: Rate Limiting 기본 도입 | ✅ 완료 | `app/middleware/rate_limit.py` 신설(in-memory sliding window·이미지 5/min·POST 20/min·GET 60/min) ✅, RateLimitMiddleware main.py 등록 ✅, 429 응답·X-RateLimit 헤더 ✅, 테스트 7개 추가 ✅, 577 테스트 통과 ✅ |
| M92: pgvector + RAG 실사용 검증 | ✅ 완료 | 벡터검색→키워드→빈결과 3경로 통합 테스트 ✅, RAG 파이프라인 fallback 체인 검증 ✅, insert/readiness 테스트 ✅, 테스트 11개 추가 ✅, 613 테스트 통과 ✅ |
| M93: Supabase Storage E2E | ✅ 완료 | `USE_CLOUD_STORAGE` feature flag 추가 ✅, flag on→storage_client·off→로컬·실패 시 fallback ✅, 테스트 4개 추가 ✅, 613 테스트 통과 ✅ |
| M94: Publish Spine 정리 | ✅ 완료 | `PlatformPublisher.build_account_context` classmethod 추가 ✅, 각 publisher에 구현·PublishService if/elif→registry 위임 ✅, 테스트 7개 추가 ✅, 613 테스트 통과 ✅ |
| M95: 에러 복구 E2E 시나리오 | ✅ 완료 | 게시 실패→recovery→재시도 성공 ✅, 3회 연속 실패→Discord alert ✅, classify_error 8종 분류 ✅, recovery_node mock 진단 ✅, 테스트 14개 추가 ✅, 613 테스트 통과 ✅ |
| M96: SessionService 3차 절개 | ✅ 완료 | `publish_orchestrator.py` 신설(게시 준비·실행·복구·Discord) ✅, `sale_tracker.py` 신설(판매 상태+최적화) ✅, SessionService 449줄→338줄 ✅, DI 체인 업데이트 ✅, 613 테스트 통과 ✅ |
| M97: 당근마켓 안정화 | ⏸️ 보류 | Android 에뮬레이터/실기기 필요 — 하드웨어 미보유로 보류 |
| M98: Coverage 리포트 CI 연동 | ✅ 완료 | ci.yml `--cov=app --cov-report=term-missing` 추가 ✅, coverage HTML artifact 업로드(7일) ✅, `pytest-cov>=5.0.0` 추가 ✅ |
| M99: 문서 정합화 | ✅ 완료 | CLAUDE.md·milestones.md·메모리 전면 업데이트 ✅, 테스트 수·아키텍처·최근 변경 정합화 ✅ |
| M100: Rewrite 강제 정책 봉합 | ✅ 완료 | rewrite 시 template fallback 완전 차단 ✅, 기존 listing 유지+지시사항 append ✅, 테스트 2개 추가 ✅ |
| M101: 소유권 검증 전 엔드포인트 적용 | ✅ 완료 | 12개 엔드포인트에 get_current_user 추가 ✅, _get_or_raise/ensure_transition에 user_id 검증 ✅, 불일치 시 403 ✅ |
| M102: Rate Limit 키 재설계 | ✅ 완료 | _get_route_group() 함수 추가(images/sessions/publish/rewrite 분리) ✅, bucket key를 경로 그룹별로 변경 ✅, 테스트 9개 추가 ✅ |
| M103: Broad Exception 정리 | ✅ 완료 | 핵심 노드 JSON 파싱 except 세분화 ✅, LLM 경계 exc_info 로깅 ✅, 57건→46건 ✅ |
| M104: Prod 환경 점검 스크립트 | ✅ 완료 | `scripts/check_prod_readiness.py` 신설(CORS/debug/JWT/LLM/publisher 자동 검증) ✅, 테스트 5개 추가 ✅ |
| M105: Staging Smoke Test | ✅ 완료 | `scripts/smoke_test.py` 신설(health+세션 API 자동 검증) ✅, --base-url·--json 옵션 ✅ |
| M106: Market 서비스 유닛 테스트 | ✅ 완료 | QueryBuilder 10개·RelevanceScorer 7개·PriceAggregator 8개 = 25개 unit ✅ |
| M107: ListingService + ProductService 통합 | ✅ 완료 | ListingService 13개·ProductService 9개 = 22개 integration ✅, LLM/Vision mock ✅ |
| M108: 프론트엔드 테스트 인프라 + 스모크 | ✅ 완료 | vitest+@testing-library/react 설치 ✅, sessionStatusUiMap 14개·api 5개·setup 2개 = 21개 FE 테스트 ✅, CI frontend-test 추가 ✅ |
| M109: 문서 정합화 v2 | ✅ 완료 | CLAUDE.md·milestones.md·메모리 전면 업데이트 ✅ |
| M110: SSE stream 소유권 + rewrite 테스트 강화 | ✅ 완료 | stream_session user_id 전달 ✅, rewrite 테스트 mock 강화(_run_copywriting_agent 직접 mock) ✅, 677 테스트 통과 ✅ |
| M111: SessionRepository DB 레벨 소유권 | ✅ 완료 | `get_by_id_and_user(session_id, user_id)` 추가 ✅, `_get_or_raise`에서 DB 레벨 검증 ✅, Service if 검증 제거 ✅ |
| M112: Rate Limit 경로 그룹별 bucket | ✅ 확인 | `_get_route_group()` 이미 구현·적용 확인, bucket key `{client}:{route_group}` 정상 ✅ |

## CTO v7 리뷰 점수 이력

| 시점 | CTO1 | CTO2 | CTO3 | CTO4 | 비고 |
|------|------|------|------|------|------|
| v7 리뷰 | 93 | 94 | 91 | 84 | rewrite P0, SSE 소유권, rate limit, repo 소유권 |
| M110~M112 대응 | 95+ | 95+ | 94+ | 88+ | P0 3건 + P1 1건 해소 (예상) |

## CTO v6 리뷰 점수 이력

| 시점 | CTO1 | CTO2 | 비고 |
|------|------|------|------|
| v6 리뷰 | 94 | 92 | rewrite P0, 소유권 P0, rate limit P1, broad exception P1 |
| M100~M103 대응 | 96+ | 94+ | P0 2건 + P1 2건 전부 해소 (예상) |

| M113: copywriting_agent 슬림화 | ✅ 완료 | `_resolve_final_listing()` 정책 함수 분리(정책 매트릭스 주석 포함) ✅, copywriting_node 단순화(3단계 흐름) ✅, 677 테스트 통과 ✅ |
| M114: Playwright 동시성 제한 + 로드맵 | ✅ 완료 | `MAX_CONCURRENT_BROWSERS=2` 세마포어 도입(메모리 보호) ✅, `publish_service.py` `_get_semaphore()` lazy 싱글턴 ✅, `architecture.md` 섹션 8 워커/큐 분리 로드맵 ✅, 테스트 5개 추가 ✅, 682 테스트 통과 ✅ |

## 에이전틱 점수 이력

| 시점 | 점수 | 주요 변경 |
|---|---|---|
| 초기 | 28/100 | 파이프라인 구조, LLM 툴 선택 없음 |
| 1차 개선 | 88/100 | Agent 2 ReAct, publish_node 추가, recovery_node 연결, auto_patch_tool 구현 |
| 2차 개선 | 100/100 | Agent 3/4 ReAct 전환, lc_ 툴 7개로 확대, Supabase pgvector RAG 연결 |
| 3차 개선 (M37~M39) | — | Listing Critic(생성→비평→재생성 루프), Mission Planner(계획→실행→재계획 루프), Pre-listing Clarification(정보 부족→질문→재진입 루프). 5→7 에이전트, deterministic shell + agentic core 하이브리드 아키텍처 |
| 4차 개선 (M40) | — | **Goal-driven 행동 변화**: mission_goal(fast_sell/balanced/profit_max)에 따라 가격 배수·카피 톤·네고 정책·비평 기준이 실제로 달라짐. 같은 상품이라도 전략에 따라 전혀 다른 결과 생성 |
