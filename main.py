import asyncio
import logging
import signal
import time

import aiohttp
from aiohttp import web
from aiohttp.client_exceptions import ClientOSError
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, HEALTH_CHECK_HOST, HEALTH_CHECK_PORT

from functions.common import common_router
from functions.edit import edit_router
from functions.items import items_router
from functions.orders import orders_router

TELEGRAM_API_URL = "https://api.telegram.org"


async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def on_startup(bot: Bot):
    try:
        bot_info = await bot.get_me()
        logging.info(f"Бот запущен: @{bot_info.username} (ID: {bot_info.id})")
    except Exception as e:
        logging.warning(f"Не удалось получить информацию о боте при старте: {e}")


async def on_shutdown(bot: Bot, web_runner: web.AppRunner):
    logging.warning("Начало процедуры остановки...")
    try:
        bot_info = await bot.get_me()
        bot_name = f"@{bot_info.username} (ID: {bot_info.id})"
    except Exception:
        bot_name = "неизвестен"

    logging.info("Остановка health check сервера...")
    await web_runner.cleanup()
    logging.info("Health check сервер остановлен.")

    logging.warning(f"Бот остановлен: {bot_name}")
    await bot.session.close()
    logging.info("Сессия бота закрыта.")


async def is_telegram_reachable(timeout: float = 3.0) -> bool:
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(TELEGRAM_API_URL) as response:
                return 200 <= response.status < 500
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        logging.warning(f"Telegram API недоступен: {e}")
        return False


async def start_health_check_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HEALTH_CHECK_HOST, HEALTH_CHECK_PORT)
    await site.start()
    logging.info(f"Health check сервер запущен на http://{HEALTH_CHECK_HOST}:{HEALTH_CHECK_PORT}")
    return runner


async def main():
    start_time = time.monotonic()
    logging.info("Запуск main()...")

    if not BOT_TOKEN:
        logging.critical("BOT_TOKEN не найден! Бот не может быть запущен.")
        return

    runner = await start_health_check_server()

    tg_ok = await is_telegram_reachable()
    if not tg_ok:
        logging.warning("Telegram API недоступен при старте.")

    session = AiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage(), web_runner=runner)

    from utils.media_handler import MediaGroupMiddleware
    dp.message.middleware(MediaGroupMiddleware())

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    dp.include_router(common_router)
    dp.include_router(items_router)
    dp.include_router(edit_router)
    dp.include_router(orders_router)

    elapsed = time.monotonic() - start_time
    logging.info(f"Инициализация завершена за {elapsed:.1f}с. Запуск polling...")

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Polling завершился с ошибкой: {e}", exc_info=True)


def handle_exception(loop, context):
    msg = context.get("exception", context["message"])
    logging.error(f"Поймано исключение: {msg}")


async def main_wrapper():
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(handle_exception)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(loop, s)))

    try:
        await main()
    except asyncio.CancelledError:
        logging.info("Main task cancelled.")
    except Exception as e:
        logging.critical(f"Critical error: {e}", exc_info=True)


async def shutdown(loop, signal=None):
    if signal:
        logging.warning(f"Получен сигнал {signal.name}. Остановка...")

    tasks = [t for t in asyncio.all_tasks(loop=loop) if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - [%(funcName)s] - %(message)s",
        force=True,
    )

    try:
        asyncio.run(main_wrapper())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped manually.")
    except Exception as e:
        logging.critical(f"Unhandled critical error: {e}", exc_info=True)
    finally:
        logging.info("Application finished.")
