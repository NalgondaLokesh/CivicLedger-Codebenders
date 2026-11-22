from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = "mongodb://localhost:27017"
    # Accepts MONGODB_DB_NAME (preferred) or the legacy MONGODB_DB.
    mongodb_db_name: str = Field(
        default="civicledger",
        validation_alias=AliasChoices("MONGODB_DB_NAME", "MONGODB_DB"),
    )
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Optional cloud services: the app starts without them.
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "civicledger_schemes"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Admin scheme-management API. When empty, /api/admin/* returns 503.
    admin_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
