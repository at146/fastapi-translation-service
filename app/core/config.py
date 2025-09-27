from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="ignore",
    )

    # UVICORN
    UVICORN_HOST: str
    UVICORN_PORT: int
    UVICORN_RELOAD: bool
    UVICORN_WORKERS: int


settings = Settings()  # type: ignore
