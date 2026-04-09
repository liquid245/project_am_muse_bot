import asyncio
import logging
import signal

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


async def on_startup(bot: Bot):
    """Логирование при запуске бота."""
    bot_info = await bot.get_me()
    logging.info(f"Бот AM Muse (Refactored) запущен: @{bot_info.username} (ID: {bot_info.id})")


async def on_shutdown(bot: Bot):
    """Логирование при остановке бота."""
    bot_info = await bot.get_me()
    logging.warning(f"Бот AM Muse (Refactored) остановлен: @{bot_info.username} (ID: {bot_info.id})")
    await bot.session.close()


async def is_telegram_reachable(timeout: float = 5.0) -> bool:
    """Ping Telegram API to detect network availability."""
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(TELEGRAM_API_URL) as response:
                return 200 <= response.status < 500
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        logging.error(f"Ошибка проверки доступа к Telegram API: {e}")
        return False


async def main():
    """Основная функция запуска бота."""
    if not BOT_TOKEN:
        logging.critical("BOT_TOKEN не найден в переменных окружения! Бот не может быть запущен.")
        return

    if not await is_telegram_reachable():
        logging.critical(
            "Telegram API недоступен. Проверьте сетевые настройки и доступ в интернет. "
            "Бот не может быть запущен."
        )
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация middleware
    from utils.media_handler import MediaGroupMiddleware
    dp.message.middleware(MediaGroupMiddleware())

    # Регистрация хуков жизненного цикла
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Регистрация роутеров
    dp.include_router(common_router)
    dp.include_router(items_router)
    dp.include_router(edit_router)
    dp.include_router(orders_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - [%(funcName)s] - %(message)s",
    )

    loop = asyncio.get_event_loop()
    main_task = None

    def signal_handler(signum, frame):
        logging.warning(f"Получен сигнал {signal.strsignal(signum)}. Завершение работы...")
        if main_task:
            main_task.cancel()

    # Устанавливаем обработчики для SIGINT и SIGTERM
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        main_task = loop.create_task(main())
        loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        logging.info("Основная задача была отменена. Бот останавливается.")
    except (KeyboardInterrupt, SystemExit):
        # Этот блок для локального запуска (Ctrl+C)
        logging.info("Бот остановлен вручную.")
    except Exception as e:
        logging.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
    finally:
        # Даем задачам на завершение немного времени
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            logging.info(f"Ожидание завершения {len(tasks)} фоновых задач...")
            loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        loop.close()
        logging.info("Цикл событий закрыт. Выход.")
