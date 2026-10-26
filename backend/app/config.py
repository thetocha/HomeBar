from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    bartender_telegram_id: int = 0
    webapp_url: str = ""
    # When true, the backend starts its own Cloudflare tunnel and keeps the
    # Telegram menu button pointed at whatever address that tunnel has.
    auto_tunnel: bool = True
    dev_telegram_user_id: int | None = None

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'homebar.db').as_posix()}"
    upload_dir: Path = BACKEND_DIR / "data" / "uploads"


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
