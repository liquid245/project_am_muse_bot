"""Compatibility shim to keep supporting python bot/bot.py."""

import asyncio
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import main as run_main  # noqa: E402


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")
