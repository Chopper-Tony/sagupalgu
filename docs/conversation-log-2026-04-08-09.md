# 사구팔구 개발 대화 기록 (2026-04-08 ~ 04-09)

## 목차
1. [EC2 배포 + 테스트 시작](#1-ec2-배포--테스트-시작)
2. [Elastic IP 시도 + 실패](#2-elastic-ip-시도--실패)
3. [크롬 익스텐션 연결 문제](#3-크롬-익스텐션-연결-문제)
4. [게시 부분 성공 처리](#4-게시-부분-성공-처리)
5. [중고나라 CloudFront 403 차단](#5-중고나라-cloudfront-403-차단)
6. [Content Script vs Playwright 논의](#6-content-script-vs-playwright-논의)
7. [번개장터 계정 영구정지](#7-번개장터-계정-영구정지)
8. [Content Script 방식 전환 결정](#8-content-script-방식-전환-결정)
9. [이미지 업로드 해결 과정](#9-이미지-업로드-해결-과정)
10. [게시 UX 통합](#10-게시-ux-통합)
11. [Supabase 보안 경고 대응](#11-supabase-보안-경고-대응)
12. [기술적/정책적 리스크 분석](#12-기술적정책적-리스크-분석)
13. [자체 마켓 논의](#13-자체-마켓-논의)
14. [서울 리전 전환](#14-서울-리전-전환)

---

## 1. EC2 배포 + 테스트 시작

### 상황
- EC2 인스턴스(us-east-1, t3.micro) 시작
- AWS 콘솔에서 "초기화" 표시 → 1~2분 대기 후 정상
- 리전 제한 정책(RestrictRegionVirginia)으로 다른 리전 접근 불가

### 핵심 교훈
- EC2 인스턴스 시작 후 상태 검사 통과까지 1~2분 소요 — 정상
- 이미 배포 완료 상태면 SSH 접속 불필요, 브라우저에서 바로 테스트

---

## 2. Elastic IP 시도 + 실패

### 상황
- 인스턴스 재시작마다 퍼블릭 IP 변경 → 익스텐션 서버 URL 수동 갱신 필요
- Elastic IP 할당 시도 → `ec2:AllocateAddress` 권한 없음 (교육기관 IAM 제한)

### 대응
- 익스텐션 팝업 "서버 URL (고급)" 입력란에서 수동 변경
- 코드의 DEFAULT_SERVER_URL은 배포 시 갱신

### 핵심 교훈
- 교육기관 AWS 계정은 IAM 권한이 제한적
- Elastic IP 없이도 운영 가능 — 익스텐션 고급 설정으로 대응

---

## 3. 크롬 익스텐션 연결 문제

### 상황
- 익스텐션에서 "연결" 클릭 시 "Failed to fetch" 에러
- 원인: DEFAULT_SERVER_URL이 이전 IP로 하드코딩

### 해결
- background.js, popup.html의 서버 URL을 현재 EC2 IP로 갱신

### 핵심 교훈
- EC2 IP 변경 시 갱신해야 할 파일: background.js, popup.html, popup.js (3곳)
- 또는 익스텐션 팝업에서 수동 입력 (코드 수정 없이)

---

## 4. 게시 부분 성공 처리

### 상황
- 번개장터 성공 + 중고나라 실패 → 전체가 `publishing_failed`로 표시
- 번개장터 성공 결과가 묻힘

### 해결
- publish_orchestrator.py, publish_worker.py: `any_success` 체크 추가
- 1개라도 성공 → `completed`, 전부 실패 → `publishing_failed`
- ChatWindow.tsx: ProgressCard/ErrorCard switch case 누락 추가

### 핵심 교훈
- 부분 성공은 성공으로 처리하되, 실패 정보도 함께 표시
- switch문에서 모든 카드 타입을 커버하는지 확인 필수

---

## 5. 중고나라 CloudFront 403 차단

### 상황
- EC2에서 중고나라 접속 시 CloudFront 403 ERROR
- AWS IP 대역 자체를 봇 방지로 차단

### 발견
- 스크린샷 다운로드하여 확인 → CloudFront 403 페이지
- 셀렉터 문제가 아니라 접속 자체가 차단

### 대응
- joongna.py에 403 감지 코드 추가
- publish_policy.py에 `access_blocked` 에러 분류 추가
- 익스텐션 쿠키 연동 후 서버 Playwright 접속 성공 (쿠키가 있으면 CloudFront 통과)

### 핵심 교훈
- CloudFront/WAF는 IP 기반 + 쿠키 기반으로 차단 판단
- 쿠키가 있으면 "로그인된 사용자"로 인식하여 통과 가능
- 하지만 근본적으로 불안정 — Content Script가 더 안전

---

## 6. Content Script vs Playwright 논의

### Content Script
- 사용자 브라우저에서 실행 → 사용자 IP, 쿠키, 핑거프린트 그대로
- 웹사이트가 자동화 탐지 불가능
- 이미지 업로드 어려움 (브라우저 보안 제약)
- 크롬 익스텐션 설치만 필요

### Playwright (서버)
- 서버에서 별도 Chromium 실행 → 서버 IP 노출
- navigator.webdriver 등 자동화 탐지 가능
- set_input_files()로 이미지 업로드 쉬움
- Python/Node.js 환경 필요

### Playwright (클라이언트/Electron)
- 사용자 PC에서 실행 → 사용자 IP
- 별도 앱 설치 필요 (200~300MB)
- set_input_files() 사용 가능
- 크로스 플랫폼 빌드 부담

### 결론
- **Content Script가 차단 위험 가장 낮음** (사용자 진짜 브라우저에서 실행)
- Electron은 이상적이지만 구현/배포 비용 큼
- Content Script + CDP로 이미지 업로드 해결

---

## 7. 번개장터 계정 영구정지

### 상황
- 번개장터에서 "사기 정황이 명확히 탐지" → 계정 영구정지
- 원인 추정: 한국에서 로그인 → 미국 IP에서 게시 (계정 탈취 패턴)
- 짧은 시간 다수 테스트도 한 원인

### 대응
- 이의제기 메시지 작성 (자동화 언급 없이)
- Content Script 전환으로 서버 IP 노출 제거
- 새 계정 필요

### 핵심 교훈
- 서버 Playwright로 플랫폼 게시는 리전 불일치 시 계정 정지 위험
- 테스트 시: 하루 1~2건, 즉시 삭제, 실물 상품만
- Content Script는 사용자 IP라 안전

---

## 8. Content Script 방식 전환 결정

### 전환 이유
1. 번개장터: 계정 영구정지 (IP 불일치)
2. 중고나라: CloudFront 403 차단 (AWS IP)
3. Content Script: 차단 위험 최저 (사용자 브라우저)

### 구현
- EXTENSION_ONLY_PLATFORMS = {"joongna", "bunjang"}
- 서버 Playwright 비활성화 (코드 유지, 설정으로 전환)
- joongna_publish.js, bunjang_publish.js Content Script
- CDP Runtime.evaluate로 이미지 업로드

### 핵심 교훈
- 설정값 하나(EXTENSION_ONLY_PLATFORMS)로 서버/익스텐션 전환 가능
- 서울 리전 전환 시 다시 서버 Playwright 복원 가능

---

## 9. 이미지 업로드 해결 과정

### 시도 1: Content Script input.files 직접 설정
- `fileInput.files = dt.files` + change 이벤트
- **실패**: React가 변경을 감지 못함

### 시도 2: DragEvent 시뮬레이션
- dragenter → dragover → drop 이벤트
- **실패**: 브라우저 보안 정책상 DragEvent의 dataTransfer.files가 read-only

### 시도 3: input.click() 인터셉트
- HTMLInputElement.prototype.click 몽키패치
- **실패**: 복잡하고 불안정

### 시도 4: CDP DOM.setFileInputFiles + chrome.downloads
- 이미지를 로컬에 다운로드 → CDP로 파일 경로 설정
- **실패**: chrome.downloads가 탐색기 대화상자를 열음 (saveAs: false에도)

### 시도 5 (성공): CDP Runtime.evaluate + React fiber onChange
- Background에서 fetch() → base64 변환
- CDP Runtime.evaluate로 페이지 내에서 File 생성 → input.files 설정
- React fiber에서 onChange 핸들러 직접 호출
- **성공!** 탐색기 안 뜨고, 로컬 파일 저장 불필요

### 추가 문제: 이미지 URL 404
- publish-data API에서 `image_urls` 키가 `image_paths`여야 했음
- nginx에서 `/uploads/` 프록시 누락 → `^~` prefix로 regex보다 우선 적용

### 추가 문제: 중고나라 AI 덮어쓰기
- 이미지 첨부 시 중고나라 자체 AI가 폼을 덮어씀
- 해결: "AI로 작성하기" 토글 자동 비활성화
- fallback: 수동 첨부 후 상품명/가격/설명 복원

### 핵심 교훈
- file input 프로그래밍 주입은 브라우저 보안상 매우 어려움
- CDP Runtime.evaluate + React fiber 직접 호출이 가장 확실
- chrome.downloads는 사용자 설정에 따라 대화상자를 열 수 있음
- nginx location 우선순위: `^~` prefix > regex

---

## 10. 게시 UX 통합

### 문제
- 세션 ID를 수동으로 복사 → 익스텐션 팝업에 붙여넣기 → 자동 게시 버튼
- 3단계가 번거로움

### 해결
- publish_bridge.js: 사구팔구 웹앱 페이지에 주입되는 Content Script
- window.postMessage → chrome.runtime.sendMessage → background.js
- PublishResultCard에 "자동 게시" 버튼 추가

### 인증 문제
- bridge에서 /publish-data API 직접 호출 → JWT 인증 필요 → 실패
- 해결: FETCH_AND_PUBLISH 메시지로 background에 위임 (background는 인증 불필요)

### 핵심 교훈
- Content Script는 페이지 컨텍스트에서 실행되지만, API 인증은 별도
- background script에서 fetch하면 CORS/인증 제약 없음
- 익스텐션 업데이트 후 웹페이지도 새로고침 필수 (Content Script 재주입)

---

## 11. Supabase 보안 경고 대응

### 경고 내용
1. Table publicly accessible (RLS 미설정)
2. Sensitive data publicly accessible
3. Function search_path mutable

### 해결
```sql
ALTER TABLE sell_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access" ON sell_sessions FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Users access own sessions" ON sell_sessions FOR ALL USING (auth.uid()::text = user_id);
-- publish_jobs도 동일
ALTER FUNCTION public.update_publish_jobs_updated_at() SET search_path = public;
```

### 핵심 교훈
- service_role_key는 RLS를 우회하므로 서버 코드 영향 없음
- RLS 활성화 = 직접 Supabase API 접근만 차단
- SQL 실행 = Supabase 활동 기록 → 프로젝트 일시중지 방지 효과도 있음

---

## 12. 기술적/정책적 리스크 분석

### 기술적 리스크
- DOM 구조 변경 → Content Script 셀렉터 깨짐 (확률 높음, 수정 30분)
- CDP 이미지 불안정 → 수동 첨부 fallback 있음
- EC2 자동 중지 → 발표 전 확인 필수
- EC2 IP 변경 → 익스텐션 URL 갱신

### 정책적 리스크
- 플랫폼 약관 위반 가능 (교육/연구 목적 명시)
- Content Script는 탐지 불가능 (사용자 브라우저)
- 개인정보 처리 (Fernet 암호화 + RLS)

---

## 13. 자체 마켓 논의

### CTO 관점 판단
- 기존 사구팔구에 붙이기 (새로 짜지 않음)
- AI 파이프라인이 핵심 가치, 마켓은 출구
- sell_sessions의 completed 상태 = 등록된 상품

### 구현
- GET /api/v1/market (공개, 인증 불필요)
- MarketPage 컴포넌트 (카드 그리드, 다크 테마)
- 해시 라우팅 (#/market)

### 정책적 리스크
- 자체 마켓 운영 시: 통신판매업 신고, 개인정보처리방침, 전자상거래법
- 프로토타입 범위에서는 문제 없음

---

## 14. 서울 리전 전환

### 교육기관 대응
- EBS 20GB 증설: 완료
- 서울 리전 t3.micro: 프록시용으로 제안 받음
- t3.small + EBS 20GB로 메인 서비스 이전 요청

### 서울 리전 장점
- 한국 IP → 플랫폼 차단/정지 위험 제거
- 서버 Playwright 복원 가능 (EXTENSION_ONLY_PLATFORMS에서 제거만 하면)
- 사용자 체감 속도 향상
- 코드 수정 0줄 (환경 변수 + Docker만 동일 세팅)

---

## 기술 스택 변천

```
초기:     서버 Playwright (headless) → 플랫폼 직접 게시
  ↓ 문제: 미국 IP → 번개장터 계정 정지, 중고나라 CloudFront 차단
전환:     크롬 익스텐션 Content Script → 사용자 브라우저에서 게시
  ↓ 문제: 이미지 업로드 (브라우저 보안 제약)
해결:     CDP Runtime.evaluate + React fiber onChange
  ↓ 개선: publish_bridge.js로 원클릭 자동 게시
현재:     Content Script + CDP 이미지 + 서버 AI 파이프라인 하이브리드
향후:     서울 리전 전환 시 서버 Playwright 복원 가능
```

## PR 이력

| PR | 내용 | 상태 |
|---|------|------|
| #127 | 중고나라 이미지 CDP | 머지 |
| #128 | 번개장터 Content Script | 머지 |
| #129 | 게시 UX 통합 | 머지 |
| #130 | M133~M135 문서화 | 머지 |
| #131 | M136 UX 개선 + M137 마켓 | 머지 |

## 마일스톤 이력

| # | 내용 | 상태 |
|---|------|------|
| M133 | 부분 성공 + 중고나라 CDP 이미지 | 완료 |
| M134 | 번개장터 Content Script | 완료 (테스트 미진행) |
| M135 | 게시 UX 통합 + RLS | 완료 |
| M136 | 프론트 UX 개선 (7항목) | 완료 |
| M137 | 자체 마켓 프로토타입 | 완료 |
