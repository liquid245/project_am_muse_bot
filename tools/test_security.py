#!/usr/bin/env python3
"""Проверки безопасности бота: секрет вебхука + фильтр IsAdmin.

Запуск: bot/.venv/bin/python tools/test_security.py
Ничего не ходит в сеть: фейковый Bot, апдейты генерируются локально.
"""
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("ADMIN_IDS", "424242")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from filters.roles import IsAdmin

FAKE_TOKEN = "424242:AAFakeFakeFakeFakeFakeFakeFakeFakeFake"
SECRET = "s3cr3t-webhook-token"


class DummySession(BaseSession):
    """Заглушка сессии — перехватывает исходящие вызовы Telegram."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []

    async def close(self) -> None:  # noqa: D401
        return None

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""


def build_app(secret_token: str | None) -> web.Application:
    bot = Bot(token=FAKE_TOKEN, session=DummySession())
    dp = Dispatcher()
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret_token).register(
        app, path="/webhook"
    )
    return app


async def probe(secret_token: str | None, header: str | None) -> int:
    headers = {"X-Telegram-Bot-Api-Secret-Token": header} if header is not None else {}
    async with TestClient(TestServer(build_app(secret_token))) as client:
        resp = await client.post("/webhook", json={"update_id": 1}, headers=headers)
        return resp.status


async def filter_checks() -> list[tuple[str, bool]]:
    from config import ADMIN_IDS

    admin_id = ADMIN_IDS[0]
    stranger_id = max(ADMIN_IDS) + 10_000_000
    user = User(id=admin_id, is_bot=False, first_name="Admin")
    other = User(id=stranger_id, is_bot=False, first_name="Stranger")
    chat = Chat(id=admin_id, type="private")
    admin_msg = Message.model_construct(message_id=1, date=0, chat=chat, from_user=user, text="x")
    other_msg = Message.model_construct(message_id=1, date=0, chat=chat, from_user=other, text="x")
    admin_cb = CallbackQuery.model_construct(
        id="1", from_user=user, chat_instance="ci", data="edit_init_1"
    )
    other_cb = CallbackQuery.model_construct(
        id="2", from_user=other, chat_instance="ci", data="edit_init_1"
    )
    f = IsAdmin()
    return [
        ("IsAdmin: message от админа", (await f(admin_msg)) is True),
        ("IsAdmin: message от чужого", (await f(other_msg)) is False),
        ("IsAdmin: callback от админа", (await f(admin_cb)) is True),
        ("IsAdmin: callback от чужого", (await f(other_cb)) is False),
    ]


async def main() -> int:
    results: list[tuple[str, bool]] = []

    # 1. Старое поведение (без секрета) — анонимный POST проходит: это и была дыра.
    results.append(("без секрета: анонимный POST -> 200 (дыра воспроизведена)",
                    await probe(None, None) == 200))

    # 2. С секретом: без заголовка -> 401
    results.append(("с секретом: без заголовка -> 401", await probe(SECRET, None) == 401))

    # 3. С секретом: неверный заголовок -> 401
    results.append(("с секретом: неверный заголовок -> 401", await probe(SECRET, "wrong") == 401))

    # 4. С секретом: верный заголовок -> 200
    results.append(("с секретом: верный заголовок -> 200", await probe(SECRET, SECRET) == 200))

    results.extend(await filter_checks())

    failed = 0
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        failed += 0 if ok else 1
    print(f"\n{len(results) - failed}/{len(results)} пройдено")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
