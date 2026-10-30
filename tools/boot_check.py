#!/usr/bin/env python3
"""Боевая проверка запуска: поднимает реальный aiohttp-сервер бота как в проде.

Сеть не нужна: Bot.set_webhook/get_me подменяются заглушками, чтобы увидеть,
что именно бот регистрирует в Telegram (url + secret_token) и как отвечает эндпоинт.

Запуск: bot/.venv/bin/python tools/boot_check.py
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["BOT_TOKEN"] = "424242:AAFakeFakeFakeFakeFakeFakeFakeFakeFake"
os.environ["WEBHOOK_URL"] = "https://bot-123.bothost.ru"
os.environ["PORT"] = "18081"
os.environ["WEBHOOK_SECRET"] = "boot-check-secret"

import aiohttp
from aiogram import Bot
from aiogram.types import User

captured: dict = {}


async def fake_set_webhook(self, url, **kwargs):
    captured["url"] = url
    captured["kwargs"] = kwargs
    return True


async def fake_get_me(self):
    return User(id=1, is_bot=True, first_name="Fake", username="am_muse_bot")


Bot.set_webhook = fake_set_webhook
Bot.get_me = fake_get_me

import main as botmain  # noqa: E402


async def probe(target: str, headers: dict) -> int:
    async with aiohttp.ClientSession() as s:
        async with s.post(target, json={"update_id": 1}, headers=headers) as r:
            return r.status


async def run() -> int:
    task = asyncio.create_task(botmain.main())
    base = "http://127.0.0.1:18081"

    # ждём готовности сервера (сетевые проверки при старте занимают время)
    ready = False
    for _ in range(40):
        await asyncio.sleep(0.5)
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(base + "/", timeout=aiohttp.ClientTimeout(total=2)) as r:
                    if r.status == 200:
                        ready = True
                        break
        except Exception:
            continue

    results = []
    results.append(("сервер поднялся и отвечает на GET /", ready))
    if not ready:
        task.cancel()
        print("FAIL  сервер не поднялся за 20с")
        return 1

    results.append(("startup вызвал set_webhook", bool(captured.get("url"))))
    results.append(("set_webhook передан secret_token",
                    captured.get("kwargs", {}).get("secret_token") == "boot-check-secret"))
    results.append(("webhook url собран из DOMAIN", captured.get("url") == "https://bot-123.bothost.ru/webhook"))

    async with aiohttp.ClientSession() as s:
        async with s.get(base + "/") as r:
            results.append(("health-check GET / -> 200 OK", r.status == 200 and await r.text() == "OK"))

    results.append(("анонимный POST /webhook -> 401",
                    await probe(base + "/webhook", {}) == 401))
    results.append(("POST с чужим секретом -> 401",
                    await probe(base + "/webhook", {"X-Telegram-Bot-Api-Secret-Token": "nope"}) == 401))
    results.append(("POST с верным секретом -> 200",
                    await probe(base + "/webhook", {"X-Telegram-Bot-Api-Secret-Token": "boot-check-secret"}) == 200))

    task.cancel()
    failed = 0
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        failed += 0 if ok else 1
    print(f"\n{len(results) - failed}/{len(results)} пройдено")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
