from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    KeyboardButton,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from .config import settings

logger = logging.getLogger(__name__)

bot: Bot | None = None
dp: Dispatcher | None = None


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
    @dispatcher.message(CommandStart())
    async def start(message: Message) -> None:
        text = (
            "<b>Djinn Antonic</b>\n"
            "Open the paper menu, pick a drink, and I will take the order."
        )
        if settings.webapp_url:
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [
                        KeyboardButton(
                            text="Open menu",
                            web_app=WebAppInfo(url=settings.webapp_url),
                        )
                    ]
                ],
                resize_keyboard=True,
            )
            await message.answer(text, reply_markup=keyboard)
        else:
            await message.answer(
                text + "\n\nWEBAPP_URL is not set yet, so the Mini App button is hidden."
            )


async def setup_menu_button(active_bot: Bot) -> None:
    if not settings.webapp_url:
        logger.warning("WEBAPP_URL is empty; skipping chat menu button")
        return
    await active_bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Menu",
            web_app=WebAppInfo(url=settings.webapp_url),
        )
    )


def build_order_notify_text(
    *,
    cocktail_name: str,
    display_name: str,
    guest_username: str | None,
    order_id: int,
) -> str:
    handle = f"@{guest_username}" if guest_username else "no username"
    return (
        f"<b>New order #{order_id}</b>\n"
        f"Drink: {cocktail_name}\n"
        f"Guest: {display_name} ({handle})"
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
