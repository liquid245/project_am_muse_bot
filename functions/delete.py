from aiogram import types, Router, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from filters.roles import IsAdmin
from utils.storage_manager import StorageManager

delete_router = Router()

@delete_router.message(F.text == "🗑️ Удалить", IsAdmin())
async def delete_list_start(message: types.Message):
    """Выбор товара для удаления из последних 10."""
    storage_manager = StorageManager()
    catalog = storage_manager.get_catalog()
    
    if not catalog.get("items"):
        return await message.answer("Каталог пуст.")
    
    # Показываем последние 10 товаров для удаления
    for item in catalog["items"][:10]:
        kb = InlineKeyboardBuilder()
        kb.button(text="🗑 Удалить это", callback_data=f"del_confirm_{item['id']}")
        await message.answer(
            f"ID: {item['id']}\nНазвание: {item['title']}",
            reply_markup=kb.as_markup()
        )

@delete_router.callback_query(F.data.startswith("del_confirm_"), IsAdmin())
async def process_delete_confirm(callback: types.CallbackQuery):
    item_id = callback.data.replace("del_confirm_", "")
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data=f"del_yes_{item_id}")
    kb.button(text="❌ Нет, отмена", callback_data="cancel_action")
    kb.adjust(1)
    
    await callback.message.answer(
        f"Вы уверены, что хотите удалить товар {item_id}?", 
        reply_markup=kb.as_markup()
    )
    await callback.answer()

@delete_router.callback_query(F.data.startswith("del_yes_"), IsAdmin())
async def process_delete_final(callback: types.CallbackQuery):
    item_id = callback.data.replace("del_yes_", "")
    
    storage_manager = StorageManager()
    try:
        # delete_item теперь атомарный: сам делает fresh read, удаляет и сохраняет с проверкой SHA
        if storage_manager.delete_item(item_id):
            await callback.message.answer(f"✅ Товар {item_id} успешно удален.")
        else:
            await callback.message.answer("❌ Товар не найден (возможно, он уже был удален).")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка при удалении: {e}")
    
    await callback.answer()
