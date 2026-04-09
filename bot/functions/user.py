import logging
import os

from aiogram import types, Router
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.functions.utils import get_catalog_data
from utils.storage_manager import StorageManager

user_router = Router()

ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
ORDER_CHAT_ID = -1003497103344
ORDER_TOPIC_ID = 43


class WriteToManager(StatesGroup):
    message_to_manager = State()


@user_router.message(Command("start"))
async def send_welcome(message: types.Message):
    """
    This handler will be called when user sends `/start` command
    """
    user_id = str(message.from_user.id)
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="🛍 Каталог")],
            [types.KeyboardButton(text="💬 Написать менеджеру")],
            [types.KeyboardButton(text="Показать ID пользователя, чата и темы")],
        ],
        resize_keyboard=True,
    )

    if user_id == ADMIN_USER_ID:
        admin_keyboard = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text="Добавить товар")],
                [types.KeyboardButton(text="Список товаров")],
                [types.KeyboardButton(text="Активные заказы")],
                [types.KeyboardButton(text="🛍 Каталог")],
                [types.KeyboardButton(text="💬 Написать менеджеру")],
                [types.KeyboardButton(text="Показать ID пользователя, чата и темы")],
            ],
            resize_keyboard=True,
        )
        await message.reply("Hi, Admin! Ready to work!", reply_markup=admin_keyboard)
    else:
        await message.reply(
            "Hi! I'm Project AM Muse Bot. Ready to work!", reply_markup=keyboard
        )


@user_router.message(
    lambda message: message.text == "Показать ID пользователя, чата и темы"
)
async def show_user_chat_topic_id(message: types.Message):
    user_id_text = f"Ваш ID пользователя: {message.from_user.id}"
    chat_topic_text = await get_chat_id_text(message)
    await message.answer(f"{user_id_text}\n{chat_topic_text}")


async def get_chat_id_text(message: types.Message) -> str:
    chat_id = message.chat.id
    text = f"ID этого чата: {chat_id}"
    if message.is_topic_message and message.message_thread_id:
        topic_id = message.message_thread_id
        text += f"\nID этой темы: {topic_id}"
    return text


@user_router.message(lambda message: message.text == "💬 Написать менеджеру")
async def write_to_manager(message: types.Message, state: FSMContext):
    await state.set_state(WriteToManager.message_to_manager)
    await message.answer("Напишите ваше сообщение менеджеру:")


@user_router.message(WriteToManager.message_to_manager)
async def forward_message_to_manager(message: types.Message, state: FSMContext):
    user_info = (
        f"Сообщение от {message.from_user.full_name} (ID: {message.from_user.id}):"
    )

    # Forward the user's message to the specified chat and topic
    try:
        # Send user info as a separate message first
        await message.bot.send_message(
            chat_id=ORDER_CHAT_ID, message_thread_id=ORDER_TOPIC_ID, text=user_info
        )
        # Then forward the actual message for direct reply
        await message.bot.forward_message(
            chat_id=ORDER_CHAT_ID,
            message_thread_id=ORDER_TOPIC_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
        logging.info(
            f"Message from user {message.from_user.id} forwarded to chat {ORDER_CHAT_ID}, topic {ORDER_TOPIC_ID}"
        )
        await message.answer("Ваше сообщение отправлено менеджеру.")
    except Exception as e:
        logging.error(f"Error forwarding message to manager chat: {e}")
        await message.answer(
            "Произошла ошибка при отправке вашего сообщения менеджеру."
        )
    finally:
        await state.clear()


@user_router.message(lambda message: message.text == "🛍 Каталог")
async def show_catalog(message: types.Message):
    """
    This handler will be called when user clicks on the "Каталог" button
    """
    catalog_data = await get_catalog_data()

    if catalog_data is None:
        await message.answer("Ошибка получения каталога.")
        return

    logging.info(f"Full catalog data: {catalog_data}")
    logging.info(f"Items before filtering: {catalog_data.get('items', [])}")

    available_items = [
        item
        for item in catalog_data["items"]
        if item.get("stock", 0) > 0 and item.get("status") == "available"
    ]

    logging.info(f"Filtered available items: {available_items}")

    if not available_items:
        await message.answer("В данный момент доступных товаров нет.")
        return

    for item in available_items:
        caption = f"""{item["title"]}

{item["description"]}

Цена: {item["price"]} руб."""
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="Заказать этот товар", callback_data=f"order_{item['id']}"
                    )
                ]
            ]
        )

        # Send all images for the item
        images = item.get("images") or []
        if images:
            media_group = []
            storage_manager = StorageManager()
            for img_name in images:
                photo_source = storage_manager.get_photo_source(
                    img_name, item_id=str(item.get("id"))
                )
                if photo_source:
                    media_group.append(types.InputMediaPhoto(media=photo_source))
                else:
                    logging.warning(
                        "Image %s missing for item %s", img_name, item.get("id")
                    )

            if media_group:
                media_group[0].caption = caption
                await message.answer_media_group(media=media_group)
                await message.answer(" ", reply_markup=keyboard)
                return

        await message.answer(
            f"Изображения для '{item['title']}' не найдены.", reply_markup=keyboard
        )
