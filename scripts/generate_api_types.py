#!/usr/bin/env python3
"""
OpenAPI 스키마에서 프론트엔드 TypeScript 타입을 생성한다.

사용법:
    python scripts/generate_api_types.py           # 타입 파일 생성
    python scripts/generate_api_types.py --check    # drift 검증만 (CI용)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GENERATED_PATH = ROOT / "frontend" / "src" / "types" / "api-generated.ts"


def get_openapi_schema() -> dict:
    from app.main import app
    return app.openapi()


def extract_session_statuses(schema: dict) -> list[str]:
    """백엔드 SessionStatus Literal 값을 추출한다."""
    from app.domain.session_status import ALLOWED_TRANSITIONS
    return sorted(ALLOWED_TRANSITIONS.keys())


def extract_response_fields(schema: dict) -> list[tuple[str, str, bool]]:
    """SessionUIResponse의 평탄화 필드를 (name, ts_type, required) 튜플로 추출한다."""
    # SaleStatusResponse가 SessionUIResponse를 상속하므로 여기서 추출
    for name in ("SessionUIResponse", "SaleStatusResponse", "CreateSessionResponse"):
        resp = schema.get("components", {}).get("schemas", {}).get(name, {})
        props = resp.get("properties", {})
        if props:
            break
    if not props:
        raise RuntimeError("SessionUIResponse 스키마를 찾을 수 없습니다")

    required_keys = set(resp.get("required", []))
    fields = []
    for key, prop in props.items():
        # 중첩 필드(product, listing, publish 등)는 프론트엔드 타입에서 제외
        if key in ("product", "listing", "publish", "agent_trace", "debug"):
            continue
        ts_type = _to_ts_type(prop)
        is_required = key in required_keys
        fields.append((key, ts_type, is_required))
    return fields


def _to_ts_type(prop: dict) -> str:
    """OpenAPI property → TypeScript 타입."""
    if "anyOf" in prop:
        types = []
        for sub in prop["anyOf"]:
            if sub.get("type") == "null":
                types.append("null")
            else:
                types.append(_to_ts_type(sub))
        return " | ".join(types)

    t = prop.get("type", "any")
    if t == "string":
        return "string"
    if t == "integer" or t == "number":
        return "number"
    if t == "boolean":
        return "boolean"
    if t == "array":
        items = prop.get("items", {})
        return f"{_to_ts_type(items)}[]"
    if t == "object":
        return "Record<string, any>"
    return "any"


def generate_typescript(schema: dict) -> str:
    """OpenAPI 스키마에서 TypeScript 코드를 생성한다."""
    statuses = extract_session_statuses(schema)
    fields = extract_response_fields(schema)

    lines = [
        "// ⚠️ 자동 생성 파일 — 직접 수정 금지",
        "// 생성: python scripts/generate_api_types.py",
        f"// 소스: FastAPI OpenAPI 스키마 (SessionUIResponse)",
        "",
        "// ── SessionStatus ──────────────────────────────────────",
        "",
        "export type SessionStatusGenerated =",
    ]
    for i, s in enumerate(statuses):
        sep = ";" if i == len(statuses) - 1 else ""
        lines.append(f'  | "{s}"{sep}')

    lines += [
        "",
        "// ── SessionResponse (평탄화 필드만) ────────────────────",
        "",
        "export interface SessionResponseGenerated {",
    ]
    for name, ts_type, required in fields:
        opt = "" if required else "?"
        lines.append(f"  {name}{opt}: {ts_type};")
    lines += ["}", ""]

    return "\n".join(lines)


def main():
    check_only = "--check" in sys.argv
    schema = get_openapi_schema()
    generated = generate_typescript(schema)

    if check_only:
        if not GENERATED_PATH.exists():
            print(f"FAIL: {GENERATED_PATH} 파일이 없습니다. `python scripts/generate_api_types.py` 실행 필요.")
            sys.exit(1)
        existing = GENERATED_PATH.read_text(encoding="utf-8")
        if existing.strip() != generated.strip():
            print("FAIL: api-generated.ts가 OpenAPI 스키마와 일치하지 않습니다.")
            print("실행: python scripts/generate_api_types.py")
            sys.exit(1)
        print("OK: api-generated.ts가 최신 상태입니다.")
        sys.exit(0)

    GENERATED_PATH.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_PATH.write_text(generated, encoding="utf-8")
    print(f"생성 완료: {GENERATED_PATH}")


if __name__ == "__main__":
    main()
