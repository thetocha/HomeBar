from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, Request, status

from .config import settings

MAX_AUTH_AGE_SECONDS = 24 * 60 * 60


@dataclass
class TelegramUser:
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    is_bartender: bool
    suggested_display_name: str
    dev_mode: bool


def _parse_user_json(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram user payload") from exc
    if not isinstance(data, dict) or "id" not in data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram user payload")
    return data


def verify_init_data(init_data: str) -> TelegramUser:
    if not settings.bot_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "BOT_TOKEN is not configured")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing initData hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram initData")

    auth_date_raw = pairs.get("auth_date")
    if auth_date_raw:
        try:
            auth_date = int(auth_date_raw)
        except ValueError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid auth_date") from exc
        age = datetime.now(timezone.utc).timestamp() - auth_date
        if age > MAX_AUTH_AGE_SECONDS:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Telegram initData expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Telegram user missing from initData")
    user = _parse_user_json(user_raw)
    return _from_user_dict(user, dev_mode=False)


def _from_user_dict(user: dict, *, dev_mode: bool) -> TelegramUser:
    telegram_id = int(user["id"])
    first_name = str(user.get("first_name") or "Guest")
    last_name = user.get("last_name")
    username = user.get("username")
    return TelegramUser(
        id=telegram_id,
        first_name=first_name,
        last_name=str(last_name) if last_name else None,
        username=str(username) if username else None,
        is_bartender=telegram_id == settings.bartender_telegram_id,
        suggested_display_name=first_name,
        dev_mode=dev_mode,
    )


def _dev_user(user_id: int) -> TelegramUser:
    label = "Bartender" if user_id == settings.bartender_telegram_id else "Guest"
    return TelegramUser(
        id=user_id,
        first_name=label,
        last_name=None,
        username="localdev" if user_id == settings.bartender_telegram_id else None,
        is_bartender=user_id == settings.bartender_telegram_id,
        suggested_display_name=label,
        dev_mode=True,
    )


def get_current_user(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None),
    x_dev_telegram_user_id: int | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> TelegramUser:
    init_data = x_telegram_init_data
    if not init_data and authorization:
        scheme, _, remainder = authorization.partition(" ")
        if scheme.lower() == "tma":
            init_data = remainder.strip()

    if not init_data:
        query_init = request.query_params.get("initData")
        if query_init:
            init_data = query_init

    if init_data:
        return verify_init_data(init_data)

    if settings.dev_telegram_user_id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Telegram initData required",
        )

    user_id = x_dev_telegram_user_id or settings.dev_telegram_user_id
    return _dev_user(user_id)


def require_bartender(user: TelegramUser = Depends(get_current_user)) -> TelegramUser:
    if not user.is_bartender:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bartender only")
    return user
