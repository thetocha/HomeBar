from __future__ import annotations

import logging

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request, status

from .. import bot as bot_module
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telegram"])


@router.post("/api/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    active_bot = bot_module.bot
    active_dp = bot_module.dp
    if active_bot is None or active_dp is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Bot is not configured")
    expected = settings.resolved_webhook_secret()
    if not expected or x_telegram_bot_api_secret_token != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid webhook secret")
    try:
        payload = await request.json()
        update = Update.model_validate(payload)
    except Exception as exc:
        logger.warning("Bad Telegram webhook payload: %s", exc)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid update") from exc
    try:
        await active_dp.feed_update(active_bot, update)
    except Exception:
        logger.exception("Telegram webhook handler failed for update %s", update.update_id)
    return {"ok": True}
