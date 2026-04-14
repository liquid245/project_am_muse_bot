import asyncio
import logging
import signal

import aiohttp
from aiohttp import web
from aiohttp.client_exceptions import ClientOSError
from aiohttp_retry import RetryClient, ExponentialRetry
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, HEALTH_CHECK_HOST, HEALTH_CHECK_PORT

# Импорт роутеров
from functions.common import common_router
from functions.edit import edit_router
from functions.items import items_router
from functions.orders import orders_router

TELEGRAM_API_URL = "https://api.telegram.org"


async def health_check(request: web.Request) -> web.Response:
    """Обработчик для health check эндпоинта."""
    return web.Response(text="OK")


async def on_startup(bot: Bot):
    """Логирование при запуске бота."""
    bot_info = await bot.get_me()
    logging.info(f"Бот AM Muse (Refactored) запущен: @{bot_info.username} (ID: {bot_info.id})")


async def on_shutdown(bot: Bot, web_runner: web.AppRunner):
    """Логирование и корректное завершение работы сервера и бота."""
    logging.warning("Начало процедуры остановки...")
    bot_info = await bot.get_me()

    logging.info("Остановка health check сервера...")
    await web_runner.cleanup()
    logging.info("Health check сервер остановлен.")

    logging.warning(f"Бот AM Muse (Refactored) остановлен: @{bot_info.username} (ID: {bot_info.id})")
    await bot.session.close()
    logging.info("Сессия бота закрыта.")


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
    """Основная функция запуска бота и health check сервера."""
    if not BOT_TOKEN:
        logging.critical("BOT_TOKEN не найден в переменных окружения! Бот не может быть запущен.")
        return

    if not await is_telegram_reachable():
        logging.critical(
            "Telegram API недоступен. Проверьте сетевые настройки и доступ в интернет. "
            "Бот не может быть запущен."
        )
        return
        
    # Настройка и запуск aiohttp сервера
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HEALTH_CHECK_HOST, HEALTH_CHECK_PORT)
    await site.start()
    logging.info(f"Health check сервер запущен на http://{HEALTH_CHECK_HOST}:{HEALTH_CHECK_PORT}")

    # Настройка и запуск бота
    retry_options = ExponentialRetry(
        attempts=5,
        start_timeout=1,
        max_timeout=60,
        factor=2,
        statuses=[500, 502, 503, 504],
        exceptions={ClientOSError, asyncio.TimeoutError},
    )
    
    # Создаем сессию с автоматическими повторами
    # aiogram's AiohttpSession passes all kwargs to BaseSession.__init__
    # which does not accept 'client'. So we instantiate it without client
    # and then manually set the _client attribute.
    session = AiohttpSession()
    session._client = RetryClient(retry_options=retry_options)
    
    # Настройка и запуск бота
    bot = Bot(token=BOT_TOKEN, session=session)
    # Передаем runner в Dispatcher для доступа в on_shutdown
    dp = Dispatcher(storage=MemoryStorage(), web_runner=runner)

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

    # Запуск polling'а
    await dp.start_polling(bot)


def handle_exception(loop, context):
    msg = context.get("exception", context["message"])
    logging.error(f"Caught exception: {msg}")

async def main_wrapper():
    """Wrapper for main() to handle startup and shutdown gracefully."""
    loop = asyncio.get_running_loop()

    # Add custom exception handler for the loop
    loop.set_exception_handler(handle_exception)

    # Signal handlers for graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(loop, s)))

    try:
        await main()
    except asyncio.CancelledError:
        logging.info("Main task cancelled. Initiating graceful shutdown.")
    except Exception as e:
        logging.critical(f"Critical error during bot runtime: {e}", exc_info=True)


async def shutdown(loop, signal=None):
    """Gracefully shuts down all running tasks and the event loop."""
    if signal:
        logging.warning(f"Received exit signal {signal.name}. Initiating graceful shutdown...")
    
    # Cancel all running tasks
    tasks = [t for t in asyncio.all_tasks(loop=loop) if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    # Wait for all tasks to complete or be cancelled
    await asyncio.gather(*tasks, return_exceptions=True)
    logging.info("All background tasks cancelled.")

    loop.stop()
    logging.info("Event loop stopped.")


if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - [%(funcName)s] - %(message)s",
    )

    try:
        asyncio.run(main_wrapper())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped manually by KeyboardInterrupt or SystemExit.")
    except Exception as e:
        logging.critical(f"Unhandled critical error: {e}", exc_info=True)
    finally:
        logging.info("Application finished.")
