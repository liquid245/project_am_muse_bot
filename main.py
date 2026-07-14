import asyncio
import logging
import signal
from functools import partial

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import (
    BOT_TOKEN,
    HOST,
    PORT,
    TELEGRAM_API_PROXY,
    WEBHOOK_URL,
    WEBHOOK_PATH,
)

from functions.common import common_router
from functions.edit import edit_router
from functions.items import items_router
from functions.orders import orders_router


async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def on_startup(bot: Bot, webhook_url: str | None = None):
    if webhook_url:
        await bot.set_webhook(url=webhook_url)
    try:
        bot_info = await bot.get_me()
        logging.info(f"Бот запущен: @{bot_info.username} (ID: {bot_info.id})")
    except Exception as e:
        logging.warning(f"Не удалось получить информацию о боте при старте: {e}")


async def on_shutdown(bot: Bot):
    logging.warning("Начало процедуры остановки...")
    try:
        await bot.delete_webhook()
        bot_info = await bot.get_me()
        bot_name = f"@{bot_info.username} (ID: {bot_info.id})"
    except Exception:
        bot_name = "неизвестен"
    logging.warning(f"Бот остановлен: {bot_name}")
    await bot.session.close()
    logging.info("Сессия бота закрыта.")


async def is_telegram_reachable(timeout: float = 3.0) -> bool:
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(TELEGRAM_API_PROXY) as response:
                return response.status < 500
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        logging.warning(f"Telegram API недоступен: {e}")
        return False


async def main():
    logging.info("Запуск main()...")

    if not BOT_TOKEN:
        logging.critical("BOT_TOKEN не найден! Бот не может быть запущен.")
        return

    tg_ok = await is_telegram_reachable()
    if not tg_ok:
        logging.warning("Telegram API недоступен при старте.")

    proxy_api = TelegramAPIServer.from_base(TELEGRAM_API_PROXY)
    session = AiohttpSession(api=proxy_api)
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())

    from utils.media_handler import MediaGroupMiddleware
    dp.message.middleware(MediaGroupMiddleware())

    dp.include_router(common_router)
    dp.include_router(items_router)
    dp.include_router(edit_router)
    dp.include_router(orders_router)

    if WEBHOOK_URL:
        await _run_webhook(bot, dp)
    else:
        logging.info("WEBHOOK_URL не задан — запуск в режиме Polling (разработка).")
        await _run_polling(bot, dp)


async def _run_webhook(bot: Bot, dp: Dispatcher):
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"

    dp.startup.register(partial(on_startup, webhook_url=webhook_url))
    dp.shutdown.register(on_shutdown)

    app = web.Application()

    app.router.add_get("/", health_check)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()

    logging.info(f"Сервер запущен на http://{HOST}:{PORT}")
    logging.info(f"Webhook URL: {webhook_url}")

    await asyncio.Event().wait()


async def _run_polling(bot: Bot, dp: Dispatcher):
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logging.info("Запуск polling...")
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
