import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN

# Импорт роутеров
from functions.common import common_router
from functions.edit import edit_router
from functions.items import items_router
from functions.orders import orders_router

TELEGRAM_API_URL = "https://api.telegram.org"


async def is_telegram_reachable(timeout: float = 5.0) -> bool:
    """Ping Telegram API to detect network availability."""
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(TELEGRAM_API_URL) as response:
                return 200 <= response.status < 500
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return False

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    if not BOT_TOKEN:
        logging.error("BOT_TOKEN не найден в переменных окружения!")
        return

    if not await is_telegram_reachable():
        logging.error(
            "Telegram API недоступен напрямую. Проверьте соединение HF Spaces с интернетом."
        )
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация middleware
    from utils.media_handler import MediaGroupMiddleware
    dp.message.middleware(MediaGroupMiddleware())

    # Регистрация роутеров
    dp.include_router(common_router)
    dp.include_router(items_router)
    dp.include_router(edit_router)
    dp.include_router(orders_router)

    logging.info("Бот AM Muse (Refactored) запущен.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")
