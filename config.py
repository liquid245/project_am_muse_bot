import os
from dotenv import load_dotenv

load_dotenv()


# Токены
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("BOT_TOKEN_1")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("REPO_NAME", "liquid245/project_am_muse")

# Роли и ID
admin_ids_raw = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_USER_ID", "")
ADMIN_IDS = [int(id_str.strip()) for id_str in admin_ids_raw.split(",") if id_str.strip()]
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "-1003497103344"))
ADMIN_TOPIC_ID = int(os.getenv("ADMIN_TOPIC_ID", "43"))

# Настройки HTTP сервера
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# Идентификаторы Bothost (автоматически инжектятся платформой)
DOMAIN = os.getenv("DOMAIN", "")
BOT_ID = os.getenv("BOT_ID", "")

# Webhook: авто-построение из DOMAIN (Bothost) или из переменной (ручной режим)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")

if not WEBHOOK_URL and DOMAIN:
    WEBHOOK_URL = f"https://{DOMAIN}"

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
# без /bot на конце — TelegramAPIServer.from_base добавляет его
TELEGRAM_API_PROXY = os.getenv(
    "TELEGRAM_API_PROXY",
    "https://api.telegram.org",
)

# Режим отладки
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")
