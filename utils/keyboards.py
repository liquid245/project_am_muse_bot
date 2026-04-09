from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from config import ADMIN_IDS, SITE_URL

def get_main_keyboard(user_id: int):
    """Генерация главного Reply-меню в зависимости от роли."""
    kb = ReplyKeyboardBuilder()
    
    if user_id in ADMIN_IDS:
        # Админ видит как свои кнопки, так и пользовательские
        kb.button(text="➕ Добавить товар")
        kb.button(text="📝 Список товаров")
        kb.button(text="🌐 Открыть каталог")
        kb.button(text="✍️ Написать менеджеру")
        kb.adjust(2)
    else:
        # Меню для пользователя
        kb.button(text="🌐 Открыть каталог")
        kb.button(text="✍️ Написать менеджеру")
        kb.adjust(1)
        
    return kb.as_markup(resize_keyboard=True)

def get_catalog_inline():
    """Inline кнопка ссылкой на внешний сайт."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Перейти на сайт-каталог", url=SITE_URL)
    return kb.as_markup()

def get_cancel_inline():
    """Кнопка отмены текущего действия."""
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="cancel_action")
    return kb.as_markup()

def get_save_images_inline():
    """Кнопка сохранения фото после загрузки."""
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Сохранить", callback_data="save_images")
    kb.button(text="❌ Отмена", callback_data="cancel_action")
    kb.adjust(1)
    return kb.as_markup()
