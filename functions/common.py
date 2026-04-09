from aiogram import types, Router, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.keyboards import get_main_keyboard, get_catalog_inline
from utils.storage_manager import StorageManager
from functions.items import send_item_card
from functions.orders import initiate_order_flow
from functions.edit import init_item_edit_state, show_edit_menu
from config import ADMIN_IDS, ADMIN_CHAT_ID, ADMIN_TOPIC_ID
import os
import logging

common_router = Router()

class ManagerContact(StatesGroup):
    waiting_for_message = State()

@common_router.message(Command("start"))
async def start_command(message: types.Message, command: CommandObject, state: FSMContext):
    """Приветствие и выдача меню по роли. Обработка Deep Link."""
    user_id = message.from_user.id
    is_admin = user_id in ADMIN_IDS
    args = (command.args or "").strip()

    if args:
        await state.clear()
        if args.startswith("order_"):
            deep_link_action = "order"
            item_arg = args.replace("order_", "", 1)
        elif args.startswith("edit_"):
            deep_link_action = "edit"
            item_arg = args.replace("edit_", "", 1)
        else:
            deep_link_action = None
            item_arg = args

        try:
            storage_manager = StorageManager()
            catalog = storage_manager.get_catalog()
            item = next((i for i in catalog.get("items", []) if str(i["id"]) == item_arg), None)

            if not item:
                await message.answer("Товар не найден или был удален.")
                return

            await send_item_card(message, item, is_admin)

            if deep_link_action == "order":
                success, error_message = await initiate_order_flow(message, state, item_arg)
                if not success and error_message:
                    await message.answer(error_message)
                return

            if deep_link_action == "edit":
                if not is_admin:
                    await message.answer("❌ У вас нет прав для редактирования этого товара.")
                    return
                item_data, _, _ = await init_item_edit_state(item_arg, state)
                if not item_data:
                    await message.answer("Товар не найден или был удален.")
                    return
                await show_edit_menu(message, state)
                return

            return
        except Exception as e:
            logging.error(f"Ошибка при обработке Deep Link: {e}")
            await message.answer("Произошла ошибка при загрузке товара. Попробуйте позже.")
            return

    welcome_text = (
        "👋 Привет! Добро пожаловать в AM Muse.\n\n"
        "Наш каталог доступен по кнопке ниже. "
        "Здесь вы можете выбрать понравившиеся броши и оформить заказ."
    )
    
    await message.answer(
        welcome_text, 
        reply_markup=get_main_keyboard(user_id)
    )
    await message.answer(
        "Нажмите на кнопку ниже, чтобы открыть сайт-каталог:",
        reply_markup=get_catalog_inline()
    )

@common_router.message(F.text == "🌐 Открыть каталог")
async def open_catalog_text(message: types.Message):
    """Дублирование ссылки на сайт по кнопке в меню."""
    await message.answer(
        "Наш сайт-каталог:",
        reply_markup=get_catalog_inline()
    )

@common_router.message(F.text == "✍️ Написать менеджеру")
async def write_to_manager_reply(message: types.Message, state: FSMContext):
    await state.set_state(ManagerContact.waiting_for_message)
    await message.answer("Напишите ваше сообщение менеджеру:")

@common_router.callback_query(F.data.startswith("contact_manager_"))
async def contact_manager_init(callback: types.CallbackQuery, state: FSMContext):
    item_id = callback.data.replace("contact_manager_", "")
    await state.update_data(contact_item_id=item_id)
    await state.set_state(ManagerContact.waiting_for_message)
    await callback.message.answer("Напишите ваше сообщение менеджеру по поводу этого товара:")
    await callback.answer()

@common_router.message(ManagerContact.waiting_for_message)
async def forward_message_to_manager(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get("contact_item_id")
    
    user_info = (
        f"📩 <b>Сообщение от {message.from_user.full_name}</b> (ID: <code>{message.from_user.id}</code>):\n"
    )
    if item_id:
        user_info += f"Предмет: {item_id}\n"

    try:
        # Пересылаем сообщение админу
        # Если есть ADMIN_CHAT_ID, шлем туда.
        await message.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            message_thread_id=ADMIN_TOPIC_ID,
            text=user_info,
            parse_mode="HTML"
        )
        await message.bot.forward_message(
            chat_id=ADMIN_CHAT_ID,
            message_thread_id=ADMIN_TOPIC_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
        
        await message.answer("✅ Ваше сообщение отправлено менеджеру. Мы свяжемся с вами в ближайшее время!")
    except Exception as e:
        logging.error(f"Ошибка при пересылке сообщения: {e}")
        await message.answer("❌ Ошибка при отправке сообщения. Попробуйте позже.")
    finally:
        await state.clear()

@common_router.callback_query(F.data == "back_to_main")
async def back_to_main_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await start_command(callback.message, CommandObject(args=None))
    await callback.answer()

@common_router.callback_query(F.data == "cancel_action")
async def cancel_action_handler(callback: types.CallbackQuery, state: FSMContext):
    """Общий обработчик отмены любых действий."""
    await state.clear()
    await callback.message.answer("Действие отменено.")
    await callback.answer()
