"""CLI-инструмент для аудита и восстановления изображений каталога."""

import argparse
import asyncio
import io
import logging
import os
from datetime import datetime, timezone
from typing import List

from aiogram import Bot
from dotenv import load_dotenv

from utils.storage_manager import StorageManager
from config import BOT_TOKEN


load_dotenv()


def format_missing_report(missing: List[dict]) -> str:
    lines = []
    for entry in missing:
        lines.append(
            f"- ID {entry['item_id']} · {entry['filename']}"
            f"{' (нет telegram_file_id)' if not entry.get('telegram_file_id') else ''}"
        )
    return "\n".join(lines)


def audit_catalog_images():
    """Печатает отчет об отсутствующих изображениях."""
    storage_manager = StorageManager()
    _, _, missing = storage_manager.audit_missing_images()

    print("📦 Catalog image audit")
    print(f"- Total missing: {len(missing)}")
    if missing:
        print("- Broken entries:")
        print(format_missing_report(missing))
    else:
        print("- Все изображения присутствуют.")


async def restore_missing_images():
    """Пытается восстановить отсутствующие изображения посредством Telegram file_id."""
    storage_manager = StorageManager()
    catalog, sha, missing = storage_manager.audit_missing_images()

    if not missing:
        print("✅ Все изображения присутствуют. Восстановление не требуется.")
        return

    token = BOT_TOKEN or os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN обязателен для восстановления изображений.")

    bot = Bot(token=token)
    restored = 0
    skipped = []

    try:
        for entry in missing:
            file_id = entry.get("telegram_file_id")
            if not file_id:
                skipped.append(entry)
                logging.warning(
                    "Пропуск восстановления %s (item %s): нет telegram_file_id.",
                    entry["filename"],
                    entry["item_id"],
                )
                continue

            file_info = await bot.get_file(file_id)
            buffer = io.BytesIO()
            await bot.download_file(file_info.file_path, destination=buffer)
            buffer.seek(0)

            storage_manager.save_photo(buffer.getvalue(), entry["filename"])

            # Обновляем метаданные каталога
            item = next(
                (i for i in catalog.get("items", []) if str(i.get("id")) == entry["item_id"]),
                None,
            )
            if item is not None:
                image_sources = item.get("image_sources") or {}
                meta = image_sources.get(entry["filename"], {})
                meta["telegram_file_id"] = file_id
                meta["restored_at"] = datetime.now(timezone.utc).isoformat()
                image_sources[entry["filename"]] = meta
                item["image_sources"] = image_sources

            restored += 1

        if restored:
            storage_manager.save_catalog_snapshot(
                catalog,
                sha,
                "Maintenance: restore missing images",
            )
            print(f"✅ Восстановлено файлов: {restored}")
        else:
            print("⚠️ Не удалось восстановить ни одного файла. См. логи выше.")

        if skipped:
            print("Следующие изображения требуют ручного file_id:")
            print(format_missing_report(skipped))
    finally:
        await bot.session.close()


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Catalog image guard")
    parser.add_argument(
        "command",
        choices=("audit", "restore"),
        help="audit — только проверка, restore — попытка восстановления",
    )
    args = parser.parse_args()

    if args.command == "audit":
        audit_catalog_images()
    else:
        asyncio.run(restore_missing_images())


if __name__ == "__main__":
    main()
