import asyncio
import hashlib
import logging
import os
import secrets
import signal
from functools import partial

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import (
    HOST,
    PORT,
    TELEGRAM_API_PROXY,
    WEBHOOK_SECRET,
    WEBHOOK_URL,
    WEBHOOK_PATH,
)

from functions.common import common_router
from functions.edit import edit_router
from functions.items import items_router
from functions.orders import orders_router


async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def on_startup(bot: Bot, webhook_url: str | None = None, secret_token: str | None = None):
    if webhook_url:
        await bot.set_webhook(url=webhook_url, secret_token=secret_token)
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


def describe_token(name: str, raw: str) -> str:
    """Отпечаток токена для лога: полный токен не печатаем никогда.

    Даёт всё для сверки: id бота (часть до ':' — не секрет), длина, последние 4 символа,
    sha256[:8] и сколько невидимых символов срезал strip (частая причина 401).
    """
    token = raw.strip()
    if not token:
        return f"{name}: ПУСТАЯ (len(raw)={len(raw)})"
    bot_id = token.split(":", 1)[0] if ":" in token else "НЕТ_ДВОЕТОЧИЯ"
    digest = hashlib.sha256(token.encode()).hexdigest()[:8]
    invisible = len(raw) - len(token)
    return (
        f"{name}: id={bot_id} len={len(token)} tail=...{token[-4:]} "
        f"sha256_8={digest} невидимых_символов={invisible}"
    )


def _token_candidates() -> list[tuple[str, str]]:
    """Пары (имя переменной, сырое значение) в порядке приоритета, без дублей по значению.

    Порядок: BOT_TOKEN_2 → BOT_TOKEN_1 → BOT_TOKEN.
    На Bothost BOT_TOKEN — системное поле, которое правкой env не изменить, и в нём
    может лежать мёртвый токен. Поэтому кандидатов три, и рабочий выбирается живой
    проверкой get_me, а не порядком переменных.
    """
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in ("BOT_TOKEN_2", "BOT_TOKEN_1", "BOT_TOKEN"):
        raw = os.getenv(name) or ""
        value = raw.strip()
        if value and value not in seen:
            seen.add(value)
            candidates.append((name, raw))
        elif not value:
            logging.warning(f"{name}: НЕ ЗАДАНА в окружении контейнера")
    return candidates


async def _pick_bot(proxy_api: TelegramAPIServer) -> Bot | None:
    """Возвращает Bot с первым живым токеном. Мёртвый (401) отбрасывается."""
    candidates = _token_candidates()
    if not candidates:
        logging.critical("Токен не найден: ни BOT_TOKEN_1, ни BOT_TOKEN не заданы.")
        return None

    for name, raw in candidates:
        token = raw.strip()
        logging.info(describe_token(name, raw))
        candidate = Bot(token=token, session=AiohttpSession(api=proxy_api))
        try:
            me = await candidate.get_me()
        except TelegramUnauthorizedError:
            logging.warning(f"{name}: невалиден (401) — пробую следующий кандидат.")
            await candidate.session.close()
            continue
        except Exception as exc:  # сеть/таймаут: не приговор токену
            logging.warning(f"{name}: проверка не удалась ({exc}) — использую как есть.")
            return candidate
        logging.info(f"ИСПОЛЬЗУЮ {name}: @{me.username} (id {me.id}) — id={name}")
        return candidate

    logging.critical(
        "Все токены из окружения невалидны (401). "
        "Сверь sha256_8 и tail с эталонным отпечатком актуального @am_muse_bot."
    )
    return None


async def main():
    logging.info("Запуск main()...")

    tg_ok = await is_telegram_reachable()
    if not tg_ok:
        logging.warning("Telegram API недоступен при старте.")

    proxy_api = TelegramAPIServer.from_base(TELEGRAM_API_PROXY)
    bot = await _pick_bot(proxy_api)
    if bot is None:
        return
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


def _resolve_webhook_secret() -> str:
    """Секрет вебхука. Без него любой POST на WEBHOOK_PATH обрабатывается как апдейт Telegram."""
    secret = (WEBHOOK_SECRET or "").strip()
    if secret:
        return secret
    generated = secrets.token_urlsafe(32)
    logging.warning(
        "WEBHOOK_SECRET не задан — сгенерирован временный секрет. "
        "Задай WEBHOOK_SECRET в переменных окружения, иначе он меняется при каждом рестарте."
    )
    return generated


async def _run_webhook(bot: Bot, dp: Dispatcher):
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
    secret = _resolve_webhook_secret()

    dp.startup.register(partial(on_startup, webhook_url=webhook_url, secret_token=secret))
    dp.shutdown.register(on_shutdown)

    app = web.Application()

    app.router.add_get("/", health_check)
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(app, path=WEBHOOK_PATH)
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
