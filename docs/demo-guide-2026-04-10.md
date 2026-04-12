## 사구팔구 멘토링 시연 — 스텝바이스텝 가이드

**EC2 IP**: `44.222.120.125`
**서비스 URL**: `http://44.222.120.125`

---

### Phase 0 — 발표 30분 전 사전 준비

#### 0-1. EC2 SSH 접속 + 서비스 기동
```bash
# 로컬 PowerShell/Bash에서
ssh -i <키페어.pem> ubuntu@44.222.120.125

# EC2 안에서
cd ~/sagupalgu
git pull origin main          # 최신 코드 (익스텐션 IP 변경 포함)

# 컨테이너 상태 확인
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# 정지 상태면 기동
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 헬스 체크 (1~2분 대기 후)
curl http://localhost:8000/health
curl http://localhost:8000/health/ready | jq
```

**기대 결과**: `caddy`, `backend`, `worker`, `frontend` 4개 컨테이너 모두 `Up (healthy)`

#### 0-2. 외부에서 접속 확인
브라우저에서 `http://44.222.120.125` 접속 → 사구팔구 랜딩 페이지 정상 렌더링 확인.

> ⚠️ 보안그룹에서 80/443 포트가 열려 있어야 함. AWS 콘솔 → EC2 → 보안그룹 → 인바운드 규칙 확인.

#### 0-3. 익스텐션 재로드 (IP 갱신 반영)
1. Chrome에서 `chrome://extensions/` 접속
2. 우측 상단 "개발자 모드" 켜짐 확인
3. **사구팔구 플랫폼 연동** 카드의 **새로고침 버튼** 클릭 (방금 갱신한 IP 반영)
4. 익스텐션 아이콘 클릭 → "서버 URL (고급)" 입력란이 `http://44.222.120.125`로 표시되는지 확인

#### 0-4. 플랫폼 로그인 (쿠키 수집)
1. **별도 탭에서** `https://m.bunjang.co.kr` 로그인 (수동)
2. **별도 탭에서** `https://web.joongna.com` 로그인 (수동)
3. 사구팔구 웹앱(`http://44.222.120.125`)에서 우하단 **사이드바 → 플랫폼 연동** 섹션 확인
   - "Connect Token 발급" 클릭 → 토큰 복사
4. 익스텐션 팝업 열기
   - 번개장터/중고나라 각각 connect token 붙여넣기 → "연결" 버튼
   - "연결 완료" 메시지 확인

#### 0-5. 데모 상품 이미지 미리 준비
- 가장 안정적으로 성공하는 카테고리: **스마트폰 / 태블릿 / 노트북** (Vision AI 인식률 높음)
- 사진 2~3장, 깔끔한 배경, 1MB~5MB
- 데스크톱에 폴더로 정리 (드래그&드롭용)

---

### Phase 1 — 발표 시작 (오프닝 + 아키텍처 설명)

#### 1-1. 프로젝트 소개 (1분)
> "중고거래 자동 게시 플랫폼입니다. 이미지만 올리면 AI가 상품 분석 → 시세 산정 → 판매글 작성 → 자동 게시까지 처리합니다. LangGraph 기반 7 에이전트 / 10 툴 / 3 Agentic Loop 구조입니다."

#### 1-2. 아키텍처 다이어그램 보여주기 (2분)
- `C:\Users\bonjo\.claude\plans\smooth-finding-wave.md` 열기
- **[1] 전체 시스템 조감도** → "프론트/백/익스텐션이 어떻게 연결되는지"
- **[2] LangGraph 워크플로우** → "7 에이전트가 어떻게 협력하는지"
- **[3] Before→After** → "왜 서버 게시에서 익스텐션으로 전환했는지" (계정 정지 스토리 — 핵심 어필 포인트)

---

### Phase 2 — 라이브 데모 (8~10분)

#### 2-1. 웹앱 접속
브라우저: `http://44.222.120.125`

#### 2-2. 새 세션 시작
1. **랜딩 페이지 → "새 세션 시작"** 클릭
2. 사이드바에 새 세션 카드 생성됨 확인

#### 2-3. 이미지 업로드
1. 채팅 영역 **이미지 업로드 카드** 등장
2. **준비한 사진 2~3장 드래그&드롭** (또는 클릭 후 선택)
3. 업로드 진행률 표시 → 자동 업로드 완료

#### 2-4. AI 상품 식별 (자동 진행)
- 자동으로 Vision AI 호출 → 상품 후보 카드 등장
- **멘트**: "Vision AI(gpt-4.1-mini)가 사진을 분석해서 상품 후보를 3개까지 제시합니다. confidence가 낮으면 사용자에게 다시 물어봅니다."
- 적절한 후보 클릭 → "이 상품으로 확정"

#### 2-5. 추가 정보 입력 (Pre-listing Clarification)
- 상품 상태 / 사용기간 / 구성품 / 거래방법 4개 항목 질문 카드 등장
- **멘트**: "정보가 부족하면 LangGraph가 사용자 입력을 기다립니다. 이게 3개 Agentic Loop 중 Clarification Loop입니다."
- 간단히 입력 → "다음"

#### 2-6. 시세 분석 + 판매글 자동 생성 (자동 진행)
- 진행 상태 카드: "시세 분석 중 → 판매글 생성 중 → AI 비평 중..."
- **멘트**: "Agent 2(시세)가 ReAct로 번개장터·중고나라를 크롤링하고, RAG로 가격을 산정합니다. Agent 3(카피)가 판매글을 쓰고, Agent 6(Critic)이 70점 미만이면 재작성 루프를 돕니다."
- 약 30초~1분 후 **DraftCard** 등장
  - 제목, 설명, 가격, 태그
  - **AI 품질 평가 섹션** (Critic score, 피드백) — 멘토에게 어필 포인트
  - **에이전트 의사결정 시각화** (도구 호출 이력, 실행 전략, 의사결정 근거)

#### 2-7. 게시 준비
1. DraftCard에서 **플랫폼 선택**: 번개장터 + 중고나라
2. **"게시 준비"** 버튼 클릭
3. **PublishApprovalCard** 등장 → 최종 확인

#### 2-8. 자동 게시 (익스텐션 Content Script)
1. **"자동 게시"** 버튼 클릭
2. **멘트 (이게 핵심!)**:
   > "여기서부터가 우리 시스템의 차별점입니다. 서버에서 Playwright로 게시하면 미국 IP라서 계정이 정지됩니다. 그래서 크롬 익스텐션의 Content Script가 사용자 브라우저에서 직접 폼을 채웁니다. CDP Runtime.evaluate + React fiber onChange로 이미지 업로드까지 해결했어요."
3. 새 탭이 열리고 **번개장터 등록 페이지**가 자동으로 채워지는 모습 보여주기
4. 이어서 **중고나라 등록 페이지**도 자동 채움
5. 게시 완료 후 **PublishResultCard**에 두 플랫폼 게시글 URL 표시

#### 2-9. 자체 마켓 (M137, M143)
1. 사이드바 또는 URL: `http://44.222.120.125/#/market`
2. **마켓 페이지**: 방금 게시한 상품 + 기존 상품 카드 그리드
3. 상품 카드 클릭 → **상세 페이지**
   - 이미지 갤러리
   - **플랫폼 게시 링크 바로가기** (번개장터/중고나라로 직접 이동)
   - **검색 + 가격 필터** 시연
   - **구매 문의** 폼 작성 → Discord 웹훅 알림 도착 보여주기 (Discord 미리 띄워두기)

---

### Phase 3 — 백엔드 동작 시연 (선택, 1~2분)

EC2 SSH 터미널을 화면에 띄워두고:

```bash
# 워커 로그 실시간 (게시 처리 과정)
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f worker --tail 50

# 백엔드 로그
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend --tail 50
```

**멘트**: "JSON 구조화 로깅으로 request_id, session_id, 상태 전이, tool_calls가 전부 추적됩니다."

---

### Phase 4 — Q&A 대응 준비

#### 멘토가 물어볼 만한 질문 + 답변 포인트

| 질문 | 답변 |
|---|---|
| "왜 LangGraph인가? FastAPI만으로도 되지 않나?" | 7 에이전트 / 3 Loop를 코드로 직접 짜면 상태 머신이 폭발한다. LangGraph가 노드/엣지/체크포인트를 관리해서 비평→재작성, 계획→실행→재계획 루프가 깔끔하게 표현된다. |
| "Vision AI 비용은?" | gpt-4.1-mini 기준 이미지 1장당 약 $0.001. 게시 1건당 $0.005~0.01 수준. |
| "익스텐션 없이는 안 되는가?" | 서울 리전 EC2로 전환하면 서버 Playwright 복원 가능. 하지만 익스텐션은 사용자 IP/쿠키/핑거프린트 그대로 쓰기 때문에 탐지가 거의 불가능. 이중화가 베스트. |
| "테스트는?" | 723개 (unit 380 + integration 180 + E2E + FE 21). CI에서 매 PR마다 자동 실행. |
| "당근마켓은?" | Android 에뮬레이터 필요해서 보류. 발표 후 우선순위 재조정. |
| "법적 리스크는?" | 교육/연구 목적. 자체 마켓 본격화 시 통신판매업 신고 검토. |

#### 발표용 핵심 어필 포인트 3가지
1. **계정 정지 → Content Script 전환** 스토리 (실패에서 배운 것)
2. **CDP + React fiber** 이미지 업로드 난제 해결 (5번 시도 끝에)
3. **7 에이전트 + 3 Agentic Loop** Goal-driven 행동 변화 (같은 상품도 fast_sell/balanced/profit_max에 따라 가격·톤·비평 기준이 달라짐)

---

### Phase 5 — 트러블슈팅 (혹시 모를 상황)

| 증상 | 원인 | 즉시 대응 |
|---|---|---|
| 사이트 접속 안 됨 | 컨테이너 다운 / 보안그룹 미개방 | `docker compose ... ps` 확인, 80/443 인바운드 확인 |
| Vision 분석 실패 | OPENAI_API_KEY 만료 / 쿼터 | `.env` 확인, `docker compose logs backend \| grep -i error` |
| 이미지 업로드 후 무한 로딩 | uploads 볼륨 권한 | `docker compose exec backend ls -la /app/uploads` |
| 익스텐션이 서버 호출 실패 | IP 갱신 미반영 | `chrome://extensions/`에서 익스텐션 새로고침 |
| 익스텐션 게시 시 "쿠키 없음" | 플랫폼 로그인 만료 | 별도 탭에서 재로그인 → connect token 재발급 |
| 번개장터 자동 게시 멈춤 | DOM 변경 | "수동 첨부" fallback 안내, 폼은 자동 채워졌으니 "등록" 버튼만 누르면 됨 |
| 워커 OOM | 메모리 초과 | `MAX_CONCURRENT_BROWSERS=1` 확인, 워커 재시작 `docker compose restart worker` |

#### 비상 백업 시나리오
- 라이브 데모가 망가지면 **자체 마켓 페이지 (`/#/market`)**만 보여주기 → 이미 등록된 상품으로 검색/필터/구매문의 시연
- 그것도 안 되면 **로컬에서 미리 녹화한 영상** 재생 (사전에 한 번 녹화 권장)

---

## 변경된 파일 (이번 작업)

| 파일 | 변경 내용 |
|---|---|
| `sagupalgu-extension/background.js:9` | DEFAULT_SERVER_URL → `http://44.222.120.125` |
| `sagupalgu-extension/popup.js:5` | DEFAULT_SERVER_URL → `http://44.222.120.125` |
| `sagupalgu-extension/popup.html:105` | input value → `http://44.222.120.125` |

> 이 변경은 **로컬 익스텐션에 즉시 반영**되니 `chrome://extensions/`에서 새로고침만 누르면 됩니다. EC2 재배포는 필요 없습니다.
