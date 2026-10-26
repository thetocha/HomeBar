from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from .bot import create_bot, dp, setup_menu_button
from .config import ROOT_DIR, settings
from .database import init_db
from .photos import optimize_stored_photos
from .routers import cocktails, me, orders
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
    if active_bot and dispatcher:
        polling_task = asyncio.create_task(dispatcher.start_polling(active_bot))
        logger.info("aiogram polling started")
    if settings.auto_tunnel:
        tunnel_task = asyncio.create_task(run_tunnel(active_bot))
    elif active_bot:
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
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me.router)
app.include_router(cocktails.router)
app.include_router(orders.router)


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


@app.get("/{full_path:path}")
def spa(full_path: str):
    index = frontend_dist / "index.html"
    if not index.exists():
        return {"detail": "Frontend is not built. Run npm run build in frontend/."}
    if full_path:
        candidate = frontend_dist / full_path
        if candidate.is_file():
            headers = None
            if full_path == "telegram-web-app.js":
                headers = {"Cache-Control": "public, max-age=86400"}
            return FileResponse(candidate, headers=headers)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, app_dir=str(Path(__file__).resolve().parents[1]))


# Keep dp imported so lifespan and tests can see the shared dispatcher module attribute.
_ = dp
