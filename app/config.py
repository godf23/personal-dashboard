import shutil
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
ENV_EXAMPLE_PATH = BASE_DIR / ".env.example"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ENV_PATH, ENV_EXAMPLE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ssl_cert: str = "certs/cert.pem"
    ssl_key: str = "certs/key.pem"
    owm_api_key: str = ""
    wapi_api_key: str = ""
    news_api_token: str = ""
    github_repo: str = "godf23/personal-dashboard"
    github_branch: str = "main"
    proxmox_host: str = ""
    proxmox_node: str = ""
    proxmox_token_id: str = ""
    proxmox_token_secret: str = ""
    proxmox_user: str = ""
    proxmox_password: str = ""
    proxmox_verify_ssl: bool = False

    @field_validator(
        "owm_api_key",
        "wapi_api_key",
        "news_api_token",
        "proxmox_host",
        "proxmox_node",
        "proxmox_token_id",
        "proxmox_token_secret",
        "proxmox_user",
        "proxmox_password",
        mode="before",
    )
    @classmethod
    def strip_strings(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @property
    def ssl_cert_path(self) -> Path:
        p = Path(self.ssl_cert)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def ssl_key_path(self) -> Path:
        p = Path(self.ssl_key)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def proxmox_base_url(self) -> str:
        host = self.proxmox_host.strip().rstrip("/")
        if not host:
            return ""
        if not host.startswith(("http://", "https://")):
            host = f"https://{host}"
        parsed = urlparse(host)
        if parsed.port is None and parsed.hostname:
            host = f"{parsed.scheme}://{parsed.hostname}:8006"
        return host.rstrip("/")

    @property
    def proxmox_configured(self) -> bool:
        if not self.proxmox_base_url or not self.proxmox_node:
            return False
        token_ok = bool(self.proxmox_token_id and self.proxmox_token_secret)
        user_ok = bool(self.proxmox_user and self.proxmox_password)
        return token_ok or user_ok

    @property
    def news_configured(self) -> bool:
        return bool(self.news_api_token)

    @property
    def owm_configured(self) -> bool:
        return bool(self.owm_api_key)

    @property
    def wapi_configured(self) -> bool:
        return bool(self.wapi_api_key)


_settings: Settings | None = None
_cached_mtime: float | None = None


def _env_sources_mtime() -> float | None:
    mtimes = []
    for path in (ENV_PATH, ENV_EXAMPLE_PATH):
        if path.exists():
            mtimes.append(path.stat().st_mtime)
    return max(mtimes) if mtimes else None


def _bootstrap_env_file() -> None:
    """Create .env from .env.example when only the example file exists."""
    if not ENV_PATH.exists() and ENV_EXAMPLE_PATH.exists():
        shutil.copy(ENV_EXAMPLE_PATH, ENV_PATH)


def reload_settings() -> Settings:
    """Reload env files from disk and refresh cached settings."""
    global _settings, _cached_mtime
    _bootstrap_env_file()
    if ENV_EXAMPLE_PATH.exists():
        load_dotenv(ENV_EXAMPLE_PATH, override=False)
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
    _settings = Settings()
    _cached_mtime = _env_sources_mtime()
    return _settings


def get_settings() -> Settings:
    """Return settings, reloading automatically when env files change."""
    global _settings, _cached_mtime
    current = _env_sources_mtime()
    if _settings is None or current != _cached_mtime:
        return reload_settings()
    return _settings
