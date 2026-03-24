"""
그래프 라우터 함수 단위 테스트 — langgraph 의존성 없음.

routing.py의 순수 상태 기반 분기 로직만 테스트.
@pytest.mark.unit — 외부 의존성 없이 0.1초 이내 완료.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestGraphRouting:

    def test_needs_user_input_clarification으로_분기(self):
        from app.graph.routing import route_after_product_identity

        state = {"needs_user_input": True}
        assert route_after_product_identity(state) == "clarification_node"

    def test_confirmed_product_market으로_분기(self):
        from app.graph.routing import route_after_product_identity

        state = {"needs_user_input": False}
        assert route_after_product_identity(state) == "pre_listing_clarification_node"

    def test_needs_user_input_없으면_pre_listing으로_분기(self):
        from app.graph.routing import route_after_product_identity

        state = {}
        assert route_after_product_identity(state) == "pre_listing_clarification_node"

    def test_validation_passed_package로_분기(self):
        from app.graph.routing import route_after_validation

        state = {"validation_passed": True, "validation_retry_count": 0}
        assert route_after_validation(state) == "package_builder_node"

    def test_validation_failed_refinement으로_분기(self):
        from app.graph.routing import route_after_validation

        state = {"validation_passed": False, "validation_retry_count": 0}
        assert route_after_validation(state) == "refinement_node"

    def test_validation_재시도초과_강제통과(self):
        from app.graph.routing import route_after_validation, MAX_VALIDATION_RETRIES

        state = {"validation_passed": False, "validation_retry_count": MAX_VALIDATION_RETRIES}
        assert route_after_validation(state) == "package_builder_node"

    def test_validation_retry_count_없으면_refinement(self):
        from app.graph.routing import route_after_validation

        state = {"validation_passed": False}
        assert route_after_validation(state) == "refinement_node"

    def test_validation_retry_count_1이면_refinement(self):
        from app.graph.routing import route_after_validation

        state = {"validation_passed": False, "validation_retry_count": 1}
        assert route_after_validation(state) == "refinement_node"

    def test_validation_passed_true_retry_초과해도_package로(self):
        """passed=True면 retry count 무관하게 항상 package_builder_node"""
        from app.graph.routing import route_after_validation

        state = {"validation_passed": True, "validation_retry_count": 99}
        assert route_after_validation(state) == "package_builder_node"

    def test_validation_retry_count_음수는_refinement(self):
        """비정상적인 음수 retry count는 refinement으로 분기 (MAX 미달)"""
        from app.graph.routing import route_after_validation

        state = {"validation_passed": False, "validation_retry_count": -1}
        assert route_after_validation(state) == "refinement_node"

    def test_validation_retry_count_문자열_처리(self):
        """retry_count가 문자열로 들어와도 안전하게 처리"""
        from app.graph.routing import route_after_validation, MAX_VALIDATION_RETRIES

        state = {"validation_passed": False, "validation_retry_count": str(MAX_VALIDATION_RETRIES)}
        assert route_after_validation(state) == "package_builder_node"

    def test_needs_user_input_truthy_값_clarification(self):
        """needs_user_input이 1 같은 truthy 값이어도 clarification으로"""
        from app.graph.routing import route_after_product_identity

        state = {"needs_user_input": 1}
        assert route_after_product_identity(state) == "clarification_node"
