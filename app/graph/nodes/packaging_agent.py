"""
패키지 빌더 + 게시 노드

노드:
  package_builder_node  — canonical listing → 플랫폼별 패키지 변환
  publish_node          — 플랫폼 게시 실행 (SessionService 직접 호출 경로에서는 미사용)
"""
from __future__ import annotations

from app.graph.seller_copilot_state import SellerCopilotState
from app.graph.nodes.helpers import _log, _record_error, _run_async, _safe_int


def package_builder_node(state: SellerCopilotState) -> SellerCopilotState:
    _log(state, "package_builder:start")

    canonical = state.get("canonical_listing") or {}
    title = canonical.get("title") or ""
    description = canonical.get("description") or ""
    price = _safe_int(canonical.get("price"), 0)
    images = canonical.get("images") or []
    product = canonical.get("product") or state.get("confirmed_product") or {}
    category = product.get("category") or ""

    selected = state.get("selected_platforms") or ["bunjang", "joongna"]
    packages = {}

    for platform in selected:
        if platform == "bunjang":
            platform_price = price + 10000 if price > 0 else 0
        elif platform == "daangn":
            platform_price = max(price - 4000, 0) if price > 0 else 0
        else:
            platform_price = price

        packages[platform] = {
            "title": title,
            "body": description,
            "price": platform_price,
            "images": images,
            "category": category,
        }

    state["platform_packages"] = packages
    state["checkpoint"] = "C_prepared"
    state["status"] = "awaiting_publish_approval"
    _log(state, f"package_builder:done platforms={list(packages.keys())}")
    return state


def publish_node(state: SellerCopilotState) -> SellerCopilotState:
    """
    패키지를 실제 플랫폼에 게시한다.
    성공/실패 결과를 state["publish_results"]에 기록.

    Note: 일반 흐름에서는 SessionService.publish_session()이 직접 처리한다.
    이 노드는 그래프 내부에서 직접 게시가 필요한 경우에만 사용.
    """
    _log(state, "publish_node:start")

    platform_packages = state.get("platform_packages") or {}
    if not platform_packages:
        _record_error(state, "publish_node", "platform_packages 없음")
        state["status"] = "failed"
        return state

    from app.services.publish_service import PublishService
    service = PublishService()
    publish_results = {}

    for platform, payload in platform_packages.items():
        _log(state, f"publish_node:publishing platform={platform}")
        try:
            result = _run_async(service.publish(platform=platform, payload=payload))
            publish_results[platform] = {
                "success": result.success,
                "external_url": result.external_url,
                "external_listing_id": result.external_listing_id,
                "error_code": result.error_code,
                "error_message": result.error_message,
                "evidence_path": result.evidence_path,
            }
            if result.success:
                _log(state, f"publish_node:success platform={platform} url={result.external_url}")
            else:
                _log(state, f"publish_node:failed platform={platform} error={result.error_message}")
        except Exception as e:
            _record_error(state, "publish_node", f"{platform}: {e}")
            publish_results[platform] = {
                "success": False,
                "error_code": "exception",
                "error_message": str(e),
            }

    state["publish_results"] = publish_results
    any_failed = any(not r.get("success") for r in publish_results.values())

    if any_failed:
        state["checkpoint"] = "D_publish_failed"
        state["status"] = "publishing_failed"
        _log(state, "publish_node:done some_failures=True → routing to recovery")
    else:
        state["checkpoint"] = "D_complete"
        state["status"] = "published"
        _log(state, "publish_node:done all_success=True")

    return state
