from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from .config import settings
from .models import STATUS_LABEL_RU
from .telegram_auth import format_display_name

logger = logging.getLogger(__name__)

RESTART_BUTTON = "Начать сначала"
MENU_BUTTON = "Открыть меню"
RESTART_TEXTS = {RESTART_BUTTON, "Старт"}

bot: Bot | None = None
dp: Dispatcher | None = None


def welcome_text(name: str) -> str:
    return (
        f"Привет, {name}! 🛋\n"
        "Правило номер один на сегодня: твой бокал никогда не должен пустовать. "
        "Устраивайся поудобнее, открывай меню и выбирай своё настроение на этот вечер. "
        "Никакого самообслуживания — бармен всё сделает красиво! ✨"
    )


def restart_keyboard() -> ReplyKeyboardMarkup:
    # A reply-keyboard web_app button opens the page with empty initData.
    # The menu itself is an inline button, which Telegram signs with the user.
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=RESTART_BUTTON)]],
        resize_keyboard=True,
    )


def menu_inline_keyboard() -> InlineKeyboardMarkup | None:
    if not settings.webapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=MENU_BUTTON,
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            ]
        ]
    )


def create_bot() -> tuple[Bot | None, Dispatcher | None]:
    global bot, dp
    if not settings.bot_token:
        logger.warning("BOT_TOKEN is empty; Telegram bot and order pings are disabled")
        return None, None

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    register_handlers(dp)
    return bot, dp


def register_handlers(dispatcher: Dispatcher) -> None:
    dispatcher.message.register(send_welcome, CommandStart())
    dispatcher.message.register(send_welcome, F.text.in_(RESTART_TEXTS))


async def send_welcome(message: Message) -> None:
    user = message.from_user
    name = format_display_name(
        user.first_name if user else None,
        user.last_name if user else None,
    )
    text = welcome_text(escape(name))
    if not settings.webapp_url:
        text += "\n\nАдрес мини-приложения ещё не задан, поэтому кнопка меню скрыта."
    await message.answer(text, reply_markup=restart_keyboard())
    menu = menu_inline_keyboard()
    if menu is not None:
        await message.answer("Откройте меню:", reply_markup=menu)


async def setup_menu_button(active_bot: Bot) -> None:
    if not settings.webapp_url:
        logger.warning("WEBAPP_URL is empty; skipping chat menu button")
        return
    await active_bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Меню",
            web_app=WebAppInfo(url=settings.webapp_url),
        )
    )
    logger.info("Telegram menu button set to %s", settings.webapp_url)


def build_order_notify_text(
    *,
    cocktail_name: str,
    display_name: str,
    guest_username: str | None,
    order_id: int,
) -> str:
    handle = f"@{guest_username}" if guest_username else "нет юзернейма"
    return (
        f"<b>Новый заказ №{order_id}</b>\n"
        f"Напиток: {escape(cocktail_name)}\n"
        f"Гость: {escape(display_name)} ({escape(handle)})"
    )


def build_status_notify_text(
    *,
    order_id: int,
    cocktail_name: str,
    status: str,
) -> str:
    label = STATUS_LABEL_RU.get(status, status)
    return (
        f"<b>Заказ №{order_id}</b>\n"
        f"{escape(cocktail_name)}\n"
        f"Новый статус: {escape(label)}"
    )


async def notify_bartender(
    *,
    cocktail_name: str,
    display_name: str,
    guest_username: str | None,
    order_id: int,
) -> None:
    text = build_order_notify_text(
        cocktail_name=cocktail_name,
        display_name=display_name,
        guest_username=guest_username,
        order_id=order_id,
    )
    if bot is None or not settings.bartender_telegram_id:
        logger.info("Order notify (bot disabled): %s", text.replace("\n", " | "))
        return
    try:
        await bot.send_message(settings.bartender_telegram_id, text)
    except Exception:
        logger.exception("Failed to send bartender Telegram notification")


async def notify_guest_status(
    *,
    chat_id: int | None,
    order_id: int,
    cocktail_name: str,
    status: str,
) -> None:
    if not chat_id:
        logger.info("Skip guest status notify for order %s: no chat id", order_id)
        return
    text = build_status_notify_text(
        order_id=order_id,
        cocktail_name=cocktail_name,
        status=status,
    )
    if bot is None:
        logger.info("Guest status notify (bot disabled): %s", text.replace("\n", " | "))
        return
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        logger.exception("Failed to send guest status notification for order %s", order_id)
