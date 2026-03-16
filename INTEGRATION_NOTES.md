# Integration Notes

## 이번 통합본에서 한 일
- 기존 spike code를 `legacy_spikes/secondhand_publisher`로 복사
- 기존 spike save/login/test 스크립트를 `scripts/manual_spikes/`로 복사
- 현재 app 구조는 아래 원칙으로 유지:
  - VisionProvider 추상화
  - Canonical Listing → PlatformPackage → Publisher
  - sell_session 상태 기반
  - Checkpoint A / C는 repository 레벨에서 write 대상으로 가정
- app/publishers/* 는 legacy spike publisher를 감싸는 adapter 형태로 변경
- app/crawlers/* 는 legacy MarketCrawler를 감싸는 wrapper 형태로 변경
- app/tools/* 중 image_preprocess / aggregator / anomaly_filter는 실용 수준 구현
- openai provider는 실제 API 호출 가능하도록 작성
- gemini provider는 구조만 유지하고 graceful fallback 포함

## 아직 수동 보완이 필요한 것
1. Supabase 테이블/버킷 생성
2. 플랫폼 계정 secret loader 구현
3. playwright / emulator 세션 확보
4. OpenAI / Gemini 응답 schema 튜닝
5. 당근 crawler 실데이터 전략 확정
