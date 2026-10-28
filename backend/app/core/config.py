import configparser
import os
import warnings

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    """App config: config.ini at $NEXFIBER_CONFIG (written by install.sh), else .env for dev."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://nexfiber:nexfiber@localhost/nexfiber_db"
    app_secret_key: str = _DEFAULT_SECRET  # Fernet key for OLT credential encryption
    jwt_secret_key: str = _DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60 * 8
    allow_write_commands: bool = True  # staging safety flag, PRD X.4
    cors_origins: list[str] = ["http://localhost:5173"]


def _from_ini(path: str) -> dict:
    ini = configparser.ConfigParser()
    if not ini.read(path):
        raise RuntimeError(f"NEXFIBER_CONFIG={path} tidak bisa dibaca")
    # Kompatibel ke belakang: config.ini lama hanya punya satu secret_key, dan
    # kedua keperluan memakai nilai itu. Instalasi baru boleh memisahkan dengan
    # menulis app_secret_key dan/atau jwt_secret_key di [app]; kunci yang tidak
    # ditulis jatuh kembali ke secret_key. Memisahkan keduanya disarankan karena
    # bocornya satu sisi tidak lagi otomatis membocorkan sisi lainnya.
    secret = ini.get("app", "secret_key")
    return {"database_url": ini.get("database", "url"),
            "app_secret_key": ini.get("app", "app_secret_key", fallback=secret),
            "jwt_secret_key": ini.get("app", "jwt_secret_key", fallback=secret)}

_ini_path = os.environ.get("NEXFIBER_CONFIG")
settings = Settings(**_from_ini(_ini_path)) if _ini_path else Settings()

if _ini_path and (settings.app_secret_key == _DEFAULT_SECRET
                  or settings.jwt_secret_key == _DEFAULT_SECRET):
    # Mode instalasi (config.ini dipakai) tidak boleh boot dengan secret publik
    # yang dikenal dari repo: JWT bisa dipalsukan dan kredensial OLT terdekripsi.
    raise RuntimeError(
        "Secret masih default 'change-me-in-production' di config.ini; "
        "isi app_secret_key/jwt_secret_key (atau secret_key) dengan nilai acak")
if not _ini_path and (settings.app_secret_key == _DEFAULT_SECRET
                      or settings.jwt_secret_key == _DEFAULT_SECRET):
    warnings.warn(
        "Secret masih default (mode dev tanpa config.ini); jangan dipakai di produksi",
        UserWarning, stacklevel=2)
