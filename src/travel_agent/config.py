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

    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    database_url: str = os.getenv("DATABASE_URL", "")

    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")


settings = Settings()
