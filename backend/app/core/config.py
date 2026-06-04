"""Application configuration loaded from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # CORS
    # Comma-separated list of exact origins (e.g. the Next.js dashboard).
    # The Chrome extension has a different ID per developer/reload, so it
    # is matched by regex via `cors_origin_regex` below.
    cors_origins: str = "http://localhost:3000"
    cors_origin_regex: str = r"chrome-extension://.*"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS_ORIGINS env var into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
