"""
Agent 1 (Product Identity 승격) 툴 — Vision 재분석 + 카탈로그 RAG + 사용자 질문.

PR4-2 신규.
ReAct에 bind: lc_image_reanalyze_tool / lc_rag_product_catalog_tool / lc_ask_user_clarification_tool.
직접 호출용 _impl 함수 분리 (테스트·fallback에서 재사용).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from langchain_core.tools import tool as _lc_tool
except ImportError:  # langchain-core 미설치 환경 대비 (테스트 등)
    def _lc_tool(fn):  # type: ignore[misc]
        return fn

logger = logging.getLogger(__name__)


# ── failure_mode taxonomy (CTO PR4-2 #5) ──────────────────────────────
# string 분산 대신 Literal로 enum화. metric/alert/분석에서 명시 사용.
from typing import Literal, TypedDict

ProductIdentityFailureMode = Literal[
    "react_exception",                       # ReAct 호출 자체 예외
    "product_identity_parse_error",          # 최종 응답 JSON 파싱 실패
    "product_identity_contract_violation",   # 필수 필드 누락
    "react_total_budget_exceeded",           # PR4-2 #1: total tool calls cap 초과
    "clarify_forced_by_heuristic",           # PR4-2 #4: explicit heuristic 발동 (정상 동작)
    "reanalyze_budget_exceeded",             # tool 단위 budget 초과
    "max_clarify_calls_reached",             # tool 단위 budget 초과
]


# ── lc_rag_product_catalog_tool 응답 contract (CTO PR4-3 #3) ──────────
# observability 가 ToolMessage.content 에서 cold_start 를 자동 추출하므로
# 이 필드들이 이름·타입 채로 항상 존재해야 한다. tool 응답 변경 시 본 schema 도 함께 갱신.

class CatalogToolResponse(TypedDict, total=False):
    matches: list                  # 매칭된 catalog 항목
    top_match_confidence: float    # 0.0 ~ 1.0
    source_count: int              # 검색된 항목 수
    cold_start: bool               # 핵심: hits<3 OR top_conf<0.5 일 때 True
    source_breakdown: dict         # {crawled: int, sell_session: int, manual: int}
    disabled_by_flag: bool         # ENABLE_CATALOG_HYBRID=false 인 경우만
    error: str                     # exception 발생 시만


CATALOG_TOOL_REQUIRED_FIELDS = ("cold_start",)


def validate_catalog_tool_response(payload: Dict[str, Any]) -> bool:
    """ToolMessage 응답이 CatalogToolResponse contract 를 만족하는지 검증.
    필수: cold_start 필드 존재 + bool 타입.
    """
    if not isinstance(payload, dict):
        return False
    for field in CATALOG_TOOL_REQUIRED_FIELDS:
        if field not in payload:
            return False
    if not isinstance(payload.get("cold_start"), bool):
        return False
    return True


# ── reanalyze 캐싱 (TTL 1h) ──────────────────────────────────────────
# 같은 세션 내에서 replan/재시도 시 동일 image+focus는 재호출 안 함.
# key: SHA256(image_paths_concat + focus + category_hint), value: (timestamp, result_json)
_REANALYZE_CACHE_TTL_SECONDS = 3600
_reanalyze_cache: Dict[str, Tuple[float, str]] = {}


def _cache_key(image_paths_json: str, focus: str, category_hint: str) -> str:
    raw = f"{image_paths_json}|{focus}|{category_hint}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str, focus: str = "?") -> Optional[str]:
    entry = _reanalyze_cache.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > _REANALYZE_CACHE_TTL_SECONDS:
        _reanalyze_cache.pop(key, None)
        return None
    # CTO PR4-2 #3: cache hit 시 debug log (input drift 추적용)
    logger.info(f"[reanalyze] cache hit focus={focus} key_prefix={key[:8]} age_sec={int(time.time() - ts)}")
    return value


def _cache_set(key: str, value: str) -> None:
    _reanalyze_cache[key] = (time.time(), value)


# ── focus별 prompt ─────────────────────────────────────────────────────
# 첫 Vision 호출(ProductService.identify_product)이 일반 프롬프트라,
# 재분석은 다른 각도에서 본다. focus가 LLM에게 "이번엔 이 측면을 강조해서 보라"는 지시.
_FOCUS_PROMPTS = {
    "ocr": (
        "이미지에서 모델 각인·로고·박스 라벨 같은 *텍스트 요소*를 최우선으로 찾아 "
        "모델명·브랜드·용량을 추출하세요. 흐릿한 글자도 추정 시도하되 confidence에 반영."
    ),
    "spec": (
        "이미지에서 *식별 가능한 스펙 차이*(색상, 크기, 포트, 카메라 모듈, 화면 비율 등)를 "
        "관찰해 같은 모델의 변형(예: Pro vs 일반, 256GB vs 512GB)을 구분하세요."
    ),
    "category_hint": (
        "사용자 힌트로 받은 카테고리({category_hint})를 출발점으로, 그 카테고리 안에서만 "
        "후보 모델을 좁혀 식별하세요. 카테고리에 맞지 않는 후보는 confidence를 낮추세요."
    ),
}


# ── Tool 1: lc_image_reanalyze_tool ───────────────────────────────────


@_lc_tool
async def lc_image_reanalyze_tool(
    image_paths_json: str,
    focus: str,
    category_hint: str = "",
    prior_candidates_json: str = "",
) -> str:
    """이미지를 다른 prompt로 재분석합니다.

    confidence가 낮거나 candidates가 모호할 때 호출하세요.
    focus 종류:
      - "ocr": 텍스트 각인·로고 강조
      - "spec": 스펙 차이로 변형 구분
      - "category_hint": 사용자가 준 카테고리로 후보 좁히기

    한 세션에서 최대 2회까지 호출 가능. 초과 시 'reanalyze_budget_exceeded' 반환.

    반환: JSON {"candidates": [...], "confidence": float, "reanalysis_reason": str}
    """
    # focus 검증
    if focus not in _FOCUS_PROMPTS:
        return json.dumps({"error": f"invalid focus: {focus}", "valid": list(_FOCUS_PROMPTS.keys())},
                          ensure_ascii=False)

    # 캐시 확인 (CTO PR4-2 #3: cache hit 시 _cache_get 내부에서 log)
    key = _cache_key(image_paths_json, focus, category_hint)
    cached = _cache_get(key, focus=focus)
    if cached:
        return cached

    try:
        image_paths = json.loads(image_paths_json) if image_paths_json else []
    except (ValueError, TypeError):
        return json.dumps({"error": "invalid image_paths_json"}, ensure_ascii=False)

    if not image_paths:
        return json.dumps({"error": "empty image_paths"}, ensure_ascii=False)

    result = await _image_reanalyze_impl(image_paths, focus, category_hint, prior_candidates_json)
    result_json = json.dumps(result, ensure_ascii=False)
    _cache_set(key, result_json)
    return result_json


async def _image_reanalyze_impl(
    image_paths: List[str],
    focus: str,
    category_hint: str,
    prior_candidates_json: str,
) -> Dict[str, Any]:
    """ProductService.identify_product()를 다른 prompt로 호출."""
    try:
        from app.services.product_service import ProductService

        focus_directive = _FOCUS_PROMPTS[focus].format(category_hint=category_hint or "(없음)")
        prior_hint = ""
        if prior_candidates_json:
            try:
                prior = json.loads(prior_candidates_json)
                if prior:
                    prior_hint = f"\n참고: 이전 분석에서 후보 → {json.dumps(prior, ensure_ascii=False)[:200]}"
            except (ValueError, TypeError):
                pass

        extra_prompt = focus_directive + prior_hint

        svc = ProductService()
        candidates = await svc.identify_product(
            image_paths=image_paths,
            extra_directive=extra_prompt,
        )

        # 가장 높은 confidence를 top-level confidence로
        top_conf = max((float(c.get("confidence", 0) or 0) for c in candidates), default=0.0)
        return {
            "candidates": candidates,
            "confidence": top_conf,
            "reanalysis_reason": f"focus={focus}",
        }
    except TypeError as e:
        # ProductService.identify_product가 extra_directive를 아직 받지 않을 수 있음.
        # fallback: 기본 호출 (재분석 효과 약하지만 안전).
        logger.warning(f"[reanalyze] extra_directive 미지원 → 기본 호출: {e}")
        try:
            from app.services.product_service import ProductService
            svc = ProductService()
            candidates = await svc.identify_product(image_paths=image_paths)
            top_conf = max((float(c.get("confidence", 0) or 0) for c in candidates), default=0.0)
            return {
                "candidates": candidates,
                "confidence": top_conf,
                "reanalysis_reason": f"focus={focus} (basic fallback)",
            }
        except Exception as e2:
            logger.error(f"[reanalyze] basic fallback도 실패: {e2}")
            return {"error": f"reanalyze failed: {e2}", "candidates": [], "confidence": 0.0}
    except Exception as e:
        logger.error(f"[reanalyze] failed: {e}", exc_info=True)
        return {"error": f"reanalyze failed: {e}", "candidates": [], "confidence": 0.0}


# ── Tool 2: lc_rag_product_catalog_tool ───────────────────────────────


@_lc_tool
async def lc_rag_product_catalog_tool(
    brand_hint: str,
    model_hint: str,
    category_hint: str = "",
    match_threshold: float = 0.35,
) -> str:
    """과거 거래 + 사구팔구 자체 sold 데이터에서 유사 상품을 RAG 검색합니다.

    Vision이 부정확한 모델명을 뽑았거나 brand가 누락됐을 때 호출해서 카탈로그에서
    매칭 후보를 찾아 보정에 사용하세요. top_match_confidence가 높으면 그 후보로 확정 가능.

    cold_start=True면 카탈로그 데이터가 부족하다는 신호 — 이때는 clarify로 빠지세요.

    반환: JSON {"matches": [...], "top_match_confidence": float, "source_count": int,
                "cold_start": bool, "source_breakdown": {...}}
    """
    return await _rag_product_catalog_impl(brand_hint, model_hint, category_hint, match_threshold)


async def _rag_product_catalog_impl(
    brand: str, model: str, category: str, threshold: float,
) -> str:
    try:
        from app.core.config import get_settings
        from app.db.product_catalog_store import hybrid_search_catalog

        settings = get_settings()

        # Feature flag off면 빈 결과 + cold_start
        if not getattr(settings, "enable_catalog_hybrid", True):
            return json.dumps({
                "matches": [], "top_match_confidence": 0.0, "source_count": 0,
                "cold_start": True, "source_breakdown": {"crawled": 0, "sell_session": 0, "manual": 0},
                "disabled_by_flag": True,
            }, ensure_ascii=False)

        api_key = settings.openai_api_key
        if not api_key:
            logger.warning("[catalog_tool] OPENAI_API_KEY 없음 → cold_start 반환")
            return json.dumps({
                "matches": [], "top_match_confidence": 0.0, "source_count": 0,
                "cold_start": True, "source_breakdown": {"crawled": 0, "sell_session": 0, "manual": 0},
                "error": "no_api_key",
            }, ensure_ascii=False)

        result = await hybrid_search_catalog(
            brand=brand, model=model, category=category, api_key=api_key,
            match_threshold=threshold,
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[catalog_tool] failed: {e}", exc_info=True)
        return json.dumps({
            "matches": [], "top_match_confidence": 0.0, "source_count": 0,
            "cold_start": True, "error": str(e),
        }, ensure_ascii=False)


# ── Tool 3: lc_ask_user_clarification_tool ────────────────────────────


@_lc_tool
def lc_ask_user_clarification_tool(questions_json: str, reason: str) -> str:
    """사용자에게 상품 식별용 추가 정보를 질문합니다.

    Vision 재분석·카탈로그 검색을 모두 시도했는데도 confidence가 부족할 때 마지막 수단.
    한 세션에서 최대 1회 호출 권장 (중복 질문 방지).

    questions_json: [{"id": "model_name", "question": "정확한 모델명 알려주세요"}, ...]
    reason: 왜 물어야 하는지 한 줄 (예: "vision confidence 0.4, category 불명")

    반환: JSON {"ack": true, "questions_count": N, "reason": ...}
    실제 state mutation은 노드(product_identity_agent)가 messages를 순회하며 처리함.
    """
    try:
        questions = json.loads(questions_json) if questions_json else []
    except (ValueError, TypeError):
        return json.dumps({"ack": False, "error": "invalid questions_json"}, ensure_ascii=False)

    valid_questions = [
        q for q in questions
        if isinstance(q, dict) and q.get("question") and q.get("id")
    ]
    if not valid_questions:
        return json.dumps({"ack": False, "error": "no valid questions"}, ensure_ascii=False)

    return json.dumps({
        "ack": True,
        "questions_count": len(valid_questions),
        "reason": reason,
    }, ensure_ascii=False)


# ── Budget 가드 헬퍼 (노드에서 사용) ───────────────────────────────────

MAX_REANALYZE_CALLS = 2
MAX_CLARIFICATION_CALLS = 1

# CTO PR4-2 #1: total tool calls soft budget.
# 개별 tool guard (2 + 1) 외에 *전체* 호출 수도 cap. heavy flow (reanalyze x2 + rag + clarify = 4)
# 정도까지는 정상이지만 그 이상은 의미 없는 반복일 가능성 높음 → 강제 종료.
# elapsed time 기반 guard는 LLM·네트워크 의존성으로 측정 어려움 → 호출 수가 더 단순·결정론적.
MAX_TOTAL_TOOL_CALLS = 4


def reanalyze_budget_exceeded(prior_calls: List[str]) -> bool:
    return prior_calls.count("lc_image_reanalyze_tool") >= MAX_REANALYZE_CALLS


def clarification_budget_exceeded(prior_calls: List[str]) -> bool:
    return prior_calls.count("lc_ask_user_clarification_tool") >= MAX_CLARIFICATION_CALLS


def total_budget_exceeded(prior_calls: List[str]) -> bool:
    """전체 tool 호출 수가 soft budget 초과한 경우 True (CTO PR4-2 #1)."""
    return len(prior_calls) >= MAX_TOTAL_TOOL_CALLS
