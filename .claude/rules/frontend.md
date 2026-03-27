---
paths:
  - "frontend/**"
---

# 프론트엔드 규칙 (React + Vite + TypeScript)

## 구조
- `src/types/` — `session.ts`(SessionStatus·SessionResponse), `ui.ts`(CardType·ComposerMode·TimelineItem)
- `src/lib/sessionStatusUiMap.ts` — 13개 상태 → CardType·ComposerMode·polling SSOT
- `src/lib/api.ts` — axios 클라이언트, baseURL `/api/v1`, timeout 120초
- `src/hooks/useSession.ts` — SSE 실시간 + 스마트 폴링 fallback (활성 2.5s / 비활성 10s)
- `src/components/layout/` — AppShell, SessionSidebar
- `src/components/chat/` — ChatWindow(타임라인), ChatComposer(4가지 모드)
- `src/components/cards/` — 13개 상태 전부 커버하는 카드 컴포넌트

## 카드 렌더링
- 상태 변화 시 useEffect가 자동으로 카드 push (수동 pushItem 중복 금지)
- 상태가 동일한 경우만 수동 push 허용 (예: rewrite 후 draft_generated 유지)

## 배포
- `Dockerfile`: node:20-alpine 멀티스테이지 + nginx:alpine
- `nginx.conf`: SPA routing + `/api/` 프록시 + 정적자산 캐시
