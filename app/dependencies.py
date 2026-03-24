"""
FastAPI 의존성 주입 (Dependency Injection).

라우터에서 전역 인스턴스 생성을 제거하고 Depends()로 wiring.
테스트에서 app.dependency_overrides로 mock 주입 가능.
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from app.repositories.session_repository import SessionRepository
from app.services.optimization_service import OptimizationService
from app.services.product_service import ProductService
from app.services.publish_service import PublishService
from app.services.recovery_service import RecoveryService
from app.services.seller_copilot_service import SellerCopilotService
from app.services.session_service import SessionService


@lru_cache(maxsize=1)
def get_session_repository() -> SessionRepository:
    return SessionRepository()


@lru_cache(maxsize=1)
def get_product_service() -> ProductService:
    return ProductService()


@lru_cache(maxsize=1)
def get_publish_service() -> PublishService:
    return PublishService()


@lru_cache(maxsize=1)
def get_copilot_service() -> SellerCopilotService:
    return SellerCopilotService()


@lru_cache(maxsize=1)
def get_recovery_service() -> RecoveryService:
    return RecoveryService()


@lru_cache(maxsize=1)
def get_optimization_service() -> OptimizationService:
    return OptimizationService()


def get_session_service(
    repo: SessionRepository = Depends(get_session_repository),
    product_service: ProductService = Depends(get_product_service),
    publish_service: PublishService = Depends(get_publish_service),
    copilot_service: SellerCopilotService = Depends(get_copilot_service),
    recovery_service: RecoveryService = Depends(get_recovery_service),
    optimization_service: OptimizationService = Depends(get_optimization_service),
) -> SessionService:
    return SessionService(
        session_repository=repo,
        product_service=product_service,
        publish_service=publish_service,
        copilot_service=copilot_service,
        recovery_service=recovery_service,
        optimization_service=optimization_service,
    )
