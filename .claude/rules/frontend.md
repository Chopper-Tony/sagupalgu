---
paths:
  - "frontend/**"
---

# 프론트엔드 규칙 (React + Vite + TypeScript)

## 구조
- `src/types/` — `session.ts`, `ui.ts`, `market.ts` (SaleStatus, MarketItem, InquiryItem, MyListingItem)
- `src/lib/sessionStatusUiMap.ts` — 13개 상태 → CardType·ComposerMode·polling SSOT
- `src/lib/api.ts` — axios 클라이언트, baseURL `/api/v1`, timeout 120초. prod: Supabase JWT `Authorization: Bearer` 주입 + 401 → `#/login` 리다이렉트. dev: `X-Dev-User-Id` bypass 유지
- `src/lib/supabase.ts` — Supabase 클라이언트 싱글턴 (`VITE_SUPABASE_URL`·`VITE_SUPABASE_ANON_KEY` 필요)
- `src/contexts/AuthContext.tsx` — user·session 상태 + signInWithPassword·signUpWithPassword·signInWithGoogle·signOut. `onAuthStateChange` 구독
- `src/pages/LoginPage.tsx` — 이메일/비밀번호 + Google OAuth 로그인 UI
- `src/components/UserMenu.tsx` — 로그인 사용자 표시 + 로그아웃 버튼 (Supabase 설정 환경에서만 노출)
- `src/hooks/useSession.ts` — SSE 실시간 + 스마트 폴링 fallback
- `src/hooks/useSessionActions.ts` — **모든 세션 액션 단일 집중 (CTO P1)**
- `src/hooks/useWishlist.ts`, `useRecentlyViewed.ts` — localStorage 기반
- `src/components/layout/` — AppShell, SessionSidebar, ThemeToggle
- `src/components/chat/` — ChatWindow(타임라인), ChatComposer(4가지 모드, 모바일 분기)
- `src/components/cards/` — 13개 상태별 카드 컴포넌트 (PublishResultCard 모바일 분기)
- `src/pages/` — MarketPage, MarketDetailPage, MyListingsPage

## 해시 라우팅
- `#/` — 셀러 코파일럿 (채팅 UI, 인증 필요)
- `#/login` — 로그인 페이지 (이메일 + Google OAuth)
- `#/market` — 마켓 목록 (공개)
- `#/market/{id}` — 마켓 상세 (공개, AI 상품 챗봇 포함)
- `#/my-listings` — 판매자 대시보드 (인증 필요)

## 인증 게이트
- prod + Supabase 설정 환경: `#/` 과 `#/my-listings` 진입 전 로그인 필수. 미로그인 시 LoginPage 리다이렉트
- dev 환경: `X-Dev-User-Id` bypass로 인증 게이트 건너뜀 (기존 개발 플로우 유지)
- 401 응답: api interceptor가 `#/login` 으로 자동 이동

## 카드 렌더링
- 상태 변화 시 useEffect가 자동으로 카드 push (수동 pushItem 중복 금지)
- 상태가 동일한 경우만 수동 push 허용 (예: rewrite 후 draft_generated 유지)

## 액션 훅 (CTO P1)
- **App.tsx에 비즈니스 로직 금지** → 모든 액션은 `useSessionActions.ts`의 `createActionHandler(ctx)` 훅 사용
- 지원 액션 (12 case, 11 unique):
  1. `upload_images` — `handleUploadImages` 위임
  2. `confirm_product` — provideProductInfo → generateListing → sellerTips 로드
  3. `prepare_publish` — 게시 준비 (플랫폼 선택)
  4. `rewrite` — rewriteListing 호출
  5. `publish` — 게시 실행
  6. `direct_edit` — updateListing (제목·설명·가격·태그 직접 수정)
  7. `edit_draft` — DraftCard 재렌더링만 (상태 변경 없음)
  8. `update_sale_status` / `mark_sold` — fall-through, `updateSaleStatus("sold")` 호출
  9. `mark_unsold` — `updateSaleStatus("unsold")` 호출
  10. `retry_publish` — publish 재호출
  11. `restart` — `handleNewSession` 위임
- `ActionContext` 타입: `activeId`, `currentStatus`, `pushItem`, `setSession`, `setLastRenderedStatus`, `handleNewSession`, `handleUploadImages` (7개 필드)
- `friendlyError()` 헬퍼: HTTP status 코드 → 한국어 사용자 친화 메시지 변환 (409/422/429/timeout/Network/502/500/404 분기)
- 액션별 API 호출 → 상태 업데이트 → 타임라인 push → 에러 처리 모두 훅 내부

## 모바일 반응형
- 감지: `window.innerWidth <= 768` (PublishResultCard, ChatComposer 동일 로직)
- 모바일 = 사이드바 숨김 + `+` 버튼으로 세션 자동 생성 + 업로드
- 모바일 placeholder: 짧은 버전 (`PLACEHOLDER_MOBILE[mode]`)
- **게시 분기**:
  - 데스크톱: 크롬 익스텐션 자동 게시 (`postMessage` → Content Script). `PublishResultCard` 가 `useAuth().session.access_token` 을 postMessage payload 에 포함 → 익스텐션이 백엔드 `/publish-data` 인증 호출 가능 (#251)
  - 모바일: 판매글 전체 복사 버튼 + 플랫폼 `products/new` 직접 올리기 링크 (`PLATFORM_WRITE`)

## 테마
- 라이트/다크 토글: `ThemeToggle` 컴포넌트
- CSS 변수 기반 테마 시스템 (`--btn-padding`, `--text-primary`, `--bg-card` 등 공통 토큰)
- 하드코딩 색상 금지 — 모두 CSS 변수로 추상화

## 테스트
- vitest 67개 (hooks, lib, 컴포넌트, 타입 계약)
- 주요 대상: `useWishlist`, `useRecentlyViewed`, `hashRouting`, `sessionStatusUiMap`, `market-types`, `session-types`, `api-methods`, `PublishResultCard` (postMessage JWT)
- FE/BE 타입 동기화: `scripts/generate_api_types.py --check` CI 필수

## 배포
- `Dockerfile`: node:20-alpine 멀티스테이지 + nginx:alpine
- `nginx.conf`: SPA routing + `/api/` 프록시 + 정적자산 캐시
