import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    travelpayouts_api_key: str = os.getenv("TRAVELPAYOUTS_API_KEY", "")

    booking_rapidapi_key: str = os.getenv("BOOKING_RAPIDAPI_KEY", "")
    google_maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    openweathermap_api_key: str = os.getenv("OPENWEATHERMAP_API_KEY", "")
    serper_api_key: str = os.getenv("SERPER_API_KEY", "")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    unsplash_access_key: str = os.getenv("UNSPLASH_ACCESS_KEY", "")

    # Week 15 FastAPI backend. Empty (default) disables API-key enforcement
    # entirely -- convenient for local dev, matching every other optional
    # credential in this file (e.g. UNSPLASH_ACCESS_KEY).
    api_key: str = os.getenv("API_KEY", "")

    # Week 16 React frontend runs on a different origin (Vite dev server,
    # default port 5173) than the API (default port 8000), so the browser
    # needs an explicit CORS allowlist. Comma-separated; defaults to the two
    # ports Vite/CRA-style dev servers commonly use.
    cors_origins: list[str] = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
        if o.strip()
    ]

    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    database_url: str = os.getenv("DATABASE_URL", "")

    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    # Week 19 observability. LangSmith tracing isn't read here at all —
    # LangChain/LangGraph pick LANGCHAIN_TRACING_V2/LANGCHAIN_API_KEY/
    # LANGCHAIN_PROJECT straight out of the environment (already populated
    # by load_dotenv() above), no application code needed. langsmith_enabled
    # below is only for this app's own startup log line, not enforcement.
    langsmith_enabled: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"

    # Empty (default) disables Sentry entirely — same optional-credential
    # pattern as every other integration in this file.
    sentry_dsn: str = os.getenv("SENTRY_DSN", "")

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    # "console" (human-readable, colorized) for local dev; "json" for
    # anywhere logs get aggregated (Docker, CI, a real deployment).
    log_format: str = os.getenv("LOG_FORMAT", "console")


settings = Settings()
