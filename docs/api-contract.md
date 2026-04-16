# API Contract — 상태·카드·액션 매핑 + 엔드포인트 명세

> 프론트엔드 개발 기준 설계 문서 + API 엔드포인트 SSOT.
> `frontend/src/lib/sessionStatusUiMap.ts` 구현과 동기화.
> baseURL: `/api/v1` (axios interceptor). Dev 환경은 `X-Dev-User-Id` 헤더 자동 주입.
>
> **검증 기준** (2026-04-16): 실제 라우터 코드 (`app/api/*.py`)와 1:1 매칭 검증 완료.
> 향후 점진적 OpenAPI 자동 생성으로 전환 권장 (현재는 수동 동기화).

---

## 세션 상태 흐름

```
session_created
  → images_uploaded
    → awaiting_product_confirmation   (confidence < 0.6)
    → market_analyzing                (confidence >= 0.6 또는 user_input 확정)
      → draft_generated
        → awaiting_publish_approval
          → publishing
            → completed
              → awaiting_sale_status_update
                → optimization_suggested
            → publishing_failed
              → awaiting_publish_approval  (재시도)
      → failed
```

---

## 상태별 UI 계약

| status | 카드 | 허용 액션 | 호출 API | 기대 next status |
|---|---|---|---|---|
| `session_created` | `ImageUploadCard` | 이미지 업로드 | `POST /sessions/{id}/images` | `images_uploaded` |
| `images_uploaded` | `ProgressCard` | 없음 (자동 진행) | — | `awaiting_product_confirmation` \| `market_analyzing` |
| `awaiting_product_confirmation` | `ProductConfirmationCard` | 상품 확정 / 수정 입력 | `POST /sessions/{id}/confirm-product` \| `POST /sessions/{id}/provide-product-info` | `market_analyzing` |
| `market_analyzing` | `ProgressCard` | 없음 (자동 진행) | — | `draft_generated` \| `failed` |
| `draft_generated` | `DraftCard` | 승인 / 재작성 지시 / 직접 수정 | `POST /sessions/{id}/prepare-publish` \| `POST /sessions/{id}/rewrite-listing` \| `POST /sessions/{id}/update-listing` | `awaiting_publish_approval` \| `draft_generated` |
| `awaiting_publish_approval` | `PublishApprovalCard` | 게시 승인 | `POST /sessions/{id}/publish` | `publishing` |
| `publishing` | `ProgressCard` | 없음 (자동 진행) | — | `completed` \| `publishing_failed` |
| `completed` | `PublishResultCard` | 판매 상태 업데이트 (모바일: 복사/직접 올리기) | `POST /sessions/{id}/sale-status` | `awaiting_sale_status_update` |
| `awaiting_sale_status_update` | `SaleStatusCard` | 상태 입력 | `POST /sessions/{id}/sale-status` | `optimization_suggested` |
| `optimization_suggested` | `OptimizationSuggestionCard` | 없음 (터미널) | — | — |
| `publishing_failed` | `ErrorCard` | 재시도 / 플랫폼 변경 | `POST /sessions/{id}/publish` | `awaiting_publish_approval` |
| `failed` | `ErrorCard` | 세션 재시작 | `POST /sessions` | `session_created` |

---

## ComposerMode

| status | ComposerMode | 설명 |
|---|---|---|
| `session_created` | `upload` | 이미지 업로드 버튼 활성 |
| `awaiting_product_confirmation` | `confirmation` | 상품 정보 텍스트 입력 |
| `draft_generated` | `rewrite` | 재작성 지시 입력 |
| `awaiting_publish_approval` | `disabled` | 입력 불가, 카드 액션만 |
| `market_analyzing` \| `publishing` \| `images_uploaded` | `disabled` | 처리 중 |
| 그 외 터미널 상태 | `disabled` | — |

---

## 세션 라우터 (`/api/v1/sessions`) — `app/api/session_router.py`

| Method | Path | 설명 |
|---|---|---|
| `POST` | `/sessions` | 세션 생성 |
| `GET` | `/sessions/{id}` | 세션 상태 조회 (폴링용) |
| `GET` | `/sessions/{id}/stream` | SSE 실시간 상태 스트림 |
| `POST` | `/sessions/{id}/images` | 이미지 업로드 (Supabase Storage) |
| `POST` | `/sessions/{id}/analyze` | 이미지 분석 시작 (Vision AI) |
| `POST` | `/sessions/{id}/confirm-product` | 상품 확정 |
| `POST` | `/sessions/{id}/provide-product-info` | 상품 정보 수동 제공 |
| `POST` | `/sessions/{id}/generate-listing` | 판매글 생성 |
| `POST` | `/sessions/{id}/rewrite-listing` | 판매글 재작성 |
| `POST` | `/sessions/{id}/update-listing` | 판매글 직접 수정 저장 |
| `POST` | `/sessions/{id}/prepare-publish` | 게시 준비 (플랫폼 선택) |
| `POST` | `/sessions/{id}/publish` | 게시 실행 |
| `POST` | `/sessions/{id}/seller-tips` | 판매 팁 생성 (LLM 기반) |
| `POST` | `/sessions/{id}/buyer-analysis` | 구매자 분석 (문의 기반) |
| `POST` | `/sessions/{id}/sale-status` | 판매 상태 변경 (sold/unsold) |
| `GET` | `/sessions/{id}/publish-data` | 익스텐션용 게시 페이로드 |
| `POST` | `/sessions/{id}/extension-publish-result` | 익스텐션 게시 결과 보고 |

> DELETE 엔드포인트는 현재 없음. 새 세션은 `POST /sessions`로 시작.

---

## 마켓 라우터 (`/api/v1/market`) — `app/api/market_router.py`

### 공개 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/market` | 상품 목록 (검색/가격필터/상태필터/정렬/페이지네이션) |
| `GET` | `/market/{id}` | 상품 상세 (view_count 자동 증가) |
| `POST` | `/market/{id}/inquiry` | 구매 문의 (Discord + Gmail SMTP 병렬 알림) |
| `POST` | `/market/{id}/chat` | AI 상품 챗봇 (구매자용) |
| `GET` | `/market/sellers/{user_id}/profile` | 판매자 공개 프로필 |

### 셀러 대시보드 엔드포인트 (tag: `seller`, 인증 필요)

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/market/my-listings` | 내 상품 목록 (대시보드) |
| `PATCH` | `/market/my-listings/{id}/status` | 판매 상태 변경 (SALE_STATUS_TRANSITIONS 검증) |
| `GET` | `/market/my-listings/{id}/inquiries` | 문의 목록 조회 |
| `POST` | `/market/my-listings/{id}/inquiries/{inquiry_id}/reply` | 문의 응답 (자동 상태 전이) |
| `POST` | `/market/my-listings/{id}/inquiries/{inquiry_id}/suggest-reply` | AI 응답 초안 (LLM + goal별 fallback 템플릿) |
| `POST` | `/market/my-listings/{id}/mock-inquiry` | 테스트 문의 생성 (dev only) |
| `POST` | `/market/my-listings/{id}/relist` | 상품 재등록 (세션 복제 + sale_status 초기화) |

> **중요**: `/my-listings/*` 경로는 `market_router`에 정의되어 있으므로 실제 풀 패스는 `/api/v1/market/my-listings/...`이다. 라우트 순서상 `/market/{id}` (GET 상세)는 시퀀스 말미에 정의되어 `/my-listings`와 충돌하지 않는다.

### `GET /market` 쿼리 파라미터
- `limit` (1-100, 기본 20)
- `offset` (기본 0)
- `q` — 키워드 검색
- `min_price`, `max_price` — 가격 범위
- `sale_status` — available / reserved / sold
- `category` — 카테고리 필터
- `sort` — `price_asc` / `price_desc` / `latest`

### `POST /market/{id}/chat` 요청/응답 (AI 상품 챗봇)

**구현 위치**: `app/api/market_router.py:141` (라우터) + `app/api/market_router.py:185-254` (`_generate_chat_reply()`)

```json
// Request
{ "message": "사용 기간이 얼마나 되나요?" }

// Response (성공)
{ "reply": "상품 설명에 따르면 약 6개월 사용했습니다.", "source": "llm" }

// Response (컨텍스트 부족 - 판매글 title/description 모두 없음)
{ "reply": "이 상품에 대한 정보가 부족합니다. 판매자에게 직접 문의해주세요.", "source": "fallback_no_context" }

// Response (LLM 호출 실패 - rate limit, 네트워크 등)
{ "reply": "AI 상담 서비스에 일시적 문제가 있습니다. 잠시 후 다시 시도해주세요.", "source": "fallback_error" }
```

**LLM 설정**:
- 모델: `gpt-4.1-mini` (OpenAI)
- timeout: 15초
- max_tokens: 300
- temperature: 0.7

**컨텍스트 소스** (`market_router.py:152-157`):
- `canonical_listing` (title, description, price, tags)
- `confirmed_product` (brand, model, category, confidence)
- `market_context` (median_price, price_band, sample_count)
- `sale_status`

**환각 방지 규칙** (`market_router.py:214-236` 시스템 프롬프트):
1. 상품 설명 확인 사실 → "상품 설명에 따르면"으로 시작
2. 제품 일반 스펙 → "일반적으로 이 모델은"으로 시작 (참고 정보임을 명시)
3. 절대 추정 금지 5개 항목 → "판매자에게 직접 확인해주세요"
   - 정품 여부 / 구성품 포함 여부 / 보증 상태 / 배터리 잔량 / 하자·결함
4. 한국어 존댓말, 1~4문장
5. 불확실한 정보 → "확인이 필요합니다"

---

## 플랫폼 라우터 (`/api/v1/platforms`) — `app/api/platform_router.py`

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/platforms/status` | 플랫폼별 로그인 상태 조회 |
| `POST` | `/platforms/{platform}/login` | 플랫폼 로그인 시작 (서버 Playwright) |
| `POST` | `/platforms/connect/start` | 크롬 익스텐션 연동 토큰 발급 |
| `POST` | `/platforms/{platform}/connect` | 익스텐션 → 서버 쿠키·세션 전달 |

---

## Admin 라우터 (`/api/v1/admin`) — `X-Admin-Key` 헤더 인증 — `app/api/admin_router.py`

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/admin/publish-queue/stats` | 게시 큐 통계 |
| `GET` | `/admin/publish-queue/jobs` | 작업 목록 조회 |
| `GET` | `/admin/publish-queue/jobs/{job_id}` | 작업 단건 조회 |
| `POST` | `/admin/publish-queue/jobs/{job_id}/retry` | 작업 재시도 (pending으로 재설정) |
| `POST` | `/admin/publish-queue/jobs/{job_id}/force-fail` | 작업 강제 실패 처리 |
| `POST` | `/admin/publish-queue/platforms/{platform}/pause` | 특정 플랫폼 일시 중지 |
| `POST` | `/admin/publish-queue/users/{user_id}/disable` | 특정 사용자 게시 비활성화 |
| `POST` | `/admin/publish-queue/release-stuck` | deadlock 걸린 작업 복구 |

---

## 기타

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/health` | 헬스체크 (배포 CI에서 사용) |

---

## ProgressCard 상태별 카피

| status | title | subtitle |
|---|---|---|
| `images_uploaded` | 상품을 분석하고 있습니다 | 잠시만 기다려 주세요 |
| `market_analyzing` | 중고 시세를 분석 중입니다 | 비슷한 상품의 거래 데이터를 수집하고 있습니다 |
| `publishing` | 플랫폼에 게시 중입니다 | 선택한 플랫폼에 판매글을 올리고 있습니다 |

---

## ErrorCard 복구 액션

| status | 표시 메시지 | 복구 액션 |
|---|---|---|
| `publishing_failed` | 게시 중 오류가 발생했습니다 | 다시 시도 / 플랫폼 변경 후 재시도 |
| `failed` | 분석에 실패했습니다 | 처음부터 다시 시작 |

---

## 예외 매핑 (HTTP 상태 코드)

`app/main.py`의 `_DOMAIN_STATUS_MAP` 글로벌 핸들러 기준:

| 예외 | HTTP | 의미 |
|---|---|---|
| `SessionNotFoundError` | 404 | 세션 없음 |
| `InvalidUserInputError` | 400 | 입력 검증 실패 |
| `InvalidStateTransitionError` | 409 | 허용되지 않은 상태 전이 (세션 또는 판매 상태) |
| `ListingGenerationError` | 500 | 판매글 생성 실패 |
| `ListingRewriteError` | 500 | 판매글 재작성 실패 |
| `PublishExecutionError` | 502 | 게시 실행 복구 불가 오류 |
| `ValueError` (generic) | 400 | 입력 검증 실패 (도메인 예외 외) |

---

## 인증 정책

`app/core/auth.py` 기준:

| 환경 | 정책 |
|---|---|
| local / dev | JWT 토큰 → `X-Dev-User-Id` 헤더 → 기본값 `dev-user` 순 허용 |
| prod | JWT 필수 / `X-Dev-User-Id` 헤더 거부 (403) |
| 공개 엔드포인트 | `get_optional_user` 완화 모드 (마켓 목록/상세/챗봇/문의) |
