from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_url: str
    mqtt_host: str
    api_v1_str: str = "/api/v1"
    cors_origins: list[str] = [
        "http://localhost",
        "http://localhost:8080",
        "http://localhost:5173",
    ]


settings = Settings()  # type: ignore[call-arg]
