from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "sagupalgu"
    environment: Literal["local", "dev", "prod"] = "local"
    demo_mode: bool = False
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(..., alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str | None = Field(default=None, alias="SUPABASE_JWT_SECRET")

    secret_encryption_key: str = Field(..., alias="SECRET_ENCRYPTION_KEY")

    # ------------------------------
    # Vision
    # ------------------------------

    vision_provider: Literal["openai", "gemini"] = Field(
        default="gemini",
        alias="VISION_PROVIDER",
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    openai_vision_model: str = Field(
        default="gpt-4.1-mini",
        alias="OPENAI_VISION_MODEL",
    )

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")

    gemini_vision_model: str = Field(
        default="gemini-2.5-flash",
        alias="GEMINI_VISION_MODEL",
    )

    # ------------------------------
    # Listing LLM
    # ------------------------------

    listing_llm_provider: Literal["openai", "gemini", "solar"] = Field(
        default="openai",
        alias="LISTING_LLM_PROVIDER",
    )

    openai_listing_model: str = Field(
        default="gpt-4.1-mini",
        alias="OPENAI_LISTING_MODEL",
    )

    gemini_listing_model: str = Field(
        default="gemini-2.5-flash",
        alias="GEMINI_LISTING_MODEL",
    )

    upstage_api_key: str | None = Field(
        default=None,
        alias="UPSTAGE_API_KEY",
    )

    solar_listing_model: str = Field(
        default="solar-pro2",
        alias="SOLAR_LISTING_MODEL",
    )

    # ------------------------------
    # Publish credentials
    # ------------------------------

    joongna_username: str | None = Field(
        default=None,
        alias="JOONGNA_USERNAME",
    )

    joongna_password: str | None = Field(
        default=None,
        alias="JOONGNA_PASSWORD",
    )

    bunjang_username: str | None = Field(
        default=None,
        alias="BUNJANG_USERNAME",
    )

    bunjang_password: str | None = Field(
        default=None,
        alias="BUNJANG_PASSWORD",
    )

    # ------------------------------
    # Daangn (Android emulator)
    # ------------------------------

    daangn_device_id: str | None = Field(
        default=None,
        alias="DAANGN_DEVICE_ID",
    )

    # ------------------------------
    # Publish runtime
    # ------------------------------

    publish_headless: bool = Field(
        default=True,
        alias="PUBLISH_HEADLESS",
    )

    publish_slow_mo: int = Field(
        default=100,
        alias="PUBLISH_SLOW_MO",
    )

    screenshot_dir: str = Field(
        default="./screenshots",
        alias="SCREENSHOT_DIR",
    )

    # Job Queue
    publish_use_queue: bool = Field(
        default=True,
        alias="PUBLISH_USE_QUEUE",
        description="True=Job Queue 비동기, False=직접 실행 (테스트/개발용)",
    )
    run_publish_worker: bool = Field(
        default=True,
        alias="RUN_PUBLISH_WORKER",
        description="True=API 서버 시작 시 워커도 시작, False=API 전용 (워커 별도 실행)",
    )

    # Admin
    admin_api_key: str | None = Field(
        default=None,
        alias="ADMIN_API_KEY",
        description="Admin API 인증 키. 미설정 시 admin 엔드포인트 접근 불가.",
    )

    # ------------------------------
    # Supabase Storage
    # ------------------------------

    storage_bucket_name: str = Field(
        default="product-images",
        alias="STORAGE_BUCKET_NAME",
    )

    use_cloud_storage: bool = Field(
        default=False,
        alias="USE_CLOUD_STORAGE",
    )

    # ------------------------------
    # Product Identity 카탈로그 (PR4)
    # ------------------------------

    # PR4-1: 옵션 D-하이브리드 카탈로그 RAG (sessions + price_history) 활성화.
    # off로 toggle하면 hybrid_search_catalog 호출이 차단되고 기존 lc_rag_price_tool만 동작.
    enable_catalog_hybrid: bool = Field(
        default=True,
        alias="ENABLE_CATALOG_HYBRID",
    )

    # ------------------------------
    # 이메일 알림 (Gmail SMTP)
    # ------------------------------

    smtp_email: str = Field(default="", alias="SMTP_EMAIL")
    smtp_app_password: str = Field(default="", alias="SMTP_APP_PASSWORD")

    # ------------------------------
    # CORS
    # ------------------------------

    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        alias="ALLOWED_ORIGINS",
        description="콤마 구분 origin 목록. prod에서는 ALLOWED_ORIGINS 환경변수로 실제 도메인 설정 필수.",
    )


@lru_cache
def get_settings() -> "Settings":
    return Settings()


def _get_settings_lazy() -> "Settings":
    """모듈 수준 `settings` 참조를 위한 lazy proxy.

    직접 Settings() 인스턴스를 모듈 로드 시점에 생성하지 않고,
    속성 접근 시점에 get_settings()를 호출한다.
    """
    return get_settings()


class _SettingsProxy:
    """속성 접근 시 get_settings()를 lazy 호출하는 프록시 객체."""

    def __getattr__(self, name: str):
        return getattr(get_settings(), name)

    def __repr__(self) -> str:
        return f"<SettingsProxy → {get_settings()!r}>"


settings = _SettingsProxy()