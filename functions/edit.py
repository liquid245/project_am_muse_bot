import logging
import io
import time
from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from filters.roles import IsAdmin
from utils.storage_manager import StorageManager
from functions.items import send_item_card

edit_router = Router()

class ItemEditForm(StatesGroup):
    main_menu = State()
    waiting_for_replacement = State()
    waiting_for_new_images = State()
    waiting_for_order = State()
    confirm_delete = State()

async def start_delete_item_scenario(message: types.Message, state: FSMContext, edit_mode=False):
    """Начало сценария удаления товара."""
    data = await state.get_data()
    item = data.get("temp_item")
    
    text = f"⚠️ Вы уверены, что хотите удалить товар '<b>{item.get('title')}</b>'? Это действие необратимо."
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data="delete_item_confirm")
    kb.button(text="❌ Отмена (назад)", callback_data="delete_item_cancel")
    kb.adjust(1)
    
    if edit_mode:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
        
    await state.set_state(ItemEditForm.confirm_delete)

@edit_router.callback_query(ItemEditForm.main_menu, F.data == "delete_item_start")
async def process_delete_item_start_callback(callback: types.CallbackQuery, state: FSMContext):
    await start_delete_item_scenario(callback.message, state, edit_mode=True)
    await callback.answer()

@edit_router.callback_query(ItemEditForm.confirm_delete, F.data == "delete_item_confirm")
async def process_delete_item_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    item = data.get("temp_item")
    item_id = item.get("id")
    
    storage_manager = StorageManager()
    try:
        # Удаляем только запись товара. Файлы остаются для безопасности.
        if storage_manager.delete_item(item_id):
            await callback.message.answer(f"🗑️ Товар успешно удален.")
        else:
            await callback.message.answer("❌ Товар не найден.")
            
    except Exception as e:
        logging.error(f"Ошибка при удалении товара: {e}")
        await callback.message.answer("❌ Ошибка при удалении товара.")
    
    await state.clear()
    await callback.answer()

@edit_router.callback_query(ItemEditForm.confirm_delete, F.data == "delete_item_cancel")
async def process_delete_item_cancel(callback: types.CallbackQuery, state: FSMContext):
    await show_edit_menu(callback.message, state, edit_mode=True)
    await callback.answer()

async def show_edit_menu(message: types.Message, state: FSMContext, edit_mode=False):
    """
    Отображает меню редактирования текущего товара.
    """
    data = await state.get_data()
    item = data.get("temp_item")
    items_list = data.get("catalog_items", [])
    item_idx = data.get("item_index", -1)
    
    text = (
        f"📝 <b>Редактирование товара</b>\n\n"
        f"<b>Название:</b> {item.get('title')}\n"
        f"<b>Описание:</b> {item.get('description')}\n"
        f"<b>Цена:</b> {item.get('price')} руб.\n"
        f"<b>Наличие:</b> {item.get('stock')} шт.\n"
        f"<b>Фотографий:</b> {len(item.get('images', []))}\n"
        f"<b>Позиция в каталоге:</b> {item_idx + 1 if item_idx != -1 else 'N/A'}\n"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="Название", callback_data="edit_prop_title")
    kb.button(text="Описание", callback_data="edit_prop_description")
    kb.button(text="Цена", callback_data="edit_prop_price")
    kb.button(text="Наличие", callback_data="edit_prop_stock")
    kb.button(text="🖼️ Изменить фотографии", callback_data="edit_prop_images")
    kb.button(text="↕️ Порядок в списке", callback_data="reorder_item")
    
    kb.button(text="✅ Сохранить изменения", callback_data="edit_save")
    kb.button(text="❌ Отмена", callback_data="edit_cancel")
    kb.button(text="🗑️ Удалить товар", callback_data="delete_item_start")
    kb.adjust(2)
    
    if edit_mode:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    
    await state.set_state(ItemEditForm.main_menu)

async def show_reorder_menu(message: types.Message, state: FSMContext, edit_mode=False):
    """Отображает меню для изменения порядка товара."""
    data = await state.get_data()
    items_list = data.get("catalog_items", [])
    item_idx = data.get("item_index", -1)
    temp_item = data.get("temp_item")

    text = (
        f"↕️ <b>Изменение порядка в каталоге</b>\n\n"
        f"Товар: <b>{temp_item.get('title')}</b>\n"
        f"Текущая позиция: <b>{item_idx + 1}</b> из {len(items_list)}\n\n"
        f"Используйте кнопки ниже для перемещения товара выше или ниже в списке."
    )

    kb = InlineKeyboardBuilder()
    if item_idx > 0:
        kb.button(text="⬆️ Выше", callback_data="edit_move_up")
    if item_idx < len(items_list) - 1:
        kb.button(text="⬇️ Ниже", callback_data="edit_move_down")
    
    kb.button(text="🔙 Назад в меню", callback_data="reorder_back")
    kb.adjust(2)

    if edit_mode:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    
    await state.set_state(ItemEditForm.waiting_for_order)

@edit_router.callback_query(F.data == "reorder_item")
async def process_reorder_start(callback: types.CallbackQuery, state: FSMContext):
    await show_reorder_menu(callback.message, state, edit_mode=True)
    await callback.answer()

@edit_router.callback_query(ItemEditForm.waiting_for_order, F.data == "edit_move_up")
async def process_move_up_in_order(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items = data.get("catalog_items", [])
    i = data.get("item_index", -1)

    if i > 0:
        items[i], items[i-1] = items[i-1], items[i]
        await state.update_data(catalog_items=items, item_index=i-1)
        await show_reorder_menu(callback.message, state, edit_mode=True)
    await callback.answer()

@edit_router.callback_query(ItemEditForm.waiting_for_order, F.data == "edit_move_down")
async def process_move_down_in_order(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items = data.get("catalog_items", [])
    i = data.get("item_index", -1)

    if i != -1 and i < len(items) - 1:
        items[i], items[i+1] = items[i+1], items[i]
        await state.update_data(catalog_items=items, item_index=i+1)
        await show_reorder_menu(callback.message, state, edit_mode=True)
    await callback.answer()

@edit_router.callback_query(ItemEditForm.waiting_for_order, F.data == "reorder_back")
async def process_reorder_back(callback: types.CallbackQuery, state: FSMContext):
    await show_edit_menu(callback.message, state, edit_mode=True)
    await callback.answer()

@edit_router.callback_query(ItemEditForm.main_menu, F.data == "edit_prop_images")
async def process_edit_images_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📎 Пришлите одну или несколько новых фотографий для товара (альбомом).")
    await state.set_state(ItemEditForm.waiting_for_new_images)
    await callback.answer()

@edit_router.message(ItemEditForm.waiting_for_new_images, F.photo)
async def process_new_photos(message: types.Message, state: FSMContext, album: list[types.Message] = None):
    """Заменяет старые фото новыми."""
    data = await state.get_data()
    temp_item = data.get("temp_item")
    storage_manager = StorageManager()
    
    messages = album if album else [message]
    
    status_msg = await message.answer(f"⏳ Загружаю {len(messages)} фотографии...")
    
    new_image_filenames = []
    new_image_sources = {}
    try:
        # 1. Загружаем новые фото
        for idx, m in enumerate(messages):
            photo = m.photo[-1]
            file_ext = 'jpeg'
            file_name = f"photo_{int(time.time() * 1000)}_{idx}.{file_ext}"

            in_memory_file = io.BytesIO()
            await message.bot.download(photo, destination=in_memory_file)
            in_memory_file.seek(0)
            
            filename = storage_manager.save_photo(in_memory_file.read(), file_name)
            new_image_filenames.append(filename)
            meta = {}
            if photo.file_id:
                meta["telegram_file_id"] = photo.file_id
            new_image_sources[filename] = meta

        # 2. Обновляем данные товара (старые фото остаются в хранилище для безопасности)
        temp_item["images"] = new_image_filenames
        temp_item["image_sources"] = new_image_sources
        await state.update_data(temp_item=temp_item)
        
        await status_msg.edit_text("✅ Фотографии обновлены.")
        await show_edit_menu(message, state)
        
    except Exception as e:
        logging.error(f"Ошибка при обновлении фотографий: {e}")
        await status_msg.edit_text("❌ Ошибка при загрузке фотографий.")
        await show_edit_menu(message, state)

async def init_item_edit_state(item_id: str, state: FSMContext):
    """Вспомогательная функция для инициализации состояния редактирования товара."""
    storage_manager = StorageManager()
    catalog = storage_manager.get_catalog()
    
    items_list = catalog.get("items", [])
    item_idx = next((i for i, item in enumerate(items_list) if str(item["id"]) == item_id), -1)
    
    if item_idx == -1:
        return None, None, None
    
    item = items_list[item_idx]
    
    # Сохраняем копию товара для редактирования, весь список для сортировки и текущий индекс
    await state.update_data(
        temp_item=item.copy(),
        catalog_items=items_list,
        item_index=item_idx
    )
    return item, items_list, item_idx

@edit_router.callback_query(F.data.startswith("edit_init_"), IsAdmin())
async def process_edit_init(callback: types.CallbackQuery, state: FSMContext):
    item_id = callback.data.replace("edit_init_", "")
    item, _, _ = await init_item_edit_state(item_id, state)

    if not item:
        return await callback.answer("Товар не найден.", show_alert=True)

    await show_edit_menu(callback.message, state)
    await callback.answer()


@edit_router.message(IsAdmin(), F.text.startswith("/edit_"))
async def process_edit_command(message: types.Message, state: FSMContext):
    item_id = message.text.replace("/edit_", "", 1).strip()
    if not item_id:
        return await message.answer(
            "Пожалуйста, укажите идентификатор товара после команды."
        )

    await state.clear()
    item, _, _ = await init_item_edit_state(item_id, state)

    if not item:
        return await message.answer("Товар не найден или уже удален.")

    await show_edit_menu(message, state)

@edit_router.callback_query(F.data.startswith("reorder_init_"), IsAdmin())
async def process_reorder_init(callback: types.CallbackQuery, state: FSMContext):
    item_id = callback.data.replace("reorder_init_", "")
    item, _, _ = await init_item_edit_state(item_id, state)
    
    if not item:
        return await callback.answer("Товар не найден.", show_alert=True)
    
    await show_reorder_menu(callback, state)
    await callback.answer()

@edit_router.callback_query(F.data.startswith("delete_init_"), IsAdmin())
async def process_delete_init(callback: types.CallbackQuery, state: FSMContext):
    item_id = callback.data.replace("delete_init_", "")
    item, _, _ = await init_item_edit_state(item_id, state)
    
    if not item:
        return await callback.answer("Товар не найден.", show_alert=True)
    
    await start_delete_item_scenario(callback.message, state, edit_mode=False)
    await callback.answer()

@edit_router.message(F.text == "📝 Список товаров", IsAdmin())
async def edit_list_start(message: types.Message):
    """Выбор товара для редактирования из последних 10."""
    storage_manager = StorageManager()
    catalog = storage_manager.get_catalog()
    
    if not catalog["items"]:
        return await message.answer("Каталог пуст.")
    
    for item in catalog["items"][:10]:
        await send_item_card(message, item, is_admin=True)

@edit_router.callback_query(ItemEditForm.main_menu, F.data.startswith("edit_prop_"))
async def process_edit_prop(callback: types.CallbackQuery, state: FSMContext):
    prop = callback.data.replace("edit_prop_", "")
    await state.update_data(current_prop=prop)
    
    prop_names = {
        "title": "Название",
        "description": "Описание",
        "price": "Цена",
        "stock": "Наличие"
    }
    
    await callback.message.answer(f"Введите новое значение для <b>{prop_names.get(prop, prop)}</b>:", parse_mode="HTML")
    await state.set_state(ItemEditForm.waiting_for_replacement)
    await callback.answer()

@edit_router.message(ItemEditForm.waiting_for_replacement)
async def process_replacement(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prop = data.get("current_prop")
    temp_item = data.get("temp_item")
    new_value = message.text
    
    if prop in ["price", "stock"]:
        if not new_value.isdigit():
            return await message.answer("Пожалуйста, введите число.")
        new_value = int(new_value)
    
    temp_item[prop] = new_value
    await state.update_data(temp_item=temp_item)
    
    await show_edit_menu(message, state)

@edit_router.callback_query(ItemEditForm.main_menu, F.data == "edit_save")
async def process_edit_save(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    temp_item = data.get("temp_item")
    catalog_items = data.get("catalog_items", [])
    item_idx = data.get("item_index", -1)
    
    try:
        storage_manager = StorageManager()
        
        # Обновляем данные товара в общем списке
        if item_idx != -1:
            # Используем атомарный метод reorder_catalog, передавая обновленные данные товара
            # и желаемый порядок ID. Это предотвращает потерю данных, добавленных другими пользователями.
            ordered_ids = [item['id'] for item in catalog_items]
            storage_manager.reorder_catalog(ordered_ids, items_to_update=[temp_item])
            await callback.message.answer("✅ Изменения и порядок в каталоге успешно сохранены!")
        else:
            # Если индекс почему-то потерян, просто обновляем данные товара
            storage_manager.update_catalog(temp_item)
            await callback.message.answer("✅ Изменения успешно сохранены!")
            
    except Exception as e:
        logging.error(f"Ошибка при сохранении изменений: {e}")
        await callback.message.answer("❌ Произошла ошибка при сохранении изменений.")
    
    await state.clear()
    await callback.answer()

@edit_router.callback_query(ItemEditForm.main_menu, F.data == "edit_cancel")
async def process_edit_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("❌ Редактирование отменено. Изменения не сохранены.")
    await callback.answer()
