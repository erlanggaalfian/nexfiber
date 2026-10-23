from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App config, read from /etc/nexfiber/config.ini or .env (PRD 4.1/X.1)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://nexfiber:nexfiber@localhost/nexfiber_db"
    app_secret_key: str = "change-me-in-production"  # Fernet key for OLT credential encryption
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60 * 8
    allow_write_commands: bool = True  # staging safety flag, PRD X.4
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
