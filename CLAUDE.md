# CLAUDE.md

## 프로젝트 개요
중고거래(당근, 번개장터, 중고나라) 자동 게시 플랫폼.
이미지 → AI 분석 → 가격 산정 → 카피라이팅 → 게시 의 파이프라인을 LangGraph로 구현.

## 기술 스택
- **백엔드**: FastAPI + Pydantic v2
- **워크플로우**: LangGraph (`app/graph/`)
- **Vision AI**: OpenAI (실사용), Gemini (구조만, graceful fallback)
- **DB**: Supabase (PostgreSQL + Storage)
- **크롤러/게시**: Playwright (웹), uiautomator2 (Android 에뮬레이터)

## 아키텍처 원칙

### 데이터 흐름
이미지 → `preprocess` → `product_identity` → [사용자 확인] → `market_intelligence` → `pricing` → `copywriting` → `validation` → 게시

### 레이어 구조
- `app/agents/` - LangGraph 노드 로직 (AI 에이전트)
- `app/graph/` - LangGraph StateGraph 정의
- `app/tools/` - 에이전트가 사용하는 유틸 툴
- `app/crawlers/` - 시세 크롤러 (legacy wrapper)
- `app/publishers/` - 플랫폼 게시 (legacy adapter)
- `app/builders/` - 플랫폼별 PlatformPackage 빌더
- `app/services/` - 비즈니스 로직
- `app/repositories/` - Supabase CRUD
- `app/vision/` - VisionProvider 추상화

### 상태 관리
- 워크플로우 상태는 `SellSessionState` 기반
- Graph는 두 단계로 분리: `build_graph()` (상품 확인 전), `build_post_confirmation_graph()` (확인 후)

## 코딩 규칙

### agents/
- 반드시 LangGraph 노드 함수 형태로 구현 (`state: SellSessionState` 인자)
- 직접 publish하지 말 것, 항상 builder → publisher 경유

### publishers/
- `app/publishers/` 는 legacy spike를 감싸는 **adapter** 패턴
- 당근 게시는 반드시 `DaangnPublisher` (`app/publishers/daangn_publisher.py`) 경유
- 당근은 Android 에뮬레이터 기반 (`uiautomator2`, `device_id` 필요)

### crawlers/
- `app/crawlers/` 는 legacy `MarketCrawler`를 감싸는 **wrapper** 패턴
- 실데이터 크롤링 전략은 아직 미확정 (당근 crawler)

### legacy_spikes/
- `legacy_spikes/` 는 **읽기 전용**, 직접 수정 금지
- 참고용으로만 사용하고, 기능 변경은 `app/` 레이어에서

## 현재 미완성 항목 (TODO)
- Supabase 테이블/버킷 미생성
- 플랫폼 계정 secret loader 미구현
- Playwright / 에뮬레이터 세션 확보 필요
- OpenAI / Gemini 응답 schema 튜닝 필요
- 당근 crawler 실데이터 전략 미확정

## 자주 쓰는 명령어
```bash
# 의존성 설치
pip install -r requirements.txt
python -m playwright install chromium

# 환경 설정
cp .env.example .env  # SECRET_ENCRYPTION_KEY 등 입력 필요

# 수동 spike 스크립트 실행
python scripts/manual_spikes/save_sessions.py
python scripts/manual_spikes/test_bunjang_publish.py
```
