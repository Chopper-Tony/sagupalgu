# API Contract — 상태·카드·액션 매핑

> M16 프론트엔드 개발 기준 설계 문서.
> `sessionStatusUiMap.ts` 구현의 단일 진실 원천.

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
| `awaiting_product_confirmation` | `ProductConfirmationCard` | 상품 확정 / 수정 입력 | `POST /sessions/{id}/provide-product-info` | `market_analyzing` |
| `market_analyzing` | `ProgressCard` | 없음 (자동 진행) | — | `draft_generated` \| `failed` |
| `draft_generated` | `DraftCard` | 승인 / 재작성 지시 | `POST /sessions/{id}/prepare-publish` \| `POST /sessions/{id}/generate-listing` | `awaiting_publish_approval` \| `draft_generated` |
| `awaiting_publish_approval` | `PublishApprovalCard` | 게시 승인 | `POST /sessions/{id}/publish` | `publishing` |
| `publishing` | `ProgressCard` | 없음 (자동 진행) | — | `completed` \| `publishing_failed` |
| `completed` | `PublishResultCard` | 판매 상태 업데이트 | `POST /sessions/{id}/sale-status` | `awaiting_sale_status_update` |
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

## 주요 API 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| `POST` | `/sessions` | 세션 생성 |
| `GET` | `/sessions/{id}` | 세션 상태 조회 (폴링용) |
| `POST` | `/sessions/{id}/images` | 이미지 업로드 + 분석 시작 |
| `POST` | `/sessions/{id}/provide-product-info` | 상품 정보 확정 |
| `POST` | `/sessions/{id}/generate-listing` | 판매글 생성 / 재작성 |
| `POST` | `/sessions/{id}/prepare-publish` | 게시 준비 (플랫폼 선택) |
| `POST` | `/sessions/{id}/publish` | 게시 실행 |
| `POST` | `/sessions/{id}/sale-status` | 판매 상태 업데이트 |
| `GET` | `/health` | 헬스체크 |

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
