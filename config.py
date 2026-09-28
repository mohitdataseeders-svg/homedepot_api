from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
ENV_FILE = Path(__file__).resolve().parent / ".env"

class Settings(BaseSettings):
    # model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    scrapedo_token: str = ""
    api_keys: str = ""  # comma separated; empty = auth disabled (dev only)
    max_urls_per_request: int = 100
    concurrency: int = 20
    retries: int = 3
    request_timeout: int = 90
    mongo_uri: str = ""
    mongo_db: str = "homedepot_api"
    cache_ttl_hours: int = 12

    @property
    def api_key_list(self) -> list[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]


settings = Settings()
