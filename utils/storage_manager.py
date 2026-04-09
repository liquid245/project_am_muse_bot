import os
import json
import logging
from typing import Dict, List, Tuple
from urllib.parse import quote
from github import Github, GithubException

from config import DEBUG, GITHUB_TOKEN, REPO_NAME, CATALOG_FILE, IMAGES_DIR, SITE_URL

class StorageManager:
    """
    Абстракция для управления хранилищем (локально или на GitHub).
    Реализует стратегию "свежего чтения" (Fresh Read) для предотвращения потери данных.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(StorageManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        # Инициализация происходит только один раз благодаря __new__
        if hasattr(self, 'initialized') and self.initialized:
            return
            
        self.debug = DEBUG
        self.catalog_path = CATALOG_FILE
        self.images_path = IMAGES_DIR
        self.github_client = None
        self.repo = None

        if not self.debug:
            if not GITHUB_TOKEN or not REPO_NAME:
                raise ValueError("GITHUB_TOKEN и REPO_NAME должны быть установлены для работы с GitHub.")
            self.github_client = Github(GITHUB_TOKEN)
            self.repo = self.github_client.get_repo(REPO_NAME)
            logging.info("StorageManager инициализирован в режиме GitHub.")
        else:
            logging.info("StorageManager инициализирован в локальном режиме (DEBUG).")
        
        self.initialized = True

    def _fetch_fresh_catalog(self, command_name: str = "unspecified"):
        """
        Внутренний метод для получения САМОЙ СВЕЖЕЙ версии каталога и его SHA.
        Всегда запрашивает данные напрямую из API GitHub.
        """
        logging.info(
            f"Fetching fresh data from GitHub for command [{command_name}]..."
        )
        if self.debug:
            if not os.path.exists(self.catalog_path):
                return {"items": []}, None
            with open(self.catalog_path, 'r', encoding='utf-8') as f:
                return json.load(f), None
        else:
            try:
                # ref="main" гарантирует получение свежих данных из ветки
                contents = self.repo.get_contents(self.catalog_path, ref="main")
                catalog = json.loads(contents.decoded_content.decode('utf-8'))
                if not isinstance(catalog, dict) or "items" not in catalog:
                    logging.error("Получены поврежденные данные каталога (не словарь или нет 'items')")
                    return {"items": []}, contents.sha
                return catalog, contents.sha
            except GithubException as e:
                if e.status == 404:
                    return {"items": []}, None
                else:
                    logging.error(f"Ошибка GitHub при получении каталога: {e}")
                    raise
            except Exception as e:
                logging.error(f"Непредвиденная ошибка при чтении каталога: {e}")
                raise

    def _ensure_image_sources(self, catalog: dict) -> dict:
        """Гарантирует наличие image_sources для каждого товара."""
        if not isinstance(catalog, dict):
            return catalog
        items = catalog.get("items", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            images = item.get("images", []) or []
            image_sources = item.get("image_sources")
            if not isinstance(image_sources, dict):
                image_sources = {}
            for image_name in images:
                image_sources.setdefault(image_name, {})
            item["image_sources"] = image_sources
        return catalog

    def _collect_missing_images(self, catalog: dict) -> List[Dict[str, str]]:
        """Собирает список отсутствующих файлов согласно каталогу."""
        missing = []
        items = catalog.get("items", []) if isinstance(catalog, dict) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id"))
            title = item.get("title", "")
            image_sources = item.get("image_sources") or {}
            for filename in item.get("images", []) or []:
                full_path = os.path.join(self.images_path, filename)
                if not os.path.exists(full_path):
                    telegram_file_id = None
                    if isinstance(image_sources, dict):
                        telegram_file_id = (
                            image_sources.get(filename, {}) or {}
                        ).get("telegram_file_id")
                    missing.append(
                        {
                            "item_id": item_id,
                            "item_title": title,
                            "filename": filename,
                            "telegram_file_id": telegram_file_id,
                        }
                    )
        return missing

    def _save_fresh_catalog(self, catalog, sha, commit_message):
        """
        Внутренний метод для безопасного сохранения каталога.
        Использует SHA для предотвращения перезаписи параллельных изменений (Optimistic Locking).
        """
        if not isinstance(catalog, dict) or "items" not in catalog:
            logging.error("Попытка сохранить некорректный каталог. Отмена.")
            return False

        catalog = self._ensure_image_sources(catalog)
        new_content_str = json.dumps(catalog, indent=2, ensure_ascii=False)
        
        try:
            if self.debug:
                with open(self.catalog_path, 'w', encoding='utf-8') as f:
                    f.write(new_content_str)
                logging.info(f"Каталог локально обновлен: {self.catalog_path}")
                return True
            else:
                if sha:
                    self.repo.update_file(
                        path=self.catalog_path,
                        message=commit_message,
                        content=new_content_str,
                        sha=sha,
                        branch="main"
                    )
                else:
                    self.repo.create_file(
                        path=self.catalog_path,
                        message=commit_message,
                        content=new_content_str,
                        branch="main"
                    )
                logging.info(f"Каталог успешно закоммичен на GitHub: {commit_message}")
                return True
        except Exception as e:
            logging.error(f"Ошибка при сохранении каталога на GitHub: {e}")
            raise

    def get_catalog_snapshot(self, command_name: str = "get_catalog_snapshot") -> Tuple[dict, str]:
        """Возвращает свежий каталог и его SHA с логированием команды."""
        return self._fetch_fresh_catalog(command_name)

    def audit_missing_images(self) -> Tuple[dict, str, List[Dict[str, str]]]:
        """Возвращает свежий каталог, его SHA и список отсутствующих изображений."""
        catalog, sha = self._fetch_fresh_catalog("audit_missing_images")
        catalog = self._ensure_image_sources(catalog)
        missing = self._collect_missing_images(catalog)
        return catalog, sha, missing

    def save_catalog_snapshot(self, catalog: dict, sha: str, commit_message: str):
        """Публичный метод для сохранения целого каталога после правок."""
        return self._save_fresh_catalog(catalog, sha, commit_message)

    def save_catalog(self, catalog: dict, sha: str, commit_message: str):
        """Сохраняет переданный каталог с заданным SHA."""
        return self._save_fresh_catalog(catalog, sha, commit_message)

    def save_photo(self, file_bytes: bytes, filename: str) -> str:
        """Сохраняет фото локально (всегда) и в репозиторий GitHub (если не DEBUG)."""
        try:
            # Всегда сохраняем локально, чтобы бот мог сразу отправить файл,
            # не дожидаясь обновления GitHub Pages.
            if not os.path.exists(self.images_path):
                os.makedirs(self.images_path)
            full_path = os.path.join(self.images_path, filename)
            with open(full_path, 'wb') as f:
                f.write(file_bytes)
            logging.info(f"Фото локально сохранено: {full_path}")

            if not self.debug:
                github_path = f"{self.images_path}/{filename}"
                self.repo.create_file(
                    path=github_path,
                    message=f"Bot Upload: add image {filename}",
                    content=file_bytes,
                    branch="main"
                )
                logging.info(f"Фото загружено на GitHub: {github_path}")
            return filename
        except Exception as e:
            logging.error(f"Ошибка при сохранении фото '{filename}': {e}")
            raise

    def delete_photo(self, filename: str, manual: bool = False):
        """Полностью отключенное удаление (защита от автоматического клинапа)."""
        logging.warning(
            "Удаление изображения %s отклонено. Data Safety Mode активен.", filename
        )
        if manual:
            logging.warning(
                "Даже ручной запрос на удаление %s не выполняется программно.", filename
            )

    def get_catalog(self):
        """Публичный метод для получения текущего каталога."""
        catalog, _ = self._fetch_fresh_catalog("get_catalog")
        return catalog

    def get_photo_source(self, filename: str, item_id: str = "Unknown"):
        """Возвращает прямую ссылку на изображение из GitHub Pages или raw."""
        encoded_name = quote(filename)
        base_site = (SITE_URL or "").rstrip("/")
        if base_site:
            return f"{base_site}/catalog/images/{encoded_name}"

        repo = (REPO_NAME or "").strip()
        if repo:
            return (
                f"https://raw.githubusercontent.com/{repo}/main/{IMAGES_DIR}/{encoded_name}"
            )

        logging.warning(
            "Не удалось сформировать ссылку на изображение %s (item %s): "
            "SITE_URL и REPO_NAME не заданы.",
            filename,
            item_id,
        )
        return None

    def update_catalog(self, item_data: dict):
        """
        АТОМАРНОЕ ОБНОВЛЕНИЕ ИЛИ ДОБАВЛЕНИЕ ТОВАРА.
        Всегда запрашивает свежие данные перед изменением.
        """
        try:
            item_id = item_data.get('id')
            catalog, sha = self._fetch_fresh_catalog(f"update_catalog:{item_id}")
            items = catalog.get("items", [])
            initial_count = len(items)
            
            logging.info(f"Свежее чтение: получено {initial_count} товаров.")

            updated = False
            for i, item in enumerate(items):
                if item.get('id') == item_id:
                    items[i] = item_data
                    updated = True
                    break
            
            if not updated:
                items.insert(0, item_data)
                logging.info(f"Добавление НОВОГО товара {item_id}. Итого: {len(items)}")
            else:
                logging.info(f"Обновление существующего товара {item_id}.")

            catalog["items"] = items
            return self._save_fresh_catalog(catalog, sha, f"Bot Update: update/add item {item_id}")
            
        except Exception as e:
            logging.error(f"Критическая ошибка при update_catalog: {e}")
            raise

    def delete_item(self, item_id: str):
        """
        АТОМАРНОЕ УДАЛЕНИЕ ТОВАРА.
        Всегда запрашивает свежие данные перед удалением.
        """
        try:
            catalog, sha = self._fetch_fresh_catalog(f"delete_item:{item_id}")
            items = catalog.get("items", [])
            initial_count = len(items)
            
            new_items = [item for item in items if str(item.get('id')) != str(item_id)]
            
            if len(new_items) < initial_count:
                catalog["items"] = new_items
                logging.info(f"Удаление товара {item_id}. Было {initial_count}, стало {len(new_items)}")
                return self._save_fresh_catalog(catalog, sha, f"Bot Update: delete item {item_id}")
            else:
                logging.warning(f"Товар {item_id} не найден для удаления.")
                return False
        except Exception as e:
            logging.error(f"Ошибка при delete_item: {e}")
            raise

    def reorder_catalog(self, ordered_ids: list, items_to_update: list = None):
        """
        АТОМАРНАЯ ПЕРЕСОРТИРОВКА И ОБНОВЛЕНИЕ.
        Берет список ID в нужном порядке и перестраивает СВЕЖИЙ каталог.
        Если передан items_to_update, сначала обновляет данные этих товаров.
        Новые товары, которых нет в ordered_ids, сохраняются в начале.
        """
        try:
            catalog, sha = self._fetch_fresh_catalog("reorder_catalog")
            fresh_items = catalog.get("items", [])
            
            # Создаем словарь для быстрого доступа
            item_map = {str(item['id']): item for item in fresh_items}
            
            # Обновляем данные товаров, если переданы изменения
            if items_to_update:
                for item in items_to_update:
                    item_id_str = str(item.get('id'))
                    item_map[item_id_str] = item
                    logging.info(f"Подготовка к обновлению данных товара {item_id_str} при пересортировке.")

            new_ordered_items = []
            
            # 1. Сначала добавляем те, что в ordered_ids (в указанном порядке)
            seen_ids = set()
            for oid in ordered_ids:
                oid_str = str(oid)
                if oid_str in item_map:
                    new_ordered_items.append(item_map[oid_str])
                    seen_ids.add(oid_str)
            
            # 2. Добавляем те, что есть в fresh_items, но НЕ были в ordered_ids
            # (например, добавленные кем-то другим во время редактирования)
            extras = [item for item in fresh_items if str(item['id']) not in seen_ids]
            if extras:
                logging.info(f"Обнаружено {len(extras)} новых товаров при пересортировке. Сохраняем их в начале.")
                new_ordered_items = extras + new_ordered_items
            
            catalog["items"] = new_ordered_items
            logging.info(f"Каталог пересортирован и обновлен. Итого товаров: {len(new_ordered_items)}")
            
            return self._save_fresh_catalog(catalog, sha, "Bot Update: full catalog reorder/update")
        except Exception as e:
            logging.error(f"Ошибка при reorder_catalog: {e}")
            raise
