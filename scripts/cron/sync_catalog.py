"""
Catalog sync cron entry point (PR4-1).

일 1회 실행 권장. sold sessions를 price_history로 incremental sync.

사용법:
    python -m scripts.cron.sync_catalog              # 실제 실행
    python -m scripts.cron.sync_catalog --dry-run    # 시뮬레이션 (insert 안 함)
    python -m scripts.cron.sync_catalog --max 50     # batch 크기 제한

prod cron 설정 (예시):
    0 4 * * *  cd /home/ec2-user/sagupalgu && python -m scripts.cron.sync_catalog >> /var/log/sagupalgu/catalog_sync.log 2>&1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _main(dry_run: bool, max_batch: int) -> int:
    from app.core.config import get_settings
    from app.services.catalog_sync_service import sync_completed_sessions_to_price_history

    settings = get_settings()
    api_key = settings.openai_api_key
    if not api_key:
        print("[ERROR] OPENAI_API_KEY 미설정 — 임베딩 생성 불가. exit 1.", file=sys.stderr)
        return 1

    if not getattr(settings, "enable_catalog_hybrid", True):
        print("[INFO] enable_catalog_hybrid=False → sync 건너뜀.")
        return 0

    result = await sync_completed_sessions_to_price_history(
        api_key=api_key,
        max_batch=max_batch,
        dry_run=dry_run,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    _setup_logging()

    parser = argparse.ArgumentParser(description="sell_sessions(sold) → price_history sync")
    parser.add_argument("--dry-run", action="store_true", help="시뮬레이션만 (insert 안 함)")
    parser.add_argument("--max", type=int, default=200, help="한 번 실행에 처리할 최대 sessions 수")
    args = parser.parse_args()

    exit_code = asyncio.run(_main(dry_run=args.dry_run, max_batch=args.max))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
