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
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(..., alias="SUPABASE_SERVICE_ROLE_KEY")

    secret_encryption_key: str = Field(..., alias="SECRET_ENCRYPTION_KEY")

    # ------------------------------
    # Vision
    # ------------------------------

    vision_provider: Literal["openai", "gemini"] = Field(
        default="openai",
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


@lru_cache
def get_settings() -> "Settings":
    return Settings()


settings = get_settings()