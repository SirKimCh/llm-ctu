from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

SECRET_KEY_PLACEHOLDER = "doi-thanh-chuoi-ngau-nhien-toi-thieu-32-ky-tu"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str
    app_host: str
    app_port: int
    secret_key: str
    session_max_age_minutes: int
    session_https_only: bool
    page_size: int
    admin_username: str
    admin_password: str
    log_level: str

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    test_db_name: str

    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    llm_temperature: float

    nlu_model_dir: str
    nlu_min_confidence: float
    nlu_base_model: str
    out_of_scope_reply: str

    search_top_k: int

    upload_max_mb: int

    brightdata_api_url: str
    brightdata_api_token: str = ""
    brightdata_zone: str
    crawl_max_urls: int
    crawl_timeout_seconds: int
    chunk_max_chars: int

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
