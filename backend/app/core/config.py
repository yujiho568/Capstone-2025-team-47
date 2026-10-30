from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    SECRET_KEY: str = Field(min_length=32)
    FERNET_KEY: str | None = None
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DATABASE_URL: str = 'sqlite:///./ueba_system.db'
    model_config=SettingsConfigDict(env_file='.env',extra='ignore')

@lru_cache
def get_settings(): return Settings()
