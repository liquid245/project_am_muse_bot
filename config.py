import os
from dotenv import load_dotenv

load_dotenv()

# Токены
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("REPO_NAME")

# Роли и ID
admin_ids_raw = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_USER_ID", "")
ADMIN_IDS = [int(id_str.strip()) for id_str in admin_ids_raw.split(",") if id_str.strip()]
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "-1003497103344"))
ADMIN_TOPIC_ID = int(os.getenv("ADMIN_TOPIC_ID", "43"))

# Константы путей
CATALOG_FILE = "docs/catalog/catalog.json"
IMAGES_DIR = "docs/catalog/images"

# Ссылка на сайт
SITE_URL = os.getenv("SITE_ADRESS", "https://liquid245.github.io/project_am_muse/")
MASTER_USERNAME = os.getenv("MASTER_USERNAME", "baegon")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")

# Реквизиты для оплаты
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "+79000000000")
BANK_NAME = os.getenv("BANK_NAME", "Сбербанк")

# Режим отладки
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")
