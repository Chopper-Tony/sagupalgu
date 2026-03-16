# Sagupalgu Integrated Base

사구팔구 spike 코드 + 구조화된 skeleton을 합친 통합 베이스입니다.

## 포함된 것
- FastAPI skeleton
- LangGraph workflow skeleton
- VisionProvider 추상화
- Publisher / Builder / Repository / Service 구조
- 기존 spike 코드 복사본 (`legacy_spikes/secondhand_publisher`)
- 수동 실행용 spike 스크립트 (`scripts/manual_spikes/`)

## 아직 TODO인 것
- OpenAI 실제 프롬프트 튜닝
- Gemini provider 실제 연결 검증
- Supabase 테이블 생성 및 버킷 설정
- 당근 에뮬레이터 실환경 재검증
- spike 셀렉터 안정화

## 실행 전
1. `.env.example`를 복사해서 `.env` 생성
2. `SECRET_ENCRYPTION_KEY` 발급
3. Supabase 프로젝트 설정
4. `python -m playwright install chromium`

## 수동 spike 재사용
- `scripts/manual_spikes/save_sessions.py`
- `legacy_spikes/secondhand_publisher/`
