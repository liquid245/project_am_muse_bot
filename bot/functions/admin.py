import datetime
import logging
import os
import uuid

from aiogram import types, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.functions.utils import lock
from utils.storage_manager import StorageManager

admin_router = Router()

ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")


class Form(StatesGroup):
    title = State()
    description = State()
    price = State()
    stock = State()
    waiting_for_images = State()
    process_images = State()


class EditForm(StatesGroup):
    field = State()
    value = State()
    waiting_for_images = State()
    process_images = State()


def get_cancel_keyboard():
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="Прервать добавление товара", callback_data="cancel_add_item"
                )
            ]
        ]
    )
    return keyboard


def get_save_and_cancel_keyboard():
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="Сохранить", callback_data="save_item")],
            [
                types.InlineKeyboardButton(
                    text="Прервать добавление товара", callback_data="cancel_add_item"
                )
            ],
        ]
    )
    return keyboard


def _load_catalog_context(command_name: str):
    """Возвращает StorageManager, свежий каталог и SHA для указанной команды."""
    storage_manager = StorageManager()
    try:
        catalog_data, sha = storage_manager.get_catalog_snapshot(
            f"admin:{command_name}"
        )
        return storage_manager, catalog_data, sha
    except Exception as exc:
        logging.error(
            "Ошибка получения каталога для команды %s: %s", command_name, exc,
            exc_info=True
        )
        return storage_manager, None, None


@admin_router.callback_query(lambda c: c.data == "cancel_add_item")
async def cancel_add_item(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.answer(
        "Добавление товара прервано.", reply_markup=types.ReplyKeyboardRemove()
    )
    await callback_query.answer()


@admin_router.message(lambda message: message.text == "Добавить товар")
async def add_item(message: types.Message, state: FSMContext):
    await state.set_state(Form.title)
    await message.answer("Введите название товара:")


@admin_router.message(Form.title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(Form.description)
    await message.answer("Введите описание товара:", reply_markup=get_cancel_keyboard())


@admin_router.message(Form.description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(Form.price)
    await message.answer("Введите цену товара:", reply_markup=get_cancel_keyboard())


@admin_router.message(Form.price)
async def process_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число.")
        return
    await state.update_data(price=int(message.text))
    await state.set_state(Form.stock)
    await message.answer(
        "Введите количество товара на складе:", reply_markup=get_cancel_keyboard()
    )


@admin_router.message(Form.stock)
async def process_stock(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число.")
        return
    await state.update_data(stock=int(message.text), temp_image_file_ids=[])
    await state.set_state(Form.waiting_for_images)
    await message.answer(
        "Отправьте одно или несколько изображений для товара...",
        reply_markup=get_cancel_keyboard(),
    )


@admin_router.message(Form.waiting_for_images)
async def process_waiting_for_images(message: types.Message, state: FSMContext):
    if message.photo:
        file_id = message.photo[-1].file_id
        async with lock:
            data = await state.get_data()
            image_file_ids = data.get("temp_image_file_ids", [])
            image_file_ids.append(file_id)
            await state.update_data(temp_image_file_ids=image_file_ids)
            await message.answer(
                "Изображение получено.", reply_markup=get_save_and_cancel_keyboard()
            )
    else:
        await message.answer(
            "Пожалуйста, отправьте изображение.",
            reply_markup=get_save_and_cancel_keyboard(),
        )


@admin_router.callback_query(lambda c: c.data == "save_item", Form.waiting_for_images)
async def save_item_callback(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("temp_image_file_ids"):
        await callback_query.answer(
            "Пожалуйста, сначала отправьте хотя бы одно изображение.", show_alert=True
        )
        return
    await state.set_state(Form.process_images)
    await process_new_item(callback_query.message, state)
    await callback_query.answer()


async def process_new_item(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    images_dir = "docs/catalog/images"
    os.makedirs(images_dir, exist_ok=True)

    saved_image_names = []
    for file_id in data["temp_image_file_ids"]:
        try:
            file_info = await message.bot.get_file(file_id)
            downloaded_file_path = file_info.file_path

            unique_filename = f"{uuid.uuid4().hex}.jpeg"
            destination_path = os.path.join(images_dir, unique_filename)

            await message.bot.download_file(downloaded_file_path, destination_path)
            saved_image_names.append(unique_filename)
            logging.info(f"Image saved to {destination_path}")
        except Exception as e:
            logging.error(f"Error saving image {file_id}: {e}")
            await message.answer(f"Ошибка при сохранении изображения: {e}")

    storage_manager, catalog_data, sha = _load_catalog_context("add_item")
    if catalog_data is None:
        await message.answer("Ошибка получения каталога.")
        return

    items = catalog_data.get("items", [])
    new_id_num = len(items) + 1
    new_id = f"brooch-{new_id_num:04d}"

    today = datetime.date.today().isoformat()

    new_item = {
        "id": new_id,
        "title": data["title"],
        "description": data["description"],
        "price": data["price"],
        "stock": data["stock"],
        "status": "available",
        "created_at": today,
        "updated_at": today,
        "images": saved_image_names,
    }

    items.append(new_item)
    catalog_data["items"] = items

    try:
        save_ok = storage_manager.save_catalog_snapshot(
            catalog_data, sha, f"Bot Update: add item {new_id}"
        )
    except Exception as exc:
        logging.error("Ошибка при сохранении товара в GitHub: %s", exc, exc_info=True)
        await message.answer("❌ Ошибка синхронизации с GitHub. Товар НЕ добавлен.")
        return

    if save_ok:
        await message.answer("Товар добавлен!")
    else:
        await message.answer("Ошибка добавления товара.")


@admin_router.message(lambda message: message.text == "Список товаров")
async def list_items(message: types.Message):
    _, catalog_data, _ = _load_catalog_context("list_items")
    if catalog_data is None:
        await message.answer("Ошибка получения каталога.")
        return

    items = catalog_data.get("items", [])
    if not items:
        await message.answer("Каталог пуст.")
        return

    for item in items:
        text = f"{item['title']} - {item['price']} руб."
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="Edit", callback_data=f"edit_{item['id']}"
                    ),
                    types.InlineKeyboardButton(
                        text="Delete", callback_data=f"delete_{item['id']}"
                    ),
                ]
            ]
        )
        await message.answer(text, reply_markup=keyboard)


@admin_router.message(lambda message: message.text == "Активные заказы")
async def active_orders(message: types.Message):
    await message.answer(
        "Заказы не хранятся в боте. Все заказы отправляются менеджеру напрямую."
    )


@admin_router.callback_query(lambda c: c.data and c.data.startswith("edit_"))
async def process_edit(callback_query: types.CallbackQuery, state: FSMContext):
    item_id = callback_query.data.split("_")[1]
    await state.update_data(item_id=item_id)

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="Название", callback_data="edit_field_title"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="Описание", callback_data="edit_field_description"
                )
            ],
            [types.InlineKeyboardButton(text="Цена", callback_data="edit_field_price")],
            [
                types.InlineKeyboardButton(
                    text="Количество", callback_data="edit_field_stock"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="Изображения", callback_data="edit_field_images"
                )
            ],
        ]
    )
    await callback_query.message.answer(
        "Какое поле вы хотите отредактировать?", reply_markup=keyboard
    )
    await state.set_state(EditForm.field)
    await callback_query.answer()


@admin_router.callback_query(EditForm.field)
async def process_edit_field(callback_query: types.CallbackQuery, state: FSMContext):
    field = callback_query.data.split("_")[2]
    await state.update_data(field=field)

    if field == "images":
        await state.update_data(temp_image_file_ids=[])
        await state.set_state(EditForm.waiting_for_images)
        await callback_query.message.answer(
            "Отправьте одно или несколько новых изображений для товара.",
            reply_markup=get_cancel_keyboard(),
        )
    else:
        await callback_query.message.answer(
            f"Введите новое значение для поля '{field}':"
        )
        await state.set_state(EditForm.value)

    await callback_query.answer()


@admin_router.message(EditForm.value)
async def process_edit_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data["item_id"]
    field = data["field"]
    new_value = message.text

    if field in ["price", "stock"]:
        if not new_value.isdigit():
            await message.answer("Пожалуйста, введите число.")
            return
        new_value = int(new_value)

    storage_manager, catalog_data, sha = _load_catalog_context("edit_field")
    if catalog_data is None:
        await message.answer("Ошибка получения каталога.")
        await state.clear()
        return

    updated = False
    for item in catalog_data.get("items", []):
        if item["id"] == item_id:
            item[field] = new_value
            updated = True
            break

    if not updated:
        await message.answer("Товар не найден.")
        await state.clear()
        return

    try:
        save_ok = storage_manager.save_catalog_snapshot(
            catalog_data, sha, f"Bot Update: edit item {item_id}"
        )
    except Exception as exc:
        logging.error(
            "Ошибка синхронизации при обновлении товара %s: %s", item_id, exc,
            exc_info=True
        )
        await message.answer(
            "❌ Ошибка синхронизации с GitHub. Изменения не сохранены."
        )
        await state.clear()
        return

    if save_ok:
        await message.answer("Товар обновлен!")
    else:
        await message.answer("Ошибка обновления товара.")

    await state.clear()


@admin_router.message(EditForm.waiting_for_images)
async def process_edit_waiting_for_images(message: types.Message, state: FSMContext):
    if message.photo:
        file_id = message.photo[-1].file_id
        async with lock:
            data = await state.get_data()
            image_file_ids = data.get("temp_image_file_ids", [])
            image_file_ids.append(file_id)
            await state.update_data(temp_image_file_ids=image_file_ids)
            await message.answer(
                "Изображение получено.", reply_markup=get_save_and_cancel_keyboard()
            )
    else:
        await message.answer(
            "Пожалуйста, отправьте изображение.",
            reply_markup=get_save_and_cancel_keyboard(),
        )


@admin_router.callback_query(
    lambda c: c.data == "save_item", EditForm.waiting_for_images
)
async def save_edited_item_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    data = await state.get_data()
    if not data.get("temp_image_file_ids"):
        await callback_query.answer(
            "Пожалуйста, сначала отправьте хотя бы одно изображение.", show_alert=True
        )
        return
    await state.set_state(EditForm.process_images)
    await process_edited_item_images(callback_query.message, state)
    await callback_query.answer()


async def process_edited_item_images(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data["item_id"]

    images_dir = "docs/catalog/images"
    os.makedirs(images_dir, exist_ok=True)

    saved_image_names = []
    for file_id in data["temp_image_file_ids"]:
        try:
            file_info = await message.bot.get_file(file_id)
            downloaded_file_path = file_info.file_path

            unique_filename = f"{uuid.uuid4().hex}.jpeg"
            destination_path = os.path.join(images_dir, unique_filename)

            await message.bot.download_file(downloaded_file_path, destination_path)
            saved_image_names.append(unique_filename)
            logging.info(f"Image saved to {destination_path}")
        except Exception as e:
            logging.error(f"Error saving image {file_id}: {e}")
            await message.answer(f"Ошибка при сохранении изображения: {e}")

    storage_manager, catalog_data, sha = _load_catalog_context("edit_images")
    if catalog_data is None:
        await message.answer("Ошибка получения каталога.")
        await state.clear()
        return

    updated = False
    for item in catalog_data.get("items", []):
        if item["id"] == item_id:
            item["images"] = saved_image_names
            updated = True
            break

    if not updated:
        await message.answer("Товар не найден.")
        await state.clear()
        return

    try:
        save_ok = storage_manager.save_catalog_snapshot(
            catalog_data, sha, f"Bot Update: edit images {item_id}"
        )
    except Exception as exc:
        logging.error(
            "Ошибка синхронизации при обновлении фотографий %s: %s", item_id, exc,
            exc_info=True
        )
        await message.answer(
            "❌ Ошибка синхронизации с GitHub. Изображения не обновлены."
        )
        await state.clear()
        return

    if save_ok:
        await message.answer("Изображения товара обновлены!")
    else:
        await message.answer("Ошибка обновления товара.")

    await state.clear()


@admin_router.callback_query(lambda c: c.data and c.data.startswith("delete_"))
async def request_delete_confirmation(callback_query: types.CallbackQuery):
    item_id = callback_query.data.split("_")[1]

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="Да, удалить", callback_data=f"confirm_delete_{item_id}"
                ),
                types.InlineKeyboardButton(
                    text="Нет, отмена", callback_data="cancel_delete"
                ),
            ]
        ]
    )
    await callback_query.message.answer(
        f"Вы уверены, что хотите удалить товар с ID: {item_id}?", reply_markup=keyboard
    )
    await callback_query.answer()


@admin_router.callback_query(lambda c: c.data and c.data.startswith("confirm_delete_"))
async def confirm_delete(callback_query: types.CallbackQuery):
    item_id = callback_query.data.split("_")[2]

    storage_manager, catalog_data, sha = _load_catalog_context("delete_item")
    if catalog_data is None:
        await callback_query.message.answer("Ошибка получения каталога.")
        await callback_query.answer()
        return

    items = catalog_data.get("items", [])
    new_items = [item for item in items if item["id"] != item_id]

    if len(new_items) == len(items):
        await callback_query.message.answer("Товар не найден.")
        await callback_query.answer()
        return

    catalog_data["items"] = new_items

    try:
        save_ok = storage_manager.save_catalog_snapshot(
            catalog_data, sha, f"Bot Update: delete item {item_id}"
        )
    except Exception as exc:
        logging.error(
            "Ошибка синхронизации при удалении товара %s: %s", item_id, exc,
            exc_info=True
        )
        await callback_query.message.answer(
            "❌ Ошибка синхронизации с GitHub. Товар НЕ удален."
        )
        await callback_query.answer()
        return

    if save_ok:
        await callback_query.message.answer(f"Товар с ID: {item_id} удален.")
    else:
        await callback_query.message.answer(
            "❌ Ошибка синхронизации с GitHub. Товар НЕ удален."
        )

    await callback_query.answer()


@admin_router.callback_query(lambda c: c.data and c.data == "cancel_delete")
async def cancel_delete(callback_query: types.CallbackQuery):
    await callback_query.message.answer("Удаление отменено.")
    await callback_query.answer()
