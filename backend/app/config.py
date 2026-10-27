import hashlib
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _on_cloud_agent() -> bool:
    """True on a Cloud Agent VM, including uvicorn started from tmux.

    ``CURSOR_AGENT`` is set on the agent shell but is often missing from the
    tmux server environment that launches the API. The socket and secret-list
    variables are present on that process.
    """
    if os.environ.get("CURSOR_AGENT") == "1":
        return True
    if os.environ.get("CURSOR_AGENT_SOCKET"):
        return True
    if os.environ.get("CLOUD_AGENT_ALL_SECRET_NAMES") or os.environ.get(
        "CLOUD_AGENT_INJECTED_SECRET_NAMES"
    ):
        return True
    return False


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
    # auto | cloudflare | localhost — auto prefers cloudflared when installed.
    tunnel_provider: str = "auto"
    # polling | webhook | auto — auto uses webhooks on Cloud Agents with AUTO_TUNNEL.
    bot_updates_mode: str = "auto"
    webhook_secret: str = ""
    dev_telegram_user_id: int | None = None

    def resolved_webhook_secret(self) -> str:
        if self.webhook_secret.strip():
            return self.webhook_secret.strip()
        if not self.bot_token:
            return ""
        return hashlib.sha256(self.bot_token.encode()).hexdigest()[:32]

    def use_webhook_updates(self) -> bool:
        mode = (self.bot_updates_mode or "auto").strip().lower()
        if mode == "webhook":
            return True
        if mode == "polling":
            return False
        return _on_cloud_agent() and self.auto_tunnel

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'homebar.db').as_posix()}"
    upload_dir: Path = BACKEND_DIR / "data" / "uploads"


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
