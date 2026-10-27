from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from .bot import create_bot, dp, setup_menu_button, setup_webhook
from .config import ROOT_DIR, settings
from .database import init_db
from .photos import optimize_stored_photos
from .routers import cocktails, me, orders, telegram_webhook
from .tunnel import run_tunnel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        optimize_stored_photos()
    except Exception:
        logger.exception("Could not shrink stored cocktail photos")
    active_bot, dispatcher = create_bot()
    polling_task: asyncio.Task | None = None
    tunnel_task: asyncio.Task | None = None
    use_webhook = settings.use_webhook_updates()
    if active_bot and dispatcher:
        if use_webhook:
            logger.info("Telegram webhook mode (no long polling)")
            if settings.webapp_url:
                try:
                    await setup_webhook(active_bot)
                    await setup_menu_button(active_bot)
                except Exception:
                    logger.exception("Could not set Telegram webhook or menu button")
        else:
            polling_task = asyncio.create_task(dispatcher.start_polling(active_bot))
            logger.info("aiogram polling started")
    if settings.auto_tunnel:
        tunnel_task = asyncio.create_task(run_tunnel(active_bot))
    elif active_bot and not use_webhook:
        try:
            await setup_menu_button(active_bot)
        except Exception:
            logger.exception("Could not set Telegram menu button")
    yield
    if tunnel_task:
        tunnel_task.cancel()
        try:
            await tunnel_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error while stopping the public tunnel")
    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error while stopping bot polling")
    if active_bot:
        await active_bot.session.close()


app = FastAPI(title="Djinn Antonic", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Vite tags module scripts with crossorigin, so Telegram's WebView will not
    # run them unless ACAO matches the public tunnel origin (which rotates).
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me.router)
app.include_router(cocktails.router)
app.include_router(orders.router)
app.include_router(telegram_webhook.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class CachedStaticFiles(StaticFiles):
    def __init__(self, *args, cache_control: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cache_control = cache_control

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = self._cache_control
        return response


settings.upload_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/media",
    CachedStaticFiles(directory=settings.upload_dir, cache_control="public, max-age=31536000, immutable"),
    name="media",
)

frontend_dist = ROOT_DIR / "frontend" / "dist"
if (frontend_dist / "assets").exists():
    app.mount(
        "/assets",
        CachedStaticFiles(
            directory=frontend_dist / "assets",
            cache_control="public, max-age=31536000, immutable",
        ),
        name="assets",
    )


def _safe_frontend_file(full_path: str) -> Path | None:
    if not full_path:
        return None
    dist_root = frontend_dist.resolve()
    try:
        candidate = (frontend_dist / full_path).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if candidate.is_file() and candidate.is_relative_to(dist_root):
        return candidate
    return None


@app.get("/{full_path:path}")
def spa(full_path: str):
    index = frontend_dist / "index.html"
    if not index.exists():
        return {"detail": "Интерфейс не собран. Запустите npm run build в папке frontend."}
    if full_path:
        candidate = _safe_frontend_file(full_path)
        if candidate is not None:
            headers = None
            if full_path == "telegram-web-app.js":
                headers = {"Cache-Control": "public, max-age=86400"}
            return FileResponse(candidate, headers=headers)
        if Path(full_path).suffix:
            return Response(status_code=404)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


def run() -> None:
    import uvicorn

    import os

    host = os.environ.get("UVICORN_HOST", "0.0.0.0")
    port = int(os.environ.get("UVICORN_PORT", "8000"))
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        app_dir=str(Path(__file__).resolve().parents[1]),
    )


# Keep dp imported so lifespan and tests can see the shared dispatcher module attribute.
_ = dp
