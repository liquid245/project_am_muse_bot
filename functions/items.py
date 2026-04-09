import datetime
import io
import logging
import time

import aiohttp

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from filters.roles import IsAdmin
from utils.keyboards import get_cancel_inline, get_save_images_inline
from utils.storage_manager import StorageManager
from config import IMAGES_DIR, MASTER_USERNAME, ADMIN_IDS, BOT_USERNAME
from aiogram.types import InputMediaPhoto

items_router = Router()


class ItemForm(StatesGroup):
    title = State()
    description = State()
    price = State()
    stock = State()
    waiting_for_images = State()
    # temp_photos будет хранить список словарей: [{'filename': str, 'data': BytesIO}, ...]
    temp_photos = State()


@items_router.message(F.text == "➕ Добавить товар", IsAdmin())
async def add_item_start(message: types.Message, state: FSMContext):
    """Начало сценария добавления."""
    await state.set_state(ItemForm.title)
    await state.update_data(temp_photos=[])
    await message.answer("Название товара:", reply_markup=get_cancel_inline())


@items_router.message(ItemForm.title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(ItemForm.description)
    await message.answer("Описание:", reply_markup=get_cancel_inline())


@items_router.message(ItemForm.description)
async def process_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(ItemForm.price)
    await message.answer("Цена (только число):", reply_markup=get_cancel_inline())


@items_router.message(ItemForm.price)
async def process_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Пожалуйста, введите число.")
    await state.update_data(price=int(message.text))
    await state.set_state(ItemForm.stock)
    await message.answer("Количество:", reply_markup=get_cancel_inline())


@items_router.message(ItemForm.stock)
async def process_stock(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Пожалуйста, введите число.")
    await state.update_data(stock=int(message.text))
    await state.set_state(ItemForm.waiting_for_images)
    await message.answer(
        "Отправьте одну или несколько фотографий.\n"
        "Когда закончите, нажмите 'Сохранить'.",
        reply_markup=get_save_images_inline(),
    )


@items_router.message(ItemForm.waiting_for_images, F.photo)
async def process_photos(
    message: types.Message, state: FSMContext, album: list[types.Message] = None
):
    """Скачивает фото в память (BytesIO) и сохраняет в FSM."""
    data = await state.get_data()
    temp_photos = data.get("temp_photos", [])

    messages = album if album else [message]

    # Информируем пользователя
    status_msg = await message.answer(f"⏳ Обработка {len(messages)} фото...")

    for m in messages:
        photo = m.photo[-1]

        # Генерируем уникальное имя файла
        file_ext = "jpeg"
        file_name = f"photo_{int(time.time() * 1000)}_{len(temp_photos)}.{file_ext}"

        # Скачиваем файл в память
        in_memory_file = io.BytesIO()
        await message.bot.download(photo, destination=in_memory_file)
        in_memory_file.seek(0)  # Возвращаем курсор в начало файла

        temp_photos.append(
            {
                "filename": file_name,
                "data": in_memory_file.read(),
                "telegram_file_id": photo.file_id,
            }
        )

    await state.update_data(temp_photos=temp_photos)
    await status_msg.edit_text(
        f"✅ Добавлено ({len(temp_photos)} фото).",
        reply_markup=get_save_images_inline(),
    )


@items_router.callback_query(ItemForm.waiting_for_images, F.data == "save_images")
async def save_item_final(callback: types.CallbackQuery, state: FSMContext):
    """Атомарно сохраняет все данные через StorageManager."""
    data = await state.get_data()
    temp_photos = data.get("temp_photos")

    if not temp_photos:
        return await callback.answer("Нужно хотя бы одно фото!", show_alert=True)

    await callback.message.edit_text("Сохраняю... Это может занять некоторое время.")

    try:
        storage_manager = StorageManager()

        # 1. Сохраняем все фото
        saved_image_filenames = []
        image_sources = {}
        for photo_data in temp_photos:
            filename = storage_manager.save_photo(
                photo_data["data"], photo_data["filename"]
            )
            saved_image_filenames.append(filename)
            telegram_file_id = photo_data.get("telegram_file_id")
            meta = {}
            if telegram_file_id:
                meta["telegram_file_id"] = telegram_file_id
            image_sources[filename] = meta

        # 2. Если все фото сохранены, формируем и сохраняем данные о товаре
        new_id = f"item_{int(time.time())}"
        today = datetime.date.today().isoformat()

        new_item = {
            "id": new_id,
            "title": data["title"],
            "description": data["description"],
            "price": data["price"],
            "stock": data["stock"],
            "status": "available",
            "created_at": today,
            "images": saved_image_filenames,
            "image_sources": image_sources,
        }

        storage_manager.update_catalog(new_item)

        await callback.message.edit_text(
            f"✅ Товар '{data['title']}' успешно добавлен!\n"
            "Товар будет отображаться первым в списке на сайте"
        )

    except Exception as e:
        logging.error(f"Критическая ошибка при сохранении товара: {e}", exc_info=True)
        # Опционально: можно добавить логику удаления уже загруженных фото, если что-то пошло не так
        await callback.message.edit_text(
            "❌ Ошибка при сохранении. Товар не был добавлен. Попробуйте снова."
        )
    finally:
        await state.clear()
        await callback.answer()


def build_action_links(item_id: str, is_admin: bool) -> str:
    actions = []
    if BOT_USERNAME:
        base_url = f"https://t.me/{BOT_USERNAME}"
        actions.append(
            f"🛍️ <a href=\"{base_url}?start=order_{item_id}\">Заказать</a>"
        )
        if is_admin:
            actions.append(
                f"⚙️ <a href=\"{base_url}?start=edit_{item_id}\">Редактировать</a>"
            )
    else:
        actions.append(f"🛍️ Заказать: /order_{item_id}")
        if is_admin:
            actions = [f"⚙️ Редактировать: /edit_{item_id}"]

    if not actions:
        return ""

    return "\n".join(actions)


async def send_item_card(message: types.Message, item: dict, is_admin: bool):
    """Визуальное отображение карточки товара для пользователя."""
    title = item.get("title", "Без названия")
    description = item.get("description", "")
    price = item.get("price", "???")
    stock = item.get("stock", 0)
    
    action_links = build_action_links(str(item.get("id")), is_admin)
    caption = (
        f"🏷 <b>{title}</b>\n\n"
        f"{description}\n\n"
        f"💰 Цена: <code>{price} ₽</code>\n"
        f"📦 В наличии: {stock} шт."
    )
    if action_links:
        caption += f"\n\n<b>Действия:</b>\n{action_links}"
    images = list(item.get("images", []) or [])
    image_sources = dict(item.get("image_sources") or {})
    storage_manager = StorageManager()
    
    item_id = str(item.get("id", "Unknown"))

    def resolve_photo_source(image_name: str):
        meta = image_sources.get(image_name) or {}
        telegram_file_id = meta.get("telegram_file_id")
        if telegram_file_id:
            return telegram_file_id
        return storage_manager.get_photo_source(image_name, item_id=item_id)

    removed_images: list[str] = []
    catalog_data = None
    catalog_sha = None
    catalog_dirty = False
    media: list[InputMediaPhoto] = []
    session: aiohttp.ClientSession | None = None

    async def ensure_url_available(url: str) -> bool:
        nonlocal session
        if session is None:
            timeout = aiohttp.ClientTimeout(total=2)
            session = aiohttp.ClientSession(timeout=timeout)
        try:
            async with session.head(url, allow_redirects=True) as response:
                return response.status == 200
        except Exception as exc:
            logging.warning(f"HEAD check failed for {url}: {exc}")
            return False

    try:
        for img_name in images:
            photo = resolve_photo_source(img_name)
            if isinstance(photo, str) and photo.startswith(("http://", "https://")):
                is_available = await ensure_url_available(photo)
                if not is_available:
                    logging.error(
                        f"Image {photo} is broken, removing from catalog."
                    )
                    removed_images.append(img_name)
                    continue

            if not photo:
                continue

            if not media:
                media.append(
                    InputMediaPhoto(
                        media=photo,
                        caption=caption,
                        parse_mode="HTML"
                    )
                )
            else:
                media.append(InputMediaPhoto(media=photo))

        if removed_images:
            catalog_data, catalog_sha = storage_manager.get_catalog_snapshot(
                "cleanup_missing_images"
            )
            updated_item_entry = None
            items_list = catalog_data.get("items", [])
            for entry in items_list:
                if not isinstance(entry, dict):
                    continue

                entry_images = entry.get("images", []) or []
                filtered_images = [
                    img for img in entry_images if img not in removed_images
                ]
                if len(filtered_images) != len(entry_images):
                    entry["images"] = filtered_images
                    catalog_dirty = True

                entry_sources = entry.get("image_sources") or {}
                removed_any = False
                for removed in removed_images:
                    if removed in entry_sources:
                        entry_sources.pop(removed, None)
                        removed_any = True
                if removed_any:
                    entry["image_sources"] = entry_sources
                    catalog_dirty = True

                if str(entry.get("id")) == item_id:
                    updated_item_entry = entry

            if updated_item_entry:
                item["images"] = updated_item_entry.get("images", [])
                item["image_sources"] = (
                    updated_item_entry.get("image_sources") or {}
                )

        if not media:
            await message.answer(caption, parse_mode="HTML")
        elif len(media) == 1:
            single = media[0]
            await message.answer_photo(
                photo=single.media,
                caption=single.caption,
                parse_mode=single.parse_mode
            )
        else:
            await message.answer_media_group(media=media)
    finally:
        if session:
            await session.close()
        if catalog_dirty and catalog_data is not None:
            storage_manager.save_catalog(
                catalog=catalog_data,
                sha=catalog_sha,
                commit_message=f"Bot Cleanup: remove broken images for {item_id}"
            )
