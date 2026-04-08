from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "MultiAgentAI"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # CORS — comma-separated list of allowed origins.
    # Render/Netlify: set ALLOWED_ORIGINS=https://your-app.netlify.app
    # Dev: defaults to allow all so local frontend works without config.
    allowed_origins_str: str = "*"

    @property
    def allowed_origins(self) -> list[str]:
        if self.allowed_origins_str.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.allowed_origins_str.split(",") if o.strip()]

    database_url: str = "sqlite+aiosqlite:///./dev.db"

    openai_api_key: str = ""   # kept for backward compat — no longer used
    groq_api_key: str = ""     # primary LLM backend (free tier available)
    default_model: str = ""    # optional model override (Groq or Ollama)

    secret_key: str = "change-me"

    # X (Twitter) API — free tier (read-only)
    x_bearer_token: str = ""
    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_token_secret: str = ""

    # LinkedIn API
    linkedin_access_token: str = ""
    linkedin_person_urn: str = ""

    # Instagram / Meta Graph API
    instagram_user_id: str = ""
    instagram_access_token: str = ""

    # Impact tracker — delay in seconds before fetching post metrics
    impact_fetch_delay_seconds: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
