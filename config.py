import os
import platform
import subprocess
from dotenv import load_dotenv

load_dotenv()


def _keychain_get(label: str) -> str | None:
    """Читает пароль из macOS Keychain по метке."""
    if platform.system() != "Darwin":
        return None
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-w", "-l", label],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _get_secret(env_name: str, keychain_label: str) -> str | None:
    """Сначала os.getenv, затем Keychain (macOS)."""
    val = os.getenv(env_name)
    if val:
        return val
    return _keychain_get(keychain_label)


# Токены
BOT_TOKEN = _get_secret("BOT_TOKEN", "telegram-bot-api-token-am-muse")
GITHUB_TOKEN = _get_secret("GITHUB_TOKEN", "github-general-api-token")
REPO_NAME = os.getenv("REPO_NAME", "liquid245/project_am_muse")

# Роли и ID
admin_ids_raw = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_USER_ID", "")
ADMIN_IDS = [int(id_str.strip()) for id_str in admin_ids_raw.split(",") if id_str.strip()]
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "-1003497103344"))
ADMIN_TOPIC_ID = int(os.getenv("ADMIN_TOPIC_ID", "43"))

# Настройки Health Check сервера для Hugging Face
HEALTH_CHECK_HOST = os.getenv("HOST", "0.0.0.0")
HEALTH_CHECK_PORT = int(os.getenv("PORT", "7860"))

# Константы путей
CATALOG_FILE = "docs/catalog/catalog.json"
IMAGES_DIR = "docs/catalog/images"

# Ссылка на сайт
SITE_URL = os.getenv("SITE_ADRESS", "https://am-muse.ru")
MASTER_USERNAME = os.getenv("MASTER_USERNAME", "baegon")
BOT_USERNAME = os.getenv("BOT_USERNAME", "project_am_muse_bot")

# Реквизиты для оплаты
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "+79000000000")
BANK_NAME = os.getenv("BANK_NAME", "Сбербанк")

# Прокси для Telegram API (Cloudflare Worker)
# without /bot suffix — TelegramAPIServer.from_base adds it
TELEGRAM_API_PROXY = os.getenv(
    "TELEGRAM_API_PROXY",
    "https://calm-resonance-dc0b.liquid245.workers.dev",
)

# Режим отладки
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")
