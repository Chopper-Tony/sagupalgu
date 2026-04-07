"""
Prod 환경 점검 스크립트.

배포 전 프로덕션 환경 설정을 자동 검증한다.
CORS wildcard, JWT secret 미설정, dev bypass 등 위험 설정을 감지.

사용법:
  python scripts/check_prod_readiness.py
  python scripts/check_prod_readiness.py --env prod
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def check_prod_readiness(env: str = "prod") -> list[dict]:
    """환경 설정을 검증하고 문제 목록을 반환한다."""
    issues: list[dict] = []

    from app.core.config import get_settings
    settings = get_settings()

    # 1. CORS wildcard 검사
    origins = settings.allowed_origins
    if origins == "*" or (not origins.strip()):
        issues.append({
            "level": "error",
            "check": "cors_origins",
            "message": "ALLOWED_ORIGINS가 '*' 또는 빈 값입니다. prod에서는 실제 도메인을 설정하세요.",
        })
    elif "localhost" in origins and env == "prod":
        issues.append({
            "level": "warning",
            "check": "cors_origins",
            "message": f"ALLOWED_ORIGINS에 localhost가 포함되어 있습니다: {origins}",
        })

    # 2. JWT secret 검사
    jwt_secret = getattr(settings, "supabase_jwt_secret", None)
    if not jwt_secret and env == "prod":
        issues.append({
            "level": "warning",
            "check": "jwt_secret",
            "message": "SUPABASE_JWT_SECRET이 설정되지 않았습니다. service_role_key로 fallback됩니다.",
        })

    # 3. 환경 변수 검사
    if settings.environment != env:
        issues.append({
            "level": "info",
            "check": "environment",
            "message": f"현재 환경: {settings.environment} (기대: {env})",
        })

    # 4. Debug 모드 검사
    if settings.debug and env == "prod":
        issues.append({
            "level": "error",
            "check": "debug_mode",
            "message": "DEBUG=True 상태입니다. prod에서는 반드시 False로 설정하세요.",
        })

    # 5. Secret encryption key 검사
    if "placeholder" in (settings.secret_encryption_key or "").lower():
        issues.append({
            "level": "error",
            "check": "encryption_key",
            "message": "SECRET_ENCRYPTION_KEY가 placeholder입니다. 실제 키를 설정하세요.",
        })

    # 6. LLM API 키 검사
    has_llm = any([
        bool(settings.openai_api_key),
        bool(settings.gemini_api_key),
        bool(getattr(settings, "upstage_api_key", None)),
    ])
    if not has_llm:
        issues.append({
            "level": "error",
            "check": "llm_api_key",
            "message": "LLM API 키가 하나도 설정되지 않았습니다.",
        })

    # 7. Admin API 키 검사
    admin_key = getattr(settings, "admin_api_key", None)
    if not admin_key and env == "prod":
        issues.append({
            "level": "error",
            "check": "admin_api_key",
            "message": "ADMIN_API_KEY가 설정되지 않았습니다. admin 엔드포인트가 보호되지 않습니다.",
        })

    # 8. Queue 모드 검사
    if getattr(settings, "publish_use_queue", False) and env == "prod":
        if not getattr(settings, "run_publish_worker", False):
            issues.append({
                "level": "warning",
                "check": "publish_worker",
                "message": "PUBLISH_USE_QUEUE=true인데 RUN_PUBLISH_WORKER=false입니다. 별도 워커 컨테이너가 필요합니다.",
            })

    # 9. Publisher credentials 검사
    publishers = []
    if settings.bunjang_username:
        publishers.append("bunjang")
    if settings.joongna_username:
        publishers.append("joongna")
    if not publishers:
        issues.append({
            "level": "warning",
            "check": "publisher_credentials",
            "message": "게시 플랫폼 인증 정보가 설정되지 않았습니다.",
        })

    return issues


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Prod 환경 점검")
    parser.add_argument("--env", default="prod", help="점검 대상 환경 (default: prod)")
    args = parser.parse_args()

    print(f"== Prod Readiness Check (env={args.env}) ==\n")

    issues = check_prod_readiness(args.env)

    if not issues:
        print("  모든 검사 통과!")
        return

    errors = [i for i in issues if i["level"] == "error"]
    warnings = [i for i in issues if i["level"] == "warning"]
    infos = [i for i in issues if i["level"] == "info"]

    for issue in errors:
        print(f"  [ERROR] {issue['check']}: {issue['message']}")
    for issue in warnings:
        print(f"  [WARN]  {issue['check']}: {issue['message']}")
    for issue in infos:
        print(f"  [INFO]  {issue['check']}: {issue['message']}")

    print(f"\n  결과: {len(errors)} errors, {len(warnings)} warnings, {len(infos)} info")

    if errors:
        print("\n  !! ERROR가 있습니다. 배포 전 반드시 수정하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
