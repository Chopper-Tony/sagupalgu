---
paths:
  - "frontend/**"
---

# 프론트엔드 규칙 (React + Vite + TypeScript)

## 구조
- `src/types/` — `session.ts`, `ui.ts`, `market.ts` (SaleStatus, MarketItem, InquiryItem, MyListingItem)
- `src/lib/sessionStatusUiMap.ts` — 13개 상태 → CardType·ComposerMode·polling SSOT
- `src/lib/api.ts` — axios 클라이언트, baseURL `/api/v1`, timeout 120초, dev 환경 `X-Dev-User-Id` 자동 주입
- `src/hooks/useSession.ts` — SSE 실시간 + 스마트 폴링 fallback
- `src/hooks/useSessionActions.ts` — **모든 세션 액션 단일 집중 (CTO P1)**
- `src/hooks/useWishlist.ts`, `useRecentlyViewed.ts` — localStorage 기반
- `src/components/layout/` — AppShell, SessionSidebar, ThemeToggle
- `src/components/chat/` — ChatWindow(타임라인), ChatComposer(4가지 모드, 모바일 분기)
- `src/components/cards/` — 13개 상태별 카드 컴포넌트 (PublishResultCard 모바일 분기)
- `src/pages/` — MarketPage, MarketDetailPage, MyListingsPage

## 해시 라우팅
- `#/` — 셀러 코파일럿 (채팅 UI)
- `#/market` — 마켓 목록
- `#/market/{id}` — 마켓 상세 (AI 상품 챗봇 포함)
- `#/my-listings` — 판매자 대시보드 (문의 관리, 재등록, 코파일럿)

## 카드 렌더링
- 상태 변화 시 useEffect가 자동으로 카드 push (수동 pushItem 중복 금지)
- 상태가 동일한 경우만 수동 push 허용 (예: rewrite 후 draft_generated 유지)

## 액션 훅 (CTO P1)
- **App.tsx에 비즈니스 로직 금지** → 모든 액션은 `useSessionActions.ts`의 `createActionHandler(ctx)` 훅 사용
- 지원 액션 10종: `upload_images`, `confirm_product`, `prepare_publish`, `rewrite`, `publish`, `direct_edit`, `edit_draft`, `mark_sold/unsold`, `retry_publish`, `restart`
- 액션별 API 호출 → 상태 업데이트 → 타임라인 push → 에러 처리 모두 훅 내부
- `ActionContext`에 activeId, currentStatus, pushItem, setSession, setLastRenderedStatus 등 5~7개 의존성 주입

## 모바일 반응형
- 감지: `window.innerWidth <= 768` (PublishResultCard, ChatComposer 동일 로직)
- 모바일 = 사이드바 숨김 + `+` 버튼으로 세션 자동 생성 + 업로드
- 모바일 placeholder: 짧은 버전 (`PLACEHOLDER_MOBILE[mode]`)
- **게시 분기**:
  - 데스크톱: 크롬 익스텐션 자동 게시 (`postMessage` → Content Script)
  - 모바일: 판매글 전체 복사 버튼 + 플랫폼 `products/new` 직접 올리기 링크 (`PLATFORM_WRITE`)

## 테마
- 라이트/다크 토글: `ThemeToggle` 컴포넌트
- CSS 변수 기반 테마 시스템 (`--btn-padding`, `--text-primary`, `--bg-card` 등 공통 토큰)
- 하드코딩 색상 금지 — 모두 CSS 변수로 추상화

## 테스트
- vitest 60개 (hooks, lib, 타입 계약)
- 주요 대상: `useWishlist`, `useRecentlyViewed`, `hashRouting`, `sessionStatusUiMap`, `market-types`, `session-types`, `api-methods`
- FE/BE 타입 동기화: `scripts/generate_api_types.py --check` CI 필수

## 배포
- `Dockerfile`: node:20-alpine 멀티스테이지 + nginx:alpine
- `nginx.conf`: SPA routing + `/api/` 프록시 + 정적자산 캐시
