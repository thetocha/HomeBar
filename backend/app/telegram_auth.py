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
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost"}


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
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Некорректные данные пользователя Telegram") from exc
    if not isinstance(data, dict) or "id" not in data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Некорректные данные пользователя Telegram")
    return data


def verify_init_data(init_data: str) -> TelegramUser:
    if not settings.bot_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Бот не настроен")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нет подписи Telegram")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Некорректные данные Telegram")

    auth_date_raw = pairs.get("auth_date")
    if auth_date_raw:
        try:
            auth_date = int(auth_date_raw)
        except ValueError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Некорректная дата авторизации") from exc
        age = datetime.now(timezone.utc).timestamp() - auth_date
        if age > MAX_AUTH_AGE_SECONDS:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия Telegram истекла")

    user_raw = pairs.get("user")
    if not user_raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "В данных Telegram нет пользователя")
    user = _parse_user_json(user_raw)
    return _from_user_dict(user, dev_mode=False)


def format_display_name(first_name: str | None, last_name: str | None = None) -> str:
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    full = " ".join(part for part in (first, last) if part)
    return full or "Гость"


def _from_user_dict(user: dict, *, dev_mode: bool) -> TelegramUser:
    telegram_id = int(user["id"])
    raw_first = str(user.get("first_name") or "").strip()
    raw_last = user.get("last_name")
    last_name = str(raw_last).strip() if raw_last else None
    username = user.get("username")
    return TelegramUser(
        id=telegram_id,
        first_name=raw_first or "Гость",
        last_name=last_name or None,
        username=str(username) if username else None,
        is_bartender=telegram_id == settings.bartender_telegram_id,
        suggested_display_name=format_display_name(raw_first, last_name),
        dev_mode=dev_mode,
    )


def _dev_user(user_id: int) -> TelegramUser:
    label = "Бармен" if user_id == settings.bartender_telegram_id else "Гость"
    return TelegramUser(
        id=user_id,
        first_name=label,
        last_name=None,
        username="localdev" if user_id == settings.bartender_telegram_id else None,
        is_bartender=user_id == settings.bartender_telegram_id,
        suggested_display_name=label,
        dev_mode=True,
    )


def _client_host(request: Request) -> str:
    return (request.client.host if request.client else "") or ""


def _hostname(value: str) -> str:
    value = value.strip().lower()
    if not value:
        return ""
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end != -1 else value
    if value.count(":") == 1:
        return value.split(":", 1)[0]
    return value


def _is_loopback_name(name: str) -> bool:
    return name in _LOOPBACK_HOSTS


def _is_loopback(request: Request) -> bool:
    return _is_loopback_name(_client_host(request))


def _forwarded_is_loopback(request: Request) -> bool:
    """SSH reverse tunnels look like 127.0.0.1; public clients still send a public Host."""
    for header in ("x-forwarded-for", "x-real-ip"):
        raw = request.headers.get(header)
        if not raw:
            continue
        for part in raw.split(","):
            host = _hostname(part)
            if host and not _is_loopback_name(host):
                return False
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        host = _hostname(forwarded_host.split(",", 1)[0])
        if host and not _is_loopback_name(host):
            return False
    return True


def local_dev_impersonation_allowed(request: Request) -> bool:
    """Dev user switching is only for http://127.0.0.1, never the public tunnel hostname."""
    if settings.dev_telegram_user_id is None:
        return False
    if not _is_loopback(request):
        return False
    host = _hostname(request.headers.get("host") or "")
    if not _is_loopback_name(host):
        return False
    return _forwarded_is_loopback(request)


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

    if init_data:
        return verify_init_data(init_data)

    if not local_dev_impersonation_allowed(request):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Нужны данные Telegram",
        )

    fallback_id = settings.dev_telegram_user_id
    if fallback_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужны данные Telegram")
    return _dev_user(x_dev_telegram_user_id or fallback_id)


def require_bartender(user: TelegramUser = Depends(get_current_user)) -> TelegramUser:
    if not user.is_bartender:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только для бармена")
    return user
