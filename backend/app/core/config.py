import configparser
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App config: config.ini at $NEXFIBER_CONFIG (written by install.sh), else .env for dev."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://nexfiber:nexfiber@localhost/nexfiber_db"
    app_secret_key: str = "change-me-in-production"  # Fernet key for OLT credential encryption
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60 * 8
    allow_write_commands: bool = True  # staging safety flag, PRD X.4
    cors_origins: list[str] = ["http://localhost:5173"]


def _from_ini(path: str) -> dict:
    ini = configparser.ConfigParser()
    if not ini.read(path):
        raise RuntimeError(f"NEXFIBER_CONFIG={path} tidak bisa dibaca")
    secret = ini.get("app", "secret_key")
    return {"database_url": ini.get("database", "url"),
            "app_secret_key": secret, "jwt_secret_key": secret}

_ini_path = os.environ.get("NEXFIBER_CONFIG")
settings = Settings(**_from_ini(_ini_path)) if _ini_path else Settings()
